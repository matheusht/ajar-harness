#!/usr/bin/env python3
"""Report supplied offline study records to stdout. Contract: docs/study-report.md.

No discovery, execution, winner selection or evidence publication occurs here.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
from itertools import combinations
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from engagement_quarantine import read_safe_offline_file
from engagement_records import RecordError, _reject_duplicate_pairs, canonical_json_bytes, sha256_bytes

METRICS = ("human_active_seconds", "elapsed_seconds", "machine_seconds", "input_tokens", "output_tokens", "cost_usd")
DURATIONS = METRICS[:3]
ACCOUNTS = ("study", "development", "maintenance")
PHASES = {"execution", "preparation", "useful_assistance", "retry", "interruption", "recovery", "synthesis", "grading", "reporting", "cleanup", "accounting", "development", "maintenance"}
CONFIG_KEYS = "runtime model model_revision model_is_alias instructions source_ref"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def shape(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys.split()), f"{label}: expected fields {keys}")


def text(value, label, *, nullable=False):
    require((nullable and value is None) or (isinstance(value, str) and bool(value.strip())), f"{label}: expected nonblank text")


def identity(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value) is not None, f"{label}: invalid identity")


def array(value, label):
    require(isinstance(value, list), f"{label}: expected array")
    return value


def number(value, label, *, nullable=True, integer=False):
    if nullable and value is None:
        return
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, f"{label}: expected finite nonnegative number")
    require(not integer or type(value) is int, f"{label}: expected integer")


def timestamp(value):
    text(value, "timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "timestamp: timezone required")
    return parsed


def measurements(value):
    shape(value, " ".join(METRICS), "metrics")
    for metric, amount in value.items():
        number(amount, metric, integer=metric.endswith("tokens"))


def configuration(value):
    shape(value, CONFIG_KEYS, "configuration")
    for key in ("runtime", "model", "model_revision", "source_ref"):
        text(value[key], key, nullable=True)
    require(type(value["model_is_alias"]) is bool or value["model_is_alias"] is None, "model_is_alias: expected boolean or null")
    seen = set()
    for instruction in array(value["instructions"], "instructions"):
        shape(instruction, "id sha256", "instruction")
        identity(instruction["id"], "instruction.id")
        require(instruction["id"] not in seen, "duplicate instruction identity")
        seen.add(instruction["id"])
        require(isinstance(instruction["sha256"], str) and re.fullmatch(r"sha256:[0-9a-f]{64}", instruction["sha256"]), "instruction: invalid sha256")


def configuration_limits(value):
    limits = []
    if value is None:
        return ["configuration_unobserved"]
    if any(value[key] is None for key in ("runtime", "model", "model_revision", "model_is_alias", "source_ref")):
        limits.append("configuration_identity_incomplete")
    if value["model_is_alias"] is True:
        limits.append("floating_model_alias")
    return limits


def definition(study):
    shape(study, "schema_version study_id question permitted_conclusion frozen_at freeze_source_ref missing_data_policy grading source_families arms assignments resource_ceilings accounting_scopes", "study")
    require(type(study["schema_version"]) is int and study["schema_version"] == 1, "unsupported study schema_version")
    identity(study["study_id"], "study_id")
    for key in ("question", "permitted_conclusion", "missing_data_policy"):
        text(study[key], key)
    timestamp(study["frozen_at"])
    text(study["freeze_source_ref"], "freeze_source_ref", nullable=True)
    shape(study["grading"], "procedure isolation reference_ref", "grading")
    for key, value in study["grading"].items():
        text(value, f"grading.{key}")
    families = set()
    for family in array(study["source_families"], "source_families"):
        shape(family, "family_id split", "source family")
        identity(family["family_id"], "family_id")
        require(family["family_id"] not in families, "duplicate source family")
        families.add(family["family_id"])
        text(family["split"], "split")
    arms = {}
    for arm in array(study["arms"], "arms"):
        shape(arm, "arm_id treatment configuration", "arm")
        identity(arm["arm_id"], "arm_id")
        require(arm["arm_id"] not in arms, "duplicate arm")
        arms[arm["arm_id"]] = arm
        text(arm["treatment"], "treatment")
        configuration(arm["configuration"])
    assignments, tuples, case_families = {}, set(), {}
    for row in array(study["assignments"], "assignments"):
        shape(row, "assignment_id case_id arm_id repeat family_id", "assignment")
        for key in ("assignment_id", "case_id", "arm_id", "family_id"):
            identity(row[key], key)
        number(row["repeat"], "repeat", nullable=False, integer=True)
        require(row["repeat"] > 0, "repeat: expected positive integer")
        require(row["arm_id"] in arms and row["family_id"] in families, "assignment references unknown arm or family")
        key = (row["case_id"], row["arm_id"], row["repeat"])
        require(row["assignment_id"] not in assignments and key not in tuples, "duplicate assignment identity or case/arm/repeat")
        require(case_families.get(row["case_id"], row["family_id"]) == row["family_id"], "case assigned to conflicting source families")
        case_families[row["case_id"]] = row["family_id"]
        assignments[row["assignment_id"]] = row
        tuples.add(key)
    require(bool(assignments), "study must assign at least one case")
    measurements(study["resource_ceilings"])
    shape(study["accounting_scopes"], " ".join(ACCOUNTS), "accounting_scopes")
    for account, scope in study["accounting_scopes"].items():
        shape(scope, "description allocation_rule included_phases", "accounting scope")
        phases = array(scope["included_phases"], "included_phases")
        expected = PHASES - {"development", "maintenance"} if account == "study" else {account}
        require(all(isinstance(phase, str) for phase in phases) and len(phases) == len(set(phases)) and set(phases) == expected, "accounting scope must explicitly include its required phases")
        text(scope["description"], "scope description")
        text(scope["allocation_rule"], "allocation rule")
    return arms, assignments


def admit_observations(study, observed, digest, assignments):
    shape(observed, "schema_version study_id study_sha256 data_kind cases receipts scope_completeness allocations unreconciled_imports", "observations")
    require(type(observed["schema_version"]) is int and observed["schema_version"] == 1, "unsupported observations schema_version")
    require(observed["study_id"] == study["study_id"] and observed["study_sha256"] == digest, "study identity or source-byte binding mismatch")
    require(observed["data_kind"] in ("synthetic", "measured"), "data_kind: expected synthetic or measured")
    cases, output_ids, assessment_ids = {}, set(), set()
    for row in array(observed["cases"], "cases"):
        shape(row, "assignment_id recorded_at status producer_id source_ref configuration loading deviations contaminated outputs", "case observation")
        identity(row["assignment_id"], "case.assignment_id")
        require(row["assignment_id"] in assignments and row["assignment_id"] not in cases, "unknown or duplicate case assignment")
        cases[row["assignment_id"]] = row
        timestamp(row["recorded_at"])
        require(row["status"] in ("completed", "failed", "interrupted", "blocked", "incomplete", "no_output"), "unknown terminal status")
        if row["producer_id"] is not None:
            identity(row["producer_id"], "producer_id")
        text(row["source_ref"], "case source_ref")
        if row["configuration"] is not None:
            configuration(row["configuration"])
        shape(row["loading"], "status source_ref", "loading")
        require(row["loading"]["status"] in ("observed", "unknown"), "loading.status: expected observed or unknown")
        text(row["loading"]["source_ref"], "loading.source_ref", nullable=row["loading"]["status"] == "unknown")
        for deviation in array(row["deviations"], "deviations"):
            text(deviation, "deviation")
        require(type(row["contaminated"]) is bool, "contaminated: expected boolean")
        for output in array(row["outputs"], "outputs"):
            shape(output, "output_id source_ref produced_at assessment", "output")
            identity(output["output_id"], "output_id")
            require(output["output_id"] not in output_ids, "duplicate or cross-case output identity")
            output_ids.add(output["output_id"])
            text(output["source_ref"], "output source_ref")
            require(timestamp(output["produced_at"]) <= timestamp(row["recorded_at"]), "output postdates its observation")
            require(row["producer_id"] is not None and row["status"] != "no_output", "output contradicts producer or no_output state")
            assessment = output["assessment"]
            if assessment is not None:
                shape(assessment, "assessment_id assessor_id eligible independent source_ref", "assessment")
                identity(assessment["assessment_id"], "assessment_id")
                identity(assessment["assessor_id"], "assessor_id")
                require(assessment["assessment_id"] not in assessment_ids, "duplicate or cross-output assessment identity")
                assessment_ids.add(assessment["assessment_id"])
                require(type(assessment["eligible"]) is bool and type(assessment["independent"]) is bool, "assessment flags must be boolean")
                require(not assessment["independent"] or assessment["assessor_id"] != row["producer_id"], "independent assessment contradicts producer identity")
                text(assessment["source_ref"], "assessment source_ref")
    receipts = {}
    for receipt in array(observed["receipts"], "receipts"):
        shape(receipt, "receipt_id assignment_id account actor_id role phase activity source_ref interval parent_receipt_id metrics not_applicable", "receipt")
        for key in ("receipt_id", "actor_id"):
            identity(receipt[key], key)
        require(receipt["account"] in ACCOUNTS, "receipt account is unknown")
        require(receipt["assignment_id"] is None or receipt["assignment_id"] in assignments, "receipt references unknown assignment")
        require(receipt["phase"] in study["accounting_scopes"][receipt["account"]]["included_phases"], "receipt phase is outside its declared account")
        for key in ("role", "activity", "source_ref"):
            text(receipt[key], key)
        measurements(receipt["metrics"])
        require(isinstance(receipt["not_applicable"], dict) and set(receipt["not_applicable"]) <= set(METRICS), "not_applicable: unknown metric")
        for metric, reason in receipt["not_applicable"].items():
            require(receipt["metrics"][metric] is None, "not_applicable contradicts measured value")
            text(reason, "not_applicable reason")
        if receipt["interval"] is not None:
            shape(receipt["interval"], "start end", "interval")
            duration = (timestamp(receipt["interval"]["end"]) - timestamp(receipt["interval"]["start"])).total_seconds()
            require(duration >= 0, "negative interval")
            require(all(receipt["metrics"][metric] is None or receipt["metrics"][metric] <= duration for metric in DURATIONS), "duration measurement exceeds its declared interval")
        if receipt["parent_receipt_id"] is not None:
            identity(receipt["parent_receipt_id"], "parent_receipt_id")
        prior = receipts.get(receipt["receipt_id"])
        require(prior is None or prior == receipt, "conflicting duplicate receipt identity")
        receipts[receipt["receipt_id"]] = receipt
    for receipt in receipts.values():
        seen = {receipt["receipt_id"]}
        child = receipt
        while child["parent_receipt_id"] is not None:
            parent_id = child["parent_receipt_id"]
            require(parent_id in receipts and parent_id not in seen, "missing or cyclic parent receipt")
            parent = receipts[parent_id]
            require(parent["account"] == child["account"] and parent["assignment_id"] in (None, child["assignment_id"]), "parent receipt crosses accounting scope or case")
            seen.add(parent_id)
            child = parent
    completeness, allocations = {}, {}
    for key, target, fields in (
        ("scope_completeness", completeness, "account metric complete asserted_by source_ref basis"),
        ("allocations", allocations, "account metric rule asserted_by source_ref nonoverlapping values"),
    ):
        for evidence in array(observed[key], key):
            shape(evidence, fields, key)
            require(evidence["account"] in ACCOUNTS and evidence["metric"] in METRICS, f"{key}: unknown account or metric")
            pair = (evidence["account"], evidence["metric"])
            require(pair not in target, f"{key}: duplicate accounting evidence")
            target[pair] = evidence
            for field in ("asserted_by", "source_ref"):
                text(evidence[field], field)
            if key == "scope_completeness":
                require(type(evidence["complete"]) is bool, "scope complete: expected boolean")
                text(evidence["basis"], "scope completeness basis")
            else:
                require(type(evidence["nonoverlapping"]) is bool, "nonoverlapping: expected boolean")
                require(evidence["rule"] == study["accounting_scopes"][pair[0]]["allocation_rule"], "allocation rule differs from frozen rule")
                scoped = {rid: row for rid, row in receipts.items() if row["account"] == pair[0]}
                require(isinstance(evidence["values"], dict) and set(evidence["values"]) == set(scoped), "allocation must name every scoped receipt exactly once")
                for rid, amount in evidence["values"].items():
                    raw = scoped[rid]["metrics"][pair[1]]
                    number(amount, "allocated value", integer=pair[1].endswith("tokens"))
                    require((raw is None and amount is None) or (raw is not None and amount is not None and amount <= raw), "allocation cannot fill unknown measurement or exceed it")
    imports = set()
    for imported in array(observed["unreconciled_imports"], "unreconciled_imports"):
        shape(imported, "import_id account source_ref reason metrics", "unreconciled import")
        identity(imported["import_id"], "import_id")
        require(imported["import_id"] not in imports, "duplicate import identity")
        imports.add(imported["import_id"])
        require(imported["account"] is None or imported["account"] in ACCOUNTS, "unknown imported account")
        text(imported["source_ref"], "import source_ref")
        text(imported["reason"], "import reason")
        measurements(imported["metrics"])
    return cases, receipts, completeness, allocations


def account_metric(account, metric, receipts, completeness, allocations, imports, scope):
    rows = [row for row in receipts.values() if row["account"] == account]
    applicable = [row for row in rows if metric not in row["not_applicable"]]
    measured = [row for row in applicable if row["metrics"][metric] is not None]
    limits, overlaps = [], []
    for row in applicable:
        parent = row["parent_receipt_id"]
        while parent is not None:
            if row["metrics"][metric] not in (None, 0) and receipts[parent]["metrics"][metric] not in (None, 0):
                overlaps.append(sorted([parent, row["receipt_id"]]))
            parent = receipts[parent]["parent_receipt_id"]
    timed = [row for row in measured if row["metrics"][metric] > 0]
    if metric in DURATIONS:
        if any(row["interval"] is None for row in timed):
            limits.append("nonoverlap_unestablished")
        # ponytail: pairwise inspection suits small supplied studies; use sorted intervals if scale requires it.
        for left, right in combinations(timed, 2):
            if (metric == "elapsed_seconds" or left["actor_id"] == right["actor_id"]) and left["interval"] and right["interval"]:
                if max(timestamp(left["interval"]["start"]), timestamp(right["interval"]["start"])) < min(timestamp(left["interval"]["end"]), timestamp(right["interval"]["end"])):
                    overlaps.append(sorted([left["receipt_id"], right["receipt_id"]]))
    if overlaps:
        limits.append("overlapping_or_nested_measurements")
    allocation = allocations.get((account, metric))
    if allocation:
        if allocation["nonoverlapping"]:
            limits = []
        else:
            limits.append("allocation_nonoverlap_unestablished")
    nonoverlap = not limits
    values = [allocation["values"][row["receipt_id"]] if allocation and allocation["nonoverlapping"] else row["metrics"][metric] for row in measured]
    subtotal = (sum(values) if metric.endswith("tokens") else float(sum(Decimal(str(value)) for value in values))) if values else None
    lower_bound = subtotal if nonoverlap else max(values, default=None)
    if subtotal is not None:
        number(subtotal, "metric subtotal")
    evidence = completeness.get((account, metric))
    if not evidence or not evidence["complete"]:
        limits.append("scope_completeness_unestablished")
    if len(measured) != len(applicable):
        limits.append("measurements_missing")
    if any(item["account"] in (None, account) for item in imports):
        limits.append("unreconciled_imports")
    return {"scope": scope, "records": len(rows), "applicable": len(applicable), "not_applicable": len(rows) - len(applicable),
            "measured": len(measured), "unknown": len(applicable) - len(measured), "measured_subtotal": subtotal, "measured_lower_bound": lower_bound,
            "complete_total": (subtotal if subtotal is not None else 0) if not limits else None,
            "nonoverlap_established": nonoverlap, "overlap_receipt_pairs": sorted({tuple(pair) for pair in overlaps}),
            "scope_completeness_evidence": evidence, "allocation": allocation, "limits": sorted(set(limits))}


def report(study, observed, digest, observations_digest):
    arms, assignments = definition(study)
    observations, receipts, completeness, allocations = admit_observations(study, observed, digest, assignments)
    rows, limits = [], []
    if study["freeze_source_ref"] is None:
        limits.append("pre_output_freeze_provenance_unavailable")
    for assignment_id, assignment in sorted(assignments.items()):
        declaration = arms[assignment["arm_id"]]["configuration"]
        row = observations.get(assignment_id)
        row_limits = configuration_limits(declaration)
        if row is None:
            rows.append({**assignment, "status": "unobserved", "outputs": [], "declared_configuration": declaration,
                         "observed_configuration": None, "limits": sorted(set(row_limits + ["case_observation_missing"]))})
            continue
        row_limits += configuration_limits(row["configuration"])
        if row["configuration"] is not None and any(row["configuration"][key] != declaration[key] for key in declaration if key != "source_ref"):
            row_limits.append("configuration_deviation")
        if row["loading"]["status"] == "unknown":
            row_limits.append("loading_unobserved")
        if row["contaminated"]:
            row_limits.append("comparison_contaminated")
        if row["deviations"]:
            row_limits.append("declared_deviations")
        if any(timestamp(output["produced_at"]) < timestamp(study["frozen_at"]) for output in row["outputs"]):
            row_limits.append("output_predates_declared_freeze")
        eligible = sum(output["assessment"] is not None and output["assessment"]["eligible"] and output["assessment"]["independent"] for output in row["outputs"])
        if any(output["assessment"] is None or not output["assessment"]["independent"] for output in row["outputs"]):
            row_limits.append("independent_assessment_missing")
        rows.append({**assignment, **{key: value for key, value in row.items() if key != "configuration"}, "declared_configuration": declaration, "observed_configuration": row["configuration"],
                     "independently_assessed_eligible_results": eligible, "limits": sorted(set(row_limits))})
    accounting = {account: {metric: account_metric(account, metric, receipts, completeness, allocations,
                  observed["unreconciled_imports"], study["accounting_scopes"][account]) for metric in METRICS} for account in ACCOUNTS}
    budgets = {}
    for metric, ceiling in study["resource_ceilings"].items():
        measured = accounting["study"][metric]
        if ceiling is None:
            budgets[metric] = "ceiling_undeclared"
        elif measured["measured_lower_bound"] is not None and measured["measured_lower_bound"] > ceiling:
            budgets[metric] = "overrun_in_measured_account"
        elif measured["complete_total"] is not None:
            budgets[metric] = "within_declared_scope"
        else:
            budgets[metric] = "unknown"
    return {"schema_version": 1, "valid": True, "study_id": study["study_id"], "study_sha256": digest,
            "observations_sha256": observations_digest, "data_kind": observed["data_kind"], "definition": study,
            "case_coverage": {"assigned": len(assignments), "observed": len(observations), "missing": len(assignments) - len(observations)},
            "cases": rows, "produced_inventory": sum(len(row["outputs"]) for row in rows),
            "independently_assessed_eligible_results": sum(row.get("independently_assessed_eligible_results", 0) for row in rows),
            "receipt_delivery": {"received": len(observed["receipts"]), "unique": len(receipts), "duplicates": len(observed["receipts"]) - len(receipts)},
            "receipts": sorted(receipts.values(), key=lambda row: row["receipt_id"]), "accounting": accounting,
            "unreconciled_imports": sorted(observed["unreconciled_imports"], key=lambda row: row["import_id"]),
            "budget_adherence": budgets, "limits": limits, "permitted_conclusion": study["permitted_conclusion"],
            "comparison_conclusion": "not_computed", "evidence_boundary": "Hashes bind supplied bytes, not freeze timing, loading or independent truth. Eligibility and completeness are attributed supplied assessments. Totals apply only to their declared accounting scope. Synthetic accounts are not experiment results."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    args = parser.parse_args()
    try:
        study_bytes = read_safe_offline_file(args.study)
        observations_bytes = read_safe_offline_file(args.observations)
        def decode(data):
            return json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs,
                              parse_constant=lambda value: require(False, "nonfinite JSON value"))
        result = report(decode(study_bytes), decode(observations_bytes), sha256_bytes(study_bytes), sha256_bytes(observations_bytes))
        output = canonical_json_bytes(result)
    except (ValueError, OSError, UnicodeError, TypeError, OverflowError, RecursionError) as exc:
        error = exc.as_dict() if isinstance(exc, RecordError) else {"code": "study_input_invalid", "message": str(exc)}
        print(json.dumps({"valid": False, "error": error}, sort_keys=True, separators=(",", ":")))
        return 1
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
