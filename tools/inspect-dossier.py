#!/usr/bin/env python3
"""Explain admitted records to stdout without changing the source. See docs/dossier-inspector.md."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from engagement_quarantine import read_safe_offline_file
from engagement_records import RecordError, _reject_duplicate_pairs, build_reference_index, canonical_json_bytes, sha256_bytes
from engagement_state import bound_engagement_source, read_governed_file, read_ledger, reduce_engagement, _relative_regular_files
from engagement_views import render_views  # Pure bytes only; never write_views/check-and-repair.


def source_bytes(bound):
    return {name: read_governed_file(bound / name) for name in sorted(_relative_regular_files(bound))}


def decode(data):
    def reject_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs, parse_constant=reject_constant)


def supplement(path, source, kind):
    if path is None:
        return {"status": "absent", "source": None, "data": None}
    path = path.absolute()
    result = {"status": "unreadable", "source": {"path": str(path)}, "data": None}
    try:
        if path.resolve().is_relative_to(source.resolve()):
            raise ValueError("separate supplements must be outside the admitted source")
        try:
            path.lstat()
        except FileNotFoundError:
            result.update(status="absent", reason="supplied path does not exist")
            return result
        data = read_safe_offline_file(path)
    except (OSError, ValueError) as exc:
        result["reason"] = str(exc)
        return result
    result["source"]["sha256"] = sha256_bytes(data)
    try:
        value = decode(data)
        result["data"] = value
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError("expected a version-1 supplement object")
        for field in ("source_ref", "recorded_at"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError(f"supplement {field} must be nonblank")
        if datetime.fromisoformat(value["recorded_at"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("supplement recorded_at requires a timezone")
        if kind == "task":
            if value.get("based_on_ledger_hash") is not None and (not isinstance(value["based_on_ledger_hash"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value["based_on_ledger_hash"])):
                raise ValueError("task ledger basis must be a SHA-256 digest or null")
            if value.get("intent") is not None and (not isinstance(value["intent"], str) or not value["intent"].strip()):
                raise ValueError("task intent must be text or null")
            if value.get("configuration") is not None and not isinstance(value["configuration"], dict):
                raise ValueError("configuration must be a supplied object or null")
            loading = value.get("loading", {"status": "unknown", "source_ref": None})
            if not isinstance(loading, dict) or loading.get("status") not in {"observed", "unknown"}:
                raise ValueError("loading must declare observed or unknown")
            if loading["status"] == "observed" and (not isinstance(loading.get("source_ref"), str) or not loading["source_ref"].strip()):
                raise ValueError("observed loading needs a source reference")
            if not isinstance(value.get("source_documents", []), list):
                raise ValueError("source_documents must be an explicit array")
            for row in value.get("source_documents", []):
                if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in ("artifact_ref", "revision", "sha256", "source_ref")):
                    raise ValueError("source-document labels need artifact, revision, digest and provenance")
        else:
            if not isinstance(value.get("rows"), list):
                raise ValueError("external outcomes require an explicit rows array")
            for row in value["rows"]:
                if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in ("external_report_id", "decision", "source_ref")):
                    raise ValueError("each external row needs external_report_id, decision and source_ref")
                for field in ("decision_at", "recorded_at"):
                    if row.get(field) is not None and datetime.fromisoformat(row[field].replace("Z", "+00:00")).tzinfo is None:
                        raise ValueError("external times require timezones")
        result["status"] = "available"
    except (RecordError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
        result.update(status="invalid", reason=str(exc))
    return result


def summarize(bound, named, state, files, task, outcomes):
    if task["status"] == "available":
        basis = task["data"].get("based_on_ledger_hash")
        task["ledger_basis_status"] = "unknown" if basis is None else ("current" if basis == state["ledger_hash"] else "stale")
        if task["ledger_basis_status"] == "stale":
            task.update(status="stale", reason="supplied task basis differs from the admitted ledger hash")
    index = build_reference_index(bound)
    ledgers = {name: read_ledger(bound, kind) for kind, name in [("event", "events.jsonl"), ("attempt", "attempts.jsonl"), ("artifact", "artifacts.jsonl")]}

    def located(entry, identity):
        path = entry["path"]
        if path.endswith(".jsonl"):
            matches = [(i, decode(line)) for i, line in enumerate(files[path].splitlines(), 1) if line.strip()]
            matches = [(i, row) for i, row in matches
                       if identity in [row.get(k) for k in ("event_id", "attempt_id", "artifact_id", "review_id", "report_id")]
                       or identity in [row.get("payload", {}).get(k) for k in ("hypothesis_id", "candidate_id", "request_id")]
                       or (entry["type"] == "engagement" and row.get("event_type") == "scope.attested" and row.get("engagement_id") == identity)]
            if not matches:
                raise RecordError("indexed_record_missing", identity)
            line, record = matches[0]
        else:
            line, record = None, decode(files[path])
        return {"source": {"path": str(named / path), "relative_path": path, "line": line,
                           "record_id": identity, "record_type": entry["type"], "sha256": sha256_bytes(files[path]),
                           "record_digest": record.get("record_hash") or sha256_bytes(files[path])}, "record": record}

    def resolve(identity, *, revision=None, before=None, review_input=False):
        candidates = [e for e in index.get(identity, []) if e.get("engagement_id") == state["engagement_id"]]
        if revision is not None:
            candidates = [e for e in candidates if e["type"] != "finding" or e.get("revision") == revision]
        if before is not None:
            candidates = [e for e in candidates if not e.get("recorded_at") or datetime.fromisoformat(e["recorded_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(before.replace("Z", "+00:00"))]
        if review_input and candidates:
            # This is the existing review-input hash's time/revision selection, not "latest" belief.
            candidates = [max(candidates, key=lambda e: (e.get("revision") or 0, e.get("recorded_at") or ""))]
        return {"reference": identity, "status": "resolved" if len(candidates) == 1 else ("unavailable" if not candidates else "ambiguous"),
                "records": [located(e, identity) for e in candidates]}

    events = ledgers["events.jsonl"]
    reviews = []
    for identity, entries in sorted(index.items()):
        if entries[0]["type"] != "review":
            continue
        wrapped = located(entries[0], identity)
        review = wrapped["record"]
        wrapped["subject"] = resolve(review["entity_ref"], revision=review.get("finding_revision"), before=review["recorded_at"])
        wrapped["inputs"] = [resolve(ref, revision=review.get("finding_revision") if ref == review["entity_ref"] else None,
                                      before=review["recorded_at"], review_input=True) for ref in review["input_refs"]]
        if review["review_type"] == "claim_adjudication":
            wrapped["relationship"] = {"kind": "predecessor_adjudication", "reviewed_revision": review["finding_revision"],
                                       "expected_filing_revision": 1 if review["finding_revision"] is None else review["finding_revision"] + 1}
        else:
            wrapped["relationship"] = {"kind": "typed_subject_review", "recorded_finding_revision": review["finding_revision"]}
        reviews.append(wrapped)
    claims = [{"finding_id": identity, "current_state": current,
               "revisions": [located(e, identity) for e in sorted(index[identity], key=lambda e: e.get("revision") or 0) if e["type"] == "finding"],
               "change_event": resolve(current["revision_event_ref"]) if current.get("revision_event_ref") else None,
               "adjudication": state["claim_adjudications"].get(identity),
               "source_environment": resolve(located(next(e for e in index[identity] if e.get("revision") == current["revision"]), identity)["record"].get("scope_provenance", {}).get("environment_ref"))} for identity, current in sorted(state["findings"].items())]
    reports = []
    for identity, current in sorted(state["reports"].items()):
        wrapped = located(index[identity][0], identity)
        manifest = wrapped["record"]
        path = manifest["report_path"]
        wrapped.update(current_state=current, birth_status=manifest["operator_status"],
                       finding=resolve(manifest["finding_id"], revision=manifest["finding_revision"]),
                       supersession_event=resolve(state["findings"][manifest["finding_id"]]["revision_event_ref"]) if current["status"] == "historical" else None,
                       adjudication_review=resolve(manifest["adjudication_review_ref"]),
                       history=[resolve(e["event_id"]) for e in events if e["payload"].get("report_ref") == identity],
                       narrative={"source": {"path": str(named / path), "sha256": sha256_bytes(files[path])}, "text": files[path].decode("utf-8")})
        reports.append(wrapped)
    documents = []
    labels = task.get("data", {}).get("source_documents", []) if task["status"] in {"available", "stale"} else []
    for artifact in ledgers["artifacts.jsonl"]:
        path, identity = artifact["relative_path"], artifact["artifact_id"]
        labels_for_artifact = [row for row in labels if row["artifact_ref"] == identity]
        text, text_status = None, "not_text"
        if artifact["media_type"].startswith("text/"):
            try:
                text, text_status = files[path].decode("utf-8"), "available"
            except UnicodeError:
                text_status = "invalid_utf8"
        documents.append({"artifact": resolve(identity), "content_source": {"path": str(named / path), "sha256": artifact["sha256"]},
                          "text": text, "text_status": text_status,
                          "source_revision_declarations": [{"data": row, "status": ("stale" if task["status"] == "stale" else "mapped") if row["sha256"] == artifact["sha256"] else "unmapped", "source": task["source"]} for row in labels_for_artifact]})
    external_rows = []
    if outcomes["status"] == "available":
        for number, row in enumerate(outcomes["data"]["rows"], 1):
            binding = row.get("revision_binding")
            mapping = {"status": "unmapped", "reason": "No exact supplied internal revision/digest binding"}
            if isinstance(binding, dict) and type(binding.get("revision")) is int and isinstance(binding.get("finding_id"), str):
                resolved = resolve(binding["finding_id"], revision=binding["revision"])
                matches = [r for r in resolved["records"] if r["record"].get("finding_id") == binding["finding_id"] and r["source"]["record_digest"] == binding.get("finding_digest")]
                if len(matches) == 1:
                    current = state["findings"].get(binding["finding_id"], {}).get("revision")
                    mapping = {"status": "mapped" if current == binding["revision"] else "stale", "record": matches[0]["source"]}
            external_rows.append({"namespace": "external_report", "row_number": number, "source": outcomes["source"], "data": row, "revision_mapping": mapping})
    projections = []
    for path, expected in {"state.snapshot.json": canonical_json_bytes(state), **render_views(state)}.items():
        status = "absent" if path not in files else ("current" if files[path] == expected else "stale")
        if path in files:
            try:
                decode(files[path]) if path.endswith(".json") else files[path].decode("utf-8")
            except (RecordError, UnicodeError, ValueError):
                status = "invalid"
        projections.append({"path": str(named / path), "status": status, "sha256": sha256_bytes(files[path]) if path in files else None,
                            "basis": "byte comparison with existing pure projection; no files regenerated"})
    cleanup = {"status": "absent", "source": str(named / "cleanup.md"), "text": None}
    if "cleanup.md" in files:
        try:
            cleanup.update(status="available", sha256=sha256_bytes(files["cleanup.md"]), text=files["cleanup.md"].decode("utf-8"))
        except UnicodeError:
            cleanup.update(status="invalid", reason="cleanup narrative is not UTF-8")
    return {"schema_version": 1, "valid": True, "status": "available",
            "inspector_sha256": sha256_bytes(Path(__file__).read_bytes()),
            "reading_basis": "Existing identity-bound read-only reduction, full base admission, reference index and locked source byte recheck; supplied statements remain attributed.",
            "source": {"path": str(named), "engagement_id": state["engagement_id"], "scope_hash": state["scope_hash"], "ledger_hash": state["ledger_hash"],
                       "file_digests": {name: sha256_bytes(data) for name, data in files.items()}},
            "last_recorded_event": resolve(state["last_event_id"]), "recorded_state": {k: state[k] for k in ("event_count", "attempt_count", "artifact_count", "coverage", "active_blockers", "cleanup", "outstanding_reviews")},
            "active_environment": resolve(state["active_environment_ref"]),
            "review_obligations": [{"recorded": row, "opening_event": resolve(row["review_ref"]), "subject": resolve(row["entity_ref"])} for row in state["outstanding_reviews"]],
            "source_documents": documents, "claims": claims, "reviews": reviews, "reports": reports,
            "projections": projections, "human_cleanup": cleanup, "task_context": task,
            "loading": {"observation": task["data"].get("loading", {"status": "unknown", "source_ref": None}) if task["status"] in {"available", "stale"} else {"status": "unknown", "source_ref": None}, "context_status": task["status"], "source": task["source"]},
            "external_outcomes": {"input": outcomes, "rows": external_rows, "limits": "No external identifier implies internal identity, latest-row supersession, current validity or remediation."}}


def inspect_dossier(source, task_context=None, outcomes=None):
    named = source.absolute()
    bound = None
    try:
        with bound_engagement_source(named) as bound:
            before = source_bytes(bound)
            state = reduce_engagement(bound)
            task = supplement(task_context, named, "task")
            external = supplement(outcomes, named, "outcomes")
            result = summarize(bound, named, state, before, task, external)
            identity = os.fstat(int(bound.name))
            result["source"]["directory_identity"] = {"device": identity.st_dev, "inode": identity.st_ino}
            if before != source_bytes(bound):
                raise RecordError("dossier_source_changed", "source bytes or file inventory changed during inspection")
        # Final bound-source exit checks must succeed before the result can reach stdout.
        return result
    except RecordError as exc:
        if bound is not None:
            details = json.loads(json.dumps(exc.details).replace(str(bound), str(named)))
            raise RecordError(exc.code, exc.message.replace(str(bound), str(named)), details) from exc
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--task-context", type=Path)
    parser.add_argument("--outcomes", type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect_dossier(args.source, args.task_context, args.outcomes)
    except (RecordError, OSError, ValueError) as exc:
        error = exc.as_dict() if isinstance(exc, RecordError) else {"code": "source_unreadable", "message": str(exc)}
        print(json.dumps({"valid": False, "status": "unavailable", "source": str(args.source.absolute()), "error": error}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
