from __future__ import annotations

import shutil
from datetime import timedelta

from engagement_records import build_registry, validate_reference_fixture_suite
from engagement_state import (
    WORK_QUEUE_CLASS_ORDER,
    WORK_QUEUE_RULES,
    compute_record_hash,
    compute_review_input_hash,
    compute_work_queue,
    engagement_may_end,
    finding_revision_lane_id,
    hypothesis_dispositions_hash,
    project_terminal_work_state,
    _filing_blocking_review_error,
    _register_legacy_artifact,
)
from engagement_views import assert_views_current
from environment_preflight import _collect_preflight_core as collect_preflight
from memory_disposition import _validate_promotable_abstraction
from work_queue_actions import decorate_work_queue_item

# Loaded only for the CLI self-test. Its supplied namespace preserves patch targets and subprocess paths.


def _run_in_pty(argv: list[str], stdin_text: str) -> str:
    """Run argv attached to a pseudo-TTY and return combined stdout+stderr. Portable across BSD and
    util-linux (unlike `/usr/bin/script`, whose command-invocation syntax differs between them). Used
    only by the self-test to prove an agent-allocated TTY alone cannot satisfy operator authority."""
    import pty, select, time as _time
    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)
    try: os.write(master, stdin_text.encode())
    except OSError: pass
    chunks = bytearray(); deadline = _time.monotonic() + 30
    while _time.monotonic() < deadline:
        try: ready, _, _ = select.select([master], [], [], 1)
        except (OSError, ValueError): break
        if ready:
            try: data = os.read(master, 4096)
            except OSError as exc:
                if exc.errno == errno.EIO: break   # Linux signals PTY EOF as EIO
                raise
            if not data: break
            chunks.extend(data)
        elif proc.poll() is not None:
            break
    try: os.close(master)
    except OSError: pass
    if proc.poll() is None: proc.kill()
    proc.wait()
    return chunks.decode(errors="replace")


def state_self_test() -> list[tuple[str, bool, str]]:
    append_event = _append_kernel_event
    checks: list[tuple[str, bool, str]] = []

    def append_historical_fixture_event(engagement: Path, proposal: dict[str, Any]) -> dict[str, Any]:
        """Build a pre-boundary ledger fixture without exercising any production writer."""
        records = read_ledger(engagement, "event")
        record = materialize_ledger_record("event", proposal, records)
        with (engagement / "events.jsonl").open("ab") as stream:
            stream.write(canonical_json_bytes(record))
        return record

    def historical_reduction_rejection(
        engagement: Path, proposal: dict[str, Any]
    ) -> str | None:
        """Exercise historical reducer semantics without opening a fresh writer bypass."""
        ledger = engagement / "events.jsonl"
        before = ledger.read_bytes()
        try:
            append_historical_fixture_event(engagement, proposal)
            reduce_engagement(engagement)
        except RecordError as exc:
            return exc.code
        finally:
            ledger.write_bytes(before)
        return None

    def test_corpus_documents(*, row_count: int, frozen_at: str) -> tuple[bytes, bytes]:
        from corpus_enumeration import CAVEAT, COLUMNS
        rows = [
            ["enumerated", "fixture", "1.0.0", "a" * 40, f"entry-{index}.js", "declared", f"{index + 1:064x}"]
            for index in range(row_count)
        ]
        tsv_bytes = ("\n".join([CAVEAT, "\t".join(COLUMNS), *("\t".join(row) for row in rows)]) + "\n").encode()
        raw_digest = sha256_bytes(tsv_bytes).removeprefix("sha256:")
        linked = {"path": "corpus-enumeration.tsv", "sha256": raw_digest}
        manifest = {
            "schema_version": 1,
            "artifact_type": "corpus-enumeration",
            "frozen_at": frozen_at,
            "generated_by": {
                "tool": "tools/corpus_enumeration.py",
                "tool_sha256": "4" * 64,
                "mode": "syntactic",
                "model_involvement": False,
                "parser_versions": {"tree-sitter": "test", "tree-sitter-javascript": "test", "tree-sitter-typescript": "test"},
            },
            "granularity": ["package", "entrypoint"],
            "columns": COLUMNS,
            "coverage_semantics": {"closes_on": "visitation", "does_not_establish": "understanding", "necessary_for_coverage": True, "sufficient_for_coverage": False},
            "artifact": {**linked, "row_count": row_count, "package_count": 1},
            "source": {"pins_path": "package-pins.tsv", "tarballs_path": "tarballs"},
            "frozen_inputs_base": "manifest",
            "frozen_inputs": {
                "corpus-enumeration": linked,
                "package-pins": {"path": "package-pins.tsv", "sha256": "5" * 64},
                "enumerator": {"path": "../../tools/corpus_enumeration.py", "sha256": "4" * 64},
                "schema": {"path": "../../schemas/corpus-enumeration.schema.json", "sha256": "6" * 64},
                "tarball:0000": {"path": "tarballs/fixture.tgz", "sha256": "7" * 64},
            },
        }
        return tsv_bytes, canonical_json_bytes(manifest)

    def scope_with_corpus_pin(scope_text: str, manifest_bytes: bytes) -> str:
        pin = f"- Frozen corpus enumeration SHA256: `{sha256_bytes(manifest_bytes)}`\n"
        return scope_text.replace("## Authorization\n", "## Authorization\n" + pin, 1)

    def register_test_corpus(target: Path, *, row_count: int = 5, created_at: str = "2026-07-10T00:02:00Z", documents: tuple[bytes, bytes] | None = None) -> tuple[str, str]:
        state = reduce_engagement(target)
        suffix = re.sub(r"[^A-Za-z0-9._:-]+", "-", state["engagement_id"])
        tsv_ref = f"artifact-corpus-tsv-{suffix}"
        manifest_ref = f"artifact-corpus-manifest-{suffix}"
        evidence = target / "evidence"
        evidence.mkdir(exist_ok=True)
        tsv_bytes, manifest_bytes = documents or test_corpus_documents(row_count=row_count, frozen_at=created_at)
        tsv_path = evidence / "corpus-enumeration.tsv"
        tsv_path.write_bytes(tsv_bytes)
        common = {
            "schema_version": 1,
            "engagement_id": state["engagement_id"],
            "created_at": created_at,
            "producer": {"role": "operator", "id": "operator-selftest"},
            "acquisition_method": "generated_local",
            "target_refs": [],
            "environment_ref": None,
            "sensitivity": "internal",
            "redaction_status": "not_needed",
            "contains_executable_capability": False,
            "advisory_zone": "clear_local",
            "escalation_confirmation_event_ref": None,
            "cleanup_obligation_ref": None,
            "supersedes_artifact_id": None,
        }
        _register_legacy_artifact(target, tsv_path, {**common, "artifact_id": tsv_ref, "media_type": "text/tab-separated-values"})
        manifest_path = evidence / "corpus-enumeration.freeze.json"
        manifest_path.write_bytes(manifest_bytes)
        _register_legacy_artifact(target, manifest_path, {**common, "artifact_id": manifest_ref, "media_type": "application/json"})
        return manifest_ref, tsv_ref

    with tempfile.TemporaryDirectory(prefix="engagement-state-selftest-") as tmp:
        root = Path(tmp).resolve()
        record_fifo = root / "record-input.fifo"; os.mkfifo(record_fifo)
        try:
            fifo_validation = subprocess.run([sys.executable, str(Path(__file__).resolve()), "validate", "--file", str(record_fifo), "--schema-only"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2, check=False)
        except subprocess.TimeoutExpired:
            fifo_validation = None
        try:
            fifo_error = json.loads(fifo_validation.stdout).get("error", {}).get("code") if fifo_validation is not None else None
        except json.JSONDecodeError:
            fifo_error = None
        checks.append(("public record validator rejects FIFO JSON input without blocking", fifo_validation is not None and fifo_validation.returncode != 0 and fifo_error == "invalid_json", "timed out" if fifo_validation is None else fifo_validation.stdout + fifo_validation.stderr))
        bound_fifo_directory = root / "bound-record-input"; bound_fifo_directory.mkdir()
        bound_record_fifo = bound_fifo_directory / "record.fifo"; os.mkfifo(bound_record_fifo)
        bound_fd = os.open(bound_fifo_directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            bound_fifo_validation = subprocess.run([sys.executable, str(Path(__file__).resolve()), "validate", "--file", f"/dev/fd/{bound_fd}/record.fifo", "--schema-only"], pass_fds=(bound_fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2, check=False)
        except subprocess.TimeoutExpired:
            bound_fifo_validation = None
        finally:
            os.close(bound_fd)
        try:
            bound_fifo_error = json.loads(bound_fifo_validation.stdout).get("error", {}).get("code") if bound_fifo_validation is not None else None
        except json.JSONDecodeError:
            bound_fifo_error = None
        checks.append(("bound record validator rejects FIFO JSON input without blocking", bound_fifo_validation is not None and bound_fifo_validation.returncode != 0 and bound_fifo_error == "invalid_json", "timed out" if bound_fifo_validation is None else bound_fifo_validation.stdout + bound_fifo_validation.stderr))
        signature_fifo = root / "signature-input.fifo"; os.mkfifo(signature_fifo)
        signature_probe = (
            "import runpy, sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(sys.argv[1]).parent))\n"
            "namespace = runpy.run_path(sys.argv[1])\n"
            "namespace['_read_regular_file_once'](Path(sys.argv[2]))\n"
        )
        try:
            signature_fifo_read = subprocess.run(
                [sys.executable, "-c", signature_probe, str(Path(__file__).resolve().with_name("run-engagement.py")), str(signature_fifo)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2, check=False,
            )
        except subprocess.TimeoutExpired:
            signature_fifo_read = None
        checks.append(("bounded signature reader rejects FIFO input without blocking", signature_fifo_read is not None and signature_fifo_read.returncode != 0, "timed out" if signature_fifo_read is None else signature_fifo_read.stdout + signature_fifo_read.stderr))
        reviewer_key = root / "reviewer-ed25519"; subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(reviewer_key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); public_parts = reviewer_key.with_suffix(".pub").read_text().split(); allowed_signers_path = root / "allowed-signers"; allowed_signers_path.write_text(f"reviewer-external-canonical {public_parts[0]} {public_parts[1]}\noperator-selftest {public_parts[0]} {public_parts[1]}\n"); allowed_signers_digest = sha256_file(allowed_signers_path)
        engagement = root / "eng-selftest"
        engagement.mkdir()
        scope = f"""# Scope — self-test

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Deterministic ledger test.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `yes`
- zone2_authorized_categories: `zone2_artifact_creation`
- zone2_escalation_ceiling: `artifact_creation`
- zone2_containment: `synthetic temporary-directory fixture`
## Accounts / fixtures
- None.
## Independent reviewer identity
- Reviewer allowed signers SHA256: {allowed_signers_digest}
## Authorization
- Operator allowed signers SHA256: {allowed_signers_digest}
- Operator: operator-selftest
- Date: 2026-07-10
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""
        (engagement / "scope.md").write_text(scope, encoding="utf-8")
        init_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "init", "--engagement", str(engagement), "--recorded-at", "2026-07-10T00:00:00Z"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: init_console_gate = init_cli.returncode != 0 and json.loads(init_cli.stdout)["error"]["code"] == "operator_signature_required"
        except (json.JSONDecodeError, KeyError): init_console_gate = False
        checks.append(("fresh public init reaches the cryptographic operator gate without requiring a prior ledger", init_console_gate, init_cli.stdout + init_cli.stderr))
        pty_output=_run_in_pty([sys.executable,str(Path(__file__).resolve()),"init","--engagement",str(engagement),"--recorded-at","2026-07-10T00:00:00Z"],"initialize-engagement operator-selftest\n");checks.append(("agent-created pseudo-TTY cannot satisfy operator authority without a scoped signature","operator_signature_required" in pty_output and not (engagement/"events.jsonl").exists(),pty_output))
        init_challenge={"schema_version":1,"namespace":"llm-redteam-harness-operator-v1","engagement_id":engagement.name,"scope_hash":sha256_file(engagement/"scope.md"),"ledger_hash":None,"operation":"initialize-engagement:2026-07-10T00:00:00Z","operator_id":"operator-selftest"};init_challenge_path=root/"init-challenge.json";init_challenge_path.write_bytes(canonical_json_bytes(init_challenge));subprocess.run(["/usr/bin/ssh-keygen","-Y","sign","-f",str(reviewer_key),"-n","llm-redteam-harness-operator-v1",str(init_challenge_path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);signed_env={**os.environ,"HARNESS_OPERATOR_SIGNATURE_FILE":str(init_challenge_path)+".sig","HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE":str(allowed_signers_path)};signed_init=subprocess.run([sys.executable,str(Path(__file__).resolve()),"init","--engagement",str(engagement),"--recorded-at","2026-07-10T00:00:00Z"],env=signed_env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False);checks.append(("public init accepts an exact scoped operator signature",signed_init.returncode==0,signed_init.stdout+signed_init.stderr))
        snapshot = initialize_engagement(engagement, "2026-07-10T00:00:00Z")
        checks.append(("signed-scope init creates one attested event", snapshot["event_count"] == 1 and read_ledger(engagement, "event")[0]["event_type"] == "scope.attested", str(snapshot)))
        initial_event_bytes = (engagement / "events.jsonl").read_bytes()
        initial_reduction = reduce_engagement(engagement)
        expected_coverage_item = {
            "class": "coverage_review_missing",
            "entity": {"type": "engagement", "id": engagement.name, "detail": None},
            "blocking": True,
            "predicate": "coverage is active and no other work queue item exists",
            "closes_when": "coverage is not active",
        }
        checks.append(("reducer projects the work queue without appending a ledger event", initial_reduction["work_queue"] == [expected_coverage_item] and (engagement / "events.jsonl").read_bytes() == initial_event_bytes and len(read_ledger(engagement, "event")) == 1, str(initial_reduction.get("work_queue"))))

        queue_cli_results: dict[str, tuple[subprocess.CompletedProcess[str], dict[str, object]]] = {}
        for queue_command, expected_returncode in (("next", 0), ("list", 0), ("gate", 3)):
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), queue_command, "--engagement", str(engagement)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            try:
                payload = json.loads(process.stdout)
            except json.JSONDecodeError:
                payload = {}
            queue_cli_results[queue_command] = (process, payload)
            common_ok = (
                process.returncode == expected_returncode
                and payload.get("schema_version") == 1
                and payload.get("command") == queue_command
                and payload.get("ok") is True
                and payload.get("engagement_id") == engagement.name
                and payload.get("state_hash") == sha256_bytes(canonical_json_bytes(initial_reduction))
                and payload.get("ledger_hash") == initial_reduction["ledger_hash"]
                and payload.get("source_hashes") == initial_reduction["source_hashes"]
                and payload.get("queue") == {
                    "blocking_count": 1,
                    "control_status": "active",
                    "coverage_status": "active",
                    "decision": "block",
                    "has_blocking_work": True,
                    "nonblocking_count": 0,
                    "should_block": True,
                    "total_count": 1,
                }
                and process.stdout.encode() == canonical_json_bytes(payload)
                and process.stderr == ""
            )
            checks.append((f"{queue_command} emits the canonical read-only queue envelope and documented exit", common_ok, process.stdout + process.stderr))
        next_payload = queue_cli_results["next"][1]
        list_payload = queue_cli_results["list"][1]
        gate_payload = queue_cli_results["gate"][1]
        coverage_action = next_payload.get("item", {}).get("next_action", {})
        checks.append(("next returns exactly the first queue item plus one reducer-valid next action", isinstance(next_payload.get("item"), dict) and next_payload["item"]["class"] == "coverage_review_missing" and coverage_action.get("action_id") == "record_cold_coverage_review" and coverage_action.get("effect") == "conditional" and coverage_action.get("recompute_after") is True and "closure" not in next_payload["item"] and "items" not in next_payload, str(next_payload)))
        checks.append(("list mirrors raw reducer truth in exact order without stale lower-ranked actions, and gate duplicates no item data", [item["class"] for item in list_payload.get("items", [])] == [item["class"] for item in initial_reduction["work_queue"]] and all("next_action" not in item for item in list_payload.get("items", [])) and "items" not in gate_payload, str((list_payload, gate_payload))))
        checks.append(("queue inspection never mutates the ledger", (engagement / "events.jsonl").read_bytes() == initial_event_bytes and len(read_ledger(engagement, "event")) == 1, "queue inspection changed the event ledger"))

        caller_order = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "next", "--engagement", str(engagement), "--class", "awaiting_operator"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        checks.append(("next exposes no caller-controlled class, filter, or ordering knob", caller_order.returncode == 2 and caller_order.stdout == "", caller_order.stdout + caller_order.stderr))

        corrupted = root / "eng-corrupted-queue-cli"
        shutil.copytree(engagement, corrupted)
        (corrupted / "attempts.jsonl").write_text("{\n", encoding="utf-8")
        corrupt_gate = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "gate", "--engagement", str(corrupted)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        try:
            corrupt_payload = json.loads(corrupt_gate.stdout)
        except json.JSONDecodeError:
            corrupt_payload = {}
        checks.append(("gate returns exit 1 with a sanitized machine error for an invalid record", corrupt_gate.returncode == 1 and corrupt_payload.get("schema_version") == 1 and corrupt_payload.get("command") == "gate" and corrupt_payload.get("ok") is False and set(corrupt_payload.get("error", {})) == {"code"} and str(corrupted) not in corrupt_gate.stdout and corrupt_gate.stderr == "", corrupt_gate.stdout + corrupt_gate.stderr))

        unavailable_gate = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "gate", "--engagement", str(root / "missing-engagement")],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        try:
            unavailable_payload = json.loads(unavailable_gate.stdout)
        except json.JSONDecodeError:
            unavailable_payload = {}
        checks.append(("gate keeps an unavailable source machine-readable and path-sanitized", unavailable_gate.returncode == 1 and unavailable_payload == {"schema_version": 1, "command": "gate", "ok": False, "error": {"code": "queue_record_unavailable"}} and str(root) not in unavailable_gate.stdout and unavailable_gate.stderr == "", unavailable_gate.stdout + unavailable_gate.stderr))

        forged_expiry = base_event(
            event_id="event-forged-authority-expiry",
            engagement_id=engagement.name,
            recorded_at="2099-01-01T00:00:00Z",
            actor_role="broker",
            actor_id="broker-forged",
            event_type="authority.expired",
            rationale="A future-dated generic append must not expire authority.",
            payload={"request_id": "request-forged", "request_event_ref": "event-request-forged", "action_digest": "sha256:" + "0" * 64, "expires_at": "2098-01-01T00:00:00Z", "status": "expired"},
            entity_refs=["event-request-forged"],
            session_id="session-forged",
            operation_class="notebook",
        )
        forged_expiry_path = root / "forged-authority-expiry.json"
        forged_expiry_path.write_bytes(canonical_json_bytes(forged_expiry))
        forged_expiry_cli = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(engagement), "--file", str(forged_expiry_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        try:
            forged_expiry_cli_code = json.loads(forged_expiry_cli.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError):
            forged_expiry_cli_code = None
        from engagement_state import append_event as public_append_event
        try:
            public_append_event(engagement, forged_expiry)
            forged_expiry_helper_code = None
        except RecordError as exc:
            forged_expiry_helper_code = exc.code
        checks.append(("generic CLI and public notebook append boundaries cannot future-forge objective authority expiry", forged_expiry_cli.returncode == 1 and forged_expiry_cli_code == "canonical_notebook_command_required" and forged_expiry_helper_code == "canonical_notebook_command_required", forged_expiry_cli.stdout + forged_expiry_cli.stderr + str(forged_expiry_helper_code)))

        synthetic_queue_state = copy.deepcopy(initial_reduction)
        synthetic_queue_state["hypotheses"] = {
            "entity-hypothesis_ran_unadjudicated": {"status": "running", "next_route": None, "unresolved_questions": []},
            "entity-hypothesis_running_unattempted": {"status": "running", "running_event_ref": "event-entity-hypothesis-running", "next_route": None, "unresolved_questions": []},
            "entity-hypothesis_unrouted": {"status": "selected", "next_route": None, "unresolved_questions": []},
            "entity-hypothesis_open_route": {"status": "running", "next_route": "detail", "unresolved_questions": []},
            "entity-hypothesis_unresolved_question": {"status": "running", "next_route": None, "unresolved_questions": ["detail"]},
        }
        synthetic_queue_state["work_queue_context"] = {
            "artifacts": {},
            "pending_attempts": {
                "entity-hypothesis_ran_unadjudicated": [
                    {
                        "attempt_id": "attempt-synthetic-unadjudicated",
                        "kind": "primary",
                        "recorded_at": "2026-07-10T00:00:01Z",
                        "evidence": [],
                    }
                ]
            }
        }
        synthetic_queue_state["findings"] = {
            "entity-claim_unadjudicated": {"revision": 1, "status": "needs_review"},
            "entity-finding_revision_pending": {"revision": 1, "status": "confirmed"},
            "entity-finding_unproved": {"revision": 1, "status": "confirmed", "claim_tuple_hash": "sha256:" + "2" * 64, "revision_event_ref": "event-entity-finding-unproved-revision"},
        }
        synthetic_queue_state["claim_adjudications"] = {
            "entity-claim_unadjudicated": {"status": "needs_review", "event_ref": "event-claim-needs-review", "review_ref": "review-claim-needs-review", "reviewer_run_id": "run-claim-needs-review", "reviewed_revision": 1, "expected_filing_revision": 2},
            "entity-finding_revision_pending": {"status": "confirmed", "event_ref": "event-claim-confirmed", "review_ref": "review-claim-confirmed", "reviewer_run_id": "run-claim-confirmed", "reviewed_revision": 1, "expected_filing_revision": 2},
            "entity-finding_unproved": {"status": "confirmed", "event_ref": "event-claim-unproved", "review_ref": "review-claim-unproved", "reviewer_run_id": "run-claim-unproved", "reviewed_revision": 1, "expected_filing_revision": 2},
        }
        synthetic_queue_state["outstanding_reviews"] = [{
            "review_type": "regrade",
            "entity_ref": "finding-review-obligation",
            "review_ref": "review-obligation-open",
            "reason": "Synthetic workflow mapping test.",
            "status": "pending",
            "hypothesis_ref": None,
            "opened_at": "2026-07-10T00:00:00Z",
        }]
        synthetic_queue_state["candidates"] = {
            "entity-candidate_undisposed": {"status": "selected"},
            "entity-deferred_candidate_unreviewed": {"status": "deferred"},
        }
        synthetic_queue_state["control_candidates"] = [{"routing_event_id": "entity-control_candidate_unverified", "source_observation_ref": "event-observation-control", "card_ids": ["card-control"], "status": "likely_held", "rationale": "Synthetic control.", "hypothesis_ref": None, "primary_attempt_ref": None}]
        synthetic_queue_state["regrade_reviews"] = {}
        synthetic_queue_state["latest_coverage_review"] = None
        entity_types = {
            "hypothesis_ran_unadjudicated": "hypothesis",
            "hypothesis_running_unattempted": "hypothesis",
            "hypothesis_unrouted": "hypothesis",
            "hypothesis_open_route": "hypothesis",
            "hypothesis_unresolved_question": "hypothesis",
            "claim_unadjudicated": "finding",
            "finding_revision_pending": "finding",
            "finding_unproved": "finding",
            "review_obligation_open": "review_obligation",
            "candidate_undisposed": "candidate",
            "deferred_candidate_unreviewed": "candidate",
            "control_candidate_unverified": "control_candidate",
            "awaiting_operator": "authority_request",
            "coverage_review_missing": "engagement",
        }
        entity_ids = {item_class: f"entity-{item_class}" for item_class in WORK_QUEUE_CLASS_ORDER}
        entity_ids["review_obligation_open"] = "review-obligation-open"
        expected_actions = {
            "hypothesis_ran_unadjudicated": "record_hypothesis_disposition",
            "hypothesis_running_unattempted": "record_hunter_primary",
            "hypothesis_unrouted": "record_hypothesis_disposition",
            "hypothesis_open_route": "record_hypothesis_disposition",
            "hypothesis_unresolved_question": "record_hypothesis_disposition",
            "claim_unadjudicated": "record_claim_adjudication",
            "finding_revision_pending": "request_finding_revision_authority",
            "finding_unproved": "record_current_revision_regrade",
            "review_obligation_open": "route_review_obligation",
            "candidate_undisposed": "create_candidate_hypothesis",
            "deferred_candidate_unreviewed": "record_candidate_skipped",
            "control_candidate_unverified": "create_control_hypothesis",
            "awaiting_operator": "operator_resolve_authority",
            "coverage_review_missing": "record_cold_coverage_review",
        }
        raw_items = []
        mapped_items = []
        for item_class in WORK_QUEUE_CLASS_ORDER:
            predicate, closes_when = WORK_QUEUE_RULES[item_class]
            raw_item = {
                "class": item_class,
                "entity": {"type": entity_types[item_class], "id": entity_ids[item_class], "detail": "detail" if item_class in {"hypothesis_open_route", "hypothesis_unresolved_question"} else None},
                "blocking": item_class != "awaiting_operator",
                "predicate": predicate,
                "closes_when": closes_when,
            }
            raw_items.append(raw_item)
            mapped_items.append(decorate_work_queue_item(raw_item, synthetic_queue_state, engagement.absolute()))
        matrix_commands = load_capability_matrix()["commands"]
        actions_ok = all(
            item["next_action"]["action_id"] == expected_actions[item["class"]]
            and item["next_action"]["command"] in matrix_commands
            and item["next_action"]["operation"] == {"tool": "run-engagement", "command": item["next_action"]["command"]}
            and item["next_action"]["arguments"][:2] == ["--engagement", str(engagement.absolute())]
            and item["next_action"]["local_invocation"]["schema_version"] == 1
            and item["next_action"]["local_invocation"]["argv"][2] == item["next_action"]["command"]
            and item["next_action"]["session_kind"] in {"ordinary_bounded", "fresh_independent_reviewer", "operator_required"}
            and item["next_action"]["principal"] in {"orchestrator", "hunter", "broker", "independent_reviewer", "operator_only"}
            and item["next_action"]["execution_principal"] in {"broker", "operator_only"}
            and item["next_action"]["execution_principal"] == ("broker" if item["next_action"]["launchable"] else "operator_only")
            and item["next_action"]["effect"] in {"closes_item", "advances_item", "conditional"}
            and isinstance(item["next_action"]["required_inputs"], list)
            and item["next_action"]["recompute_after"] is True
            and "closure" not in item
            for item in mapped_items
        )
        operator_action = next(item["next_action"] for item in mapped_items if item["class"] == "awaiting_operator")
        deferred_action = next(item["next_action"] for item in mapped_items if item["class"] == "deferred_candidate_unreviewed")
        checks.append(("every reducer queue class maps to one closed-shape capability-classified next action", actions_ok and len(mapped_items) == len(WORK_QUEUE_CLASS_ORDER) and operator_action["session_kind"] == "operator_required" and operator_action["principal"] == "operator_only" and operator_action["execution_principal"] == "operator_only" and operator_action["launchable"] is False, str([(item["class"], item["next_action"]["action_id"]) for item in mapped_items])))
        checks.append(("skipping a deferred candidate advances state without claiming the candidate debt is closed", deferred_action["effect"] == "advances_item", str(deferred_action)))

        attempt_stage_state = copy.deepcopy(synthetic_queue_state)
        attempt_stage_state["control_candidates"][0]["hypothesis_ref"] = "entity-hypothesis_ran_unadjudicated"
        attempt_stage_state["hypotheses"]["entity-hypothesis_ran_unadjudicated"]["status"] = "running"
        mediated_attempt = decorate_work_queue_item(raw_items[WORK_QUEUE_CLASS_ORDER.index("control_candidate_unverified")], attempt_stage_state, engagement.absolute())["next_action"]
        checks.append(("broker-mediated actions keep the cognitive producer distinct from the process-bound recorder", mediated_attempt["principal"] == "hunter" and mediated_attempt["execution_principal"] == "broker" and "process-bound broker recorder identity" in str(mediated_attempt["required_inputs"]), str(mediated_attempt)))
        independent_action_text = " ".join(
            requirement
            for item in mapped_items
            if item["next_action"]["session_kind"] == "fresh_independent_reviewer"
            for required_input in item["next_action"]["required_inputs"]
            for requirement in required_input["requirements"]
        )
        checks.append(("fresh independent actions record outcome-open reviews rather than prescribing favorable verdicts", all(fragment not in independent_action_text for fragment in ("verdict is confirmed", "verdict is verified", "verdict is reward_hacked", "verdict is coverage_dry")), independent_action_text))

        poc_blocked_state = copy.deepcopy(synthetic_queue_state)
        poc_blocked_state["findings"]["finding-poc-blocked"] = {"revision": 1, "status": "confirmed", "claim_tuple_hash": "sha256:" + "3" * 64, "revision_event_ref": "event-finding-poc-blocked-revision"}
        poc_blocked_state["outstanding_reviews"] = [{"review_type": "pocinator", "entity_ref": "finding-poc-blocked", "review_ref": "event-poc-blocked", "reason": "Fresh proof review could not run.", "status": "blocked", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:00Z", "opening_reviewer_run_id": "run-poc-blocked"}]
        poc_blocked_item = {"class": "review_obligation_open", "entity": {"type": "review_obligation", "id": "event-poc-blocked", "detail": "finding-poc-blocked"}, "blocking": True, "predicate": WORK_QUEUE_RULES["review_obligation_open"][0], "closes_when": WORK_QUEUE_RULES["review_obligation_open"][1]}
        poc_blocked_action = decorate_work_queue_item(poc_blocked_item, poc_blocked_state, engagement.absolute())["next_action"]
        checks.append(("blocked Pocinator debt maps to exact prior-run supersession without prescribing its outcome", poc_blocked_action["action_id"] == "supersede_blocked_review_obligation" and "event-poc-blocked" in str(poc_blocked_action["required_inputs"]) and all(fragment not in str(poc_blocked_action["required_inputs"]) for fragment in ("verdict is verified", "verdict is reward_hacked")), str(poc_blocked_action)))

        target_like_cwd = root / "target-like-cwd"; target_like_cwd.mkdir()
        local_prefix = coverage_action["local_invocation"]["argv"][:2]
        local_help = subprocess.run([*local_prefix, "--help"], cwd=target_like_cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append(("local invocation preserves the active venv and executes from a target-repo cwd while semantics stay tool-relative", local_help.returncode == 0 and local_prefix[0] == str(Path(sys.executable).absolute()) and coverage_action["operation"] == {"tool": "run-engagement", "command": "record-review"} and coverage_action["arguments"][0] == "--engagement", local_help.stdout + local_help.stderr))

        coverage_fresh_state = copy.deepcopy(initial_reduction)
        coverage_fresh_state["hypotheses"] = {"hypothesis-terminal": {"status": "closed"}}
        coverage_fresh_state["event_count"] = 12
        coverage_fresh_state["coverage_relevant_sequence"] = 11
        coverage_fresh_state["latest_coverage_review"] = {
            "event_ref": "event-coverage-review-current",
            "event_sequence": 11,
            "review_refs": ["review-coverage-current"],
            "verdict": "coverage_dry",
            "hypothesis_dispositions_hash": hypothesis_dispositions_hash(coverage_fresh_state["hypotheses"]),
        }
        coverage_item = next(item for item in raw_items if item["class"] == "coverage_review_missing")
        neutral_end_action = decorate_work_queue_item(coverage_item, coverage_fresh_state, engagement.absolute())["next_action"]
        coverage_stale_state = copy.deepcopy(coverage_fresh_state)
        coverage_stale_state["coverage_relevant_sequence"] = 12
        substantive_action = decorate_work_queue_item(coverage_item, coverage_stale_state, engagement.absolute())["next_action"]
        checks.append(("neutral session end checks preserve a current cold review while any later substantive event invalidates it", neutral_end_action["action_id"] == "record_coverage_dry" and substantive_action["action_id"] == "record_cold_coverage_review", str((neutral_end_action, substantive_action))))

        coverage_continue_state = copy.deepcopy(coverage_fresh_state)
        coverage_continue_state["latest_coverage_review"]["verdict"] = "continue"
        coverage_continue_action = decorate_work_queue_item(coverage_item, coverage_continue_state, engagement.absolute())["next_action"]
        checks.append(("a current continue verdict advances through one exact cold-review-grounded hypothesis instead of confirmation-shopping or re-reviewing", coverage_continue_action["action_id"] == "create_coverage_followup_hypothesis" and coverage_continue_action["effect"] == "advances_item" and "review-coverage-current" in str(coverage_continue_action["required_inputs"]) and coverage_continue_action["session_kind"] == "ordinary_bounded" and coverage_continue_action["principal"] == "orchestrator", str(coverage_continue_action)))

        first_blocking_state = copy.deepcopy(synthetic_queue_state)
        first_blocking_state["work_queue"] = [
            next(item for item in raw_items if item["class"] == "awaiting_operator"),
            next(item for item in raw_items if item["class"] == "hypothesis_unrouted"),
        ]
        first_blocking = queue_command_payload("next", first_blocking_state, engagement.absolute())
        operator_only_state = copy.deepcopy(initial_reduction)
        operator_only_state["work_queue"] = [next(item for item in raw_items if item["class"] == "awaiting_operator")]
        operator_only_gate = queue_command_payload("gate", operator_only_state, engagement.absolute())
        parked_blocking_state = copy.deepcopy(first_blocking_state)
        parked_blocking_state["queue_control"]["status"] = "parked"
        parked_blocking_gate = queue_command_payload("gate", parked_blocking_state, engagement.absolute())
        terminal_coverage_gates = {}
        for coverage_status in ("budget_bounded", "blocked", "coverage_dry"):
            terminal_state = copy.deepcopy(first_blocking_state)
            terminal_state["coverage"] = coverage_status
            terminal_coverage_gates[coverage_status] = queue_command_payload("gate", terminal_state, engagement.absolute())
        checks.append(("next chooses the first blocking item and active blocking work exits 3", first_blocking["item"]["class"] == "hypothesis_unrouted" and first_blocking["queue"]["has_blocking_work"] is True and first_blocking["queue"]["should_block"] is True and first_blocking["queue"]["decision"] == "block" and queue_gate_exit(first_blocking) == 3, str(first_blocking)))
        checks.append(("gate releases operator-only and signed parked queues without hiding blocking record truth", operator_only_gate["queue"]["has_blocking_work"] is False and operator_only_gate["queue"]["decision"] == "release" and queue_gate_exit(operator_only_gate) == 0 and parked_blocking_gate["queue"]["control_status"] == "parked" and parked_blocking_gate["queue"]["blocking_count"] == 1 and parked_blocking_gate["queue"]["has_blocking_work"] is True and parked_blocking_gate["queue"]["should_block"] is False and parked_blocking_gate["queue"]["decision"] == "release" and queue_gate_exit(parked_blocking_gate) == 0, str((operator_only_gate, parked_blocking_gate))))
        checks.append(("terminal and blocked coverage release without hiding invariant-violating queue rows", all(payload["queue"]["coverage_status"] == coverage_status and payload["queue"]["blocking_count"] == 1 and payload["queue"]["has_blocking_work"] is True and payload["queue"]["should_block"] is False and payload["queue"]["decision"] == "release" and queue_gate_exit(payload) == 0 for coverage_status, payload in terminal_coverage_gates.items()), str(terminal_coverage_gates)))

        queue_state = {
            "engagement_id": "eng-queue-selftest",
            "coverage": "active",
            "hypotheses": {
                "hypothesis-unrouted": {"status": "selected", "origin_type": "operator_prior", "origin_ref": "prior-1", "experiment_refs": [], "unresolved_questions": [], "next_route": "route-selected"},
                "hypothesis-route": {"status": "running", "origin_type": "operator_prior", "origin_ref": "prior-2", "experiment_refs": ["experiment-route"], "unresolved_questions": ["question-z", "", "question-z", "question-a"], "next_route": "route-z"},
                "hypothesis-terminal-route": {"status": "closed", "origin_type": "operator_prior", "origin_ref": "prior-terminal", "experiment_refs": [], "control_refs": [], "unresolved_questions": [], "next_route": "route-terminal"},
                "hypothesis-ran": {"status": "queued", "origin_type": "operator_prior", "origin_ref": "prior-3", "experiment_refs": ["unrelated-attempt-ref"], "control_refs": [], "unresolved_questions": [], "next_route": None},
                "hypothesis-cites-candidate": {"status": "held", "origin_type": "candidate", "origin_ref": "candidate-cited", "experiment_refs": ["experiment-cited"], "unresolved_questions": [], "next_route": None},
                "hypothesis-adjudicated": {"status": "running", "origin_type": "operator_prior", "origin_ref": "prior-4", "experiment_refs": ["attempt-hypothesis-adjudicated"], "control_refs": [], "unresolved_questions": [], "next_route": None},
            },
            "findings": {
                "finding-verified": {"revision": 3, "status": "confirmed", "adjudication_review_ref": "review-verified", "adjudication_event_ref": "event-claim-verified"},
                "finding-proof": {"revision": 2, "status": "confirmed", "adjudication_review_ref": "review-proof", "adjudication_event_ref": "event-claim-proof"},
                "finding-claim": {"revision": 1, "status": "needs_review", "adjudication_review_ref": "review-claim", "adjudication_event_ref": "event-claim-needs-review"},
                "finding-filing": {"revision": 1, "status": "supported", "adjudication_review_ref": "review-filing-old", "adjudication_event_ref": "event-claim-filing-old"},
            },
            "claim_adjudications": {
                "finding-verified": {"status": "confirmed", "event_ref": "event-claim-verified", "review_ref": "review-verified", "reviewed_revision": 2, "expected_filing_revision": 3},
                "finding-proof": {"status": "confirmed", "event_ref": "event-claim-proof", "review_ref": "review-proof", "reviewed_revision": 1, "expected_filing_revision": 2},
                "finding-claim": {"status": "needs_review", "event_ref": "event-claim-needs-review", "review_ref": "review-claim", "reviewed_revision": None, "expected_filing_revision": 1},
                "finding-filing": {"status": "confirmed", "event_ref": "event-claim-filing", "review_ref": "review-filing-new", "reviewed_revision": 1, "expected_filing_revision": 2},
            },
            "proof_reviews": {
                "finding-verified:r3": {"terminal_status": "verified"},
                "finding-proof:r1": {"terminal_status": "verified"},
            },
            "outstanding_reviews": [
                {"review_type": "pocinator", "entity_ref": "finding-verified", "review_ref": "event-review-z", "reason": "Proof review remains blocked.", "status": "blocked", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:02Z"},
                {"review_type": "regrade", "entity_ref": "finding-verified", "review_ref": "event-review-a", "reason": "Confirmed claim still requires a correction.", "status": "correction_required", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:01Z"},
            ],
            "candidates": {
                "candidate-selected": {"status": "selected"},
                "candidate-cited": {"status": "selected"},
                "candidate-deferred": {"status": "deferred"},
                "candidate-closed": {"status": "closed"},
            },
            "control_candidates": [
                {"routing_event_id": "event-control-verified", "status": "likely_held"},
                {"routing_event_id": "event-control-candidate", "status": "likely_held"},
            ],
            "authority_requests": {
                "request-approved": {"request_id": "request-approved", "status": "approved"},
                "request-pending": {"request_id": "request-pending", "status": "pending_authority"},
            },
        }
        queue_attempts = [
            {"attempt_id": "attempt-control-wrong-kind", "hypothesis_ref": None, "experiment_ref": "event-control-candidate", "kind": "primary"},
            {"attempt_id": "attempt-control-wrong-ref", "hypothesis_ref": None, "experiment_ref": "event-other", "kind": "negative_control"},
            {"attempt_id": "attempt-control-verified", "hypothesis_ref": None, "experiment_ref": "event-control-verified", "kind": "positive_control"},
            {"attempt_id": "attempt-hypothesis-adjudicated", "hypothesis_ref": "hypothesis-adjudicated", "experiment_ref": "experiment-adjudicated", "kind": "primary"},
            {"attempt_id": "attempt-hypothesis-ran", "hypothesis_ref": "hypothesis-ran", "experiment_ref": "experiment-ran", "kind": "primary"},
            {"attempt_id": "attempt-terminal-late", "hypothesis_ref": "hypothesis-terminal-route", "experiment_ref": "experiment-terminal", "kind": "primary"},
        ]
        expected_review_a = {"class": "review_obligation_open", "entity": {"type": "review_obligation", "id": "event-review-a", "detail": "finding-verified"}, "blocking": True, "predicate": "review_ref is present in outstanding_reviews", "closes_when": "review_ref is absent from outstanding_reviews"}
        expected_review_z = {"class": "review_obligation_open", "entity": {"type": "review_obligation", "id": "event-review-z", "detail": "finding-verified"}, "blocking": True, "predicate": "review_ref is present in outstanding_reviews", "closes_when": "review_ref is absent from outstanding_reviews"}
        expected_queue = [
            {"class": "hypothesis_ran_unadjudicated", "entity": {"type": "hypothesis", "id": "hypothesis-ran", "detail": None}, "blocking": True, "predicate": "a matching attempt_id is absent from experiment_refs and control_refs", "closes_when": "every matching attempt_id is present in experiment_refs or control_refs"},
            {"class": "hypothesis_ran_unadjudicated", "entity": {"type": "hypothesis", "id": "hypothesis-terminal-route", "detail": None}, "blocking": True, "predicate": "a matching attempt_id is absent from experiment_refs and control_refs", "closes_when": "every matching attempt_id is present in experiment_refs or control_refs"},
            {"class": "hypothesis_running_unattempted", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": None}, "blocking": True, "predicate": "status is running and no matching attempt is recorded", "closes_when": "a matching attempt is recorded or status is outside running"},
            {"class": "hypothesis_unrouted", "entity": {"type": "hypothesis", "id": "hypothesis-ran", "detail": None}, "blocking": True, "predicate": "status in {queued, selected}", "closes_when": "status is outside {queued, selected}"},
            {"class": "hypothesis_unrouted", "entity": {"type": "hypothesis", "id": "hypothesis-unrouted", "detail": None}, "blocking": True, "predicate": "status in {queued, selected}", "closes_when": "status is outside {queued, selected}"},
            {"class": "hypothesis_open_route", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": "route-z"}, "blocking": True, "predicate": "next_route is not null", "closes_when": "next_route is null"},
            {"class": "hypothesis_open_route", "entity": {"type": "hypothesis", "id": "hypothesis-terminal-route", "detail": "route-terminal"}, "blocking": True, "predicate": "next_route is not null", "closes_when": "next_route is null"},
            {"class": "hypothesis_open_route", "entity": {"type": "hypothesis", "id": "hypothesis-unrouted", "detail": "route-selected"}, "blocking": True, "predicate": "next_route is not null", "closes_when": "next_route is null"},
            {"class": "hypothesis_unresolved_question", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": ""}, "blocking": True, "predicate": "unresolved_questions contains this exact question", "closes_when": "this exact question is absent from unresolved_questions"},
            {"class": "hypothesis_unresolved_question", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": "question-a"}, "blocking": True, "predicate": "unresolved_questions contains this exact question", "closes_when": "this exact question is absent from unresolved_questions"},
            {"class": "hypothesis_unresolved_question", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": "question-z"}, "blocking": True, "predicate": "unresolved_questions contains this exact question", "closes_when": "this exact question is absent from unresolved_questions"},
            {"class": "claim_unadjudicated", "entity": {"type": "finding", "id": "finding-claim", "detail": None}, "blocking": True, "predicate": "effective claim status in {needs_review, supported}", "closes_when": "effective claim status in {confirmed, contaminated, refuted}"},
            expected_review_a,
            expected_review_z,
            {"class": "finding_revision_pending", "entity": {"type": "finding", "id": "finding-filing", "detail": None}, "blocking": True, "predicate": "latest fileable claim adjudication is not reflected by its expected finding revision", "closes_when": "the expected finding revision reflects the latest adjudication, or a newer adjudication supersedes it"},
            {"class": "finding_unproved", "entity": {"type": "finding", "id": "finding-proof", "detail": None}, "blocking": True, "predicate": "status in {supported, confirmed} and the current revision has no verified proof review", "closes_when": "the current revision has a proof review with terminal_status verified or status is outside {supported, confirmed}"},
            {"class": "candidate_undisposed", "entity": {"type": "candidate", "id": "candidate-closed", "detail": None}, "blocking": True, "predicate": "status in {queued, selected, closed} and no hypothesis cites this candidate as origin", "closes_when": "a hypothesis has origin_type candidate and origin_ref equal to this candidate id"},
            {"class": "candidate_undisposed", "entity": {"type": "candidate", "id": "candidate-selected", "detail": None}, "blocking": True, "predicate": "status in {queued, selected, closed} and no hypothesis cites this candidate as origin", "closes_when": "a hypothesis has origin_type candidate and origin_ref equal to this candidate id"},
            {"class": "deferred_candidate_unreviewed", "entity": {"type": "candidate", "id": "candidate-deferred", "detail": None}, "blocking": True, "predicate": "status is deferred", "closes_when": "status is not deferred"},
            {"class": "control_candidate_unverified", "entity": {"type": "control_candidate", "id": "event-control-candidate", "detail": None}, "blocking": True, "predicate": "status is likely_held and no control-kind attempt references this routing event", "closes_when": "a negative_control or positive_control attempt has experiment_ref equal to this routing event id"},
            {"class": "awaiting_operator", "entity": {"type": "authority_request", "id": "request-pending", "detail": None}, "blocking": False, "predicate": "status is pending_authority", "closes_when": "status is not pending_authority"},
        ]
        computed_queue = compute_work_queue(queue_state, queue_attempts)
        reordered_state = copy.deepcopy(queue_state)
        for key in ("hypotheses", "findings", "claim_adjudications", "proof_reviews", "candidates", "authority_requests"):
            reordered_state[key] = dict(reversed(list(reordered_state[key].items())))
        reordered_state["control_candidates"].reverse()
        reordered_state["outstanding_reviews"].reverse()
        for hypothesis_state in reordered_state["hypotheses"].values():
            hypothesis_state["unresolved_questions"].reverse()
        reordered_queue = compute_work_queue(reordered_state, list(reversed(queue_attempts)))
        checks.append(("computed work queue covers every debt class in canonical order with exact overlapping predicates", computed_queue == expected_queue, str(computed_queue)))
        checks.append(("computed work queue is independent of source insertion order", canonical_json_bytes(computed_queue) == canonical_json_bytes(reordered_queue), str(reordered_queue)))
        checks.append(("only pending operator authority is nonblocking and it suppresses coverage review", [item for item in computed_queue if not item["blocking"]] == [expected_queue[-1]] and all(item["class"] != "coverage_review_missing" for item in computed_queue), str(computed_queue)))
        checks.append(("the one ending predicate permits empty or operator-only queues and fails closed on blocking, missing, or malformed queue state", engagement_may_end({"work_queue": []}) and engagement_may_end({"work_queue": [expected_queue[-1]]}) and not engagement_may_end({"work_queue": [expected_queue[0]]}) and not engagement_may_end({}) and not engagement_may_end({"work_queue": {}}), "ending predicate admitted malformed or blocking work"))

        operator_only_state = {**queue_state, "hypotheses": {}, "findings": {}, "claim_adjudications": {}, "proof_reviews": {}, "outstanding_reviews": [], "candidates": {}, "control_candidates": [], "authority_requests": {"request-pending": queue_state["authority_requests"]["request-pending"]}}
        terminal_debt_state = {
            **operator_only_state,
            "coverage": "active",
            "authority_requests": {},
            "hypotheses": {
                "hypothesis-running-unattempted": {
                    "status": "running",
                    "running_event_ref": "event-hypothesis-running-unattempted",
                    "origin_type": "operator_prior",
                    "origin_ref": "prior-running-unattempted",
                    "experiment_refs": [],
                    "control_refs": [],
                    "unresolved_questions": [],
                    "next_route": None,
                }
            },
            "candidates": {"candidate-queued": {"status": "queued"}},
        }
        terminal_debt_projection = project_terminal_work_state(
            terminal_debt_state,
            [],
            coverage="coverage_dry",
            recorded_at="2026-07-10T00:00:10Z",
        )
        terminal_debt_actions = {
            item["class"]: decorate_work_queue_item(item, terminal_debt_projection, engagement.absolute())["next_action"]
            for item in terminal_debt_projection["work_queue"]
        }
        checks.append((
            "terminal projection keeps queued candidates and running unattempted hypotheses blocking with deterministic next actions",
            [item["class"] for item in terminal_debt_projection["work_queue"]] == ["hypothesis_running_unattempted", "candidate_undisposed"]
            and not engagement_may_end(terminal_debt_projection)
            and terminal_debt_actions["hypothesis_running_unattempted"]["action_id"] == "record_hunter_primary"
            and terminal_debt_actions["hypothesis_running_unattempted"]["effect"] == "advances_item"
            and terminal_debt_actions["candidate_undisposed"]["action_id"] == "select_candidate"
            and terminal_debt_actions["candidate_undisposed"]["effect"] == "advances_item",
            str((terminal_debt_projection["work_queue"], terminal_debt_actions)),
        ))
        specialized_running_state = {
            **operator_only_state,
            "coverage": "coverage_dry",
            "scope_hash": initial_reduction["scope_hash"],
            "active_environment_ref": "environment-specialized",
            "authority_requests": {},
            "outstanding_reviews": [{
                "review_type": "regrade",
                "entity_ref": "finding-specialized-review",
                "review_ref": "review-specialized-running",
                "reason": "The exact routed review owns this running hypothesis.",
                "status": "routed",
                "hypothesis_ref": "hypothesis-specialized-review",
                "opened_at": "2026-07-10T00:00:00Z",
            }],
            "hypotheses": {
                "hypothesis-specialized-review": {"status": "running", "running_event_ref": "event-specialized-review-running", "next_route": "review experiment", "unresolved_questions": []},
                "hypothesis-specialized-control": {"status": "running", "running_event_ref": "event-specialized-control-running", "next_route": "control experiment", "unresolved_questions": []},
            },
            "control_candidates": [{
                "routing_event_id": "event-specialized-control-routing",
                "status": "likely_held",
                "hypothesis_ref": "hypothesis-specialized-control",
                "primary_attempt_ref": None,
            }],
            "work_queue_context": {
                "pending_attempts": {},
                "artifacts": {
                    "artifact-specialized-review": {
                        "created_at": "2026-07-10T00:00:01Z",
                        "environment_ref": "environment-specialized",
                    }
                },
            },
        }
        specialized_running_state["work_queue"] = compute_work_queue(specialized_running_state, [])
        specialized_review_item = next(item for item in specialized_running_state["work_queue"] if item["class"] == "review_obligation_open")
        specialized_control_item = next(item for item in specialized_running_state["work_queue"] if item["class"] == "control_candidate_unverified")
        specialized_review_action = decorate_work_queue_item(specialized_review_item, specialized_running_state, engagement.absolute())["next_action"]
        specialized_control_action = decorate_work_queue_item(specialized_control_item, specialized_running_state, engagement.absolute())["next_action"]
        from work_queue_admission import build_action_admission
        specialized_control_admission = build_action_admission(specialized_control_item, specialized_control_action, specialized_running_state, engagement.absolute())
        specialized_control_experiment_constraints = [
            constraint
            for constraint in specialized_control_admission["constraints"]
            if constraint["document"] == "proposal" and constraint["path"] == ["experiment_ref"]
        ]
        checks.append((
            "running review and control hypotheses retain their exact specialized evidence actions",
            [item["class"] for item in specialized_running_state["work_queue"]] == ["review_obligation_open", "control_candidate_unverified"]
            and specialized_review_action["action_id"] == "collect_review_evidence"
            and specialized_control_action["action_id"] == "record_control_primary"
            and specialized_control_experiment_constraints == [{"document": "proposal", "path": ["experiment_ref"], "operator": "equals", "value": "event-specialized-control-routing"}],
            str((specialized_running_state["work_queue"], specialized_review_action, specialized_control_action, specialized_control_admission)),
        ))
        review_only_state = {**operator_only_state, "findings": {"finding-verified": queue_state["findings"]["finding-verified"]}, "proof_reviews": {"finding-verified:r3": queue_state["proof_reviews"]["finding-verified:r3"]}, "outstanding_reviews": [queue_state["outstanding_reviews"][1]], "authority_requests": {}}
        resolved_review_state = {**review_only_state, "outstanding_reviews": []}
        expected_queue_coverage = {**expected_coverage_item, "entity": {**expected_coverage_item["entity"], "id": queue_state["engagement_id"]}}
        checks.append(("confirmed and proof-verified review debt blocks coverage until the exact outstanding row is removed", compute_work_queue(review_only_state, []) == [expected_review_a] and compute_work_queue(resolved_review_state, []) == [expected_queue_coverage], str(compute_work_queue(review_only_state, []))))
        stage_base = {**operator_only_state, "authority_requests": {}, "coverage": "active"}
        initial_supported = {**stage_base, "claim_adjudications": {"finding-initial": {"status": "supported", "event_ref": "event-claim-initial", "review_ref": "review-claim-initial", "reviewed_revision": None, "expected_filing_revision": 1}}}
        initial_needs_review = {**stage_base, "claim_adjudications": {"finding-needs-review": {"status": "needs_review", "event_ref": "event-claim-needs-review-new", "review_ref": "review-needs-review-new", "reviewed_revision": None, "expected_filing_revision": 1}}}
        reflected_supported = {**initial_supported, "findings": {"finding-initial": {"revision": 1, "status": "supported", "adjudication_review_ref": "review-claim-initial", "adjudication_event_ref": "event-claim-initial"}}}
        newer_confirmed = {**stage_base, "findings": {"finding-current": {"revision": 1, "status": "supported", "adjudication_review_ref": "review-old", "adjudication_event_ref": "event-old"}}, "claim_adjudications": {"finding-current": {"status": "confirmed", "event_ref": "event-claim-new", "review_ref": "review-new", "reviewed_revision": 1, "expected_filing_revision": 2, "recorded_at": "2026-07-10T00:00:10Z", "event_sequence": 10}}}
        reflected_confirmed = {**newer_confirmed, "findings": {"finding-current": {"revision": 2, "status": "confirmed", "adjudication_review_ref": "review-new", "adjudication_event_ref": "event-claim-new"}}}
        stage_classes = lambda snapshot: [(item["class"], item["entity"]["id"]) for item in compute_work_queue(snapshot, [])]
        checks.append(("claim stage distinguishes initial review, filing, reflected review, and current-revision proof debt", stage_classes(initial_needs_review) == [("claim_unadjudicated", "finding-needs-review")] and stage_classes(initial_supported) == [("claim_unadjudicated", "finding-initial"), ("finding_revision_pending", "finding-initial")] and stage_classes(reflected_supported) == [("claim_unadjudicated", "finding-initial"), ("finding_unproved", "finding-initial")] and stage_classes(newer_confirmed) == [("finding_revision_pending", "finding-current")] and stage_classes(reflected_confirmed) == [("finding_unproved", "finding-current")], str([stage_classes(item) for item in (initial_needs_review, initial_supported, reflected_supported, newer_confirmed, reflected_confirmed)])))

        legacy_overlap = copy.deepcopy(reflected_supported)
        legacy_overlap["outstanding_reviews"] = [{"review_type": "legacy_adjudication", "entity_ref": "finding-initial", "review_ref": "event-legacy-import", "reason": "Imported claim needs exact review.", "status": "pending", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:01Z"}]
        legacy_claim_item = next(item for item in compute_work_queue(legacy_overlap, []) if item["class"] == "claim_unadjudicated")
        legacy_claim_action = decorate_work_queue_item(legacy_claim_item, legacy_overlap, engagement.absolute())["next_action"]
        refuted_overlap = copy.deepcopy(reflected_supported)
        refuted_overlap["outstanding_reviews"] = [{"review_type": "regrade", "entity_ref": "finding-initial", "review_ref": "event-regrade-refuted", "reason": "Independent regrade refuted the claim.", "status": "correction_required", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:02Z", "required_claim_status": "refuted"}]
        refuted_claim_item = next(item for item in compute_work_queue(refuted_overlap, []) if item["class"] == "claim_unadjudicated")
        refuted_claim_action = decorate_work_queue_item(refuted_claim_item, refuted_overlap, engagement.absolute())["next_action"]
        legacy_requirements = " ".join(requirement for value in legacy_claim_action["required_inputs"] for requirement in value["requirements"])
        refuted_requirements = " ".join(requirement for value in refuted_claim_action["required_inputs"] for requirement in value["requirements"])
        checks.append(("claim-first overlap actions bind exact legacy and refuted review debt", "event-legacy-import" in legacy_requirements and "event-regrade-refuted" in refuted_requirements and "verdict is exactly refuted" in refuted_requirements, str((legacy_claim_action, refuted_claim_action))))

        eligible_reviews = [
            {"review_type": "regrade", "entity_ref": "finding-current", "review_ref": "review-correction", "status": "correction_required", "opened_at": "2026-07-10T00:00:01Z"},
            {"review_type": "regrade_escalation", "entity_ref": "finding-current", "review_ref": "review-escalation", "status": "evidence_collected", "opened_at": "2026-07-10T00:00:02Z"},
            {"review_type": "pocinator", "entity_ref": "finding-current", "review_ref": "review-poc", "status": "correction_required", "opened_at": "2026-07-10T00:00:03Z"},
            {"review_type": "legacy_adjudication", "entity_ref": "finding-current", "review_ref": "review-legacy", "status": "pending", "opened_at": "2026-07-10T00:00:04Z"},
        ]
        blocking_regrade_reviews = [
            {"review_type": "regrade", "entity_ref": "finding-current", "review_ref": "review-pending", "status": "pending", "opened_at": "2026-07-10T00:00:05Z"},
            {"review_type": "regrade", "entity_ref": "finding-current", "review_ref": "review-routed", "status": "routed", "opened_at": "2026-07-10T00:00:06Z"},
        ]
        ineligible_reviews = [
            {"review_type": "pocinator", "entity_ref": "finding-current", "review_ref": "review-blocked", "status": "blocked", "opened_at": "2026-07-10T00:00:07Z"},
        ]
        target = {"type": "finding", "id": "finding-current", "expected_revision": 2, "claim_state": "confirmed", "adjudication_event_ref": "event-claim-new", "adjudication_review_ref": "review-new", "resolves_review_refs": sorted(item["review_ref"] for item in eligible_reviews), "file_digest": "sha256:" + "7" * 64}
        pending_request = {"request_id": "request-v2-pending", "action_kind": "revise-finding", "status": "pending_authority", "lane_id": finding_revision_lane_id(target), "target": target}
        pending_filing = copy.deepcopy({**newer_confirmed, "outstanding_reviews": eligible_reviews, "authority_requests": {"request-v2-pending": pending_request}})
        pending_filing["claim_adjudications"]["finding-current"]["input_refs"] = sorted(item["review_ref"] for item in eligible_reviews)
        pending_keys = stage_classes(pending_filing)
        past_deadline_pending = copy.deepcopy(pending_filing); past_deadline_pending["authority_requests"]["request-v2-pending"]["expires_at"] = "2000-01-01T00:00:00Z"
        checks.append(("current v2 pending authority suppresses its exact filing-ready rows and expiry remains explicit record state", pending_keys == [("awaiting_operator", "request-v2-pending")] and stage_classes(past_deadline_pending) == pending_keys, str(pending_keys)))
        blocked_poc_filing = {**pending_filing, "outstanding_reviews": [*eligible_reviews, *ineligible_reviews]}
        blocked_poc_keys = stage_classes(blocked_poc_filing)
        checks.append(("blocked pocinator debt prevents filing suppression and remains ahead of revision work", ("finding_revision_pending", "finding-current") in blocked_poc_keys and ("review_obligation_open", "review-blocked") in blocked_poc_keys and blocked_poc_keys.index(("review_obligation_open", "review-blocked")) < blocked_poc_keys.index(("finding_revision_pending", "finding-current")), str(blocked_poc_keys)))
        blocked_filing = {**pending_filing, "outstanding_reviews": [*pending_filing["outstanding_reviews"], *blocking_regrade_reviews]}
        blocked_keys = stage_classes(blocked_filing)
        blocked_filing["work_queue"] = compute_work_queue(blocked_filing, [])
        blocked_list = queue_command_payload("list", blocked_filing, engagement.absolute())
        checks.append(("pending and routed regrade debt blocks filing and list never advertises a stale lower-ranked authority action", ("finding_revision_pending", "finding-current") in blocked_keys and all(("review_obligation_open", item["review_ref"]) in blocked_keys for item in blocking_regrade_reviews) and all("next_action" not in item for item in blocked_list["items"]), str((blocked_keys, blocked_list))))
        new_eligible = {"review_type": "pocinator", "entity_ref": "finding-current", "review_ref": "review-new-debt", "status": "correction_required", "opened_at": "2026-07-10T00:00:11Z"}
        stale_review_set = {**pending_filing, "outstanding_reviews": [*pending_filing["outstanding_reviews"], new_eligible]}
        stale_adjudication = copy.deepcopy(pending_filing); stale_adjudication["claim_adjudications"]["finding-current"] = {**stale_adjudication["claim_adjudications"]["finding-current"], "event_ref": "event-claim-newer", "review_ref": "review-newer"}
        wrong_lane = copy.deepcopy(pending_filing); wrong_lane["authority_requests"]["request-v2-pending"]["lane_id"] = "caller-controlled-lane"
        approved_overlap = copy.deepcopy(pending_filing); approved_overlap["authority_requests"] = {"request-v2-approved": {
            **pending_request,
            "request_id": "request-v2-approved",
            "status": "approved",
            "expires_at": "2099-01-01T00:00:00Z",
            "application": {"action_path": "authority/requests/request-v2-approved.action.json", "executor_id": "broker-approved", "session_id": "session-approved", "operator_id": "operator-approved"},
        }}
        explicitly_expired = copy.deepcopy(pending_filing); explicitly_expired["authority_requests"]["request-v2-pending"]["status"] = "expired"
        checks.append(("stale adjudication, changed filing-ready debt, wrong lane, approved overlap, and explicit expiry all re-expose filing debt", all(("finding_revision_pending", "finding-current") in stage_classes(item) for item in (stale_review_set, stale_adjudication, wrong_lane, approved_overlap, explicitly_expired)), str([stage_classes(item) for item in (stale_review_set, stale_adjudication, wrong_lane, approved_overlap, explicitly_expired)])))
        approved_overlap["work_queue"] = compute_work_queue(approved_overlap, [])
        approved_review_item = next(item for item in approved_overlap["work_queue"] if item["class"] == "review_obligation_open")
        approved_finding_item = next(item for item in approved_overlap["work_queue"] if item["class"] == "finding_revision_pending")

        class _EarlyQueueClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 1, 1, tzinfo=tz)

        class _LateQueueClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2100, 1, 1, tzinfo=tz)

        from unittest.mock import patch
        with patch("work_queue_actions.datetime", _EarlyQueueClock):
            early_approved_action = decorate_work_queue_item(approved_review_item, approved_overlap, engagement.absolute())["next_action"]
        with patch("work_queue_actions.datetime", _LateQueueClock):
            late_approved_action = decorate_work_queue_item(approved_review_item, approved_overlap, engagement.absolute())["next_action"]
        approved_finding_action = decorate_work_queue_item(approved_finding_item, approved_overlap, engagement.absolute())["next_action"]
        checks.append(("approved revision actions are identical across wall time and route both higher review debt and revision work through one atomic settlement", canonical_json_bytes(early_approved_action) == canonical_json_bytes(late_approved_action) and early_approved_action["action_id"] == approved_finding_action["action_id"] == "settle_approved_finding_revision" and early_approved_action["command"] == "settle-approved-revision" and early_approved_action["effect"] == "conditional", str((early_approved_action, late_approved_action, approved_finding_action))))
        stale_filing = copy.deepcopy(pending_filing)
        stale_filing["claim_adjudications"]["finding-current"].update({"recorded_at": "2026-07-10T00:00:01Z", "input_refs": []})
        stale_review_item = next(item for item in compute_work_queue(stale_filing, []) if item["class"] == "review_obligation_open")
        stale_review_action = decorate_work_queue_item(stale_review_item, stale_filing, engagement.absolute())["next_action"]
        checks.append(("a pre-opening or input-unbound adjudication never advances review debt to revision authority", _filing_blocking_review_error(stale_filing, "finding-current") in {"review_adjudication_not_fresh", "review_adjudication_inputs_missing"} and stale_review_action["action_id"] == "record_claim_adjudication", str(stale_review_action)))
        current_proposal = {"finding_id": "finding-current", "revision": 2, "supersedes_revision": 1, "claim_state": "confirmed", "adjudication": {"review_ref": "review-new"}}
        current_target = {**target, "resolves_review_refs": [], "file_digest": sha256_bytes(canonical_json_bytes(current_proposal))}; current_request = {**pending_request, "lane_id": finding_revision_lane_id(current_target), "target": current_target}; current_target_state = {**newer_confirmed, "outstanding_reviews": []}
        stale_same_status_state = copy.deepcopy(current_target_state); stale_same_status_state["claim_adjudications"]["finding-current"].update({"event_ref": "event-confirmed-newer", "review_ref": "review-confirmed-newer"})
        checks.append(("v2 apply-time currentness rejects a newer same-status adjudication", revise_finding_target_is_current(current_target_state, current_request, current_proposal) and not revise_finding_target_is_current(stale_same_status_state, current_request, current_proposal), str(stale_same_status_state["claim_adjudications"])))
        second_finding = {**pending_filing, "findings": {**pending_filing["findings"], "finding-other": {"revision": 1, "status": "supported", "adjudication_review_ref": "review-other-old", "adjudication_event_ref": "event-other-old"}}, "claim_adjudications": {**pending_filing["claim_adjudications"], "finding-other": {"status": "confirmed", "event_ref": "event-other-new", "review_ref": "review-other-new", "reviewed_revision": 1, "expected_filing_revision": 2}}}
        legacy_pending = {**newer_confirmed, "authority_requests": {"request-legacy": {"request_id": "request-legacy", "action_kind": "revise-finding", "status": "pending_authority", "lane_id": "legacy-lane", "target": None}}}
        checks.append(("v2 suppression is finding-scoped and legacy pending authority never hides filing debt", ("finding_revision_pending", "finding-other") in stage_classes(second_finding) and ("finding_revision_pending", "finding-current") in stage_classes(legacy_pending), str([stage_classes(second_finding), stage_classes(legacy_pending)])))
        terminal_queues = [compute_work_queue({**queue_state, "coverage": status}, queue_attempts) for status in ("coverage_dry", "budget_bounded")]
        checks.append(("coverage review is the sole last item only when active work is otherwise empty", compute_work_queue({**operator_only_state, "authority_requests": {}}, []) == [expected_queue_coverage] and compute_work_queue(operator_only_state, []) == [expected_queue[-1]], "coverage or operator-only queue mismatch"))
        terminal_classes = [{item["class"] for item in queue if item["blocking"]} for queue in terminal_queues]
        checks.append(("terminal coverage removes only its sentinel and preserves unadjudicated claims, deferred candidates, closed candidates, and unverified controls", all({"claim_unadjudicated", "deferred_candidate_unreviewed", "candidate_undisposed", "control_candidate_unverified"}.issubset(classes) for classes in terminal_classes) and all("coverage_review_missing" not in classes for classes in terminal_classes), str(terminal_queues)))
        healthy_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "ledger-health", "--engagement", str(engagement)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: healthy_status = json.loads(healthy_cli.stdout)
        except json.JSONDecodeError: healthy_status = {}
        checks.append(("public ledger health reports a reducible engagement as healthy", healthy_cli.returncode == 0 and healthy_status.get("status") == "healthy" and healthy_status.get("reducible") is True and healthy_status.get("error") is None, healthy_cli.stdout + healthy_cli.stderr))
        invalid_health = root / "invalid-health"; invalid_health.mkdir(); invalid_health.joinpath("scope.md").write_text(scope.replace("self-test", "invalid-health"), encoding="utf-8"); initialize_engagement(invalid_health, "2026-07-10T00:00:01Z")
        sensitive_marker = "health-probe-redaction-" + "x" * 32; invalid_event = copy.deepcopy(read_ledger(invalid_health, "event")[0]); invalid_event["event_type"] = sensitive_marker; invalid_event["record_hash"] = compute_record_hash(invalid_event); (invalid_health / "events.jsonl").write_bytes(canonical_json_bytes(invalid_event))
        invalid_bytes = (invalid_health / "events.jsonl").read_bytes(); raw_read_code = None; raw_reduce_code = None; raw_append_code = None
        try: read_ledger(invalid_health, "event")
        except RecordError as exc: raw_read_code = exc.code
        try: reduce_engagement(invalid_health)
        except RecordError as exc: raw_reduce_code = exc.code
        invalid_proposal = base_event(event_id="event-health-invalid-append", engagement_id=invalid_health.name, recorded_at="2026-07-10T00:00:02Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Prove the existing append refusal remains unchanged.", payload={"entity_id": "invalid-health", "entity_type": "ledger_health_control", "status": "invalid", "reason": "The invalid ledger must refuse mutation."}, session_id="session-health-invalid", operation_class="notebook")
        try: append_event(invalid_health, invalid_proposal)
        except RecordError as exc: raw_append_code = exc.code
        invalid_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "ledger-health", "--engagement", str(invalid_health)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: invalid_status = json.loads(invalid_cli.stdout)
        except json.JSONDecodeError: invalid_status = {}
        checks.append(("public ledger health reports an invalid ledger as sanitized status without raising", invalid_cli.returncode == 0 and invalid_status.get("status") == "invalid" and invalid_status.get("reducible") is False and invalid_status.get("error", {}).get("code") == raw_reduce_code and invalid_status.get("error", {}).get("details") == [] and sensitive_marker not in (invalid_cli.stdout + invalid_cli.stderr), invalid_cli.stdout + invalid_cli.stderr))
        checks.append(("raw read, reduce, and append paths still refuse the invalid ledger unchanged", raw_read_code == "ledger_schema_invalid" and raw_reduce_code == raw_read_code and raw_append_code == raw_read_code and (invalid_health / "events.jsonl").read_bytes() == invalid_bytes, f"read={raw_read_code} reduce={raw_reduce_code} append={raw_append_code}"))
        unreadable_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "ledger-health", "--engagement", str(root / "missing-health")], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: unreadable_status = json.loads(unreadable_cli.stdout)
        except json.JSONDecodeError: unreadable_status = {}
        checks.append(("public ledger health distinguishes an unreadable engagement from an invalid ledger", unreadable_cli.returncode == 0 and unreadable_status.get("status") == "unreadable" and unreadable_status.get("reducible") is False and unreadable_status.get("error", {}).get("code") == "ledger_unreadable", unreadable_cli.stdout + unreadable_cli.stderr))
        signature_events=read_ledger(engagement,"event");signature_challenge={"schema_version":1,"namespace":"llm-redteam-harness-operator-v1","engagement_id":engagement.name,"scope_hash":snapshot["scope_hash"],"ledger_hash":signature_events[-1]["record_hash"],"operation":"selftest-signed-operation","operator_id":"operator-selftest"};challenge_path=root/"operator-challenge.json";challenge_path.write_bytes(canonical_json_bytes(signature_challenge));subprocess.run(["/usr/bin/ssh-keygen","-Y","sign","-f",str(reviewer_key),"-n","llm-redteam-harness-operator-v1",str(challenge_path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);prior_signature=os.environ.get("HARNESS_OPERATOR_SIGNATURE_FILE");prior_signers=os.environ.get("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE");os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"]=str(challenge_path)+".sig";os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"]=str(allowed_signers_path);signed_gate_passed=True
        try:
            _require_operator_console(engagement,"operator-selftest","selftest-signed-operation");swapped_blocked=False
            try:_require_operator_console(engagement,"operator-selftest","selftest-swapped-operation")
            except RecordError as exc:swapped_blocked=exc.code=="operator_signature_invalid"
            signed_gate_passed=signed_gate_passed and swapped_blocked
        except RecordError:signed_gate_passed=False
        finally:
            if prior_signature is None:os.environ.pop("HARNESS_OPERATOR_SIGNATURE_FILE",None)
            else:os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"]=prior_signature
            if prior_signers is None:os.environ.pop("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE",None)
            else:os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"]=prior_signers
        checks.append(("scoped SSH signature authorizes only the exact operator challenge",signed_gate_passed,"valid operator signature rejected"))
        denied = root/"zone2-denied"; denied.mkdir(); denied.joinpath("scope.md").write_text(scope.replace("impact_demo_authorized: `yes`", "impact_demo_authorized: `no`").replace("zone2_authorized_categories: `zone2_artifact_creation`", "zone2_authorized_categories: `none`").replace("zone2_escalation_ceiling: `artifact_creation`", "zone2_escalation_ceiling: `none`")); denied_state = initialize_engagement(denied, "2026-07-10T00:00:00Z"); denied_blocked = False
        try: require_scope_zone2_authorized(denied, denied_state["scope_hash"])
        except RecordError as exc: denied_blocked = exc.code == "zone2_not_authorized_by_scope"
        checks.append(("signed scope denial mechanically blocks Zone-2 before confirmation", denied_blocked, "impact-demo denial was ignored"))
        legacy_kernel=root/"legacy-kernel";legacy_kernel.mkdir();legacy_kernel.joinpath("scope.md").write_text(scope.replace("decision-0006-v1","decision-0005-v1"));initialize_engagement(legacy_kernel,"2026-07-10T00:00:00Z");legacy_broker_blocked=False
        try:_require_decision6_kernel(legacy_kernel)
        except RecordError as exc:legacy_broker_blocked=exc.code=="decision6_kernel_not_selected"
        checks.append(("Decision-0005 signed scope cannot invoke Decision-0006 broker authority model",legacy_broker_blocked,"legacy kernel enabled autonomous broker commands"))
        # migrate-kernel: decision-0005 -> decision-0006 with orphan reconciliation, operator-signed.
        mig_root = root / "migrate-kernel-eng"
        mig_root.mkdir()
        mig_scope = scope.replace("self-test", "migrate-kernel-eng").replace("decision-0006-v1", "decision-0005-v1")
        mig_root.joinpath("scope.md").write_text(mig_scope)
        initialize_engagement(mig_root, "2026-07-10T00:00:00Z")
        # create orphan evidence + report draft
        mig_evidence = mig_root / "evidence"
        mig_evidence.mkdir(exist_ok=True)
        mig_evidence.joinpath("orphan-canary.md").write_text("# orphan evidence canary\n", encoding="utf-8")
        mig_reports = mig_root / "reports"
        mig_reports.mkdir(exist_ok=True)
        mig_reports.joinpath("draft-report.md").write_text("# draft report canary\n", encoding="utf-8")
        # 0005 cannot register a finding/report; a 0006-only command must be refused pre-migration
        mig_draft = root / "migrate-kernel-draft.md"
        mig_draft.write_text(scope.replace("self-test", "migrate-kernel-eng"))
        # sign the migration challenge with the operator key
        mig_challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
                         "engagement_id": mig_root.name, "scope_hash": sha256_file(mig_draft),
                         "source_scope_hash": next(e["payload"]["scope_hash"] for e in reversed(read_ledger(mig_root, "event")) if e["event_type"] == "scope.attested"),
                         "ledger_hash": read_ledger(mig_root, "event")[-1]["record_hash"],
                         "operation": f"migrate-kernel:{sha256_file(mig_draft)}", "operator_id": "operator-selftest"}
        mig_challenge_path = root / "migrate-kernel-challenge.json"
        mig_challenge_path.write_bytes(canonical_json_bytes(mig_challenge))
        subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(mig_challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        prior_signature = os.environ.get("HARNESS_OPERATOR_SIGNATURE_FILE"); prior_signers = os.environ.get("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE")
        os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"] = str(mig_challenge_path) + ".sig"
        os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"] = str(allowed_signers_path)
        try:
            mig_result = command_migrate_kernel(argparse.Namespace(
                engagement=mig_root, draft=mig_draft, operator_id="operator-selftest",
                recorded_at="2026-07-10T00:00:02Z", reason="self-test kernel upgrade",
                executor_id="broker-selftest", session_id="session-selftest",
                attest_synthetic=True))
            mig_ok = mig_result == 0
            mig_err = ""
        except RecordError as exc:
            mig_ok = False
            mig_err = exc.code + ": " + str(exc.details)
        finally:
            if prior_signature is None: os.environ.pop("HARNESS_OPERATOR_SIGNATURE_FILE", None)
            else: os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"] = prior_signature
            if prior_signers is None: os.environ.pop("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE", None)
            else: os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"] = prior_signers
        mig_state = reduce_engagement(mig_root) if mig_ok else None
        mig_attested = mig_state is not None and mig_state["scope_hash"] == sha256_file(mig_draft)
        mig_0006 = mig_state is not None and any(e["event_type"] == "scope.attested" and e["payload"].get("record_kernel") == "decision-0006-v1" for e in read_ledger(mig_root, "event"))
        mig_reconciled = mig_state is not None and not (mig_root / "reports/draft-report.md").exists() and (mig_root / "report-drafts/draft-report.md").is_file()
        mig_artifact = mig_state is not None and any(a["relative_path"] == "evidence/orphan-canary.md" for a in read_ledger(mig_root, "artifact"))
        checks.append(("migrate-kernel upgrades decision-0005 to decision-0006 with orphan reconciliation", mig_ok and mig_attested and mig_0006 and mig_reconciled and mig_artifact, f"mig_ok={mig_ok} attested={mig_attested} 0006={mig_0006} drafts={mig_reconciled} artifact={mig_artifact} err={mig_err}"))
        mig_refuse_bad_source = False
        try:
            command_migrate_kernel(argparse.Namespace(engagement=mig_root, draft=mig_draft, operator_id="operator-selftest", recorded_at="2026-07-10T00:00:03Z", reason="double migration", executor_id="broker-selftest", session_id="session-selftest"))
        except RecordError as exc:
            mig_refuse_bad_source = exc.code == "migrate_kernel_source_invalid"
        checks.append(("migrate-kernel refuses a non-decision-0005 source", mig_refuse_bad_source, "double migration was not refused"))
        duplicate_signer_root = root / "migrate-kernel-duplicate-signer"
        duplicate_signer_root.mkdir()
        duplicate_signer_root.joinpath("scope.md").write_text(mig_scope)
        initialize_engagement(duplicate_signer_root, "2026-07-10T00:00:00Z")
        duplicate_signer_draft = root / "migrate-kernel-duplicate-signer-draft.md"
        signer_line = f"- Operator allowed signers SHA256: {allowed_signers_digest}"
        duplicate_signer_draft.write_text(
            scope.replace("self-test", duplicate_signer_root.name).replace(
                signer_line, f"{signer_line}\n{signer_line}"
            )
        )
        duplicate_events = read_ledger(duplicate_signer_root, "event")
        duplicate_challenge = {
            "schema_version": 1,
            "namespace": "llm-redteam-harness-operator-v1",
            "engagement_id": duplicate_signer_root.name,
            "scope_hash": sha256_file(duplicate_signer_draft),
            "source_scope_hash": duplicate_events[-1]["payload"]["scope_hash"],
            "ledger_hash": duplicate_events[-1]["record_hash"],
            "operation": f"migrate-kernel:{sha256_file(duplicate_signer_draft)}",
            "operator_id": "operator-selftest",
        }
        duplicate_challenge_path = root / "migrate-kernel-duplicate-signer-challenge.json"
        duplicate_challenge_path.write_bytes(canonical_json_bytes(duplicate_challenge))
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(duplicate_challenge_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        prior_signature = os.environ.get("HARNESS_OPERATOR_SIGNATURE_FILE")
        prior_signers = os.environ.get("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE")
        os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"] = str(duplicate_challenge_path) + ".sig"
        os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"] = str(allowed_signers_path)
        duplicate_signer_rejected = False
        try:
            command_migrate_kernel(argparse.Namespace(
                engagement=duplicate_signer_root,
                draft=duplicate_signer_draft,
                operator_id="operator-selftest",
                recorded_at="2026-07-10T00:00:02Z",
                reason="reject ambiguous signer binding",
                executor_id="broker-selftest",
                session_id="session-selftest",
                attest_synthetic=True,
            ))
        except RecordError as exc:
            duplicate_signer_rejected = exc.code == "operator_signature_invalid"
        finally:
            if prior_signature is None: os.environ.pop("HARNESS_OPERATOR_SIGNATURE_FILE", None)
            else: os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"] = prior_signature
            if prior_signers is None: os.environ.pop("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE", None)
            else: os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"] = prior_signers
        duplicate_state = reduce_engagement(duplicate_signer_root)
        duplicate_signer_stayed_legacy = not any(
            event["event_type"] == "scope.attested"
            and event["payload"].get("record_kernel") == "decision-0006-v1"
            for event in read_ledger(duplicate_signer_root, "event")
        )
        checks.append((
            "migrate-kernel rejects duplicate operator signer bindings without changing the source kernel",
            duplicate_signer_rejected and duplicate_signer_stayed_legacy
            and duplicate_state["scope_hash"] == duplicate_events[-1]["payload"]["scope_hash"],
            f"rejected={duplicate_signer_rejected} stayed_legacy={duplicate_signer_stayed_legacy}",
        ))
        migration_tree = root / "migration-tree-symlink"
        migration_source = migration_tree / "engagements" / "source-fixture"
        migration_source.joinpath("nested", "deeper").mkdir(parents=True)
        migration_source.joinpath("scope.md").write_text(scope, encoding="utf-8")
        migration_outside = root / "migration-tree-outside"
        migration_outside.mkdir()
        migration_source.joinpath("nested", "deeper", "redirect").symlink_to(
            migration_outside, target_is_directory=True
        )
        migration_destination = root / "migration-tree-destination"
        migration_destination.mkdir()
        migration_destination.joinpath("scope.md").write_text(scope, encoding="utf-8")
        migration_root_fd = os.open(migration_tree, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        migration_destination_fd = os.open(
            migration_destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        migration_nested_symlink_blocked = False
        try:
            try:
                _require_migration_tree_safety(
                    migration_root_fd,
                    migration_destination_fd,
                    canonical_json_bytes({"engagement_id": "source-fixture"}),
                )
            except RecordError as exc:
                migration_nested_symlink_blocked = exc.code == "migration_source_symlink_rejected"
        finally:
            os.close(migration_root_fd)
            os.close(migration_destination_fd)
        checks.append((
            "migration tree safety finds nested symlinks through dirfd recursion",
            migration_nested_symlink_blocked,
            "nested source symlink was skipped",
        ))
        symlink_root = root/"symlink-ledger"; symlink_root.mkdir(); symlink_root.joinpath("scope.md").write_text(scope); outside_ledger = root/"outside-ledger"; outside_ledger.write_bytes(b""); symlink_root.joinpath("events.jsonl").symlink_to(outside_ledger); symlink_ledger_blocked = False
        try: initialize_engagement(symlink_root, "2026-07-10T00:00:00Z")
        except (OSError, RecordError): symlink_ledger_blocked = outside_ledger.read_bytes() == b""
        checks.append(("preexisting ledger symlink is rejected before external append", symlink_ledger_blocked, "ledger symlink redirected a write"))
        symlink_parent_root = root/"symlink-parent"; symlink_parent_root.mkdir(); symlink_parent_root.joinpath("scope.md").write_text(scope); outside_dir = root/"outside-dir"; outside_dir.mkdir(); symlink_parent_root.joinpath("authority").symlink_to(outside_dir, target_is_directory=True); symlink_parent_blocked = False
        try: atomic_write(symlink_parent_root/"authority/requests/action.json", b"{}\n")
        except (OSError, RecordError): symlink_parent_blocked = not any(outside_dir.iterdir())
        checks.append(("preexisting governed parent symlink is rejected before file write", symlink_parent_blocked, "parent symlink redirected a write"))
        root_target = root/"engagement-root-target"; root_target.mkdir(); root_target.joinpath("scope.md").write_text(scope); root_link = root/"engagement-root-link"; root_link.symlink_to(root_target, target_is_directory=True); root_link_blocked = False
        try: initialize_engagement(root_link, "2026-07-10T00:00:00Z")
        except (OSError, RecordError): root_link_blocked = not root_target.joinpath("events.jsonl").exists()
        checks.append(("preexisting engagement-root symlink is rejected before initialization", root_link_blocked, "engagement-root symlink redirected initialization"))
        ancestor_target = root/"ancestor-target"; ancestor_target.mkdir(); ancestor_engagement = ancestor_target/"eng"; ancestor_engagement.mkdir(); ancestor_engagement.joinpath("scope.md").write_text(scope); ancestor_link = root/"ancestor-link"; ancestor_link.symlink_to(ancestor_target, target_is_directory=True); ancestor_identity = ancestor_engagement.stat(); ancestor_alias_bound = False
        try:
            alias_snapshot = initialize_engagement(ancestor_link/"eng", "2026-07-10T00:00:00Z")
            alias_identity = os.stat(ancestor_link/"eng", follow_symlinks=False)
            ancestor_alias_bound = (
                alias_snapshot["engagement_id"] == "eng"
                and (alias_identity.st_dev, alias_identity.st_ino)
                == (ancestor_identity.st_dev, ancestor_identity.st_ino)
                and ancestor_link.is_symlink()
                and ancestor_engagement.joinpath("events.jsonl").is_file()
            )
        except (OSError, RecordError):
            ancestor_alias_bound = False
        checks.append(("intermediate ancestor aliases resolve once and initialize only the bound terminal inode", ancestor_alias_bound, "ancestor alias did not remain bound to the resolved terminal inode"))
        checks.append(("init writes deterministic snapshot and six generated views", (engagement / "state.snapshot.json").read_bytes() == canonical_json_bytes(snapshot) and len(render_views(snapshot)) == 6 and all((engagement / name).is_file() for name in render_views(snapshot)), "missing/stale initialization output"))

        authority_engagement = root / "authority-lanes"; authority_engagement.mkdir(); authority_engagement.joinpath("scope.md").write_text(scope.replace("self-test", "authority-lanes"), encoding="utf-8"); initialize_engagement(authority_engagement, "2026-07-10T00:00:00Z")
        action = _authority_action("test-authority", lane_id="lane-main", value="exact"); action_digest = sha256_bytes(canonical_json_bytes(action)); authority_scope = reduce_engagement(authority_engagement)["scope_hash"]
        request_event = base_event(event_id="event-authority-request-main", engagement_id=authority_engagement.name, recorded_at="2026-07-10T00:00:01Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="authority.requested", rationale="Request one exact lane-local test action.", payload={"request_id": "request-main", "action_kind": "test-authority", "action_digest": action_digest, "lane_id": "lane-main", "request_status": "pending_authority", "scope_hash": authority_scope, "environment_ref": None, "expires_at": "2099-07-10T00:10:00Z"}, session_id="session-authority-request", operation_class="notebook"); append_event(authority_engagement, request_event)
        unrelated = base_event(event_id="event-authority-unrelated", engagement_id=authority_engagement.name, recorded_at="2026-07-10T00:00:02Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Unrelated lane continues while authority is pending.", payload={"entity_id": "unrelated-observation", "entity_type": "observation", "status": "recorded"}, session_id="session-authority-request", operation_class="notebook"); append_event(authority_engagement, unrelated)
        retrospective_blocked = False
        try: require_approved_authority(authority_engagement, "request-main", "test-authority", action_digest, "lane-main", "2026-07-10T00:00:02Z")
        except RecordError as exc: retrospective_blocked = exc.code == "approved_authority_request_required"
        resolution = base_event(event_id="event-authority-resolution-main", engagement_id=authority_engagement.name, recorded_at="2026-07-10T00:00:03Z", actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact pending action.", payload={"request_id": "request-main", "request_event_ref": "event-authority-request-main", "action_digest": action_digest, "resolution": "approved", "resolved_at": "2026-07-10T00:00:03Z"}, entity_refs=["event-authority-request-main"], session_id="session-operator-authority", operation_class="authority"); append_event(authority_engagement, resolution)
        exact_approved = require_approved_authority(authority_engagement, "request-main", "test-authority", action_digest, "lane-main", "2026-07-10T00:00:04Z")["status"] == "approved"
        consumed = base_event(event_id="event-authority-consumed", engagement_id=authority_engagement.name, recorded_at="2026-07-10T00:00:04Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Consume the exact approval without changing another lane.", payload={"entity_id": "authority-consumption", "entity_type": "authority_application", "status": "recorded", "authority_request_ref": "request-main"}, session_id="session-authority-request", operation_class="notebook"); append_event(authority_engagement, consumed)
        reuse_blocked = False
        try: require_approved_authority(authority_engagement, "request-main", "test-authority", action_digest, "lane-main", "2026-07-10T00:00:05Z")
        except RecordError as exc: reuse_blocked = exc.code == "authority_request_already_consumed"
        resolutions = (("rejected", "2026-07-10T00:00:07Z", "2026-07-10T00:00:08Z", "2026-07-10T00:10:00Z"), ("expired", "2026-07-10T00:00:09Z", "2026-07-10T00:00:11Z", "2026-07-10T00:00:10Z"), ("superseded", "2026-07-10T00:00:12Z", "2026-07-10T00:00:13Z", "2026-07-10T00:10:00Z"))
        for resolution_name, requested_at, resolved_at, expires in resolutions:
            request_id = f"request-{resolution_name}"; request_ref = f"event-authority-request-{resolution_name}"
            append_event(authority_engagement, base_event(event_id=request_ref, engagement_id=authority_engagement.name, recorded_at=requested_at, actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="authority.requested", rationale=f"Request for {resolution_name} test.", payload={"request_id": request_id, "action_kind": "test-authority", "action_digest": action_digest, "lane_id": f"lane-{resolution_name}", "request_status": "pending_authority", "scope_hash": authority_scope, "environment_ref": None, "expires_at": expires}, session_id=f"session-{resolution_name}", operation_class="notebook"))
            append_event(authority_engagement, base_event(event_id=f"event-authority-resolution-{resolution_name}", engagement_id=authority_engagement.name, recorded_at=resolved_at, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale=f"Resolve request as {resolution_name}.", payload={"request_id": request_id, "request_event_ref": request_ref, "action_digest": action_digest, "resolution": resolution_name, "resolved_at": resolved_at}, entity_refs=[request_ref], session_id="session-operator-authority", operation_class="authority"))
        authority_state = reduce_engagement(authority_engagement); states_seen = {item["status"] for item in authority_state["authority_requests"].values()}
        checks.append(("digest-bound async authority is lane-local, non-retrospective, one-use, and state-complete", retrospective_blocked and exact_approved and reuse_blocked and {"approved", "rejected", "expired", "superseded"}.issubset(states_seen), str(authority_state["authority_requests"])))

        invalid = base_event(event_id="event-invalid", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:00Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Invalid direct confirmation must not append.", payload={"entity_id": "claim-1", "status": "confirmed", "review_ref": "review-invalid", "review_digest": "sha256:" + "0" * 64}, state_changes=[{"dimension": "claim", "entity_id": "claim-1", "previous": None, "current": "confirmed"}])
        invalid_caught = False
        before = (engagement / "events.jsonl").read_bytes()
        try:
            append_event(engagement, invalid)
        except RecordError as exc:
            invalid_caught = exc.code in {"invalid_state_transition", "record_reference_invalid"}
        checks.append(("invalid confirmation shortcut is rejected before append", invalid_caught and (engagement / "events.jsonl").read_bytes() == before, "invalid event changed ledger"))
        zero_cost = {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0}
        mismatch = base_event(event_id="event-mismatch", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:30Z", actor_role="operator", actor_id="operator-selftest", event_type="candidate.proposed", rationale="Payload/state entity mismatch must fail.", payload={"candidate_id": "candidate-a", "source_observation_ref": "event-source", "routing_review_ref": "event-route", "activation_strength": "strong", "card_ids": ["card-1"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-source", "event-route"], state_changes=[{"dimension": "search", "entity_id": "candidate-b", "previous": None, "current": "queued"}]); mismatch["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}
        mismatch_caught = False
        try:
            append_event(engagement, mismatch)
        except RecordError as exc:
            mismatch_caught = exc.code == "event_state_entity_mismatch"
        checks.append(("event type, payload entity, and state change are inseparable", mismatch_caught and (engagement / "events.jsonl").read_bytes() == before, "mismatched event appended"))

        observation = base_event(event_id="event-observation-c1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:31Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Bounded source observation.", payload={"entity_id": "observation-c1", "entity_type": "observation", "status": "recorded"})
        append_event(engagement, observation)
        routing = base_event(event_id="event-routing-c1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:32Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Signal independently routed to one card.", payload={"entity_id": "routing-c1", "source_observation_ref": "event-observation-c1", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "assessed"}, entity_refs=["event-observation-c1"])
        append_event(engagement, routing)
        negative_route = base_event(event_id="event-routing-negative", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:32Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Observed control appears to hold and becomes a positive-control candidate.", payload={"entity_id": "routing-negative", "source_observation_ref": "event-observation-c1", "activation_strength": "negative", "card_ids": ["card-control"], "status": "likely_held"}, entity_refs=["event-observation-c1"])
        append_event(engagement, negative_route)
        candidate = base_event(event_id="event-candidate-c1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:33Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Candidate is justified by the routed observation.", payload={"candidate_id": "candidate-c1", "source_observation_ref": "event-observation-c1", "routing_review_ref": "event-routing-c1", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-observation-c1", "event-routing-c1"], state_changes=[{"dimension": "search", "entity_id": "candidate-c1", "previous": None, "current": "queued"}]); candidate["ex_ante"] = {"probability": 0.6, "ordinal": "strong", "recorded_before_outcome": True}
        append_event(engagement, candidate)
        negative_candidate = json.loads(json.dumps(candidate)); negative_candidate["event_id"] = "event-candidate-negative"; negative_candidate["payload"]["candidate_id"] = "candidate-negative"; negative_candidate["payload"]["activation_strength"] = "negative"; negative_candidate["state_changes"][0]["entity_id"] = "candidate-negative"
        negative_blocked = False
        try:
            append_event(engagement, negative_candidate)
        except RecordError as exc:
            negative_blocked = exc.code == "negative_signal_not_candidate"
        checks.append(("negative routing signal remains a control candidate, never a research candidate", negative_blocked, "negative signal entered candidate queue"))
        selection = base_event(event_id="event-candidate-selected", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:34Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.selected", rationale="Highest bounded information gain.", payload={"candidate_id": "candidate-c1", "status": "selected", "reason": "highest bounded information gain"}, state_changes=[{"dimension": "search", "entity_id": "candidate-c1", "previous": "queued", "current": "selected"}])
        append_event(engagement, selection)
        hypothesis = base_event(event_id="event-hypothesis-h1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:35Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Bounded hypothesis derived from selected candidate.", payload={"hypothesis_id": "hypothesis-h1", "origin_type": "candidate", "origin_ref": "candidate-c1", "candidate_ref": "candidate-c1", "hypothesis_statement": "The local branch omits the expected check.", "suspected_invariant": "The guard should dominate the local state transition.", "trust_boundary": "local caller to guarded state", "attacker_path": ["entry", "branch", "state transition"], "impact_ceiling": "owned fixture only", "bounded_space": "One pinned branch and matched sibling.", "lens_ids": ["authorization"], "card_ids": ["card-selftest"], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "primary guard trace", "required": True}, {"evidence_type": "control", "description": "matched sibling trace", "required": True}], "decisive_falsifiers": ["matched sibling proves the guard is irrelevant"], "cost_estimate": zero_cost, "constraints": ["local only"], "next_experiment": "trace primary and sibling branches", "completion_criteria": ["primary trace", "matched negative control"], "status": "queued"}, entity_refs=["candidate-c1"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-h1", "previous": None, "current": "queued"}])
        append_event(engagement, hypothesis)
        for status, previous, suffix in (("selected", "queued", "selected"), ("running", "selected", "running")):
            change = base_event(event_id=f"event-hypothesis-{suffix}", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:36Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale=f"Hypothesis {status} under the bounded search plan.", payload={"hypothesis_id": "hypothesis-h1", "status": status, "reason": "bounded lifecycle", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": f"Hypothesis moved to {status} before execution.", "unresolved_questions": ["execution pending"], "next_route": "primary trace"}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-h1", "previous": previous, "current": status}])
            if status == "running": change["provenance"].update({"session_id": "session-origin-selftest", "model": "origin-model"})
            append_event(engagement, change)
        model_prior = base_event(event_id="event-prior-model", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:37Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="operator_prior.recorded", rationale="A model cannot mint operator authority.", payload={"prior_id": "prior-model", "prior_statement": "Unauthorized prior.", "strength": "strong", "reason": "invalid authority"})
        model_prior_blocked = False
        try:
            append_event(engagement, model_prior)
        except RecordError as exc:
            model_prior_blocked = exc.code == "operator_prior_actor_unauthorized"
        checks.append(("model cannot mint an operator prior", model_prior_blocked, "model prior appended"))
        prior = base_event(event_id="event-prior-p1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:38Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="Operator prior deepens search but proves no claim.", payload={"prior_id": "prior-p1", "prior_statement": "Inspect the sibling branch before declaring dry.", "strength": "strong", "reason": "operator source familiarity"}, entity_refs=["hypothesis-h1"])
        append_event(engagement, prior)
        search_state = reduce_engagement(engagement)
        checks.append(("candidate→selection→hypothesis lifecycle preserves separate search/claim/coverage state", search_state["candidates"]["candidate-c1"]["status"] == "selected" and search_state["hypotheses"]["hypothesis-h1"]["status"] == "running" and len(search_state["operator_priors"]) == 1 and len(search_state["control_candidates"]) == 1 and search_state["findings"] == {} and search_state["coverage"] == "active", str(search_state)))

        candidate_skip_case = root / "candidate-skip-accounting"; candidate_skip_case.mkdir(); candidate_skip_case.joinpath("scope.md").write_text(scope.replace("self-test", "candidate-skip-accounting"), encoding="utf-8"); initialize_engagement(candidate_skip_case, "2026-07-10T00:01:30Z")
        append_event(candidate_skip_case, base_event(event_id="event-skip-observation", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:31Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Candidate skip accounting observation.", payload={"entity_id": "observation-skip", "entity_type": "observation", "status": "recorded"}))
        append_event(candidate_skip_case, base_event(event_id="event-skip-routing", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:32Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Route one candidate for skip accounting.", payload={"entity_id": "routing-skip", "source_observation_ref": "event-skip-observation", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "assessed"}, entity_refs=["event-skip-observation"]))
        skip_candidate = base_event(event_id="event-skip-candidate", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:33Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Propose one candidate whose skip must stay accounted.", payload={"candidate_id": "candidate-skip", "source_observation_ref": "event-skip-observation", "routing_review_ref": "event-skip-routing", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-skip-observation", "event-skip-routing"], state_changes=[{"dimension": "search", "entity_id": "candidate-skip", "previous": None, "current": "queued"}]); skip_candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}; append_event(candidate_skip_case, skip_candidate)
        append_event(candidate_skip_case, base_event(event_id="event-skip-deferred", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:34Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.deferred", rationale="Defer the candidate for operator disposition.", payload={"candidate_id": "candidate-skip", "status": "deferred", "reason": "bounded prioritization"}, state_changes=[{"dimension": "search", "entity_id": "candidate-skip", "previous": "queued", "current": "deferred"}]))
        append_event(candidate_skip_case, base_event(event_id="event-skip-closed", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:35Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.skipped", rationale="Record the skip without erasing the lead.", payload={"candidate_id": "candidate-skip", "status": "closed", "reason": "bounded prioritization"}, state_changes=[{"dimension": "search", "entity_id": "candidate-skip", "previous": "deferred", "current": "closed"}]))
        skipped_candidate_state = reduce_engagement(candidate_skip_case)
        append_event(candidate_skip_case, base_event(event_id="event-skip-reopened", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:36Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.reopened", rationale="Reopen the exact candidate for explicit routing.", payload={"candidate_id": "candidate-skip", "status": "selected", "reason": "Reopen the exact candidate for explicit routing."}, state_changes=[{"dimension": "search", "entity_id": "candidate-skip", "previous": "closed", "current": "selected"}]))
        reopened_candidate_state = reduce_engagement(candidate_skip_case)
        routed_payload = json.loads(json.dumps(hypothesis["payload"])); routed_payload.update({"hypothesis_id": "hypothesis-from-skipped-candidate", "origin_ref": "candidate-skip", "candidate_ref": "candidate-skip", "status": "queued"})
        append_event(candidate_skip_case, base_event(event_id="event-skip-hypothesis", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:37Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Route the retained candidate into explicit work.", payload=routed_payload, entity_refs=["candidate-skip"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-from-skipped-candidate", "previous": None, "current": "queued"}]))
        routed_candidate_state = reduce_engagement(candidate_skip_case)
        candidate_debt = lambda value: [item for item in value["work_queue"] if item["class"] == "candidate_undisposed" and item["entity"]["id"] == "candidate-skip"]
        skipped_candidate_action = decorate_work_queue_item(
            candidate_debt(skipped_candidate_state)[0],
            skipped_candidate_state,
            candidate_skip_case,
        )["next_action"]
        reopened_candidate_action = decorate_work_queue_item(
            candidate_debt(reopened_candidate_state)[0],
            reopened_candidate_state,
            candidate_skip_case,
        )["next_action"]
        checks.append(("a skipped candidate remains blocking through close and reopen until an explicit candidate-origin hypothesis accounts for it", len(candidate_debt(skipped_candidate_state)) == 1 and len(candidate_debt(reopened_candidate_state)) == 1 and not candidate_debt(routed_candidate_state), str((skipped_candidate_state["work_queue"], reopened_candidate_state["work_queue"], routed_candidate_state["work_queue"]))))
        checks.append(("the feedback loop reopens a closed candidate before offering hypothesis creation, so free-text skip cannot bypass lifecycle accounting", skipped_candidate_action["action_id"] == "reopen_candidate" and skipped_candidate_action["effect"] == "advances_item" and reopened_candidate_action["action_id"] == "create_candidate_hypothesis" and reopened_candidate_action["effect"] == "closes_item", str((skipped_candidate_action, reopened_candidate_action))))

        mediation_case = root / "queue-action-broker-mediation"; shutil.copytree(engagement, mediation_case)
        # Attempts are admissible only against an environment that was active at
        # their immutable recorded time.  Keep this action-contract fixture
        # self-contained instead of relying on the main lifecycle's later
        # preflight setup.
        mediation_package = root / "mediation-package-fixture.bin"; mediation_package.write_bytes(b"broker mediation fixture\n")
        mediation_runtime = Path(sys.executable).resolve()
        collect_preflight(mediation_case, preflight_id="preflight-broker-mediation", mode="package", target=mediation_package, expected_identity=sha256_file(mediation_package), runtime=mediation_runtime, reproduction_argv=[str(mediation_runtime), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:01:38.500000Z", operator_redaction_attested=True, endpoint_identity="local", account_role="owner")
        mediation_broker_id, mediation_broker_session = _local_identity("broker")
        def execute_emitted_file_action(action: dict[str, Any], proposal_path: Path) -> subprocess.CompletedProcess[str]:
            argv = list(action["local_invocation"]["argv"])
            argv[argv.index("--file") + 1] = str(proposal_path)
            return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

        mediation_state = reduce_engagement(mediation_case)
        mediation_control_item = next(item for item in mediation_state["work_queue"] if item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative")
        mediation_create_action = decorate_work_queue_item(mediation_control_item, mediation_state, mediation_case)["next_action"]
        mediation_hypothesis = base_event(event_id="event-control-hypothesis-created", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:39Z", actor_role="broker", actor_id=mediation_broker_id, event_type="hypothesis.created", rationale="Broker records the orchestrator's bounded matched-control hypothesis.", payload={"hypothesis_id": "hypothesis-control", "origin_type": "reviewer_challenge", "origin_ref": "event-routing-negative", "hypothesis_statement": "The likely-held route should remain held under one matched bounded control.", "suspected_invariant": "The negative route's guard should reject the matched primary condition.", "trust_boundary": "owned fixture input to guarded branch", "attacker_path": ["owned fixture", "guarded branch"], "impact_ceiling": "owned fixture only", "bounded_space": "One matched primary and one negative control.", "lens_ids": ["authorization"], "card_ids": ["card-control"], "expected_confirming_evidence": [{"evidence_type": "control", "description": "matched control remains held", "required": True}], "decisive_falsifiers": ["matched control exhibits the primary signal"], "cost_estimate": zero_cost, "constraints": ["local only"], "next_experiment": "record matched primary then negative control", "completion_criteria": ["primary and linked control recorded"], "status": "queued"}, entity_refs=["event-routing-negative"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-control", "previous": None, "current": "queued"}], session_id=mediation_broker_session, operation_class="notebook")
        mediation_create_path = root / "mediation-control-hypothesis.json"; mediation_create_path.write_bytes(canonical_json_bytes(mediation_hypothesis)); mediation_create_cli = execute_emitted_file_action(mediation_create_action, mediation_create_path)

        mediation_stage_results = []
        for status, previous, recorded_at in (("selected", "queued", "2026-07-10T00:01:40Z"), ("running", "selected", "2026-07-10T00:01:41Z")):
            mediation_state = reduce_engagement(mediation_case)
            mediation_control_item = next(item for item in mediation_state["work_queue"] if item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative")
            mediation_stage_action = decorate_work_queue_item(mediation_control_item, mediation_state, mediation_case)["next_action"]
            mediation_transition = base_event(event_id=f"event-control-hypothesis-{status}", engagement_id=engagement.name, recorded_at=recorded_at, actor_role="broker", actor_id=mediation_broker_id, event_type="hypothesis.status_changed", rationale=f"Broker records bounded control hypothesis {status}.", payload={"hypothesis_id": "hypothesis-control", "status": status, "reason": "bounded control progression", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "Advance only the current matched-control stage.", "unresolved_questions": [], "next_route": "matched control"}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-control", "previous": previous, "current": status}], session_id=mediation_broker_session, operation_class="notebook")
            mediation_transition_path = root / f"mediation-control-{status}.json"; mediation_transition_path.write_bytes(canonical_json_bytes(mediation_transition)); mediation_stage_results.append(execute_emitted_file_action(mediation_stage_action, mediation_transition_path))

        def mediated_control_attempt(attempt_id: str, recorded_at: str, kind: str, assessment: str, control_of: list[str]) -> dict[str, Any]:
            return {"schema_version": 2, "attempt_id": attempt_id, "engagement_id": engagement.name, "recorded_at": recorded_at, "actor": {"role": "broker", "id": mediation_broker_id}, "operation_class": "notebook", "provenance": {"actor": {"role": "broker", "id": mediation_broker_id}, "provider": "selftest", "model": "broker-recorder", "prompt_version": "queue-action-selftest", "tool_versions": ["source-inspection-v1"], "card_versions": ["card-control"], "session_id": mediation_broker_session}, "scope_hash": mediation_state["scope_hash"], "environment_ref": mediation_state["active_environment_ref"], "escalation_confirmation_event_ref": None, "hypothesis_ref": "hypothesis-control", "experiment_ref": "event-routing-negative", "surface": "owned local fixture", "action_summary": "Record one bounded matched-control observation.", "redaction_attestation": True, "observation": {"source": "broker", "statement": "Matched control observation recorded by the broker from the bounded hunter result."}, "evidence_refs": [], "kind": kind, "control_of": control_of, "assessment": assessment, "contamination": {"status": "none_observed", "sources": [], "note": ""}, "cost": {**zero_cost, "wall_seconds": 1, "tool_seconds": 1}}

        mediation_state = reduce_engagement(mediation_case)
        mediation_control_item = next(item for item in mediation_state["work_queue"] if item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative")
        mediation_primary_action = decorate_work_queue_item(mediation_control_item, mediation_state, mediation_case)["next_action"]
        mediation_primary = mediated_control_attempt("attempt-control-primary", "2026-07-10T00:01:42Z", "primary", "suspected_signal", []); mediation_primary_path = root / "mediation-control-primary.json"; mediation_primary_path.write_bytes(canonical_json_bytes(mediation_primary)); mediation_primary_cli = execute_emitted_file_action(mediation_primary_action, mediation_primary_path)
        mediation_state = reduce_engagement(mediation_case)
        mediation_control_item = next(item for item in mediation_state["work_queue"] if item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative")
        mediation_control_action = decorate_work_queue_item(mediation_control_item, mediation_state, mediation_case)["next_action"]
        mediation_control = mediated_control_attempt("attempt-control-negative", "2026-07-10T00:01:43Z", "negative_control", "held", ["attempt-control-primary"]); mediation_control_path = root / "mediation-control-negative.json"; mediation_control_path.write_bytes(canonical_json_bytes(mediation_control)); mediation_control_cli = execute_emitted_file_action(mediation_control_action, mediation_control_path)
        mediation_final_state = reduce_engagement(mediation_case)
        checks.append(("advertised staged control actions execute under broker mediation while retaining orchestrator and hunter cognitive principals", mediation_create_cli.returncode == 0 and all(result.returncode == 0 for result in mediation_stage_results) and mediation_primary_cli.returncode == 0 and mediation_control_cli.returncode == 0 and mediation_create_action["principal"] == "orchestrator" and mediation_create_action["execution_principal"] == "broker" and mediation_primary_action["principal"] == "hunter" and mediation_primary_action["execution_principal"] == "broker" and mediation_control_action["principal"] == "hunter" and not any(item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative" for item in mediation_final_state["work_queue"]), str({"create": mediation_create_cli.stdout + mediation_create_cli.stderr, "stages": [(item.returncode, item.stdout, item.stderr) for item in mediation_stage_results], "primary": mediation_primary_cli.stdout + mediation_primary_cli.stderr, "control": mediation_control_cli.stdout + mediation_control_cli.stderr, "queue": mediation_final_state["work_queue"]})))

        blocked = base_event(event_id="event-blocked", engagement_id=engagement.name, recorded_at="2026-07-10T00:02:00Z", actor_role="operator", actor_id="operator-selftest", event_type="engagement.blocked", rationale="Self-test blocker.", payload={"entity_id": engagement.name, "status": "blocked", "reason": "fixture"}, state_changes=[{"dimension": "engagement", "entity_id": engagement.name, "previous": "active", "current": "blocked"}, {"dimension": "coverage", "entity_id": engagement.name, "previous": "active", "current": "blocked"}])
        try:
            append_event(engagement, blocked)
            ordinary_block_code = None
        except RecordError as exc:
            ordinary_block_code = exc.code
        pre_override_state = reduce_engagement(engagement)
        override_projection = project_current_terminal_work_state(
            pre_override_state,
            read_ledger(engagement, "attempt"),
            coverage="blocked",
        )
        override_blockers = blocking_work_identities(override_projection)
        blocked_override_reason = "Self-test blocker with exact unfinished work recorded."
        blocked_override_time = "2026-07-10T00:02:00Z"
        blocked_override_session = _local_identity("operator")[1]
        blocked_override_payload = {
            "entity_id": engagement.name,
            "terminal_kind": "engagement",
            "status": "blocked",
            "reason": blocked_override_reason,
            "operator_id": "operator-selftest",
            "scope_hash": pre_override_state["scope_hash"],
            "blocking_items": override_blockers,
            "blocking_queue_digest": sha256_bytes(canonical_json_bytes(override_blockers)),
            **attempt_ledger_context(read_ledger(engagement, "attempt")),
        }
        blocked_override_changes = [
            {"dimension": "engagement", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
            {"dimension": "coverage", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
        ]
        blocked_override_action = ending_override_action(
            engagement_id=engagement.name,
            recorded_at=blocked_override_time,
            actor={"role": "operator", "id": "operator-selftest"},
            payload=blocked_override_payload,
            entity_refs=[],
            evidence_refs=[],
            state_changes=blocked_override_changes,
            session_id=blocked_override_session,
        )
        blocked_override_action_digest = sha256_bytes(canonical_json_bytes(blocked_override_action))
        blocked_override_challenge = operator_challenge_bytes(
            engagement_id=engagement.name,
            scope_hash=pre_override_state["scope_hash"],
            ledger_hash=read_ledger(engagement, "event")[-1]["record_hash"],
            operation=f"override-ending:{blocked_override_action_digest}",
            operator_id="operator-selftest",
        )
        forged_payload = copy.deepcopy(blocked_override_payload)
        forged_payload["operator_signature"] = {
            "challenge_digest": sha256_bytes(blocked_override_challenge),
            "signature_base64": base64.b64encode(b"forged-signature").decode("ascii"),
            "allowed_signers_base64": base64.b64encode(allowed_signers_path.read_bytes()).decode("ascii"),
            "signer_fingerprint": "sha256:" + "0" * 64,
        }
        forged_override = base_event(
            event_id=f"event-ending-override-{blocked_override_action_digest[-12:]}",
            engagement_id=engagement.name,
            recorded_at=blocked_override_time,
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.ending_overridden",
            rationale=blocked_override_reason,
            payload=forged_payload,
            state_changes=blocked_override_changes,
            session_id=blocked_override_session,
            operation_class="authority",
        )
        before_forged_override = (engagement / "events.jsonl").read_bytes()
        try:
            append_event(engagement, forged_override)
            forged_override_code = None
        except RecordError as exc:
            forged_override_code = exc.code
        forged_override_left_ledger_unchanged = (
            engagement / "events.jsonl"
        ).read_bytes() == before_forged_override
        blocked_override_challenge_path = root / "blocked-ending-override-challenge.json"
        blocked_override_challenge_path.write_bytes(blocked_override_challenge)
        subprocess.run(
            [
                "/usr/bin/ssh-keygen", "-q", "-Y", "sign",
                "-f", str(reviewer_key),
                "-n", "llm-redteam-harness-operator-v1",
                str(blocked_override_challenge_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        blocked_override_argv = [
            sys.executable,
            str(Path(__file__).resolve()),
            "override-ending",
            "--engagement", str(engagement),
            "--terminal-kind", "engagement",
            "--status", "blocked",
            "--operator-id", "operator-selftest",
            "--session-id", blocked_override_session,
            "--recorded-at", blocked_override_time,
            "--reason", blocked_override_reason,
        ]
        blocked_override_env = {
            **os.environ,
            "HARNESS_OPERATOR_SIGNATURE_FILE": str(blocked_override_challenge_path) + ".sig",
            "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers_path),
        }
        blocked_override_cli = subprocess.run(
            blocked_override_argv,
            env=blocked_override_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        reduced_once = reduce_engagement(engagement)
        reduced_twice = reduce_engagement(engagement)
        override_retry_case = root / "ending-override-retry"; shutil.copytree(engagement, override_retry_case)
        override_retry_argv = list(blocked_override_argv)
        override_retry_argv[override_retry_argv.index(str(engagement))] = str(override_retry_case)
        exact_blocked_override_retry = subprocess.run(override_retry_argv, env=blocked_override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try:
            exact_blocked_override_retry_payload = json.loads(exact_blocked_override_retry.stdout)
        except json.JSONDecodeError:
            exact_blocked_override_retry_payload = {}
        changed_blocked_override_retry = subprocess.run([*override_retry_argv, "--coverage-review-ref", "review-changed-after-signing"], env=blocked_override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        override_retry_count = len(read_ledger(override_retry_case, "event"))
        _append_kernel_event(override_retry_case, base_event(
            event_id="event-ending-override-reopened",
            engagement_id=engagement.name,
            recorded_at="2026-07-10T00:02:00.500000Z",
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.reopened",
            rationale="Reopen the synthetic fixture to prove an old override cannot self-apply again.",
            payload={"entity_id": engagement.name, "status": "active", "operator_id": "operator-selftest"},
            state_changes=[
                {"dimension": "engagement", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
                {"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
            ],
            operation_class="authority",
        ))
        reopened_blocked_override_retry = subprocess.run(override_retry_argv, env=blocked_override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        reopened_override_state = reduce_engagement(override_retry_case)
        checks.append(("reducer is byte-deterministic", canonical_json_bytes(reduced_once) == canonical_json_bytes(reduced_twice), "same ledgers reduced differently"))
        checks.append(("coverage cannot leave active with blocking work unless the reducer verifies an exact operator-signed first-class override", ordinary_block_code == "coverage_terminal_work_remaining" and forged_override_code == "operator_signature_invalid" and forged_override_left_ledger_unchanged and blocked_override_cli.returncode == 0 and reduced_once["coverage"] == "blocked" and reduced_once["active_blockers"] and reduced_once["ending_overrides"][-1]["blocking_items"] == override_blockers, str({"ordinary": ordinary_block_code, "forged": forged_override_code, "forged_ledger_unchanged": forged_override_left_ledger_unchanged, "cli": blocked_override_cli.stdout + blocked_override_cli.stderr, "state": reduced_once})))
        checks.append((
            "ending override idempotency accepts only the exact unchanged tail and cannot return false success after changed inputs or reopen",
            exact_blocked_override_retry.returncode == 0
            and exact_blocked_override_retry_payload.get("override") == reduced_once["ending_overrides"][-1]
            and "allowed_signers_base64" not in exact_blocked_override_retry.stdout
            and "signature_base64" not in exact_blocked_override_retry.stdout
            and changed_blocked_override_retry.returncode != 0
            and override_retry_count == len(read_ledger(override_retry_case, "event")) - 1
            and reopened_blocked_override_retry.returncode != 0
            and reopened_override_state["coverage"] == "active"
            and not reopened_override_state["active_blockers"]
            and len(reopened_override_state["ending_overrides"]) == len(reduced_once["ending_overrides"]),
            str({"exact": exact_blocked_override_retry.stdout + exact_blocked_override_retry.stderr, "changed": changed_blocked_override_retry.stdout + changed_blocked_override_retry.stderr, "reopened": reopened_blocked_override_retry.stdout + reopened_blocked_override_retry.stderr, "state": reopened_override_state}),
        ))

        secret_signers_path = root / "allowed-signers-with-secret-comment"
        secret_signers_path.write_bytes(allowed_signers_path.read_bytes() + b"# password=synthetic-secret-value\n")
        secret_signers_digest = sha256_file(secret_signers_path)
        secret_signers_case = root / "secret-signers-override"
        secret_signers_case.mkdir()
        secret_signers_case.joinpath("scope.md").write_text(
            scope.replace(allowed_signers_digest, secret_signers_digest),
            encoding="utf-8",
        )
        initialize_engagement(secret_signers_case, "2026-07-10T00:00:00Z")
        secret_prior = base_event(
            event_id="event-secret-signers-prior",
            engagement_id=secret_signers_case.name,
            recorded_at="2026-07-10T00:00:01Z",
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="operator_prior.recorded",
            rationale="Seed one bounded hypothesis so an ending override is required.",
            payload={"prior_id": "prior-secret-signers", "prior_statement": "The bounded fixture branch requires adjudication.", "strength": "strong", "reason": "secret-signers self-test setup"},
        )
        append_event(secret_signers_case, secret_prior)
        secret_hypothesis_payload = json.loads(json.dumps(hypothesis["payload"]))
        secret_hypothesis_payload.update({"hypothesis_id": "hypothesis-secret-signers", "origin_type": "operator_prior", "origin_ref": secret_prior["event_id"], "status": "queued"})
        secret_hypothesis_payload.pop("candidate_ref", None)
        append_event(secret_signers_case, base_event(
            event_id="event-secret-signers-hypothesis",
            engagement_id=secret_signers_case.name,
            recorded_at="2026-07-10T00:00:02Z",
            actor_role="orchestrator",
            actor_id="orchestrator-selftest",
            event_type="hypothesis.created",
            rationale="Create one bounded blocking hypothesis for the secret-signers regression.",
            payload=secret_hypothesis_payload,
            entity_refs=[secret_prior["event_id"]],
            state_changes=[{"dimension": "search", "entity_id": "hypothesis-secret-signers", "previous": None, "current": "queued"}],
        ))
        secret_signers_state = reduce_engagement(secret_signers_case)
        secret_signers_attempts = read_ledger(secret_signers_case, "attempt")
        secret_signers_blockers = blocking_work_identities(project_current_terminal_work_state(secret_signers_state, secret_signers_attempts, coverage="blocked"))
        secret_signers_time = "2026-07-10T00:00:03Z"
        secret_signers_reason = "Operator accepts the exact bounded residual queue for this redaction regression."
        secret_signers_session = _local_identity("operator")[1]
        secret_signers_payload = {
            "entity_id": secret_signers_case.name,
            "terminal_kind": "engagement",
            "status": "blocked",
            "reason": secret_signers_reason,
            "operator_id": "operator-selftest",
            "scope_hash": secret_signers_state["scope_hash"],
            "blocking_items": secret_signers_blockers,
            "blocking_queue_digest": sha256_bytes(canonical_json_bytes(secret_signers_blockers)),
            **attempt_ledger_context(secret_signers_attempts),
        }
        secret_signers_action = ending_override_action(
            engagement_id=secret_signers_case.name,
            recorded_at=secret_signers_time,
            actor={"role": "operator", "id": "operator-selftest"},
            payload=secret_signers_payload,
            entity_refs=[],
            evidence_refs=[],
            state_changes=[
                {"dimension": "engagement", "entity_id": secret_signers_case.name, "previous": "active", "current": "blocked"},
                {"dimension": "coverage", "entity_id": secret_signers_case.name, "previous": "active", "current": "blocked"},
            ],
            session_id=secret_signers_session,
        )
        secret_signers_action_digest = sha256_bytes(canonical_json_bytes(secret_signers_action))
        secret_signers_challenge = operator_challenge_bytes(
            engagement_id=secret_signers_case.name,
            scope_hash=secret_signers_state["scope_hash"],
            ledger_hash=read_ledger(secret_signers_case, "event")[-1]["record_hash"],
            operation=f"override-ending:{secret_signers_action_digest}",
            operator_id="operator-selftest",
        )
        secret_signers_challenge_path = root / "secret-signers-override-challenge.json"
        secret_signers_challenge_path.write_bytes(secret_signers_challenge)
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(secret_signers_challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        secret_signers_before = (secret_signers_case / "events.jsonl").read_bytes()
        secret_signers_cli = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "override-ending", "--engagement", str(secret_signers_case), "--terminal-kind", "engagement", "--status", "blocked", "--operator-id", "operator-selftest", "--session-id", secret_signers_session, "--recorded-at", secret_signers_time, "--reason", secret_signers_reason],
            env={**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(secret_signers_challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(secret_signers_path)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        try:
            secret_signers_error = json.loads(secret_signers_cli.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError):
            secret_signers_error = None
        secret_signers_embedded_payload = copy.deepcopy(secret_signers_payload)
        secret_signers_embedded_payload["operator_signature"] = encode_operator_signature_proof(
            challenge_bytes=secret_signers_challenge,
            signature_bytes=Path(str(secret_signers_challenge_path) + ".sig").read_bytes(),
            allowed_signers_bytes=secret_signers_path.read_bytes(),
            signer_fingerprint=reduced_once["ending_overrides"][-1]["operator_signer_fingerprint"],
        )
        secret_signers_embedded_event = base_event(
            event_id=f"event-ending-override-{secret_signers_action_digest[-12:]}",
            engagement_id=secret_signers_case.name,
            recorded_at=secret_signers_time,
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.ending_overridden",
            rationale=secret_signers_reason,
            payload=secret_signers_embedded_payload,
            state_changes=[
                {"dimension": "engagement", "entity_id": secret_signers_case.name, "previous": "active", "current": "blocked"},
                {"dimension": "coverage", "entity_id": secret_signers_case.name, "previous": "active", "current": "blocked"},
            ],
            session_id=secret_signers_session,
            operation_class="authority",
        )
        try:
            _append_kernel_event(secret_signers_case, secret_signers_embedded_event)
            secret_signers_replay_error = None
        except RecordError as exc:
            secret_signers_replay_error = exc.code
        checks.append((
            "operator ending override construction and replay refuse secret-shaped raw signer material",
            secret_signers_blockers
            and secret_signers_cli.returncode != 0
            and secret_signers_error == "operator_signature_invalid"
            and secret_signers_replay_error == "operator_signature_invalid"
            and (secret_signers_case / "events.jsonl").read_bytes() == secret_signers_before
            and "synthetic-secret-value" not in secret_signers_cli.stdout + secret_signers_cli.stderr,
            secret_signers_cli.stdout + secret_signers_cli.stderr + str(secret_signers_replay_error),
        ))

        def run_signed_queue_commands(target: Path, command_name: str, previous_status: str, status: str, recorded_at: str, reason: str, *, concurrency: int = 1) -> list[subprocess.CompletedProcess[str]]:
            session_id = _local_identity("operator")[1]
            target_state = reduce_engagement(target); target_events = read_ledger(target, "event")
            action = {"command": command_name, "entity_id": target_state["engagement_id"], "previous_status": previous_status, "reason": reason, "recorded_at": recorded_at, "session_id": session_id, "status": status}
            action_digest = sha256_bytes(canonical_json_bytes(action))
            challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1", "engagement_id": target_state["engagement_id"], "scope_hash": target_state["scope_hash"], "ledger_hash": target_events[-1]["record_hash"], "operation": f"{command_name}:{action_digest}", "operator_id": "operator-selftest"}
            challenge_path = root / f"{command_name}-challenge.json"; challenge_path.write_bytes(canonical_json_bytes(challenge))
            subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            command_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers_path)}
            argv = [sys.executable, str(Path(__file__).resolve()), command_name, "--engagement", str(target), "--operator-id", "operator-selftest", "--session-id", session_id, "--recorded-at", recorded_at, "--reason", reason]
            processes = [subprocess.Popen(argv, env=command_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(concurrency)]
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                results.append(subprocess.CompletedProcess(argv, process.returncode, stdout, stderr))
            return results

        operator_control = root / "operator-control"; shutil.copytree(engagement, operator_control)
        stop_reason = "Operator deliberately parks this bounded run for an external scheduling decision."
        stop_clis = run_signed_queue_commands(operator_control, "operator-stop", "active", "parked", "2026-07-10T00:02:00.100000Z", stop_reason, concurrency=4)
        stopped_state = reduce_engagement(operator_control); stopped_events = read_ledger(operator_control, "event"); stopped_progress = (operator_control / "progress.md").read_text(encoding="utf-8")
        stopped_control = stopped_state.get("queue_control", {})
        stop_detail = "".join(result.stdout + result.stderr for result in stop_clis) + str(stopped_control)
        checks.append(("concurrent signed operator-stop retries all succeed and append one typed reason without pretending the run exhausted", all(result.returncode == 0 for result in stop_clis) and sum(event["event_type"] == "operator_stop.recorded" for event in stopped_events) == 1 and stopped_control.get("status") == "parked" and stopped_control.get("last_stop", {}).get("reason") == stop_reason and stopped_events[-1]["event_type"] == "operator_stop.recorded" and stopped_state["coverage"] == "blocked" and "Work queue: `parked`" in stopped_progress and stop_reason in stopped_progress, stop_detail))

        resume_reason = "The operator's scheduling constraint is resolved."
        resume_cli = run_signed_queue_commands(operator_control, "operator-resume", "parked", "active", "2026-07-10T00:02:00.200000Z", resume_reason)[0]
        resumed_state = reduce_engagement(operator_control); resumed_events = read_ledger(operator_control, "event"); resumed_control = resumed_state.get("queue_control", {})
        checks.append(("signed operator resume makes the parked queue runnable while preserving the stop/resume record", resume_cli.returncode == 0 and resumed_control.get("status") == "active" and resumed_control.get("last_stop", {}).get("reason") == stop_reason and resumed_control.get("last_resume", {}).get("reason") == resume_reason and [event["event_type"] for event in resumed_events[-2:]] == ["operator_stop.recorded", "operator_resume.recorded"] and resumed_state["coverage"] == "blocked", resume_cli.stdout + resume_cli.stderr + str(resumed_control)))

        forged_control = root / "forged-operator-control"; shutil.copytree(engagement, forged_control); forged_before = (forged_control / "events.jsonl").read_bytes()
        forged_stop = base_event(event_id="event-forged-operator-stop", engagement_id=engagement.name, recorded_at="2026-07-10T00:02:00.100000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="operator_stop.recorded", rationale="An orchestrator cannot manufacture an operator stop.", payload={"entity_id": engagement.name, "status": "parked", "reason": "An orchestrator cannot manufacture an operator stop.", "operator_id": "operator-selftest"}, state_changes=[{"dimension": "queue", "entity_id": engagement.name, "previous": "active", "current": "parked"}], session_id="session-orchestrator-selftest", operation_class="authority")
        forged_stop_blocked = False
        try: append_event(forged_control, forged_stop)
        except RecordError as exc: forged_stop_blocked = exc.code in {"actor_capability_invalid", "operator_queue_control_invalid"}
        checks.append(("non-operator principals cannot manufacture the deliberate-stop record", forged_stop_blocked and (forged_control / "events.jsonl").read_bytes() == forged_before and reduce_engagement(forged_control)["queue_control"]["status"] == "active", "forged operator stop changed the ledger"))

        budget_documents = test_corpus_documents(
            row_count=5,
            frozen_at="2026-07-09T23:59:00Z",
        )
        budget_base = root / "budget-base"; budget_base.mkdir(); budget_base.joinpath("scope.md").write_text(scope_with_corpus_pin(scope.replace("self-test", "budget-base"), budget_documents[1]), encoding="utf-8"); initialize_engagement(budget_base, "2026-07-10T00:00:00Z")
        budget_prior = base_event(event_id="event-budget-prior", engagement_id=budget_base.name, recorded_at="2026-07-10T00:00:01Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="Seed one already-disposed hypothesis for the reopening control.", payload={"prior_id": "prior-budget", "prior_statement": "The bounded fixture branch was already resolved.", "strength": "strong", "reason": "self-test setup"})
        append_event(budget_base, budget_prior)
        budget_hypothesis_payload = json.loads(json.dumps(hypothesis["payload"])); budget_hypothesis_payload.update({"hypothesis_id": "hypothesis-budget", "origin_type": "operator_prior", "origin_ref": "event-budget-prior", "status": "queued"}); budget_hypothesis_payload.pop("candidate_ref", None)
        append_event(budget_base, base_event(event_id="event-budget-hypothesis", engagement_id=budget_base.name, recorded_at="2026-07-10T00:00:02Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Create the bounded reopening-control hypothesis.", payload=budget_hypothesis_payload, entity_refs=["event-budget-prior"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": None, "current": "queued"}]))
        append_event(budget_base, base_event(event_id="event-budget-hypothesis-closed", engagement_id=budget_base.name, recorded_at="2026-07-10T00:00:03Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Dispose the bounded setup hypothesis before terminal coverage.", payload={"hypothesis_id": "hypothesis-budget", "status": "closed", "reason": "setup disposed", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The synthetic setup branch is already disposed.", "unresolved_questions": [], "next_route": None}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": "queued", "current": "closed"}]))
        budget_manifest_ref, budget_tsv_ref = register_test_corpus(
            budget_base,
            row_count=5,
            documents=budget_documents,
        )
        budget_bounded = root / "budget-bounded"; shutil.copytree(budget_base, budget_bounded); budget_broker_id, budget_broker_session = _local_identity("broker")
        budget_event = base_event(event_id="event-budget-bounded", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:01Z", actor_role="broker", actor_id=budget_broker_id, event_type="coverage.status_changed", rationale="The configured ceiling fired after disposing three queue items against a frozen five-row corpus denominator.", payload={"entity_id": budget_base.name, "status": "budget_bounded", "disposed_count": 3, "enumerated_count": 5, "corpus_enumeration_ref": budget_manifest_ref}, evidence_refs=[budget_manifest_ref, budget_tsv_ref], state_changes=[{"dimension": "coverage", "entity_id": budget_base.name, "previous": "active", "current": "budget_bounded"}], session_id=budget_broker_session, operation_class="notebook")
        budget_state = None; budget_detail = ""
        try:
            _append_kernel_event(budget_bounded, budget_event)
            budget_state = reduce_engagement(budget_bounded); budget_progress = (budget_bounded / "progress.md").read_text(encoding="utf-8")
            budget_reached = budget_state["coverage"] == "budget_bounded" and budget_state["coverage_counts"]["enumerated_count"] == 5 and budget_state["coverage_counts"]["corpus_enumeration_ref"] == budget_manifest_ref and "Coverage: `budget_bounded`" in budget_progress and "Frozen corpus denominator: `5` package-entrypoint rows" in budget_progress and "Declared disposed rows (not mechanically cross-checked): `3`" in budget_progress
            budget_detail = str(budget_state)
        except RecordError as exc:
            budget_reached = False; budget_detail = exc.code
        checks.append(("budget-bounded coverage binds its enumerated count to registered frozen corpus evidence without presenting mixed units as a fraction", budget_reached, budget_detail))
        checks.append(("run exhaustion does not fabricate an operator stop or park the queue", budget_state is not None and budget_state["queue_control"] == {"status": "active", "last_stop": None, "last_resume": None}, str((budget_state or {}).get("queue_control"))))

        generic_budget = root / "budget-generic-public"; shutil.copytree(budget_base, generic_budget); budget_proposal_path = root / "budget-bounded-event.json"; budget_proposal_path.write_bytes(canonical_json_bytes(budget_event)); budget_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(generic_budget), "--file", str(budget_proposal_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: generic_budget_code = json.loads(budget_cli.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError): generic_budget_code = None
        checks.append(("generic model-reachable append cannot set the outer driver's budget boundary", budget_cli.returncode != 0 and generic_budget_code == "external_driver_budget_boundary_required" and reduce_engagement(generic_budget)["coverage"] == "active", budget_cli.stdout + budget_cli.stderr))

        missing_count_refusals = []
        for missing_field in ("disposed_count", "enumerated_count"):
            missing_counts = root / f"budget-missing-{missing_field}"; shutil.copytree(budget_base, missing_counts)
            invalid_budget = json.loads(json.dumps(budget_event)); invalid_budget["event_id"] = f"event-budget-missing-{missing_field}"; invalid_budget["payload"].pop(missing_field)
            try: _append_kernel_event(missing_counts, invalid_budget); invalid_code = None
            except RecordError as exc: invalid_code = exc.code
            missing_count_refusals.append(invalid_code is not None and reduce_engagement(missing_counts)["coverage"] == "active")
        checks.append(("budget-bounded coverage refuses either missing count", all(missing_count_refusals), str(missing_count_refusals)))

        mismatched_denominator = root / "budget-mismatched-denominator"; shutil.copytree(budget_base, mismatched_denominator); mismatched_budget = json.loads(json.dumps(budget_event)); mismatched_budget["event_id"] = "event-budget-mismatched-denominator"; mismatched_budget["payload"].update({"disposed_count": 1, "enumerated_count": 1})
        try: _append_kernel_event(mismatched_denominator, mismatched_budget); mismatched_code = None
        except RecordError as exc: mismatched_code = exc.code
        checks.append(("a self-declared 1/1 budget boundary is refused against the registered five-row frozen denominator", mismatched_code == "coverage_enumerated_count_mismatch" and reduce_engagement(mismatched_denominator)["coverage"] == "active", str(mismatched_code)))

        incoherent_counts = root / "budget-incoherent-counts"; shutil.copytree(budget_base, incoherent_counts); incoherent_budget = json.loads(json.dumps(budget_event)); incoherent_budget["event_id"] = "event-budget-incoherent-counts"; incoherent_budget["payload"].update({"disposed_count": 6, "enumerated_count": 5})
        try: _append_kernel_event(incoherent_counts, incoherent_budget); incoherent_code = None
        except RecordError as exc: incoherent_code = exc.code
        checks.append(("budget-bounded disposed count cannot exceed its enumerated denominator", incoherent_code == "budget_bounded_counts_invalid" and reduce_engagement(incoherent_counts)["coverage"] == "active", str(incoherent_code)))

        active_budget_documents = test_corpus_documents(
            row_count=1,
            frozen_at="2026-07-10T00:01:59Z",
        )
        active_budget = root / "budget-active"; active_budget.mkdir(); active_budget.joinpath("scope.md").write_text(scope_with_corpus_pin(scope.replace("self-test", "budget-active"), active_budget_documents[1]), encoding="utf-8"); initialize_engagement(active_budget, "2026-07-10T00:02:00Z"); active_manifest_ref, active_tsv_ref = register_test_corpus(active_budget, row_count=1, documents=active_budget_documents); active_event = json.loads(json.dumps(budget_event)); active_event["event_id"] = "event-budget-from-active"; active_event["engagement_id"] = active_budget.name; active_event["payload"].update({"entity_id": active_budget.name, "disposed_count": 0, "enumerated_count": 1, "corpus_enumeration_ref": active_manifest_ref}); active_event["evidence_refs"] = [active_manifest_ref, active_tsv_ref]; active_event["state_changes"] = [{"dimension": "coverage", "entity_id": active_budget.name, "previous": "active", "current": "budget_bounded"}]
        try: _append_kernel_event(active_budget, active_event); active_code = None
        except RecordError as exc: active_code = exc.code
        checks.append(("active coverage can end budget-bounded only against its registered frozen denominator", active_code is None and reduce_engagement(active_budget)["coverage_counts"]["enumerated_count"] == 1, str(active_code)))

        identity_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "runtime-identity", "--role", "orchestrator"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: orchestrator_identity = json.loads(identity_cli.stdout)
        except json.JSONDecodeError: orchestrator_identity = {"actor_id": "unavailable", "session_id": "unavailable"}
        orchestrator_id, orchestrator_session = orchestrator_identity["actor_id"], orchestrator_identity["session_id"]
        forged_orchestrator_reopenable = root / "budget-forged-orchestrator-reopen"; shutil.copytree(budget_bounded, forged_orchestrator_reopenable)
        forged_orchestrator_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(forged_orchestrator_reopenable), "--recorded-at", "2026-07-10T00:02:02Z", "--reason", "A forged identity must not reopen coverage.", "--actor-id", "orchestrator-selftest", "--session-id", orchestrator_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append(("public coverage reopen requires a process-bound orchestrator identity", forged_orchestrator_cli.returncode != 0 and reduce_engagement(forged_orchestrator_reopenable)["coverage"] == "budget_bounded", forged_orchestrator_cli.stdout + forged_orchestrator_cli.stderr))
        concurrent_reopenable = root / "budget-concurrent-orchestrator-reopen"; shutil.copytree(budget_bounded, concurrent_reopenable); before_concurrent_reopen_events = len(read_ledger(concurrent_reopenable, "event"))
        concurrent_reopen_command = [sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(concurrent_reopenable), "--recorded-at", "2026-07-10T00:02:01Z", "--reason", "Concurrent retries describe one orchestrator decision.", "--actor-id", orchestrator_id, "--session-id", orchestrator_session]
        concurrent_reopen_processes = [subprocess.Popen(concurrent_reopen_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
        concurrent_reopen_outcomes = [process.communicate(timeout=30) + (process.returncode,) for process in concurrent_reopen_processes]
        try: concurrent_reopen_event_ids = {json.loads(outcome[0])["event_id"] for outcome in concurrent_reopen_outcomes}
        except (json.JSONDecodeError, KeyError): concurrent_reopen_event_ids = set()
        concurrent_reopened_state = reduce_engagement(concurrent_reopenable)
        checks.append(("concurrent public coverage-reopen retries all succeed and append one event", all(outcome[2] == 0 for outcome in concurrent_reopen_outcomes) and len(concurrent_reopen_event_ids) == 1 and len(read_ledger(concurrent_reopenable, "event")) == before_concurrent_reopen_events + 1 and concurrent_reopened_state["coverage"] == "active" and concurrent_reopened_state["coverage_counts"] is None, str(concurrent_reopen_outcomes)))
        orchestrator_reopenable = root / "budget-orchestrator-reopen"; shutil.copytree(budget_bounded, orchestrator_reopenable); before_reopen_events = len(read_ledger(orchestrator_reopenable, "event"))
        reopen_command = [sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(orchestrator_reopenable), "--recorded-at", "2026-07-10T00:02:02Z", "--reason", "A materially distinct bounded branch remains to be tested.", "--actor-id", orchestrator_id, "--session-id", orchestrator_session]
        orchestrator_reopen_cli = subprocess.run(reopen_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False); orchestrator_reopen_retry = subprocess.run(reopen_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        active_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(orchestrator_reopenable), "--recorded-at", "2026-07-10T00:02:03Z", "--reason", "Active coverage is not a terminal state.", "--actor-id", orchestrator_id, "--session-id", orchestrator_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        orchestrator_reopened_state = reduce_engagement(orchestrator_reopenable); orchestrator_reopened_event = read_ledger(orchestrator_reopenable, "event")[-1]
        try: reopen_result, retry_result = json.loads(orchestrator_reopen_cli.stdout), json.loads(orchestrator_reopen_retry.stdout)
        except json.JSONDecodeError: reopen_result = retry_result = {}
        expected_orchestrator = {"role": "orchestrator", "id": orchestrator_id}
        checks.append(("public orchestrator command reopens only terminal budget-bounded coverage with exact identity and idempotence", identity_cli.returncode == 0 and orchestrator_reopen_cli.returncode == 0 and orchestrator_reopen_retry.returncode == 0 and active_reopen_cli.returncode != 0 and orchestrator_reopened_state["coverage"] == "active" and orchestrator_reopened_state["coverage_counts"] is None and not orchestrator_reopened_state["authority_requests"] and len(read_ledger(orchestrator_reopenable, "event")) == before_reopen_events + 1 and reopen_result.get("event_id") == retry_result.get("event_id") == orchestrator_reopened_event["event_id"] and orchestrator_reopened_event["event_type"] == "coverage.reopened" and orchestrator_reopened_event["actor"] == expected_orchestrator and orchestrator_reopened_event["provenance"]["actor"] == expected_orchestrator and orchestrator_reopened_event["provenance"]["session_id"] == orchestrator_session and orchestrator_reopened_event["payload"]["reason"] == "A materially distinct bounded branch remains to be tested.", orchestrator_reopen_cli.stdout + orchestrator_reopen_cli.stderr + orchestrator_reopen_retry.stdout + orchestrator_reopen_retry.stderr + active_reopen_cli.stdout + active_reopen_cli.stderr))

        broker_reopenable = root / "budget-broker-reopen"; shutil.copytree(budget_bounded, broker_reopenable)
        broker_reopen = base_event(event_id="event-coverage-reopened-broker", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02Z", actor_role="broker", actor_id=budget_broker_id, event_type="coverage.reopened", rationale="A broker must not obscure who reopened coverage.", payload={"entity_id": budget_base.name, "status": "active", "reason": "A broker must not obscure who reopened coverage."}, state_changes=[{"dimension": "coverage", "entity_id": budget_base.name, "previous": "budget_bounded", "current": "active"}], session_id=budget_broker_session, operation_class="notebook")
        broker_reopen_path = root / "budget-broker-reopen.json"; broker_reopen_path.write_bytes(canonical_json_bytes(broker_reopen)); broker_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(broker_reopenable), "--file", str(broker_reopen_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append(("generic broker append cannot obscure the orchestrator coverage-reopen actor", broker_reopen_cli.returncode != 0 and reduce_engagement(broker_reopenable)["coverage"] == "budget_bounded", broker_reopen_cli.stdout + broker_reopen_cli.stderr))

        missing_reopen_reason = root / "budget-reopen-missing-reason"; shutil.copytree(budget_bounded, missing_reopen_reason)
        no_reason_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(missing_reopen_reason), "--recorded-at", "2026-07-10T00:02:02Z", "--reason", "", "--actor-id", orchestrator_id, "--session-id", orchestrator_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        no_reason_state = reduce_engagement(missing_reopen_reason)
        checks.append(("coverage reopen is refused without a recorded reason", no_reason_cli.returncode != 0 and no_reason_state["coverage"] == "budget_bounded" and no_reason_state["coverage_counts"]["enumerated_count"] == 5 and no_reason_state["coverage_counts"]["corpus_enumeration_ref"] == budget_manifest_ref, no_reason_cli.stdout + no_reason_cli.stderr))

        untyped_reopenable = root / "budget-untyped-reopen"; shutil.copytree(budget_bounded, untyped_reopenable)
        untyped_reopen = json.loads(json.dumps(broker_reopen)); untyped_reopen["event_id"] = "event-budget-untyped-reopen"; untyped_reopen["event_type"] = "coverage.status_changed"; untyped_reopen["payload"] = {"entity_id": budget_base.name, "status": "active", "coverage_review_ref": "event-budget-bounded"}
        untyped_reopen_path = root / "budget-untyped-reopen.json"; untyped_reopen_path.write_bytes(canonical_json_bytes(untyped_reopen)); untyped_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(untyped_reopenable), "--file", str(untyped_reopen_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append(("terminal coverage cannot reopen through the untyped status-change path", untyped_reopen_cli.returncode != 0 and reduce_engagement(untyped_reopenable)["coverage"] == "budget_bounded", untyped_reopen_cli.stdout + untyped_reopen_cli.stderr))

        operator_reopen_bypass = root / "operator-reopen-without-authority"; shutil.copytree(engagement, operator_reopen_bypass)
        operator_reopen = base_event(event_id="event-operator-reopen-without-authority", engagement_id=engagement.name, recorded_at="2026-07-10T00:02:02Z", actor_role="broker", actor_id=budget_broker_id, event_type="engagement.reopened", rationale="Attempt to bypass the existing operator reopen authority.", payload={"entity_id": engagement.name, "status": "active", "operator_id": "operator-selftest", "executor_id": budget_broker_id}, state_changes=[{"dimension": "engagement", "entity_id": engagement.name, "previous": "blocked", "current": "active"}, {"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "active"}], session_id=budget_broker_session, operation_class="authority")
        operator_reopen_path = root / "operator-reopen-without-authority.json"; operator_reopen_path.write_bytes(canonical_json_bytes(operator_reopen)); operator_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(operator_reopen_bypass), "--file", str(operator_reopen_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        operator_reopen_state = reduce_engagement(operator_reopen_bypass)
        checks.append(("existing engagement reopen remains authority-gated and distinct", operator_reopen_cli.returncode != 0 and bool(operator_reopen_state["active_blockers"]) and operator_reopen_state["coverage"] == "blocked" and all(event["event_type"] != "engagement.reopened" for event in read_ledger(operator_reopen_bypass, "event")), operator_reopen_cli.stdout + operator_reopen_cli.stderr))

        budget_reopen = base_event(event_id="event-budget-reopened-by-prior", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="A new material branch reopens the budget-bounded run.", payload={"prior_id": "prior-budget-reopen", "prior_statement": "A materially distinct branch remains.", "strength": "strong", "reason": "operator target-model knowledge", "reopen_hypothesis_id": "hypothesis-budget", "reopening_condition": "Test the distinct branch."}, entity_refs=["hypothesis-budget"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": "closed", "current": "queued"}, {"dimension": "coverage", "entity_id": budget_base.name, "previous": "budget_bounded", "current": "active"}]); append_event(budget_bounded, budget_reopen); reopened_budget = reduce_engagement(budget_bounded)
        checks.append(("budget-bounded coverage can reopen to active and clears terminal denominator accounting", reopened_budget["coverage"] == "active" and reopened_budget["coverage_counts"] is None, str(reopened_budget)))
        append_event(budget_bounded, base_event(event_id="event-budget-hypothesis-selected", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02.100000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Select the reopened bounded branch.", payload={"hypothesis_id": "hypothesis-budget", "status": "selected", "reason": "execute the reopened bounded branch", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The reopened branch is now selected.", "unresolved_questions": [], "next_route": budget_hypothesis_payload["next_experiment"]}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": "queued", "current": "selected"}]))
        append_event(budget_bounded, base_event(event_id="event-budget-hypothesis-running", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02.200000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Begin the reopened bounded branch without recording an attempt yet.", payload={"hypothesis_id": "hypothesis-budget", "status": "running", "reason": "begin the reopened bounded branch", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The reopened branch is running and still requires its first attempt.", "unresolved_questions": [], "next_route": budget_hypothesis_payload["next_experiment"]}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": "selected", "current": "running"}]))
        budget_escape = json.loads(json.dumps(budget_event)); budget_escape["event_id"] = "event-budget-escape-with-work"; budget_escape["recorded_at"] = "2026-07-10T00:02:03Z"; budget_escape["state_changes"][0]["previous"] = "active"
        budget_escape_before = (budget_bounded / "events.jsonl").read_bytes()
        try:
            _append_kernel_event(budget_bounded, budget_escape)
            budget_escape_code = None
        except RecordError as exc:
            budget_escape_code = exc.code
        budget_escape_state = reduce_engagement(budget_bounded)
        checks.append(("budget_bounded cannot be used as a free ending after a queued-selected-running lifecycle records zero attempts", budget_escape_code == "coverage_terminal_work_remaining" and (budget_bounded / "events.jsonl").read_bytes() == budget_escape_before and budget_escape_state["coverage"] == "active" and any(item["class"] == "hypothesis_running_unattempted" and item["entity"]["id"] == "hypothesis-budget" for item in budget_escape_state["work_queue"]), str((budget_escape_code, budget_escape_state["work_queue"]))))

        cycle_case = root / "budget-redeclaration-cycle"; shutil.copytree(budget_base, cycle_case)
        first_cycle_budget = json.loads(json.dumps(budget_event)); first_cycle_budget["event_id"] = "event-budget-cycle-1"
        _append_kernel_event(cycle_case, first_cycle_budget)
        append_event(cycle_case, base_event(event_id="event-budget-cycle-reopen", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="coverage.reopened", rationale="Repeat the same bounded declaration without disposing work.", payload={"entity_id": budget_base.name, "status": "active", "reason": "Repeat the same bounded declaration without disposing work."}, state_changes=[{"dimension": "coverage", "entity_id": budget_base.name, "previous": "budget_bounded", "current": "active"}], session_id="session-cycle-reopen", operation_class="notebook"))
        second_cycle_budget = json.loads(json.dumps(budget_event)); second_cycle_budget["event_id"] = "event-budget-cycle-2"; second_cycle_budget["recorded_at"] = "2026-07-10T00:02:03Z"; second_cycle_budget["state_changes"][0]["previous"] = "active"
        _append_kernel_event(cycle_case, second_cycle_budget)
        cycle_state = reduce_engagement(cycle_case)
        cycle_facts = cycle_state["budget_redeclaration_cycles"]
        checks.append(("consecutive budget redeclarations without intervening work disposition surface as deterministic reduced facts", len(cycle_facts) == 1 and cycle_facts[0]["first_event_ref"] == "event-budget-cycle-1" and cycle_facts[0]["redeclaration_event_ref"] == "event-budget-cycle-2" and cycle_facts[0]["recorded_at"] == "2026-07-10T00:02:03Z" and "event-budget-cycle-1" in (cycle_case / "progress.md").read_text(), str(cycle_facts)))

        progress = engagement / "progress.md"
        expected_progress = progress.read_bytes()
        progress.write_text("operator edit to generated view\n", encoding="utf-8")
        stale_view_caught = False
        try:
            assert_views_current(engagement, reduced_once)
        except RecordError as exc:
            stale_view_caught = exc.code == "stale_derived_views"
        write_views(engagement, reduced_once)
        checks.append(("derived-view edits are detected and deterministically overwritten", stale_view_caught and progress.read_bytes() == expected_progress, "generated view edit survived"))

        crash_event = base_event(event_id="event-crash-boundary", engagement_id=engagement.name, recorded_at="2026-07-10T00:03:00Z", actor_role="operator", actor_id="operator-selftest", event_type="observation.recorded", rationale="Ledger commit succeeds before simulated projection crash.", payload={"entity_id": "observation-1", "entity_type": "observation", "status": "recorded"})
        append_ledger_record(engagement, "event", crash_event)
        stale_snapshot = (engagement / "state.snapshot.json").read_bytes() != canonical_json_bytes(reduce_engagement(engagement))
        recovered = reduce_engagement(engagement); write_snapshot(engagement, recovered); write_views(engagement, recovered)
        checks.append(("resume recovers a ledger commit made before projection crash", stale_snapshot and recovered["last_event_id"] == "event-crash-boundary", "authoritative event was lost"))

        before_concurrent_count = len(read_ledger(engagement, "event")); local_broker_id, local_broker_session = _local_identity("broker")
        processes = []
        for number in range(4):
            proposal = base_event(event_id=f"event-concurrent-{number}", engagement_id=engagement.name, recorded_at="2026-07-10T00:10:00Z", actor_role="broker", actor_id=local_broker_id, event_type="observation.recorded", rationale=f"Concurrent append {number}.", payload={"entity_id": f"observation-{number + 2}", "entity_type": "observation", "status": "recorded"}, session_id=local_broker_session, operation_class="notebook")
            proposal_path = root / f"proposal-{number}.json"
            proposal_path.write_bytes(canonical_json_bytes(proposal))
            processes.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(engagement), "--file", str(proposal_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for _ in range(2):
            processes.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "reduce", "--engagement", str(engagement)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        outcomes = [process.communicate(timeout=30) + (process.returncode,) for process in processes]
        concurrent_records = read_ledger(engagement, "event")
        current = reduce_engagement(engagement)
        checks.append(("concurrent writers serialize without loss or stale projections", all(result[2] == 0 for result in outcomes) and len(concurrent_records) == before_concurrent_count + 4 and (engagement / "state.snapshot.json").read_bytes() == canonical_json_bytes(current), str(outcomes)))
        forged=base_event(event_id="event-forged-operator",engagement_id=engagement.name,recorded_at="2026-07-10T00:10:01Z",actor_role="operator",actor_id="operator-selftest",event_type="observation.recorded",rationale="Attempt noninteractive operator impersonation.",payload={"entity_id":"observation-forged","entity_type":"observation","status":"recorded"});forged_path=root/"forged-operator.json";forged_path.write_bytes(canonical_json_bytes(forged));forged_run=subprocess.run([sys.executable,str(Path(__file__).resolve()),"append-event","--engagement",str(engagement),"--file",str(forged_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
        try:forged_payload=json.loads(forged_run.stdout);forged_blocked=forged_run.returncode!=0 and forged_payload.get("error",{}).get("code")=="operator_signature_required"
        except json.JSONDecodeError:forged_blocked=False
        checks.append(("noninteractive caller cannot impersonate signed operator through generic append",forged_blocked,forged_run.stdout+forged_run.stderr))
        snapshot_bytes = (engagement / "state.snapshot.json").read_bytes()
        stale_value = json.loads(snapshot_bytes); stale_value["event_count"] -= 1
        (engagement / "state.snapshot.json").write_bytes(canonical_json_bytes(stale_value))
        stale_resume_caught = False
        try:
            assert_resume_current(engagement)
        except RecordError as exc:
            stale_resume_caught = exc.code == "stale_state_snapshot"
        (engagement / "state.snapshot.json").write_bytes(snapshot_bytes)
        checks.append(("check-resume rejects a stale snapshot", stale_resume_caught, "stale snapshot accepted"))

        package_fixture = root / "package-fixture.bin"; package_fixture.write_bytes(b"pinned package fixture\n"); package_digest = sha256_file(package_fixture); runtime_fixture = Path(sys.executable).resolve()
        blocked_environment = collect_preflight(engagement, preflight_id="preflight-wrong-identity", mode="package", target=package_fixture, expected_identity="sha256:" + "f" * 64, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:00Z", operator_redaction_attested=True)
        review_environment = collect_preflight(engagement, preflight_id="preflight-zone-review", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:01Z", operator_redaction_attested=True, advisory_zone="unknown")
        environment_record = collect_preflight(engagement, preflight_id="preflight-selftest", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:02Z", operator_redaction_attested=True, endpoint_identity="local", account_role="owner")
        retry_event_count = reduce_engagement(engagement)["event_count"]; retried_environment = collect_preflight(engagement, preflight_id="preflight-selftest", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:02Z", operator_redaction_attested=True, endpoint_identity="local", account_role="owner")
        environment_state = reduce_engagement(engagement)
        checks.append(("preflight retry is byte-idempotent after record and event commit", retried_environment == environment_record and environment_state["event_count"] == retry_event_count, "preflight retry appended or changed immutable bytes"))
        checks.append(("wrong identity blocks and advisory Zone never authorizes or replaces a ready preflight", environment_record["status"] == "ready" and blocked_environment["status"] == "blocked" and review_environment["status"] == "needs_review" and environment_state["active_environment_ref"] == "preflight-selftest" and not any(item["safety"]["zone2_authorization_granted"] for item in (environment_record, blocked_environment, review_environment)), str(environment_state["environment_preflights"])))
        local_broker_id, local_broker_session = _local_identity("broker")
        collector_engagement = root / "collector-modes"; collector_engagement.mkdir(); collector_engagement.joinpath("scope.md").write_text(scope.replace("self-test", "collector-modes"), encoding="utf-8"); initialize_engagement(collector_engagement, "2026-07-10T00:13:10Z")
        agent_source_path = root / "agent-artifact-source.txt"; agent_source_path.write_text("benign agent evidence\n", encoding="utf-8"); source_time = datetime.fromisoformat("2026-07-10T00:13:09Z".replace("Z", "+00:00")).timestamp(); os.utime(agent_source_path, (source_time, source_time))
        agent_preflight_run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "preflight", "--engagement", str(collector_engagement), "--preflight-id", "preflight-agent", "--mode", "package", "--target", str(package_fixture), "--expected-identity", package_digest, "--runtime", str(runtime_fixture), "--reproduction-argv", json.dumps([str(runtime_fixture), "-c", "pass"]), "--actor-role", "broker", "--actor-id", local_broker_id, "--session-id", local_broker_session, "--recorded-at", "2026-07-10T00:13:10.500000Z"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        agent_record = load_json(collector_engagement / "environment" / "preflight-preflight-agent.json") if agent_preflight_run.returncode == 0 else {}
        checks.append(("agent clear-local preflight is noninteractive, truthful, and separately collected", agent_preflight_run.returncode == 0 and agent_record.get("schema_version") == 2 and agent_record.get("status") == "ready" and agent_record.get("provenance", {}).get("actor") == {"role": "broker", "id": local_broker_id} and agent_record.get("provenance", {}).get("session_id") == local_broker_session and "operator_redaction_attested" not in agent_record.get("safety", {}), agent_preflight_run.stdout + agent_preflight_run.stderr))
        review_candidate = collect_agent_preflight(collector_engagement, preflight_id="preflight-agent-review", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id=local_broker_id, recorded_at="2026-07-10T00:13:10.510000Z", advisory_zone="unknown", actor_role="broker", actor_id=local_broker_id, session_id=local_broker_session)
        review_action = _authority_action("review-preflight", lane_id="lane-preflight-review", executor_id=local_broker_id, session_id=local_broker_session, preflight_id="preflight-agent-review", verdict="accepted", reason="Identity is exact; advisory zone remains non-authorizing.", operator_id="operator-selftest", recorded_at="2026-07-10T00:13:10.540000Z"); review_action_digest = sha256_bytes(canonical_json_bytes(review_action)); review_action_relative = "authority/requests/request-preflight-review.action.json"; atomic_write(collector_engagement / review_action_relative, canonical_json_bytes(review_action)); review_scope = reduce_engagement(collector_engagement)["scope_hash"]
        append_event(collector_engagement, base_event(event_id="event-authority-request-preflight-review", engagement_id=collector_engagement.name, recorded_at="2026-07-10T00:13:10.520000Z", actor_role="broker", actor_id=local_broker_id, event_type="authority.requested", rationale="Request operator review of immutable preflight facts.", payload={"request_id": "request-preflight-review", "action_kind": "review-preflight", "action_digest": review_action_digest, "action_path": review_action_relative, "lane_id": "lane-preflight-review", "request_status": "pending_authority", "scope_hash": review_scope, "environment_ref": None, "expires_at": "2099-07-10T00:00:00Z"}, session_id=local_broker_session, operation_class="notebook"))
        append_event(collector_engagement, base_event(event_id="event-authority-resolution-preflight-review", engagement_id=collector_engagement.name, recorded_at="2026-07-10T00:13:10.530000Z", actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Accept exact identity facts without granting Zone-2 authority.", payload={"request_id": "request-preflight-review", "request_event_ref": "event-authority-request-preflight-review", "action_digest": review_action_digest, "resolution": "approved", "resolved_at": "2026-07-10T00:13:10.530000Z"}, entity_refs=["event-authority-request-preflight-review"], session_id="session-operator-review", operation_class="authority"))
        preflight_bytes = (collector_engagement / "environment" / "preflight-preflight-agent-review.json").read_bytes(); preflight_review = review_preflight(collector_engagement, "preflight-agent-review", "accepted", "Identity is exact; advisory zone remains non-authorizing.", "operator-selftest", "2026-07-10T00:13:10.540000Z", "request-preflight-review", "lane-preflight-review", local_broker_id, local_broker_session); reviewed_state = reduce_engagement(collector_engagement)
        checks.append(("preflight collection is immutable and separate from digest-bound operator review", review_candidate["status"] == "needs_review" and preflight_review["review_type"] == "operator" and (collector_engagement / "environment" / "preflight-preflight-agent-review.json").read_bytes() == preflight_bytes and reviewed_state["environment_preflights"]["preflight-agent-review"]["status"] == "ready" and reviewed_state["active_environment_ref"] == "preflight-agent-review" and review_candidate["safety"]["zone2_authorization_granted"] is False, str(reviewed_state["environment_preflights"])))
        agent_metadata = {"schema_version": 1, "artifact_id": "artifact-agent", "engagement_id": collector_engagement.name, "created_at": "2026-07-10T00:13:10.700000Z", "producer": {"role": "broker", "id": local_broker_id}, "producer_session_id": local_broker_session, "operation_class": "notebook", "acquisition_method": "source_inspection", "target_refs": [], "environment_ref": "preflight-agent-review", "sensitivity": "internal", "redaction_status": "not_needed", "contains_executable_capability": False, "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None, "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"}
        agent_metadata_path = root / "agent-artifact-metadata.json"; agent_metadata_path.write_bytes(canonical_json_bytes(agent_metadata)); classification_path = root / "agent-artifact-classification.json"
        classify_run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "classify-artifact", "--engagement", str(collector_engagement), "--metadata", str(agent_metadata_path), "--source", str(agent_source_path), "--relative-path", "evidence/agent-artifact.txt", "--recorded-at", "2026-07-10T00:13:10.600000Z", "--actor-role", "broker", "--actor-id", local_broker_id, "--session-id", local_broker_session, "--output", str(classification_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        agent_artifact_path = collector_engagement / "evidence" / "agent-artifact.txt"; agent_artifact_path.parent.mkdir(exist_ok=True)
        if classify_run.returncode == 0: shutil.copyfile(agent_source_path, agent_artifact_path)
        register_run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "register-artifact", "--engagement", str(collector_engagement), "--file", str(agent_artifact_path), "--metadata", str(agent_metadata_path), "--classification", str(classification_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if register_run.returncode != 0: agent_artifact_path.unlink(missing_ok=True)
        dangling_destination=collector_engagement/"evidence"/"dangling-artifact.txt"; dangling_target=root/"outside-dangling-target"; dangling_destination.symlink_to(dangling_target); dangling_metadata=dict(agent_metadata); dangling_metadata["artifact_id"]="artifact-dangling"; dangling_metadata_path=root/"dangling-metadata.json"; dangling_metadata_path.write_bytes(canonical_json_bytes(dangling_metadata)); dangling_run=subprocess.run([sys.executable,str(Path(__file__).resolve()),"classify-artifact","--engagement",str(collector_engagement),"--metadata",str(dangling_metadata_path),"--source",str(agent_source_path),"--relative-path","evidence/dangling-artifact.txt","--recorded-at","2026-07-10T00:13:10.750000Z","--actor-role","broker","--actor-id",local_broker_id,"--session-id",local_broker_session],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False); checks.append(("clear-local classification rejects dangling destination symlink before permit",dangling_run.returncode!=0 and not dangling_target.exists(),dangling_run.stdout+dangling_run.stderr)); dangling_destination.unlink()
        zone2_metadata = dict(agent_metadata); zone2_metadata["artifact_id"] = "artifact-zone2-blocked"; zone2_metadata["advisory_zone"] = "review_required"; zone2_metadata["operation_class"] = "real_world"; zone2_path = root / "zone2-metadata.json"; zone2_path.write_bytes(canonical_json_bytes(zone2_metadata)); blocked_zone2_path = collector_engagement / "evidence" / "zone2-blocked.bin"
        classify_zone2 = subprocess.run([sys.executable, str(Path(__file__).resolve()), "classify-artifact", "--engagement", str(collector_engagement), "--metadata", str(zone2_path), "--planned-sha256", sha256_file(agent_source_path), "--planned-size", str(agent_source_path.stat().st_size), "--relative-path", "evidence/zone2-blocked.bin", "--recorded-at", "2026-07-10T00:13:10.800000Z", "--actor-role", "broker", "--actor-id", local_broker_id, "--session-id", local_broker_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: zone2_error = json.loads(classify_zone2.stdout).get("error", {}).get("code")
        except json.JSONDecodeError: zone2_error = None
        checks.append(("artifact creation is classified before bytes and Zone-2 fails before creation", classify_run.returncode == 0 and register_run.returncode == 0 and not blocked_zone2_path.exists() and zone2_error == "artifact_creation_requires_fresh_confirmation", classify_run.stdout + register_run.stdout + classify_zone2.stdout))
        secret_package = root / "secret-package.txt"; secret_package.write_text("Authorization: Bearer synthetic-credential-shape-1234567890\n", encoding="utf-8"); secret_preflight = collect_agent_preflight(collector_engagement, preflight_id="preflight-secret-blocked", mode="package", target=secret_package, expected_identity=sha256_file(secret_package), runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id=local_broker_id, recorded_at="2026-07-10T00:13:10.900000Z", actor_role="broker", actor_id=local_broker_id, session_id=local_broker_session)
        checks.append(("automatic preflight scanning blocks secret-shaped target bytes without storing values", secret_preflight["status"] == "blocked" and secret_preflight["safety"]["credentials_present"] is True and secret_preflight["safety"]["secret_scan_status"] == "blocked" and "authorization_header" in secret_preflight["safety"]["secret_pattern_classes"] and "synthetic-credential" not in canonical_json_bytes(secret_preflight).decode("utf-8"), str(secret_preflight["safety"])))
        checks.append(("secret scanner distinguishes assignments from absolute-path bind mounts", "password_assignment" in detect_secret_classes(b'password=\"synthetic-password-value\"') and "password_assignment" in detect_secret_classes(b'password: synthetic-password-value') and "password_assignment" not in detect_secret_classes(b'/etc/passwd:/etc/passwd:ro'), str(detect_secret_classes(b'/etc/passwd:/etc/passwd:ro'))))
        git_fixture = root / "git-fixture"; git_fixture.mkdir(); subprocess.run(["git", "init", "-q", str(git_fixture)], check=True); subprocess.run(["git", "-C", str(git_fixture), "config", "user.email", "fixture@example.invalid"], check=True); subprocess.run(["git", "-C", str(git_fixture), "config", "user.name", "Fixture"], check=True); git_fixture.joinpath("fixture.txt").write_text("fixture\n"); subprocess.run(["git", "-C", str(git_fixture), "add", "fixture.txt"], check=True); subprocess.run(["git", "-C", str(git_fixture), "commit", "-qm", "fixture"], check=True); git_commit = subprocess.check_output(["git", "-C", str(git_fixture), "rev-parse", "HEAD"], text=True).strip(); fsmonitor_sentinel = root / "fsmonitor-ran"; fsmonitor_hook = root / "fsmonitor-hook.sh"; fsmonitor_hook.write_text(f"#!/bin/sh\ntouch '{fsmonitor_sentinel}'\nexit 0\n"); fsmonitor_hook.chmod(0o700); subprocess.run(["git", "-C", str(git_fixture), "config", "core.fsmonitor", str(fsmonitor_hook)], check=True)
        git_preflight = collect_preflight(collector_engagement, preflight_id="preflight-git", mode="git", target=git_fixture, expected_identity=git_commit, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:11Z", operator_redaction_attested=True); fsmonitor_suppressed = not fsmonitor_sentinel.exists()
        git_fifo = git_fixture / "fixture.txt"; git_fifo.unlink(); os.mkfifo(git_fifo)
        git_fifo_preflight = collect_preflight(collector_engagement, preflight_id="preflight-git-fifo", mode="git", target=git_fixture, expected_identity=git_commit, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:11.100000Z", actor_role="broker", actor_id=local_broker_id, session_id=local_broker_session)
        configuration_fifo = root / "configuration-fifo"; os.mkfifo(configuration_fifo)
        configuration_fifo_preflight = collect_preflight(collector_engagement, preflight_id="preflight-configuration-fifo", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:11.200000Z", actor_role="broker", actor_id=local_broker_id, session_id=local_broker_session, configuration_files=[configuration_fifo])
        checks.append(("git and configuration FIFOs fail closed without blocking preflight", git_fifo_preflight["status"] == "blocked" and configuration_fifo_preflight["status"] == "blocked", str((git_fifo_preflight["status"], configuration_fifo_preflight["status"]))))
        git_fixture.joinpath("secret.txt").write_text("Authorization: Bearer synthetic-git-credential-1234567890\n"); subprocess.run(["git", "-C", str(git_fixture), "add", "secret.txt"], check=True); subprocess.run(["git", "-C", str(git_fixture), "commit", "-qm", "secret fixture"], check=True); secret_git_commit = subprocess.check_output(["git", "-C", str(git_fixture), "rev-parse", "HEAD"], text=True).strip()
        secret_git_preflight = collect_agent_preflight(collector_engagement, preflight_id="preflight-git-secret", mode="git", target=git_fixture, expected_identity=secret_git_commit, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id=local_broker_id, recorded_at="2026-07-10T00:13:11.500000Z", actor_role="broker", actor_id=local_broker_id, session_id=local_broker_session)
        local_preflight = collect_preflight(collector_engagement, preflight_id="preflight-local-runtime", mode="local_runtime", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:12Z", operator_redaction_attested=True)
        checks.append(("demonstrated Git, package, and local-runtime collectors pin identity without executing reproduction argv", git_preflight["status"] == "ready" and fsmonitor_suppressed and secret_git_preflight["status"] == "blocked" and "authorization_header" in secret_git_preflight["safety"]["secret_pattern_classes"] and local_preflight["status"] == "ready" and reduce_engagement(collector_engagement)["active_environment_ref"] == "preflight-local-runtime", str((git_preflight["status"], local_preflight["status"]))))
        cleanup_event = base_event(event_id="event-cleanup-open", engagement_id=collector_engagement.name, recorded_at="2026-07-10T00:13:13Z", actor_role="operator", actor_id="operator-selftest", event_type="cleanup.updated", rationale="Track an unresolved local fixture cleanup obligation.", payload={"entity_id": "cleanup-selftest", "status": "open", "scope_hash": reduce_engagement(collector_engagement)["scope_hash"], "operator_id": "operator-selftest", "updated_at": "2026-07-10T00:13:13Z", "cleanup_obligations": [{"obligation_id": "cleanup-selftest", "kind": "local_fixture", "status": "open", "artifact_refs": [], "rationale": "Fixture cleanup remains open.", "closed_at": None}]}, state_changes=[{"dimension": "cleanup", "entity_id": "cleanup-selftest", "previous": None, "current": "open"}]); append_event(collector_engagement, cleanup_event)
        cleanup_blocked = collect_preflight(collector_engagement, preflight_id="preflight-cleanup-debt", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:14Z", operator_redaction_attested=True)
        checks.append(("reduced cleanup debt blocks and invalidates environment activation", cleanup_blocked["status"] == "blocked" and cleanup_blocked["safety"]["cleanup_open_count"] == 1 and reduce_engagement(collector_engagement)["active_environment_ref"] is None, str(cleanup_blocked)))
        second_cleanup = base_event(event_id="event-cleanup-second", engagement_id=collector_engagement.name, recorded_at="2026-07-10T00:13:15Z", actor_role="operator", actor_id="operator-selftest", event_type="cleanup.updated", rationale="A delta update must not erase an earlier open obligation.", payload={"entity_id": "cleanup-second", "status": "open", "scope_hash": reduce_engagement(collector_engagement)["scope_hash"], "operator_id": "operator-selftest", "updated_at": "2026-07-10T00:13:15Z", "cleanup_obligations": [{"obligation_id": "cleanup-second", "kind": "local_fixture", "status": "open", "artifact_refs": [], "rationale": "Second fixture cleanup remains open.", "closed_at": None}]}, state_changes=[{"dimension": "cleanup", "entity_id": "cleanup-second", "previous": None, "current": "open"}]); append_event(collector_engagement, second_cleanup)
        checks.append(("cleanup delta cannot silently drop an earlier open obligation", reduce_engagement(collector_engagement)["cleanup"]["open_count"] == 2, str(reduce_engagement(collector_engagement)["cleanup"])))
        normalization_engagement = root / "operator-normalization"; normalization_engagement.mkdir(); normalization_engagement.joinpath("scope.md").write_text(scope.replace("self-test", "operator-normalization").replace("operator-selftest", "Operator Name!"), encoding="utf-8"); initialize_engagement(normalization_engagement, "2026-07-10T00:13:15Z")
        empty_argv = collect_preflight(normalization_engagement, preflight_id="preflight-empty-argv", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[], operator_id="Operator Name!", recorded_at="2026-07-10T00:13:16Z", operator_redaction_attested=True)
        unattested = collect_preflight(normalization_engagement, preflight_id="preflight-unattested", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="Operator Name!", recorded_at="2026-07-10T00:13:17Z")
        checks.append(("empty argv records blocked, redaction requires attestation, and operator labels normalize once", empty_argv["status"] == "blocked" and empty_argv["collector"]["reproduction_argv"] == [] and unattested["status"] == "blocked" and empty_argv["provenance"]["actor"]["id"] == "Operator-Name", str((empty_argv, unattested))))
        secret_engagement = root / "secret-artifact"; shutil.copytree(engagement, secret_engagement); secret_file = secret_engagement / "evidence" / "secret.txt"; secret_file.parent.mkdir(exist_ok=True); secret_file.write_text("Authorization: Bearer not-a-real-token-value-123456\n")
        secret_blocked = False
        try:
            _register_legacy_artifact(secret_engagement, secret_file, {"schema_version": 1, "artifact_id": "artifact-secret", "engagement_id": engagement.name, "created_at": "2026-07-10T00:13:13Z", "producer": {"role": "operator", "id": "operator-selftest"}, "acquisition_method": "operator", "target_refs": [], "environment_ref": "preflight-selftest", "sensitivity": "secret", "redaction_status": "pending", "contains_executable_capability": False, "advisory_zone": "unknown", "escalation_confirmation_event_ref": None, "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"})
        except RecordError as exc:
            secret_blocked = exc.code == "secret_shaped_artifact_content" and all("not-a-real" not in str(item) for item in exc.details)
        checks.append(("secret-shaped artifact content is rejected without echoing the value", secret_blocked, "secret-shaped artifact accepted or disclosed"))

        evidence_file = engagement / "evidence" / "artifact.txt"; evidence_file.write_text("benign evidence\n", encoding="utf-8")
        artifact_metadata = {"schema_version": 1, "artifact_id": "artifact-selftest", "engagement_id": engagement.name, "created_at": "2026-07-10T00:15:00Z", "producer": {"role": "operator", "id": "operator-selftest"}, "acquisition_method": "operator", "target_refs": [], "environment_ref": "preflight-selftest", "sensitivity": "internal", "redaction_status": "not_needed", "contains_executable_capability": False, "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None, "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"}
        registered = _register_legacy_artifact(engagement, evidence_file, artifact_metadata)
        checks.append(("register-artifact derives and commits path/digest/size", registered["sha256"] == sha256_file(evidence_file) and reduce_engagement(engagement)["artifact_count"] == 1, str(registered)))
        artifact_boundary = (engagement / "artifacts.jsonl").read_bytes(); duplicate_metadata = json.loads(json.dumps(artifact_metadata)); duplicate_metadata["artifact_id"] = "artifact-duplicate-path"; duplicate_metadata["created_at"] = "2026-07-10T00:15:01Z"
        duplicate_registration_rolled_back = False
        try:
            _register_legacy_artifact(engagement, evidence_file, duplicate_metadata)
        except RecordError as exc:
            duplicate_registration_rolled_back = exc.code == "duplicate_artifact_path"
        checks.append(("artifact append rolls back when prospective reduction rejects", duplicate_registration_rolled_back and (engagement / "artifacts.jsonl").read_bytes() == artifact_boundary, "rejected artifact remained committed"))

        def attempt_proposal(attempt_id: str, recorded_at: str, kind: str, assessment: str, statement: str, control_of: list[str]) -> dict:
            return {"schema_version": 2, "attempt_id": attempt_id, "engagement_id": engagement.name, "recorded_at": recorded_at, "actor": {"role": "hunter", "id": "hunter-selftest"}, "provenance": {"actor": {"role": "hunter", "id": "hunter-selftest"}, "provider": "selftest", "model": "semantic-researcher", "prompt_version": "decision5-selftest", "tool_versions": ["source-inspection-v1"], "card_versions": ["card-selftest"]}, "scope_hash": snapshot["scope_hash"], "environment_ref": "preflight-selftest", "escalation_confirmation_event_ref": None, "hypothesis_ref": "hypothesis-h1", "experiment_ref": "event-hypothesis-running", "surface": "owned local fixture", "action_summary": statement, "redaction_attestation": True, "observation": {"source": "source_inspection", "statement": statement}, "evidence_refs": ["artifact-selftest"], "kind": kind, "control_of": control_of, "assessment": assessment, "contamination": {"status": "none_observed", "sources": [], "note": ""}, "cost": {"wall_seconds": 1, "model_seconds": 0, "tool_seconds": 1, "target_calls": 0, "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0}}
        attempt_specs = [
            ("attempt-primary", "2026-07-10T00:15:10Z", "primary", "suspected_signal", "Primary trace reaches the bounded missing guard.", []),
            ("attempt-negative", "2026-07-10T00:15:11Z", "negative_control", "no_signal", "Matched guarded sibling does not exhibit the signal.", ["attempt-primary"]),
            ("attempt-positive", "2026-07-10T00:15:12Z", "positive_control", "suspected_signal", "Owned known-positive fixture emits the expected marker.", ["attempt-primary"]),
            ("attempt-replay", "2026-07-10T00:15:13Z", "replay", "suspected_signal", "Fresh-state replay reproduces the bounded trace.", ["attempt-primary"]),
        ]
        for spec in attempt_specs:
            append_attempt(engagement, attempt_proposal(*spec))
        routing_control = attempt_proposal(
            "attempt-routing-negative-control",
            "2026-07-10T00:15:13.500000Z",
            "negative_control",
            "no_signal",
            "The likely-held routing control remains held under its bounded matched check.",
            ["attempt-primary"],
        )
        routing_control["experiment_ref"] = "event-routing-negative"
        append_attempt(engagement, routing_control)
        proof_state = reduce_engagement(engagement)
        checks.append(("baseline evidence→primary→matched controls→fresh replay is structured and linked", proof_state["attempt_count"] == 5 and [item["kind"] for item in read_ledger(engagement, "attempt")] == ["primary", "negative_control", "positive_control", "replay", "negative_control"] and not any(item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative" for item in proof_state["work_queue"]), str(proof_state["attempt_count"])))

        same_identity_retry = root / "override-same-identity-attempt"; shutil.copytree(engagement, same_identity_retry)
        _append_kernel_event(same_identity_retry, base_event(
            event_id="event-same-identity-reopened",
            engagement_id=engagement.name,
            recorded_at="2026-07-10T00:15:13.600000Z",
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.reopened",
            rationale="Reopen before recording a fresh exact ending context.",
            payload={"entity_id": engagement.name, "status": "active", "operator_id": "operator-selftest"},
            state_changes=[
                {"dimension": "engagement", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
                {"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
            ],
            operation_class="authority",
        ))
        same_identity_state = reduce_engagement(same_identity_retry)
        same_identity_attempts = read_ledger(same_identity_retry, "attempt")
        same_identity_blockers = blocking_work_identities(project_current_terminal_work_state(same_identity_state, same_identity_attempts, coverage="blocked"))
        same_identity_reason = "Operator accepts this exact synthetic residual queue and attempt ledger context."
        same_identity_time = "2026-07-10T00:15:14Z"
        same_identity_session = _local_identity("operator")[1]
        same_identity_payload = {
            "entity_id": engagement.name,
            "terminal_kind": "engagement",
            "status": "blocked",
            "reason": same_identity_reason,
            "operator_id": "operator-selftest",
            "scope_hash": same_identity_state["scope_hash"],
            "blocking_items": same_identity_blockers,
            "blocking_queue_digest": sha256_bytes(canonical_json_bytes(same_identity_blockers)),
            **attempt_ledger_context(same_identity_attempts),
        }
        same_identity_changes = [
            {"dimension": "engagement", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
            {"dimension": "coverage", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
        ]
        same_identity_action = ending_override_action(
            engagement_id=engagement.name,
            recorded_at=same_identity_time,
            actor={"role": "operator", "id": "operator-selftest"},
            payload=same_identity_payload,
            entity_refs=[],
            evidence_refs=[],
            state_changes=same_identity_changes,
            session_id=same_identity_session,
        )
        same_identity_action_digest = sha256_bytes(canonical_json_bytes(same_identity_action))
        same_identity_challenge = operator_challenge_bytes(
            engagement_id=engagement.name,
            scope_hash=same_identity_state["scope_hash"],
            ledger_hash=read_ledger(same_identity_retry, "event")[-1]["record_hash"],
            operation=f"override-ending:{same_identity_action_digest}",
            operator_id="operator-selftest",
        )
        same_identity_challenge_path = root / "same-identity-override-challenge.json"
        same_identity_challenge_path.write_bytes(same_identity_challenge)
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(same_identity_challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        same_identity_argv = [sys.executable, str(Path(__file__).resolve()), "override-ending", "--engagement", str(same_identity_retry), "--terminal-kind", "engagement", "--status", "blocked", "--operator-id", "operator-selftest", "--session-id", same_identity_session, "--recorded-at", same_identity_time, "--reason", same_identity_reason]
        same_identity_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(same_identity_challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers_path)}
        same_identity_override = subprocess.run(same_identity_argv, env=same_identity_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        equal_time_replay = root / "override-equal-time-later-attempt"; shutil.copytree(same_identity_retry, equal_time_replay)
        _append_kernel_event(equal_time_replay, base_event(
            event_id="event-equal-time-override-reopened",
            engagement_id=engagement.name,
            recorded_at=same_identity_time,
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.reopened",
            rationale="Reopen the exact prior ending before recording later work at the same timestamp precision.",
            payload={"entity_id": engagement.name, "status": "active", "operator_id": "operator-selftest"},
            state_changes=[
                {"dimension": "engagement", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
                {"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
            ],
            operation_class="authority",
        ))
        equal_time_before_attempt = reduce_engagement(equal_time_replay)
        try:
            append_attempt(equal_time_replay, attempt_proposal("attempt-equal-time-after-reopen", same_identity_time, "primary", "suspected_signal", "Later append order, not timestamp precision, separates this attempt from the prior signed ending.", []))
            equal_time_replay_state = reduce_engagement(equal_time_replay)
            equal_time_replay_error = None
        except RecordError as exc:
            equal_time_replay_state = None
            equal_time_replay_error = exc.code
        checks.append((
            "historical override replay uses its signed attempt prefix so later equal-timestamp work after reopen stays reducible",
            same_identity_override.returncode == 0
            and equal_time_replay_error is None
            and equal_time_replay_state is not None
            and equal_time_replay_state["coverage"] == "active"
            and equal_time_replay_state["attempt_count"] == equal_time_before_attempt["attempt_count"] + 1
            and equal_time_replay_state["ending_overrides"][-1]["attempt_ledger_count"] == same_identity_payload["attempt_ledger_count"],
            str({"override": same_identity_override.stdout + same_identity_override.stderr, "error": equal_time_replay_error, "state": equal_time_replay_state}),
        ))
        before_same_identity_attempt = reduce_engagement(same_identity_retry)
        blocker_identity_before = blocking_work_identities(before_same_identity_attempt)
        late_same_identity_attempt = attempt_proposal("attempt-same-identity-later", "2026-07-10T00:15:14.100000Z", "primary", "suspected_signal", "A later attempt preserves the same unadjudicated-hypothesis queue identity.", [])
        append_attempt(same_identity_retry, late_same_identity_attempt)
        after_same_identity_attempt = reduce_engagement(same_identity_retry)
        same_identity_event_count = len(read_ledger(same_identity_retry, "event"))
        stale_same_identity_retry = subprocess.run(same_identity_argv, env=same_identity_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append((
            "a later same-hypothesis attempt keeps the coarse blocker identity but invalidates the signed override and its retry",
            same_identity_override.returncode == 0
            and blocker_identity_before == blocking_work_identities(after_same_identity_attempt)
            and after_same_identity_attempt["attempt_count"] == before_same_identity_attempt["attempt_count"] + 1
            and after_same_identity_attempt["source_hashes"]["attempts.jsonl"] != before_same_identity_attempt["source_hashes"]["attempts.jsonl"]
            and stale_same_identity_retry.returncode != 0
            and len(read_ledger(same_identity_retry, "event")) == same_identity_event_count,
            str({"first": same_identity_override.stdout + same_identity_override.stderr, "retry": stale_same_identity_retry.stdout + stale_same_identity_retry.stderr, "before": blocker_identity_before, "after": blocking_work_identities(after_same_identity_attempt)}),
        ))

        supported_negative = root / "supported-negative"; shutil.copytree(engagement, supported_negative)
        exhausted = base_event(event_id="event-hypothesis-exhausted", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:14Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Matched controls and fresh replay exhaust the bounded mechanism without manufacturing a finding.", payload={"hypothesis_id": "hypothesis-h1", "status": "exhausted", "reason": "matched controls refute the bounded path", "experiment_refs": ["attempt-primary", "attempt-replay"], "control_refs": ["attempt-negative", "attempt-positive", "attempt-routing-negative-control"], "supporting_evidence_refs": ["artifact-selftest"], "conflicting_evidence_refs": ["attempt-negative"], "disposition_rationale": "The primary anomaly does not survive the matched guarded sibling while detector and replay controls are healthy.", "unresolved_questions": [], "next_route": None}, evidence_refs=["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay", "attempt-routing-negative-control", "artifact-selftest"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-h1", "previous": "running", "current": "exhausted"}]); append_event(supported_negative, exhausted)
        backdated_terminal = root / "backdated-terminal"; shutil.copytree(supported_negative, backdated_terminal)
        late_unadjudicated = attempt_proposal("attempt-late-unadjudicated", "2026-07-10T00:15:20Z", "primary", "suspected_signal", "A ledgered attempt must not disappear behind a backdated terminal timestamp.", [])
        append_attempt(backdated_terminal, late_unadjudicated)
        backdated_state = reduce_engagement(backdated_terminal)
        backdated_attempts = read_ledger(backdated_terminal, "attempt")
        historical_backdated_projection = project_terminal_work_state(backdated_state, backdated_attempts, coverage=backdated_state["coverage"], recorded_at="2026-07-10T00:15:14.500000Z")
        current_backdated_projection = project_current_terminal_work_state(backdated_state, backdated_attempts, coverage=backdated_state["coverage"])
        prior_engagement_status = "active"
        for prior_event in read_ledger(backdated_terminal, "event"):
            for change in prior_event["state_changes"]:
                if change["dimension"] == "engagement" and change["entity_id"] == backdated_state["engagement_id"]:
                    prior_engagement_status = change["current"]
        backdated_close = base_event(
            event_id="event-backdated-close",
            engagement_id=backdated_state["engagement_id"],
            recorded_at="2026-07-10T00:15:14.500000Z",
            actor_role="broker",
            actor_id=_local_identity("broker")[0],
            event_type="engagement.closed",
            rationale="A caller timestamp cannot hide an attempt already committed to the ledger.",
            payload={"entity_id": backdated_state["engagement_id"], "status": "closed", "scope_hash": backdated_state["scope_hash"], "operator_id": "operator-selftest", "disposition_ref": "memory-not-reached", "disposition_digest": "sha256:" + "0" * 64},
            state_changes=[{"dimension": "engagement", "entity_id": backdated_state["engagement_id"], "previous": prior_engagement_status, "current": "closed"}],
            session_id=_local_identity("broker")[1],
            operation_class="authority",
        )
        backdated_before = (backdated_terminal / "events.jsonl").read_bytes()
        try:
            _append_kernel_event(backdated_terminal, backdated_close)
            backdated_terminal_code = None
        except RecordError as exc:
            backdated_terminal_code = exc.code
        checks.append((
            "current terminal admission sees every already-ledgered attempt even when the proposed ending timestamp is backdated",
            engagement_may_end(historical_backdated_projection)
            and not engagement_may_end(current_backdated_projection)
            and blocking_work_identities(current_backdated_projection) == [{"class": "hypothesis_ran_unadjudicated", "entity": {"type": "hypothesis", "id": "hypothesis-h1", "detail": None}}]
            and backdated_terminal_code == "terminal_event_precedes_recorded_attempt"
            and (backdated_terminal / "events.jsonl").read_bytes() == backdated_before,
            str({"historical": historical_backdated_projection["work_queue"], "current": current_backdated_projection["work_queue"], "code": backdated_terminal_code}),
        ))
        negative_review = {"schema_version": 1, "review_id": "review-coverage-negative", "engagement_id": engagement.name, "review_type": "coverage", "proposed_finding_id": None, "entity_ref": engagement.name, "finding_revision": None, "recorded_at": "2026-07-10T00:15:15Z", "input_refs": ["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay"], "input_hash": "sha256:" + "5" * 64, "evidence_refs": ["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay", "artifact-selftest"], "conflicting_evidence": [], "independence": {"reviewer_id": "coverage-reviewer", "reviewer_model": "cold-reviewer", "reviewer_run_id": "run-coverage-negative", "originating_run_id": "event-hypothesis-running", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Find an omitted materially distinct path."}, "verdict": "coverage_dry", "rationale": "The bounded hypothesis is decisively exhausted by healthy matched controls.", "corrections": [], "required_next_actions": [], "bounded_space": "One owned-fixture branch and matched guarded sibling.", "hypothesis_dispositions": [{"hypothesis_ref": "hypothesis-h1", "status": "exhausted", "rationale": "Matched negative plus healthy positive and replay controls exhaust the route."}], "omitted_branch_challenge": "Cold review found no unmodeled sibling in the declared bounded space.", "residual_uncertainty": ["future versions not assessed"]}
        negative_review["input_hash"] = compute_review_input_hash(supported_negative, negative_review, build_reference_index(supported_negative))
        negative_review_path = supported_negative / "reviews" / "coverage-negative.json"; negative_review_path.write_bytes(canonical_json_bytes(negative_review))
        negative_review_commit = base_event(event_id="event-coverage-negative-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:16Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit cold negative coverage review.", payload={"record_path": "reviews/coverage-negative.json", "record_digest": sha256_file(negative_review_path), "record_type": "review", "record_id": "review-coverage-negative", "record_revision": None}); append_event(supported_negative, negative_review_commit)
        negative_review_event = base_event(event_id="event-coverage-negative-reviewed", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:17Z", actor_role="reviewer", actor_id="coverage-reviewer", event_type="review.coverage_completed", rationale="Cold reviewer closes every material hypothesis in the bounded negative engagement.", payload={"review_type": "coverage", "verdict": "coverage_dry"}, review_refs=["review-coverage-negative"]); append_event(supported_negative, negative_review_event)
        negative_dry = base_event(event_id="event-coverage-negative-dry", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:18Z", actor_role="operator", actor_id="operator-selftest", event_type="coverage.status_changed", rationale="Supported negative reaches coverage dry without a finding.", payload={"entity_id": engagement.name, "status": "coverage_dry", "coverage_review_ref": "event-coverage-negative-reviewed"}, entity_refs=["event-coverage-negative-reviewed"], state_changes=[{"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "coverage_dry"}]); append_event(supported_negative, negative_dry)
        negative_state = reduce_engagement(supported_negative)
        checks.append(("well-supported negative reaches cold-reviewed coverage_dry without a finding", negative_state["coverage"] == "coverage_dry" and negative_state["hypotheses"]["hypothesis-h1"]["status"] == "exhausted" and negative_state["findings"] == {}, str(negative_state)))
        dry_reopenable = root / "coverage-dry-orchestrator-reopen"; shutil.copytree(supported_negative, dry_reopenable)
        dry_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(dry_reopenable), "--recorded-at", "2026-07-10T00:15:18.250000Z", "--reason", "Cold review omitted a materially distinct bounded branch.", "--actor-id", orchestrator_id, "--session-id", orchestrator_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        dry_reopened_state = reduce_engagement(dry_reopenable)
        checks.append(("public orchestrator command reopens coverage_dry without changing claim or search state", dry_reopen_cli.returncode == 0 and dry_reopened_state["coverage"] == "active" and dry_reopened_state["hypotheses"] == negative_state["hypotheses"] and dry_reopened_state["findings"] == negative_state["findings"], dry_reopen_cli.stdout + dry_reopen_cli.stderr))
        late_payload = json.loads(json.dumps(hypothesis["payload"])); late_payload["hypothesis_id"] = "hypothesis-after-dry"
        late_hypothesis = base_event(event_id="event-hypothesis-after-dry", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:18.500000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Must explicitly reopen coverage before introducing new search material.", payload=late_payload, entity_refs=["candidate-c1"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-after-dry", "previous": None, "current": "queued"}])
        late_hypothesis_blocked = False
        try: append_event(supported_negative, late_hypothesis)
        except RecordError as exc: late_hypothesis_blocked = exc.code == "search_material_after_closed_coverage"
        checks.append(("new hypotheses cannot preserve a false coverage_dry state", late_hypothesis_blocked, "hypothesis appended after dry coverage without reopening"))
        reopen_prior = base_event(event_id="event-prior-reopens-negative", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:19Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="A strong operator prior reopens bounded search but supplies no claim evidence.", payload={"prior_id": "prior-reopen-negative", "prior_statement": "One materially distinct parser branch was not represented.", "strength": "strong", "reason": "operator target-model knowledge", "reopen_hypothesis_id": "hypothesis-h1", "reopening_condition": "Test the newly identified materially distinct parser branch."}, entity_refs=["hypothesis-h1"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-h1", "previous": "exhausted", "current": "queued"}, {"dimension": "coverage", "entity_id": engagement.name, "previous": "coverage_dry", "current": "active"}]); append_event(supported_negative, reopen_prior)
        reopened_negative = reduce_engagement(supported_negative)
        checks.append(("strong operator prior reopens search and coverage without proving a claim", reopened_negative["coverage"] == "active" and reopened_negative["hypotheses"]["hypothesis-h1"]["status"] == "queued" and reopened_negative["findings"] == {}, str(reopened_negative)))
        telemetry = export_telemetry(supported_negative); telemetry_score = score_telemetry(telemetry)
        telemetry_states = telemetry["candidates"][0]["funnel_states"]
        checks.append(("complete-funnel export retains eligible, selected, and reopened states", telemetry["denominator"] == {"eligible_count": 1, "exported_count": 1, "complete": True} and all(value in telemetry_states for value in ("eligible", "selected", "reopened")), str(telemetry)))
        checks.append(("missing independent outcomes remains telemetry, never fake calibration", telemetry["classification"] == "telemetry" and "missing_independent_outcome" in telemetry["calibration_eligibility"]["reasons"] and telemetry_score["brier_score"] is None and telemetry_score["automatic_actions"] == [] and telemetry_score["bandit_enabled"] is False, str(telemetry_score)))

        artifact_tampered = root / "artifact-tampered"; shutil.copytree(engagement, artifact_tampered); (artifact_tampered / "evidence" / "artifact.txt").write_text("changed\n")
        artifact_tamper_caught = False
        try:
            reduce_engagement(artifact_tampered)
        except RecordError as exc:
            artifact_tamper_caught = exc.code == "artifact_file_digest_mismatch"
        checks.append(("modified registered artifact fails reduction", artifact_tamper_caught, "artifact modification accepted"))
        artifact_orphan = root / "artifact-orphan"; shutil.copytree(engagement, artifact_orphan); (artifact_orphan / "evidence" / "orphan.txt").write_text("orphan\n")
        artifact_orphan_caught = False
        try:
            reduce_engagement(artifact_orphan)
        except RecordError as exc:
            artifact_orphan_caught = exc.code == "orphan_artifact_file"
        checks.append(("orphan evidence file fails reduction", artifact_orphan_caught, "orphan artifact accepted"))

        reviews_dir = engagement / "reviews"; reviews_dir.mkdir(exist_ok=True)
        def claim_review(review_id: str, recorded_at: str, verdict: str, entity_ref: str, finding_revision: int | None, origin_run: str) -> dict:
            return {"schema_version": 1, "review_id": review_id, "engagement_id": engagement.name, "review_type": "claim_adjudication", "proposed_finding_id": "F-selftest", "entity_ref": entity_ref, "finding_revision": finding_revision, "recorded_at": recorded_at, "input_refs": ["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay", "preflight-selftest"], "input_hash": "sha256:" + ("3" if finding_revision is None else "4") * 64, "evidence_refs": ["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay", "artifact-selftest"], "conflicting_evidence": [], "independence": {"reviewer_id": "reviewer-selftest", "reviewer_model": "independent-reviewer", "reviewer_run_id": f"run-{review_id}", "reviewer_session_id": f"session-{review_id}", "originating_run_id": origin_run, "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Refute the bounded mechanism and control linkage."}, "verdict": verdict, "rationale": "Primary trace, matched controls, and replay support only the bounded claim.", "corrections": [], "required_next_actions": ["preserve bounded language"], "control_applicability": [{"attempt_ref": "attempt-negative", "applicable": True, "rationale": "Matched negative branch."}, {"attempt_ref": "attempt-positive", "applicable": True, "rationale": "Known-positive detector check."}, {"attempt_ref": "attempt-replay", "applicable": True, "rationale": "Fresh-state replay."}]}
        review1_path = reviews_dir / "review-claim-1.json"; review1 = claim_review("review-claim-1", "2026-07-10T00:15:20Z", "supported", "F-selftest", None, "event-hypothesis-running"); review1["input_hash"] = compute_review_input_hash(engagement, review1, build_reference_index(engagement)); review1_path.write_bytes(canonical_json_bytes(review1))
        review1_commit = base_event(event_id="event-review-claim-1-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:21Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit independent claim review.", payload={"record_path": "reviews/review-claim-1.json", "record_digest": sha256_file(review1_path), "record_type": "review", "record_id": "review-claim-1", "record_revision": None}); append_event(engagement, review1_commit)
        adjudication1 = base_event(event_id="event-claim-supported", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:22Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Independent review supports the bounded primitive.", payload={"entity_id": "F-selftest", "status": "supported", "review_ref": "review-claim-1", "review_digest": sha256_file(review1_path)}, review_refs=["review-claim-1"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": None, "current": "supported"}]); append_event(engagement, adjudication1)

        suite_records = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "engagement-records" / "suite.json").read_text())["cases"]
        finding1 = json.loads(json.dumps(next(case["record"] for case in suite_records if case["id"] == "finding-v3-rich")))
        finding1.update({"finding_id": "F-selftest", "engagement_id": engagement.name, "revision": 1, "supersedes_revision": None, "recorded_at": "2026-07-10T00:15:23Z", "change_reason": "Initial bounded adjudication.", "claim_state": "supported"})
        finding1["scope_provenance"].update({"scope_hash": snapshot["scope_hash"], "environment_ref": "preflight-selftest", "target_refs": []}); finding1["scope_provenance"]["provenance"]["actor"] = {"role": "reviewer", "id": "reviewer-selftest"}
        finding1["adjudication"] = {"review_ref": "review-claim-1", "justification": "Independent review bound primary evidence, both controls, and replay."}; finding1["search_linkage"] = {"candidate_refs": ["candidate-c1"], "hypothesis_refs": ["hypothesis-h1"]}
        for claim_name in ("mechanism", "reachability"): finding1["claims"][claim_name]["evidence_refs"] = ["artifact-selftest"]
        for impact in finding1["claims"]["impact_claims"]: impact["evidence_refs"] = ["artifact-selftest"]
        proof = finding1["proof"]; proof.update({"primary_attempt_refs": ["attempt-primary"], "negative_control_refs": ["attempt-negative"], "positive_control_refs": ["attempt-positive"], "replay_refs": ["attempt-replay"], "evidence_refs": ["artifact-selftest"], "control_applicability": {"negative": "required", "positive": "required", "replay": "required", "rationale": "Matched negative, known-positive, and fresh replay are all required."}})
        for mapping in proof["claim_proofs"]: mapping.update({"attempt_refs": ["attempt-primary"], "artifact_refs": ["artifact-selftest"], "control_refs": ["attempt-negative", "attempt-positive"], "replay_refs": ["attempt-replay"]})
        finding_dir = engagement / "findings" / "F-selftest"; finding_dir.mkdir(parents=True); finding1_path = finding_dir / "rev-1.json"; finding1_path.write_bytes(canonical_json_bytes(finding1))
        finding1_commit = base_event(event_id="event-finding-1-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:24Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit finding revision one.", payload={"record_path": "findings/F-selftest/rev-1.json", "record_digest": sha256_file(finding1_path), "record_type": "finding-v3", "record_id": "F-selftest", "record_revision": 1}); append_event(engagement, finding1_commit)
        filing1 = base_event(event_id="event-finding-revision-1", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:25Z", actor_role="operator", actor_id="operator-selftest", event_type="finding.revised", rationale="Operator files the independently supported bounded claim.", payload={"finding_id": "F-selftest", "finding_revision": 1, "status": "supported", "finding_digest": sha256_file(finding1_path), "adjudication_review_ref": "review-claim-1", "adjudication_review_digest": sha256_file(review1_path), "adjudication_event_ref": "event-claim-supported", "supersedes_revision": None, "change_reason": "Initial bounded adjudication."}, entity_refs=["F-selftest", "event-claim-supported"], finding_refs=["F-selftest"], review_refs=["review-claim-1"]); append_historical_fixture_event(engagement, filing1)

        review2_path = reviews_dir / "review-claim-2.json"; review2 = claim_review("review-claim-2", "2026-07-10T00:15:26Z", "confirmed", "F-selftest", 1, "event-hypothesis-running"); review2["input_refs"].append("F-selftest"); review2["input_hash"] = compute_review_input_hash(engagement, review2, build_reference_index(engagement)); review2_path.write_bytes(canonical_json_bytes(review2))
        review2_commit = base_event(event_id="event-review-claim-2-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:27Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit fresh confirmation review.", payload={"record_path": "reviews/review-claim-2.json", "record_digest": sha256_file(review2_path), "record_type": "review", "record_id": "review-claim-2", "record_revision": None}); append_event(engagement, review2_commit)
        adjudication2 = base_event(event_id="event-claim-confirmed", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:28Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Fresh independent review confirms the bounded primitive.", payload={"entity_id": "F-selftest", "status": "confirmed", "review_ref": "review-claim-2", "review_digest": sha256_file(review2_path)}, review_refs=["review-claim-2"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": "supported", "current": "confirmed"}]); append_event(engagement, adjudication2)
        finding2 = json.loads(json.dumps(finding1)); finding2.update({"revision": 2, "supersedes_revision": 1, "recorded_at": "2026-07-10T00:15:29Z", "change_reason": "Fresh independent replay review confirmed the bounded primitive.", "claim_state": "confirmed"}); finding2["adjudication"] = {"review_ref": "review-claim-2", "justification": "Fresh reviewer confirmed the exact bounded claim tuple."}
        finding2_path = finding_dir / "rev-2.json"; finding2_path.write_bytes(canonical_json_bytes(finding2))
        finding2_commit = base_event(event_id="event-finding-2-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:29Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit contiguous finding revision two.", payload={"record_path": "findings/F-selftest/rev-2.json", "record_digest": sha256_file(finding2_path), "record_type": "finding-v3", "record_id": "F-selftest", "record_revision": 2}); append_event(engagement, finding2_commit)
        filing2 = base_event(event_id="event-finding-revision-2", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:30Z", actor_role="operator", actor_id="operator-selftest", event_type="finding.revised", rationale="Operator files contiguous confirmed revision without rewriting revision one.", payload={"finding_id": "F-selftest", "finding_revision": 2, "status": "confirmed", "finding_digest": sha256_file(finding2_path), "adjudication_review_ref": "review-claim-2", "adjudication_review_digest": sha256_file(review2_path), "adjudication_event_ref": "event-claim-confirmed", "supersedes_revision": 1, "change_reason": "Fresh independent replay review confirmed the bounded primitive."}, entity_refs=["F-selftest", "event-claim-confirmed"], finding_refs=["F-selftest"], review_refs=["review-claim-2"]); append_historical_fixture_event(engagement, filing2)
        chain_hypothesis = base_event(event_id="event-hypothesis-chain", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:31Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Confirmed primitive opens bounded chainability search without broadening the finding.", payload={"hypothesis_id": "hypothesis-chain", "origin_type": "confirmed_primitive", "origin_ref": "F-selftest", "hypothesis_statement": "The confirmed local primitive may compose with one adjacent owned-fixture transition.", "suspected_invariant": "Composition must not cross the adjacent trust boundary.", "trust_boundary": "confirmed primitive to adjacent owned state", "attacker_path": ["confirmed primitive", "adjacent transition"], "impact_ceiling": "owned fixture composition only", "bounded_space": "One adjacent transition.", "lens_ids": ["composition"], "card_ids": ["card-selftest"], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "end-to-end adjacent trace", "required": True}], "decisive_falsifiers": ["adjacent transition rejects primitive output"], "cost_estimate": zero_cost, "constraints": ["no target contact"], "next_experiment": "trace adjacent owned transition", "completion_criteria": ["trace or decisive rejection"], "status": "queued"}, entity_refs=["F-selftest"], finding_refs=["F-selftest"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-chain", "previous": None, "current": "queued"}]); append_event(engagement, chain_hypothesis)
        finding_state = reduce_engagement(engagement)
        checks.append(("revisioned finding history and active chainability search coexist", finding_state["findings"]["F-selftest"]["revision"] == 2 and finding_state["findings"]["F-selftest"]["status"] == "confirmed" and finding_state["hypotheses"]["hypothesis-chain"]["status"] == "queued" and finding1_path.read_bytes() == canonical_json_bytes(finding1), str(finding_state["findings"])))
        forged_filing = copy.deepcopy(filing2); forged_filing["event_id"] = "event-finding-forged-operator"; forged_filing["recorded_at"] = "2026-07-10T00:15:32Z"; forged_filing["actor"] = {"role": "operator", "id": "other-operator"}; forged_filing["provenance"]["actor"] = forged_filing["actor"]
        before_forged = (engagement / "events.jsonl").read_bytes(); forged_blocked = historical_reduction_rejection(engagement, forged_filing) == "finding_filing_not_scope_operator"
        checks.append(("only the active signed-scope operator can file a finding revision", forged_blocked and (engagement / "events.jsonl").read_bytes() == before_forged, "forged operator filing appended"))
        skip_revision = copy.deepcopy(filing2); skip_revision["event_id"] = "event-finding-revision-4"; skip_revision["recorded_at"] = "2026-07-10T00:15:33Z"; skip_revision["payload"]["finding_revision"] = 4; skip_revision["payload"]["supersedes_revision"] = 2
        before_skip = (engagement / "events.jsonl").read_bytes(); skip_blocked = historical_reduction_rejection(engagement, skip_revision) == "finding_revision_not_contiguous"
        checks.append(("finding revision cannot skip history", skip_blocked and (engagement / "events.jsonl").read_bytes() == before_skip, "skipped revision appended"))

        tuple_hash = claim_tuple_hash(finding2)
        regrade = {"schema_version": 1, "review_id": "review-regrade-selftest", "engagement_id": engagement.name, "review_type": "regrade", "proposed_finding_id": "F-selftest", "recorded_at": "2026-07-10T00:15:34Z", "entity_ref": "F-selftest", "finding_revision": 2, "input_refs": ["F-selftest", "attempt-primary", "attempt-negative", "attempt-replay"], "input_hash": "sha256:" + "0" * 64, "evidence_refs": ["attempt-primary", "attempt-negative", "attempt-replay", "artifact-selftest"], "rationale": "Fresh regrade identifies a distinct adjacent composition that still needs evidence.", "conflicting_evidence": [], "verdict": "escalation_found", "corrections": [], "required_next_actions": ["collect evidence before revising impact"], "independence": {"reviewer_id": "regrade-reviewer", "reviewer_run_id": "run-regrade-selftest", "reviewer_model": "independent-regrader", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Refute the adjacent composition.", "originating_run_id": "event-finding-revision-2"}, "control_applicability": [{"attempt_ref": "attempt-negative", "applicable": True, "rationale": "Matched negative remains applicable."}], "claim_tuple_hash": tuple_hash, "replay_freshness": [{"attempt_ref": "attempt-replay", "fresh": True, "rationale": "Fresh-state replay."}], "prior_review_run_ids": ["run-review-claim-2"], "escalation_claims": ["Adjacent owned transition may compose with the confirmed primitive."], "blocked_reason": None}
        regrade["input_hash"] = compute_review_input_hash(engagement, regrade, build_reference_index(engagement)); regrade_path = reviews_dir / "regrade-selftest.json"; regrade_path.write_bytes(canonical_json_bytes(regrade))
        regrade_commit = base_event(event_id="event-regrade-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:35Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit fresh regrade review.", payload={"record_path": "reviews/regrade-selftest.json", "record_digest": sha256_file(regrade_path), "record_type": "review", "record_id": "review-regrade-selftest", "record_revision": None}); append_event(engagement, regrade_commit)
        regrade_event = base_event(event_id="event-regrade-escalation", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:36Z", actor_role="reviewer", actor_id="regrade-reviewer", event_type="review.regrade_completed", rationale="Escalation is a search obligation, not a finding claim.", payload={"review_ref": "review-regrade-selftest", "finding_id": "F-selftest", "finding_revision": 2, "verdict": "escalation_found", "claim_tuple_hash": tuple_hash}, review_refs=["review-regrade-selftest"], finding_refs=["F-selftest"]); append_event(engagement, regrade_event)
        premature_revision = copy.deepcopy(filing2); premature_revision["event_id"] = "event-premature-escalation-revision"; premature_revision["recorded_at"] = "2026-07-10T00:15:37Z"; premature_revision["payload"]["finding_revision"] = 3; premature_revision["payload"]["supersedes_revision"] = 2
        premature_blocked = historical_reduction_rejection(engagement, premature_revision) == "escalation_evidence_not_collected"
        checks.append(("regrade escalation routes to evidence collection before finding revision", premature_blocked, "escalation directly revised finding"))
        escalation_hypothesis = base_event(event_id="event-hypothesis-escalation", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:38Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Route reviewer escalation into bounded evidence collection.", payload={"hypothesis_id": "hypothesis-escalation", "origin_type": "reviewer_challenge", "origin_ref": "event-regrade-escalation", "hypothesis_statement": "The adjacent owned transition composes with the confirmed primitive.", "suspected_invariant": "Primitive output must not cross the adjacent boundary.", "trust_boundary": "primitive to adjacent owned transition", "attacker_path": ["primitive", "adjacent transition"], "impact_ceiling": "owned fixture only", "bounded_space": "One adjacent transition.", "lens_ids": ["composition"], "card_ids": ["card-selftest"], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "end-to-end composition trace", "required": True}], "decisive_falsifiers": ["adjacent transition rejects primitive output"], "cost_estimate": zero_cost, "constraints": ["offline fixture"], "next_experiment": "trace composition", "completion_criteria": ["trace or decisive rejection"], "status": "queued"}, entity_refs=["event-regrade-escalation"], finding_refs=["F-selftest"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-escalation", "previous": None, "current": "queued"}]); append_event(engagement, escalation_hypothesis)
        escalation_evidence_path = engagement / "evidence" / "escalation.txt"; escalation_evidence_path.write_text("new bounded escalation trace\n", encoding="utf-8")
        escalation_artifact = json.loads(json.dumps(artifact_metadata)); escalation_artifact.update({"artifact_id": "artifact-escalation", "created_at": "2026-07-10T00:15:40.500000Z", "acquisition_method": "source_inspection"}); _register_legacy_artifact(engagement, escalation_evidence_path, escalation_artifact)
        for status, previous, timestamp in (("selected", "queued", "2026-07-10T00:15:39Z"), ("running", "selected", "2026-07-10T00:15:40Z")):
            transition = base_event(event_id=f"event-escalation-{status}", engagement_id=engagement.name, recorded_at=timestamp, actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale=f"Escalation hypothesis {status}.", payload={"hypothesis_id": "hypothesis-escalation", "status": status, "reason": "bounded escalation evidence route", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "Bounded evidence route recorded without changing finding truth.", "unresolved_questions": [], "next_route": "independent composition trace"}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-escalation", "previous": previous, "current": status}]); append_event(engagement, transition)
        escalation_attempt = attempt_proposal("attempt-escalation", "2026-07-10T00:15:40.600000Z", "primary", "suspected_signal", "Fresh bounded trace exercises the reviewer-routed adjacent composition.", [])
        escalation_attempt.update({"hypothesis_ref": "hypothesis-escalation", "experiment_ref": "event-regrade-escalation", "evidence_refs": ["artifact-escalation"]})
        append_attempt(engagement, escalation_attempt)
        escalation_attempt_state = reduce_engagement(engagement)
        escalation_attempt_item = next(item for item in escalation_attempt_state["work_queue"] if item["class"] == "hypothesis_ran_unadjudicated" and item["entity"]["id"] == "hypothesis-escalation")
        escalation_attempt_action = decorate_work_queue_item(escalation_attempt_item, escalation_attempt_state, engagement.absolute())["next_action"]
        checks.append(("routed review evidence progression exposes the fresh attempt as required supporting evidence", "includes every fresh matching attempt in supporting_evidence_refs" in str(escalation_attempt_action["required_inputs"]), str(escalation_attempt_action)))
        escalation_held = base_event(event_id="event-escalation-held", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:41Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Escalation hypothesis held with fresh bounded evidence.", payload={"hypothesis_id": "hypothesis-escalation", "status": "held", "reason": "bounded escalation evidence route", "experiment_refs": ["attempt-escalation"], "control_refs": [], "supporting_evidence_refs": ["attempt-escalation", "artifact-escalation"], "conflicting_evidence_refs": [], "disposition_rationale": "Bounded evidence route recorded without changing finding truth.", "unresolved_questions": ["composition impact remains unproven"], "next_route": "independent composition trace"}, evidence_refs=["attempt-escalation", "artifact-escalation"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-escalation", "previous": "running", "current": "held"}]); append_event(engagement, escalation_held)
        escalation_evidence_state = reduce_engagement(engagement)
        escalation_row = next(item for item in escalation_evidence_state["outstanding_reviews"] if item["review_ref"] == "event-regrade-escalation")
        checks.append(("pending review routes through a bound hypothesis and only fresh cited evidence reaches evidence_collected", escalation_row["status"] == "evidence_collected" and escalation_row["resolution_input_refs"] == ["attempt-escalation", "artifact-escalation"], str(escalation_row)))

        def poc_review(review_id: str, recorded_at: str, reviewer_id: str, run_id: str, verdict: str, prior_runs: list[str], mismatches: list[str], reward_indicators: list[str]) -> dict:
            value = {"schema_version": 1, "review_id": review_id, "engagement_id": engagement.name, "review_type": "pocinator", "proposed_finding_id": "F-selftest", "recorded_at": recorded_at, "entity_ref": "F-selftest", "finding_revision": 2, "input_refs": ["F-selftest", "artifact-selftest"], "input_hash": "sha256:" + "0" * 64, "evidence_refs": ["artifact-selftest"], "rationale": f"Pocinator outcome: {verdict}.", "conflicting_evidence": [], "verdict": verdict, "corrections": mismatches, "required_next_actions": ["route back without changing finding truth"] if verdict != "verified" else [], "independence": {"reviewer_id": reviewer_id, "reviewer_run_id": run_id, "reviewer_signer_fingerprint": sha256_bytes(reviewer_id.encode("utf-8")), "reviewer_model": "pocinator-reviewer", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Break the exact claim tuple and composition.", "originating_run_id": "event-finding-revision-2"}, "claim_tuple_hash": tuple_hash, "high_value": True, "proof_profile_ref": "artifact-selftest", "claim_mismatches": mismatches, "reward_hack_indicators": reward_indicators, "module_level_only": True, "end_to_end_composition_reviewed": False, "blocked_reason": None, "prior_review_run_ids": prior_runs}
            value["input_hash"] = compute_review_input_hash(engagement, value, build_reference_index(engagement)); return value
        poc_specs = [
            ("review-poc-mismatch", "2026-07-10T00:15:42Z", "poc-reviewer", "run-poc-mismatch", "claim_mismatch", ["run-regrade-selftest"], ["Proof demonstrates only the module-level mechanism."], []),
            ("review-poc-reward-1", "2026-07-10T00:15:45Z", "poc-reward-reviewer-1", "run-poc-reward-1", "reward_hacked", ["run-poc-mismatch"], [], ["Evaluator marker without end-to-end proof."]),
            ("review-poc-reward-2", "2026-07-10T00:15:48Z", "poc-reward-reviewer-2", "run-poc-reward-2", "reward_hacked", ["run-poc-reward-1"], [], ["Independent reviewer confirms reward-only optimization."]),
        ]
        mismatch_state = None
        reward_one_state = None
        reward_one_action = None
        for offset, spec in enumerate(poc_specs):
            review_value = poc_review(*spec); review_path = reviews_dir / f"{spec[0]}.json"; review_path.write_bytes(canonical_json_bytes(review_value))
            commit_time = ["2026-07-10T00:15:43Z", "2026-07-10T00:15:46Z", "2026-07-10T00:15:49Z"][offset]; event_time = ["2026-07-10T00:15:44Z", "2026-07-10T00:15:47Z", "2026-07-10T00:15:50Z"][offset]
            commit = base_event(event_id=f"event-{spec[0]}-commit", engagement_id=engagement.name, recorded_at=commit_time, actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit typed Pocinator review.", payload={"record_path": f"reviews/{spec[0]}.json", "record_digest": sha256_file(review_path), "record_type": "review", "record_id": spec[0], "record_revision": None}); append_event(engagement, commit)
            reviewed = base_event(event_id=f"event-{spec[0]}", engagement_id=engagement.name, recorded_at=event_time, actor_role="reviewer", actor_id=spec[2], event_type="review.pocinator_completed", rationale="Pocinator result routes proof state only.", payload={"review_ref": spec[0], "finding_id": "F-selftest", "finding_revision": 2, "verdict": spec[4], "claim_tuple_hash": tuple_hash, "high_value": True}, review_refs=[spec[0]], finding_refs=["F-selftest"]); append_event(engagement, reviewed)
            if offset == 0: mismatch_state = reduce_engagement(engagement)
            if offset == 1:
                reward_one_state = reduce_engagement(engagement)
                reward_one_row = next(item for item in reward_one_state["work_queue"] if item["class"] == "review_obligation_open" and item["entity"]["id"] == "event-review-poc-reward-1")
                reward_one_action = decorate_work_queue_item(reward_one_row, reward_one_state, engagement.absolute())["next_action"]
        typed_state = reduce_engagement(engagement); proof_review = typed_state["proof_reviews"]["F-selftest:r2"]
        checks.append(("claim_mismatch routes correction without refuting finding", mismatch_state is not None and mismatch_state["findings"]["F-selftest"]["status"] == "confirmed" and mismatch_state["proof_reviews"]["F-selftest:r2"]["terminal_status"] == "route_back", str(mismatch_state)))
        checks.append(("first high-value reward_hacked blocks filing and requests one distinct independent second review", reward_one_state is not None and reward_one_state["proof_reviews"]["F-selftest:r2"]["terminal_status"] == "pending_second_review" and _filing_blocking_review_error(reward_one_state, "F-selftest") == "pocinator_second_review_pending" and reward_one_action is not None and reward_one_action["action_id"] == "record_distinct_pocinator_second_review" and "run-poc-reward-1" in str(reward_one_action["required_inputs"]), str((reward_one_state, reward_one_action))))
        reward_one_row_after_second = next(item for item in typed_state["outstanding_reviews"] if item["review_ref"] == "event-review-poc-reward-1")
        checks.append(("definite high-value reward_hacked requires two independent reviewers and binds the second review as correction evidence", proof_review["terminal_status"] == "second_review_confirmed" and proof_review["reviewer_run_ids"] == ["run-poc-reward-1", "run-poc-reward-2"] and reward_one_row_after_second.get("resolution_input_refs") == ["review-poc-reward-2"] and typed_state["findings"]["F-selftest"]["status"] == "confirmed", str((proof_review, reward_one_row_after_second))))
        report_manifest = generate_report(engagement, "F-selftest", 2, ["claim-mechanism", "claim-reach", "claim-impact"], [], "operator-selftest", "2026-07-10T00:15:50.500000Z")
        report_state = reduce_engagement(engagement); checks.append(("report generation binds exact finding revision, review, claims, proof matrix, and bytes", report_state["reports"][report_manifest["report_id"]]["status"] == "draft" and (engagement / report_manifest["report_path"]).is_file(), str(report_manifest)))

        correction = {"schema_version": 1, "review_id": "review-regrade-correction", "engagement_id": engagement.name, "review_type": "regrade", "proposed_finding_id": "F-selftest", "recorded_at": "2026-07-10T00:15:51Z", "entity_ref": "F-selftest", "finding_revision": 2, "input_refs": ["F-selftest", "attempt-negative", "attempt-replay"], "input_hash": "sha256:" + "0" * 64, "evidence_refs": ["attempt-negative", "attempt-replay"], "rationale": "Finding remains real but residual uncertainty must be narrowed.", "conflicting_evidence": [], "verdict": "confirmed_with_correction", "corrections": ["Narrow the residual uncertainty to future versions only."], "required_next_actions": ["file contiguous corrected revision"], "independence": {"reviewer_id": "correction-reviewer", "reviewer_run_id": "run-regrade-correction", "reviewer_model": "independent-regrader", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Find unsupported breadth in the claim.", "originating_run_id": "event-finding-revision-2"}, "control_applicability": [{"attempt_ref": "attempt-negative", "applicable": True, "rationale": "Matched negative bounds breadth."}], "claim_tuple_hash": tuple_hash, "replay_freshness": [{"attempt_ref": "attempt-replay", "fresh": True, "rationale": "Fresh replay remains valid."}], "prior_review_run_ids": ["run-regrade-selftest"], "escalation_claims": [], "blocked_reason": None}
        correction["input_hash"] = compute_review_input_hash(engagement, correction, build_reference_index(engagement)); correction_path = reviews_dir / "regrade-correction.json"; correction_path.write_bytes(canonical_json_bytes(correction))
        correction_commit = base_event(event_id="event-regrade-correction-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:52Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit correction regrade.", payload={"record_path": "reviews/regrade-correction.json", "record_digest": sha256_file(correction_path), "record_type": "review", "record_id": "review-regrade-correction", "record_revision": None}); append_event(engagement, correction_commit)
        correction_event = base_event(event_id="event-regrade-correction", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:53Z", actor_role="reviewer", actor_id="correction-reviewer", event_type="review.regrade_completed", rationale="Correction must become a contiguous revision before closure.", payload={"review_ref": "review-regrade-correction", "finding_id": "F-selftest", "finding_revision": 2, "verdict": "confirmed_with_correction", "claim_tuple_hash": tuple_hash}, review_refs=["review-regrade-correction"], finding_refs=["F-selftest"]); append_event(engagement, correction_event)
        unresolved_correction = copy.deepcopy(filing2); unresolved_correction["event_id"] = "event-unresolved-correction"; unresolved_correction["recorded_at"] = "2026-07-10T00:15:53.500000Z"; unresolved_correction["payload"]["finding_revision"] = 3; unresolved_correction["payload"]["supersedes_revision"] = 2
        correction_block_code = historical_reduction_rejection(engagement, unresolved_correction)
        checks.append(("confirmed_with_correction blocks filing until a fresh correction-bound adjudication", correction_block_code == "review_adjudication_not_fresh", str(correction_block_code or "unresolved correction allowed finding revision")))
        review3_path = reviews_dir / "review-claim-3.json"; review3 = claim_review("review-claim-3", "2026-07-10T00:15:54Z", "confirmed", "F-selftest", 2, "event-regrade-correction"); review3["input_refs"].extend(["event-regrade-escalation", "attempt-escalation", "artifact-escalation", "event-regrade-correction", "event-review-poc-mismatch", "event-review-poc-reward-1", "review-poc-reward-2"]); review3["input_refs"] = sorted(set(review3["input_refs"])); review3["input_hash"] = compute_review_input_hash(engagement, review3, build_reference_index(engagement)); review3_path.write_bytes(canonical_json_bytes(review3))
        review3_commit = base_event(event_id="event-review-claim-3-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:55Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit correction adjudication.", payload={"record_path": "reviews/review-claim-3.json", "record_digest": sha256_file(review3_path), "record_type": "review", "record_id": "review-claim-3", "record_revision": None}); append_event(engagement, review3_commit)
        adjudication3 = base_event(event_id="event-claim-correction-confirmed", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:56Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Independent review confirms corrected bounded claim.", payload={"entity_id": "F-selftest", "status": "confirmed", "review_ref": "review-claim-3", "review_digest": sha256_file(review3_path)}, review_refs=["review-claim-3"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": "confirmed", "current": "confirmed"}]); append_event(engagement, adjudication3)
        adjudicated_correction_state = reduce_engagement(engagement)
        missing_escalation_evidence = copy.deepcopy(adjudicated_correction_state); missing_escalation_evidence["claim_adjudications"]["F-selftest"]["input_refs"].remove("artifact-escalation")
        missing_second_review = copy.deepcopy(adjudicated_correction_state); missing_second_review["claim_adjudications"]["F-selftest"]["input_refs"].remove("review-poc-reward-2")
        checks.append(("filing adjudication binds both routed evidence and the distinct second Pocinator review", _filing_blocking_review_error(adjudicated_correction_state, "F-selftest") is None and _filing_blocking_review_error(missing_escalation_evidence, "F-selftest") == "review_adjudication_inputs_missing" and _filing_blocking_review_error(missing_second_review, "F-selftest") == "review_adjudication_inputs_missing", str(adjudicated_correction_state["outstanding_reviews"])))
        finding3 = json.loads(json.dumps(finding2)); finding3.update({"revision": 3, "supersedes_revision": 2, "recorded_at": "2026-07-10T00:15:57Z", "change_reason": "Resolve regrade correction and evidence-routed escalation.", "claim_state": "confirmed"}); finding3["claims"]["uncertainty"] = ["future versions not assessed"]; finding3["adjudication"] = {"review_ref": "review-claim-3", "justification": "Fresh review confirms the corrected bounded tuple."}
        finding3_path = finding_dir / "rev-3.json"; finding3_path.write_bytes(canonical_json_bytes(finding3)); finding3_commit = base_event(event_id="event-finding-3-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:57.500000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit corrected finding revision three.", payload={"record_path": "findings/F-selftest/rev-3.json", "record_digest": sha256_file(finding3_path), "record_type": "finding-v3", "record_id": "F-selftest", "record_revision": 3}); append_event(engagement, finding3_commit)
        filing3 = base_event(event_id="event-finding-revision-3", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:58Z", actor_role="operator", actor_id="operator-selftest", event_type="finding.revised", rationale="Operator files correction-bound contiguous revision.", payload={"finding_id": "F-selftest", "finding_revision": 3, "status": "confirmed", "finding_digest": sha256_file(finding3_path), "adjudication_review_ref": "review-claim-3", "adjudication_review_digest": sha256_file(review3_path), "adjudication_event_ref": "event-claim-correction-confirmed", "supersedes_revision": 2, "change_reason": "Resolve regrade correction and evidence-routed escalation.", "resolves_review_refs": ["event-regrade-escalation", "event-regrade-correction"]}, entity_refs=["F-selftest", "event-claim-correction-confirmed"], finding_refs=["F-selftest"], review_refs=["review-claim-3"]); append_historical_fixture_event(engagement, filing3)
        corrected_state = reduce_engagement(engagement)
        checks.append(("correction review closes only through a contiguous adjudicated revision", corrected_state["findings"]["F-selftest"]["revision"] == 3 and not any(item["review_ref"] in {"event-regrade-escalation", "event-regrade-correction"} for item in corrected_state["outstanding_reviews"]), str(corrected_state["outstanding_reviews"])))
        checks.append(("finding revision makes prior report visibly historical", corrected_state["reports"][report_manifest["report_id"]]["status"] == "historical" and "revision 3" in corrected_state["reports"][report_manifest["report_id"]]["historical_reason"], str(corrected_state["reports"])))

        tuple_hash3 = claim_tuple_hash(finding3)

        refuted_case = root / "regrade-refuted-debt"; shutil.copytree(engagement, refuted_case); refuted_reviews = refuted_case / "reviews"
        refuted_regrade = json.loads(json.dumps(correction)); refuted_regrade.update({"review_id": "review-regrade-refuted", "recorded_at": "2026-07-10T00:15:59Z", "finding_revision": 3, "verdict": "refuted", "rationale": "Independent regrade refutes the current bounded claim.", "corrections": ["Adjudicate the independent refutation before any revision."], "required_next_actions": ["record a fresh refutation-bound claim adjudication"], "claim_tuple_hash": tuple_hash3, "prior_review_run_ids": ["run-review-claim-3"], "escalation_claims": [], "blocked_reason": None}); refuted_regrade["independence"].update({"reviewer_id": "refutation-reviewer", "reviewer_run_id": "run-regrade-refuted", "originating_run_id": "event-finding-revision-3"}); refuted_regrade["input_hash"] = compute_review_input_hash(refuted_case, refuted_regrade, build_reference_index(refuted_case)); refuted_regrade_path = refuted_reviews / "regrade-refuted.json"; refuted_regrade_path.write_bytes(canonical_json_bytes(refuted_regrade))
        _append_kernel_event(refuted_case, base_event(event_id="event-regrade-refuted-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.100000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit independent refutation.", payload={"record_path": "reviews/regrade-refuted.json", "record_digest": sha256_file(refuted_regrade_path), "record_type": "review", "record_id": "review-regrade-refuted", "record_revision": None}))
        _append_kernel_event(refuted_case, base_event(event_id="event-regrade-refuted", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.200000Z", actor_role="reviewer", actor_id="refutation-reviewer", event_type="review.regrade_completed", rationale="Independent refutation becomes explicit filing debt.", payload={"review_ref": "review-regrade-refuted", "finding_id": "F-selftest", "finding_revision": 3, "verdict": "refuted", "claim_tuple_hash": tuple_hash3}, review_refs=["review-regrade-refuted"], finding_refs=["F-selftest"]))
        refuted_open_state = reduce_engagement(refuted_case)
        refuted_row = next(item for item in refuted_open_state["outstanding_reviews"] if item["review_ref"] == "event-regrade-refuted")

        confirmation_shop = claim_review("review-claim-confirmation-shop", "2026-07-10T00:15:59.300000Z", "confirmed", "F-selftest", 3, "event-regrade-refuted"); confirmation_shop["input_refs"] = sorted({*review3["input_refs"], "event-regrade-refuted"}); confirmation_shop["input_hash"] = compute_review_input_hash(refuted_case, confirmation_shop, build_reference_index(refuted_case)); confirmation_shop_path = refuted_reviews / "claim-confirmation-shop.json"; confirmation_shop_path.write_bytes(canonical_json_bytes(confirmation_shop))
        _append_kernel_event(refuted_case, base_event(event_id="event-claim-confirmation-shop-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.400000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit an adversarial later confirmation review.", payload={"record_path": "reviews/claim-confirmation-shop.json", "record_digest": sha256_file(confirmation_shop_path), "record_type": "review", "record_id": "review-claim-confirmation-shop", "record_revision": None}))
        confirmation_shop_code = None
        try:
            _append_kernel_event(refuted_case, base_event(event_id="event-claim-confirmation-shop", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.500000Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="A later confirmation must not erase independent refutation debt.", payload={"entity_id": "F-selftest", "status": "confirmed", "review_ref": "review-claim-confirmation-shop", "review_digest": sha256_file(confirmation_shop_path)}, review_refs=["review-claim-confirmation-shop"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": "confirmed", "current": "confirmed"}]))
        except RecordError as exc:
            confirmation_shop_code = exc.code

        refutation_claim = claim_review("review-claim-refuted", "2026-07-10T00:15:59.600000Z", "refuted", "F-selftest", 3, "event-regrade-refuted"); refutation_claim["input_refs"] = sorted({*review3["input_refs"], "event-regrade-refuted"}); refutation_claim["input_hash"] = compute_review_input_hash(refuted_case, refutation_claim, build_reference_index(refuted_case)); refutation_claim_path = refuted_reviews / "claim-refuted.json"; refutation_claim_path.write_bytes(canonical_json_bytes(refutation_claim))
        _append_kernel_event(refuted_case, base_event(event_id="event-claim-refuted-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.700000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit the refutation-bound claim review.", payload={"record_path": "reviews/claim-refuted.json", "record_digest": sha256_file(refutation_claim_path), "record_type": "review", "record_id": "review-claim-refuted", "record_revision": None}))
        _append_kernel_event(refuted_case, base_event(event_id="event-claim-refuted", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.800000Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Fresh claim adjudication records the independent refutation.", payload={"entity_id": "F-selftest", "status": "refuted", "review_ref": "review-claim-refuted", "review_digest": sha256_file(refutation_claim_path)}, review_refs=["review-claim-refuted"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": "confirmed", "current": "refuted"}]))
        refuted_adjudicated_state = reduce_engagement(refuted_case); refuted_queue_row = next(item for item in refuted_adjudicated_state["work_queue"] if item["class"] == "review_obligation_open" and item["entity"]["id"] == "event-regrade-refuted"); refuted_next_action = decorate_work_queue_item(refuted_queue_row, refuted_adjudicated_state, refuted_case)["next_action"]
        checks.append(("refuted regrade becomes disposition-bound debt that rejects confirmation-shopping and advances only after a fresh exact refutation adjudication", refuted_row.get("required_claim_status") == "refuted" and confirmation_shop_code == "claim_review_obligation_disposition_mismatch" and refuted_adjudicated_state["claim_adjudications"]["F-selftest"]["status"] == "refuted" and _filing_blocking_review_error(refuted_adjudicated_state, "F-selftest") is None and refuted_next_action["action_id"] == "request_finding_revision_authority", str({"row": refuted_row, "shop": confirmation_shop_code, "action": refuted_next_action})))

        blocked_review = json.loads(json.dumps(correction)); blocked_review.update({"review_id": "review-regrade-blocked", "recorded_at": "2026-07-10T00:15:59Z", "finding_revision": 3, "verdict": "blocked", "rationale": "Pinned proof environment is unavailable; truth remains unchanged.", "corrections": [], "required_next_actions": ["restore pinned environment"], "claim_tuple_hash": tuple_hash3, "prior_review_run_ids": ["run-review-claim-3"], "escalation_claims": [], "blocked_reason": "Pinned proof environment unavailable."}); blocked_review["independence"].update({"reviewer_id": "blocked-reviewer", "reviewer_run_id": "run-regrade-blocked", "originating_run_id": "event-finding-revision-3"}); blocked_review["input_hash"] = compute_review_input_hash(engagement, blocked_review, build_reference_index(engagement)); blocked_path = reviews_dir / "regrade-blocked.json"; blocked_path.write_bytes(canonical_json_bytes(blocked_review))
        blocked_commit = base_event(event_id="event-regrade-blocked-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.200000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit blocked regrade.", payload={"record_path": "reviews/regrade-blocked.json", "record_digest": sha256_file(blocked_path), "record_type": "review", "record_id": "review-regrade-blocked", "record_revision": None}); append_event(engagement, blocked_commit)
        blocked_event = base_event(event_id="event-regrade-blocked", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.500000Z", actor_role="reviewer", actor_id="blocked-reviewer", event_type="review.regrade_completed", rationale="Blocked review records no truth change.", payload={"review_ref": "review-regrade-blocked", "finding_id": "F-selftest", "finding_revision": 3, "verdict": "blocked", "claim_tuple_hash": tuple_hash3}, review_refs=["review-regrade-blocked"], finding_refs=["F-selftest"]); append_event(engagement, blocked_event)
        blocked_state = reduce_engagement(engagement); checks.append(("typed blocked regrade preserves finding truth and names blocker", blocked_state["findings"]["F-selftest"]["status"] == "confirmed" and _filing_blocking_review_error(blocked_state, "F-selftest") == "regrade_review_blocked" and any(item["status"] == "blocked" for item in blocked_state["outstanding_reviews"]), str(blocked_state["outstanding_reviews"])))
        blocked_source = root / "blocked-review-source"; shutil.copytree(engagement, blocked_source)
        blocked_manual_filing = copy.deepcopy(filing3); blocked_manual_filing["event_id"] = "event-blocked-manual-filing"; blocked_manual_filing["recorded_at"] = "2026-07-10T00:16:00Z"; blocked_manual_filing["payload"].update({"finding_revision": 4, "supersedes_revision": 3, "resolves_review_refs": []})
        blocked_manual_code = historical_reduction_rejection(blocked_source, blocked_manual_filing)
        blocked_queue_row = next(item for item in blocked_state["work_queue"] if item["class"] == "review_obligation_open" and item["entity"]["id"] == "event-regrade-blocked")
        blocked_next_action = decorate_work_queue_item(blocked_queue_row, blocked_state, engagement.absolute())["next_action"]

        def supersede_blocked_regrade(case: Path, suffix: str, verdict: str) -> dict[str, Any]:
            fresh = json.loads(json.dumps(blocked_review)); fresh.update({"review_id": f"review-regrade-supersede-{suffix}", "recorded_at": "2026-07-10T00:16:00.100000Z", "verdict": verdict, "rationale": f"Fresh independent review records {verdict} without hiding prior debt.", "corrections": [], "required_next_actions": ["preserve the replacement blocker"] if verdict == "blocked" else [], "prior_review_run_ids": ["run-regrade-blocked"], "blocked_reason": "Fresh review remains blocked." if verdict == "blocked" else None}); fresh["independence"].update({"reviewer_id": f"superseding-reviewer-{suffix}", "reviewer_run_id": f"run-regrade-supersede-{suffix}", "originating_run_id": "event-finding-revision-3"}); fresh["input_hash"] = compute_review_input_hash(case, fresh, build_reference_index(case)); fresh_path = case / "reviews" / f"regrade-supersede-{suffix}.json"; fresh_path.write_bytes(canonical_json_bytes(fresh))
            _append_kernel_event(case, base_event(event_id=f"event-regrade-supersede-{suffix}-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:16:00.200000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit fresh exact superseding regrade.", payload={"record_path": f"reviews/regrade-supersede-{suffix}.json", "record_digest": sha256_file(fresh_path), "record_type": "review", "record_id": fresh["review_id"], "record_revision": None}))
            _append_kernel_event(case, base_event(event_id=f"event-regrade-supersede-{suffix}", engagement_id=engagement.name, recorded_at="2026-07-10T00:16:00.300000Z", actor_role="reviewer", actor_id=fresh["independence"]["reviewer_id"], event_type="review.regrade_completed", rationale="Explicitly supersede only the exact named blocked row.", payload={"review_ref": fresh["review_id"], "finding_id": "F-selftest", "finding_revision": 3, "verdict": verdict, "claim_tuple_hash": tuple_hash3, "resolves_review_refs": ["event-regrade-blocked"]}, review_refs=[fresh["review_id"]], finding_refs=["F-selftest"]))
            return reduce_engagement(case)

        supersede_confirmed_case = root / "blocked-review-superseded-confirmed"; shutil.copytree(blocked_source, supersede_confirmed_case); superseded_confirmed_state = supersede_blocked_regrade(supersede_confirmed_case, "confirmed", "confirmed")
        supersede_blocked_case = root / "blocked-review-superseded-blocked"; shutil.copytree(blocked_source, supersede_blocked_case); superseded_blocked_state = supersede_blocked_regrade(supersede_blocked_case, "blocked", "blocked")
        replacement_blocked_rows = [row for row in superseded_blocked_state["outstanding_reviews"] if row.get("review_type") == "regrade" and row.get("status") == "blocked"]
        blocked_action_text = str(blocked_next_action["required_inputs"])
        checks.append(("blocked review debt rejects filing and supports only exact prior-run supersession; blocked-to-blocked replaces rather than erases debt", blocked_manual_code == "regrade_review_blocked" and blocked_next_action["action_id"] == "supersede_blocked_review_obligation" and "event-regrade-blocked" in blocked_action_text and "verdict is confirmed" not in blocked_action_text and not any(row.get("review_ref") == "event-regrade-blocked" for row in superseded_confirmed_state["outstanding_reviews"]) and _filing_blocking_review_error(superseded_confirmed_state, "F-selftest") is None and superseded_confirmed_state["findings"]["F-selftest"]["status"] == "confirmed" and len(replacement_blocked_rows) == 1 and replacement_blocked_rows[0]["review_ref"] == "event-regrade-supersede-blocked" and superseded_blocked_state["findings"]["F-selftest"]["status"] == "confirmed", str({"manual": blocked_manual_code, "action": blocked_next_action, "confirmed": superseded_confirmed_state["outstanding_reviews"], "blocked": replacement_blocked_rows})))
        current_report = generate_report(engagement, "F-selftest", 3, ["claim-mechanism", "claim-reach", "claim-impact"], [], "operator-selftest", "2026-07-10T00:15:59.600000Z")
        accept_report(engagement, current_report["report_id"], "operator-selftest", "Claims and proof links match revision three.", "2026-07-10T00:15:59.700000Z")
        submission_path = engagement / "submissions" / "F-selftest.txt"; submission_path.write_text("Operator-authored external submission for F-selftest revision 3.\n", encoding="utf-8")
        submission_id = record_submission(engagement, current_report["report_id"], submission_path, "selftest-program", "operator-selftest", "2026-07-10T00:15:59.800000Z")
        submitted_state = reduce_engagement(engagement); checks.append(("external submission remains separate, operator-authored, and reduced from events", submitted_state["reports"][current_report["report_id"]]["status"] == "submitted" and submission_id in submitted_state["submission_refs"] and submission_path.read_bytes() != (engagement / current_report["report_path"]).read_bytes(), str(submitted_state["reports"])))
        package_fixture.write_bytes(b"changed pinned package fixture\n"); changed_digest = sha256_file(package_fixture); collect_preflight(engagement, preflight_id="preflight-changed-target", mode="package", target=package_fixture, expected_identity=changed_digest, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:15:59.850000Z", operator_redaction_attested=True)
        stale_attempt = attempt_proposal("attempt-stale-environment", "2026-07-10T00:15:59.900000Z", "environment_check", "no_signal", "Attempt incorrectly tries to reuse the superseded target identity.", []); stale_environment_blocked = False
        try:
            append_attempt(engagement, stale_attempt)
        except RecordError as exc:
            stale_environment_blocked = exc.code == "attempt_environment_not_active"
        checks.append(("changing target identity prevents stale preflight reuse", stale_environment_blocked and reduce_engagement(engagement)["active_environment_ref"] == "preflight-changed-target" and all(item["attempt_id"] != "attempt-stale-environment" for item in read_ledger(engagement, "attempt")), "stale preflight was reused"))

        rendered = render_claim_proof(finding2)
        checks.append(("claim-to-proof rendering binds every atomic claim and preserves inferred impact labels", tuple_hash in rendered and all(claim_id in rendered for claim_id in ("claim-mechanism", "claim-reach", "claim-impact")) and "demonstrated" in rendered, rendered))

        manifest_path = engagement / "legacy" / "migration-manifest.json"; manifest_path.parent.mkdir(exist_ok=True); manifest_path.write_bytes(canonical_json_bytes({"schema_version": 1, "migration_id": "migration-selftest", "engagement_id": engagement.name, "recorded_at": "2026-07-10T00:16:00Z", "source_inventory_hash": "sha256:" + "0" * 64, "operator": {"role": "operator", "id": "operator-selftest"}, "entries": [], "outcome_counts": {"imported": 0, "needs_review": 0, "skipped": 0, "errors": 0}}))
        commit_event = base_event(event_id="event-record-committed", engagement_id=engagement.name, recorded_at="2026-07-10T00:16:00Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit immutable self-test migration manifest.", payload={"record_path": "legacy/migration-manifest.json", "record_digest": sha256_file(manifest_path), "record_type": "migration-manifest", "record_id": "migration-selftest", "record_revision": None})
        append_event(engagement, commit_event)
        checks.append(("record.committed binds an existing immutable file digest", reduce_engagement(engagement)["last_event_id"] == "event-record-committed", "committed file not reducible"))
        missing_commit = base_event(event_id="event-missing-record", engagement_id=engagement.name, recorded_at="2026-07-10T00:16:30Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Missing committed file must fail.", payload={"record_path": "reports/missing.manifest.json", "record_digest": "sha256:" + "0" * 64, "record_type": "report-manifest", "record_id": "report-manifest-missing", "record_revision": None})
        before_missing_commit = (engagement / "events.jsonl").read_bytes(); missing_commit_caught = False
        try:
            append_event(engagement, missing_commit)
        except RecordError as exc:
            missing_commit_caught = exc.code == "committed_file_missing"
        checks.append(("record.committed cannot point to a missing file", missing_commit_caught and (engagement / "events.jsonl").read_bytes() == before_missing_commit, "missing file commit appended"))
        committed_tampered = root / "committed-tampered"; shutil.copytree(engagement, committed_tampered); (committed_tampered / "legacy" / "migration-manifest.json").write_text("{}\n")
        committed_tamper_caught = False
        try:
            reduce_engagement(committed_tampered)
        except RecordError as exc:
            committed_tamper_caught = exc.code == "committed_file_digest_mismatch"
        checks.append(("modified committed record fails reduction", committed_tamper_caught, "modified committed record accepted"))
        report_tampered = root / "report-tampered"; shutil.copytree(engagement, report_tampered); (report_tampered / "reports" / "F-selftest-r3.md").write_text("tampered report\n", encoding="utf-8")
        report_tamper_blocked = False
        try:
            reduce_engagement(report_tampered)
        except RecordError as exc:
            report_tamper_blocked = exc.code == "report_manifest_binding_mismatch"
        checks.append(("report byte replacement fails revision-bound reduction", report_tamper_blocked, "tampered report reduced"))
        record_orphan = root / "record-orphan"; shutil.copytree(engagement, record_orphan); (record_orphan / "reports" / "orphan.manifest.json").write_text("{}\n")
        record_orphan_caught = False
        try:
            reduce_engagement(record_orphan)
        except RecordError as exc:
            record_orphan_caught = exc.code == "orphan_immutable_record"
        checks.append(("orphan immutable record fails reduction", record_orphan_caught, "orphan record accepted"))
        report_orphan = root / "report-orphan"; shutil.copytree(engagement, report_orphan); (report_orphan / "reports" / "rogue.md").write_text("# unbound advisory\n", encoding="utf-8")
        report_orphan_blocked = False
        try:
            reduce_engagement(report_orphan)
        except RecordError as exc:
            report_orphan_blocked = exc.code == "orphan_report_file"
        checks.append(("unbound advisory Markdown fails reduction", report_orphan_blocked, "unbound advisory accepted"))

        current = reduce_engagement(engagement)
        tampered = root / "tampered"; shutil.copytree(engagement, tampered)
        lines = (tampered / "events.jsonl").read_text().splitlines(); value = json.loads(lines[1]); value["rationale"] += " tampered"; lines[1] = json.dumps(value, sort_keys=True, separators=(",", ":")); (tampered / "events.jsonl").write_text("\n".join(lines) + "\n")
        tamper_caught = False
        try:
            read_ledger(tampered, "event")
        except RecordError as exc:
            tamper_caught = exc.code == "ledger_record_hash_mismatch"
        checks.append(("one-byte-equivalent ledger tamper is detected", tamper_caught, "tampered event accepted"))
        noncanonical = root / "noncanonical"; shutil.copytree(engagement, noncanonical)
        lines = (noncanonical / "events.jsonl").read_text().splitlines(); first_value = json.loads(lines[0]); lines[0] = json.dumps(dict(reversed(list(first_value.items()))), separators=(",", ":")); (noncanonical / "events.jsonl").write_text("\n".join(lines) + "\n")
        noncanonical_caught = False
        try:
            read_ledger(noncanonical, "event")
        except RecordError as exc:
            noncanonical_caught = exc.code == "ledger_noncanonical_line"
        checks.append(("noncanonical historical JSONL text fails even when values are unchanged", noncanonical_caught, "noncanonical line accepted"))
        blank = root / "blank-line"; shutil.copytree(engagement, blank)
        lines = (blank / "events.jsonl").read_bytes().splitlines(keepends=True); (blank / "events.jsonl").write_bytes(lines[0] + b"\n" + b"".join(lines[1:]))
        blank_caught = False
        try:
            read_ledger(blank, "event")
        except RecordError as exc:
            blank_caught = exc.code == "ledger_blank_line"
        checks.append(("blank physical JSONL lines fail", blank_caught, "blank line accepted"))

        cross_ledger = root / "cross-ledger"; shutil.copytree(engagement, cross_ledger)
        artifact_lines = [json.loads(line) for line in (cross_ledger / "artifacts.jsonl").read_text().splitlines()]; artifact_lines[-1]["engagement_id"] = "eng-other"; artifact_lines[-1]["record_hash"] = compute_record_hash(artifact_lines[-1]); (cross_ledger / "artifacts.jsonl").write_bytes(b"".join(canonical_json_bytes(item) for item in artifact_lines))
        cross_caught = False
        try:
            reduce_engagement(cross_ledger)
        except RecordError as exc:
            cross_caught = exc.code == "cross_engagement_ledger_record"
        checks.append(("direct-ledger cross-engagement records fail reduction", cross_caught, "cross-engagement artifact reduced"))
        dangling = root / "dangling-ref"; shutil.copytree(engagement, dangling)
        artifact_lines = [json.loads(line) for line in (dangling / "artifacts.jsonl").read_text().splitlines()]; artifact_lines[-1]["target_refs"] = ["target-missing"]; artifact_lines[-1]["record_hash"] = compute_record_hash(artifact_lines[-1]); (dangling / "artifacts.jsonl").write_bytes(b"".join(canonical_json_bytes(item) for item in artifact_lines))
        dangling_caught = False
        try:
            reduce_engagement(dangling)
        except RecordError as exc:
            dangling_caught = exc.code == "record_reference_invalid"
        checks.append(("direct-ledger dangling references fail reduction", dangling_caught, "dangling artifact reference reduced"))
        collision = root / "cross-type-id-collision"; shutil.copytree(engagement, collision)
        collision_event = base_event(event_id="artifact-selftest", engagement_id=engagement.name, recorded_at="2026-07-10T00:17:00Z", actor_role="operator", actor_id="operator-selftest", event_type="observation.recorded", rationale="Cross-type ID collision attack.", payload={"entity_id": "collision-observation", "entity_type": "observation", "status": "recorded"}); append_ledger_record(collision, "event", collision_event)
        collision_blocked = False
        try:
            reduce_engagement(collision)
        except RecordError as exc:
            collision_blocked = exc.code == "cross_type_record_id_collision"
        checks.append(("record IDs cannot collide across event/attempt/artifact/review types", collision_blocked, "cross-type collision reduced"))

        interrupted = root / "interrupted"; shutil.copytree(engagement, interrupted)
        with open(interrupted / "events.jsonl", "ab") as handle: handle.write(b'{\"partial\"')
        interrupted_caught = False
        try:
            read_ledger(interrupted, "event")
        except RecordError as exc:
            interrupted_caught = exc.code == "ledger_unterminated_tail"
        checks.append(("interrupted JSONL tail fails closed without truncation", interrupted_caught, "partial tail accepted"))
        repaired = repair_ledger_tail(interrupted, "event", "operator-selftest", "injected partial append", "2026-07-10T00:17:30Z")
        checks.append(("operator repair quarantines the partial tail and records recovery", (interrupted / repaired["quarantine_path"]).read_bytes() == b'{\"partial\"' and read_ledger(interrupted, "event")[-1]["event_id"] == repaired["event_id"], str(repaired)))

        pending = root / "pending-repair"; shutil.copytree(engagement, pending)
        pending_tail = b'{\"pending\"'; pending_path = pending / "events.jsonl"; prefix = pending_path.read_bytes(); pending_path.write_bytes(prefix + pending_tail)
        pending_digest = sha256_bytes(pending_tail); quarantine_rel = f"legacy/quarantine/event-tail-{pending_digest[-12:]}.bin"; (pending / "legacy" / "quarantine").mkdir(parents=True, exist_ok=True); (pending / quarantine_rel).write_bytes(pending_tail)
        marker = {"schema_version": 1, "ledger_kind": "event", "ledger_path": "events.jsonl", "prefix_digest": sha256_bytes(prefix), "quarantine_path": quarantine_rel, "quarantine_digest": pending_digest, "operator_id": "operator-selftest", "reason": "resume fixture", "recorded_at": "2026-07-10T00:17:45Z"}; (pending / "legacy" / "tail-repair.pending.json").write_bytes(canonical_json_bytes(marker))
        resumed = repair_ledger_tail(pending, "event", "operator-selftest", "resume fixture", "2026-07-10T00:17:45Z")
        checks.append(("repair resumes deterministically after crash between truncation and event", not (pending / "legacy" / "tail-repair.pending.json").exists() and read_ledger(pending, "event")[-1]["event_id"] == resumed["event_id"], str(resumed)))

        authorized_repair = root / "authorized-repair"; shutil.copytree(engagement, authorized_repair); broker_id, broker_session = _local_identity("broker"); repair_now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); repair_action = _authority_action("repair-ledger-tail", lane_id="lane-repair", executor_id=broker_id, session_id=broker_session, ledger="attempt", operator_id="operator-selftest", reason="repair approved interrupted attempt tail", recorded_at=repair_now); repair_digest = sha256_bytes(canonical_json_bytes(repair_action)); repair_action_relative = "authority/requests/request-repair.action.json"; atomic_write(authorized_repair / repair_action_relative, canonical_json_bytes(repair_action)); repair_state = reduce_engagement(authorized_repair)
        append_event(authorized_repair, base_event(event_id="event-request-repair", engagement_id=repair_state["engagement_id"], recorded_at=repair_now, actor_role="broker", actor_id=broker_id, event_type="authority.requested", rationale="Request exact interrupted-tail repair.", payload={"request_id": "request-repair", "action_kind": "repair-ledger-tail", "action_digest": repair_digest, "action_path": repair_action_relative, "lane_id": "lane-repair", "request_status": "pending_authority", "scope_hash": repair_state["scope_hash"], "environment_ref": repair_state["active_environment_ref"], "expires_at": "2099-07-10T00:00:00Z"}, session_id=broker_session, operation_class="notebook")); append_event(authorized_repair, base_event(event_id="event-resolution-repair", engagement_id=repair_state["engagement_id"], recorded_at=repair_now, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve exact repair only.", payload={"request_id": "request-repair", "request_event_ref": "event-request-repair", "action_digest": repair_digest, "resolution": "approved", "resolved_at": repair_now}, entity_refs=["event-request-repair"], session_id=broker_session, operation_class="authority"))
        with open(authorized_repair / "attempts.jsonl", "ab") as handle: handle.write(b'{"interrupted-attempt"')
        command_repair_tail(argparse.Namespace(engagement=authorized_repair, ledger="attempt", operator_id="operator-selftest", reason="repair approved interrupted attempt tail", recorded_at=repair_now, authority_request_id="request-repair", lane_id="lane-repair", executor_id=broker_id, session_id=broker_session)); checks.append(("approved tail repair verifies authority from intact event prefix before reducing damaged ledger", (authorized_repair / "attempts.jsonl").read_bytes().endswith(b"\n") and read_ledger(authorized_repair, "event")[-1]["payload"].get("authority_request_ref") == "request-repair", "authorized repair did not recover"))

        rollback_event = base_event(event_id="event-short-write", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:00Z", actor_role="operator", actor_id="operator-selftest", event_type="observation.recorded", rationale="Injected short write must roll back.", payload={"entity_id": "observation-short", "entity_type": "observation", "status": "recorded"})
        before_short = (engagement / "events.jsonl").read_bytes(); real_write = __import__("os").write; write_calls = [0]
        def injected_write(fd, data):
            write_calls[0] += 1
            if write_calls[0] == 1:
                return real_write(fd, data[:5])
            raise OSError("injected append interruption")
        short_rolled_back = False
        from unittest.mock import patch
        try:
            with patch("engagement_state.os.write", side_effect=injected_write):
                append_ledger_record(engagement, "event", rollback_event)
        except RecordError as exc:
            short_rolled_back = exc.code == "ledger_append_rolled_back"
        checks.append(("partial append is truncated to the last verified boundary", short_rolled_back and (engagement / "events.jsonl").read_bytes() == before_short and len(read_ledger(engagement, "event")) == current["event_count"], "short write left a tail"))

        forged_prior = base_event(event_id="event-prior-forged-operator", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:05Z", actor_role="operator", actor_id="other-operator", event_type="operator_prior.recorded", rationale="Role label alone must not grant signed-scope authority.", payload={"prior_id": "prior-forged", "prior_statement": "Forged authority.", "strength": "strong", "reason": "adversarial fixture"})
        forged_prior_blocked = False
        try:
            append_event(engagement, forged_prior)
        except RecordError as exc:
            forged_prior_blocked = exc.code == "operator_prior_not_scope_authorized"
        checks.append(("operator prior actor is bound to active signed-scope operator", forged_prior_blocked and (engagement / "events.jsonl").read_bytes() == before_short, "forged operator prior appended"))

        future_refs = root / "future-candidate-refs"; shutil.copytree(engagement, future_refs)
        future_candidate = base_event(event_id="event-candidate-future", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:10Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Adversarial candidate references later provenance.", payload={"candidate_id": "candidate-future", "source_observation_ref": "event-observation-future", "routing_review_ref": "event-routing-future", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-observation-future", "event-routing-future"], state_changes=[{"dimension": "search", "entity_id": "candidate-future", "previous": None, "current": "queued"}]); future_candidate["ex_ante"] = {"probability": 0.9, "ordinal": "strong", "recorded_before_outcome": True}
        append_ledger_record(future_refs, "event", future_candidate)
        future_observation = base_event(event_id="event-observation-future", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:11Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Later observation.", payload={"entity_id": "observation-future", "entity_type": "observation", "status": "recorded"}); append_ledger_record(future_refs, "event", future_observation)
        future_routing = base_event(event_id="event-routing-future", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:12Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Later routing assessment.", payload={"entity_id": "routing-future", "source_observation_ref": "event-observation-future", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "assessed"}, entity_refs=["event-observation-future"]); append_ledger_record(future_refs, "event", future_routing)
        future_ref_blocked = False
        try:
            reduce_engagement(future_refs)
        except RecordError as exc:
            future_ref_blocked = exc.code == "candidate_source_not_prior_observation"
        checks.append(("candidate provenance must exist earlier in the event ledger", future_ref_blocked, "candidate referenced future provenance"))

        precommit = root / "precommit-reference"; shutil.copytree(engagement, precommit); (precommit / "reviews").mkdir(exist_ok=True)
        review_record = {"schema_version": 1, "review_id": "review-precommit", "engagement_id": engagement.name, "review_type": "signal", "proposed_finding_id": None, "entity_ref": "event-observation-c1", "finding_revision": None, "recorded_at": "2026-07-10T00:18:20Z", "input_refs": ["event-observation-c1"], "input_hash": "sha256:" + "0" * 64, "evidence_refs": [], "conflicting_evidence": [], "independence": {"reviewer_id": "reviewer-selftest", "reviewer_model": "selftest", "reviewer_run_id": "run-review-precommit", "originating_run_id": "event-observation-c1", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Refute the routing signal."}, "verdict": "strong", "rationale": "Signal review fixture.", "corrections": [], "required_next_actions": ["route candidate"]}
        review_record["input_hash"] = compute_review_input_hash(precommit, review_record, build_reference_index(precommit))
        review_path = precommit / "reviews" / "precommit.json"; review_path.write_bytes(canonical_json_bytes(review_record))
        precommit_candidate = base_event(event_id="event-candidate-precommit", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:30Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Adversarial pre-commit review reference.", payload={"candidate_id": "candidate-precommit", "source_observation_ref": "event-observation-c1", "routing_review_ref": "review-precommit", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-observation-c1", "review-precommit"], state_changes=[{"dimension": "search", "entity_id": "candidate-precommit", "previous": None, "current": "queued"}]); precommit_candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}; append_ledger_record(precommit, "event", precommit_candidate)
        later_commit = base_event(event_id="event-review-later-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:31Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit arrives after forbidden use.", payload={"record_path": "reviews/precommit.json", "record_digest": sha256_file(review_path), "record_type": "review", "record_id": "review-precommit", "record_revision": None}); append_ledger_record(precommit, "event", later_commit)
        precommit_blocked = False
        try:
            reduce_engagement(precommit)
        except RecordError as exc:
            precommit_blocked = exc.code == "record_reference_precedes_commit"
        checks.append(("immutable review must be committed before it can influence search", precommit_blocked, "future record commitment authorized prior reference"))

        dry_bypass = root / "dry-bypass"; shutil.copytree(engagement, dry_bypass)
        fake_review_event = base_event(event_id="event-coverage-review-fake", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:20Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="review.coverage_completed", rationale="Missing cold review record.", payload={"review_type": "coverage", "verdict": "coverage_dry"}); append_ledger_record(dry_bypass, "event", fake_review_event)
        dry_event = base_event(event_id="event-dry-bypass", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:21Z", actor_role="operator", actor_id="operator-selftest", event_type="coverage.status_changed", rationale="Attempt to close coverage around active work.", payload={"entity_id": engagement.name, "status": "coverage_dry", "coverage_review_ref": "event-coverage-review-fake"}, entity_refs=["event-coverage-review-fake"], state_changes=[{"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "coverage_dry"}]); append_ledger_record(dry_bypass, "event", dry_event)
        dry_bypass_blocked = False
        try:
            reduce_engagement(dry_bypass)
        except RecordError as exc:
            dry_bypass_blocked = exc.code == "coverage_review_event_invalid"
        checks.append(("coverage_dry cannot bypass a committed cold coverage review", dry_bypass_blocked, "dry coverage accepted without cold review"))

        drifted = root / "scope-drift"; shutil.copytree(engagement, drifted)
        with open(drifted / "scope.md", "a", encoding="utf-8") as handle: handle.write("\nchanged\n")
        before_drift_write = (drifted / "events.jsonl").read_bytes(); old_scope_after_drift = reduce_engagement(drifted)["scope_hash"]
        broker_id, broker_session = _local_identity("broker"); ordinary_after_drift = base_event(event_id="event-after-scope-drift", engagement_id=engagement.name, recorded_at="2026-07-10T00:19:00Z", actor_role="broker", actor_id=broker_id, event_type="observation.recorded", rationale="Continue a lane already bounded by the prior attestation.", payload={"entity_id": "observation-drift", "entity_type": "observation", "status": "recorded"}, session_id=broker_session, operation_class="notebook"); append_event(drifted, ordinary_after_drift)
        command_propose_scope(argparse.Namespace(engagement=drifted, draft=drifted/"scope.md", actor_id=broker_id, session_id=broker_session, recorded_at="2026-07-10T00:19:01Z", reason="Preserve drifted bytes without activating them.")); drift_state = reduce_engagement(drifted)
        checks.append(("scope drift is preserved as an unattested draft while old-scope lanes continue", old_scope_after_drift == current["scope_hash"] and drift_state["scope_hash"] == current["scope_hash"] and drift_state["scope_drafts"] and (drifted/str(drift_state["scope_drafts"][-1]["draft_path"])).is_file() and (drifted / "events.jsonl").read_bytes().startswith(before_drift_write), "scope drift was activated, lost, or globally stalled"))
        operator_drift = root/"operator-drift"; shutil.copytree(engagement, operator_drift); operator_drift.joinpath("scope.md").write_text(operator_drift.joinpath("scope.md").read_text().replace("Operator: operator-selftest", "Operator: attacker")); redirected_operator_blocked = False
        try: _require_operator_console(operator_drift, "attacker", "resolve-authority")
        except RecordError as exc: redirected_operator_blocked = exc.code == "operator_authority_invalid"
        checks.append(("drifted scope bytes cannot redirect active operator authority", redirected_operator_blocked, "draft operator replaced attested operator"))
        active_hash = current["scope_hash"]
        new_hash = sha256_file(drifted / "scope.md")
        model_reattestation = base_event(event_id="event-model-scope", engagement_id=engagement.name, recorded_at="2026-07-10T00:19:30Z", actor_role="orchestrator", actor_id="model-orchestrator", event_type="scope.attested", rationale="Model must not re-attest scope.", payload={"scope_hash": new_hash, "operator_id": "operator-selftest", "signed_date": "2026-07-10", "record_kernel": "decision-0006-v1", "supersedes_scope_hash": active_hash}, entity_refs=[engagement.name])
        model_scope_blocked = False
        try:
            append_event(drifted, model_reattestation)
        except RecordError as exc:
            model_scope_blocked = exc.code in {"scope_attestation_not_operator_bound", "scope_reattestation_not_operator_bound"}
        checks.append(("model-role scope re-attestation is rejected", model_scope_blocked and reduce_engagement(drifted)["scope_hash"] == active_hash, "model re-attested scope"))
        model_injected = root / "model-scope-injected"; shutil.copytree(drifted, model_injected); injected_proposal = json.loads(json.dumps(model_reattestation)); injected_proposal["payload"]["scope_snapshot_path"] = persist_scope_snapshot(model_injected, new_hash); append_ledger_record(model_injected, "event", injected_proposal)
        injected_scope_caught = False
        try:
            reduce_engagement(model_injected)
        except RecordError as exc:
            injected_scope_caught = exc.code in {"scope_attestation_not_operator_bound", "historical_scope_attestation_mismatch"}
        checks.append(("reducer rejects directly injected model scope authority", injected_scope_caught, "direct model scope event reduced"))
        reattestation = base_event(event_id="event-scope-reattested", engagement_id=engagement.name, recorded_at="2026-07-10T00:20:00Z", actor_role="operator", actor_id="operator-selftest", event_type="scope.attested", rationale="Operator re-attests changed scope bytes.", payload={"scope_hash": new_hash, "operator_id": "operator-selftest", "signed_date": "2026-07-10", "record_kernel": "decision-0006-v1", "supersedes_scope_hash": active_hash}, entity_refs=[engagement.name])
        append_event(drifted, reattestation)
        checks.append(("fresh operator scope re-attestation activates the draft without mutating history", reduce_engagement(drifted)["scope_hash"] == new_hash and (drifted / "events.jsonl").read_bytes().startswith(before_drift_write), "scope re-attestation failed or rewrote ledger"))

        closure_documents = test_corpus_documents(
            row_count=3,
            frozen_at="2026-07-10T00:20:59Z",
        )
        closure = root / "memory-closure"; closure.mkdir(); closure.joinpath("scope.md").write_text(scope_with_corpus_pin(scope.replace("self-test", "memory-closure"), closure_documents[1]), encoding="utf-8"); initialize_engagement(closure, "2026-07-10T00:21:00Z"); closure_state = reduce_engagement(closure)
        append_event(closure, base_event(event_id="event-closure-blocked", engagement_id=closure.name, recorded_at="2026-07-10T00:21:01Z", actor_role="operator", actor_id="operator-selftest", event_type="engagement.blocked", rationale="Exercise an evidence-preserving blocked closure.", payload={"entity_id": closure.name, "status": "blocked", "reason": "A bounded fixture blocker prevents coverage completion."}, state_changes=[{"dimension": "engagement", "entity_id": closure.name, "previous": "active", "current": "blocked"}, {"dimension": "coverage", "entity_id": closure.name, "previous": "active", "current": "blocked"}]))
        append_event(closure, base_event(event_id="event-cleanup-na", engagement_id=closure.name, recorded_at="2026-07-10T00:21:02Z", actor_role="operator", actor_id="operator-selftest", event_type="cleanup.updated", rationale="No live artifact cleanup exists.", payload={"entity_id": "cleanup-none", "status": "not_applicable", "scope_hash": closure_state["scope_hash"], "operator_id": "operator-selftest", "updated_at": "2026-07-10T00:21:02Z", "cleanup_obligations": [{"obligation_id": "cleanup-none", "kind": "no_live_artifacts", "status": "not_applicable", "artifact_refs": [], "rationale": "The engagement created no live target artifacts.", "closed_at": "2026-07-10T00:21:02Z"}]}, state_changes=[{"dimension": "cleanup", "entity_id": "cleanup-none", "previous": None, "current": "not_applicable"}]))
        missing_memory_blocked = False
        try: close_engagement(closure, "operator-selftest", "Must not close without memory disposition.", "2026-07-10T00:21:03Z")
        except RecordError as exc: missing_memory_blocked = exc.code == "engagement_closure_memory_missing"
        memory_proposal = {"schema_version": 1, "disposition_id": "memory-closure-final", "engagement_id": closure.name, "recorded_at": "2026-07-10T00:21:04Z", "scope_hash": closure_state["scope_hash"], "disposition": "no_novel_lesson", "lesson_kind": "none", "lesson_summary": None, "rationale": "Independent operator review found no reusable lesson.", "candidate_refs": [], "source_refs": {key: [] for key in ("event_refs", "candidate_refs", "hypothesis_refs", "attempt_refs", "artifact_refs", "review_refs", "finding_refs", "environment_refs")}, "sanitization": {"status": "not_applicable", "secret_scan_status": "clean", "target_identifiers_removed": True, "credential_values_removed": True, "harmful_recipe_removed": True, "target_terms_checked": [], "notes": "No lesson body exists to promote."}, "human_review": {"reviewer": {"role": "operator", "id": "operator-selftest"}, "reviewed_at": "2026-07-10T00:21:04Z", "decision": "no_novel_lesson", "rationale": "No novel lesson survived review.", "source_material_compared": True, "abstraction_only": True, "plane1_pr_required": True}, "reopening_condition": None, "provenance": {"actor": {"role": "operator", "id": "operator-selftest"}}}
        unsafe_promotion = json.loads(json.dumps(memory_proposal)); unsafe_promotion.update({"disposition": "promote", "lesson_kind": "negative", "lesson_summary": "A target-neutral defensive lesson.", "candidate_refs": ["candidate-c1"]}); unsafe_promotion["sanitization"].update({"status": "sanitized", "target_terms_checked": [closure.name]}); unsafe_promotion["human_review"]["decision"] = "promote"; unsafe_promotion["human_review"]["rationale"] = "Run curl against a retained endpoint."
        unsafe_promotion_blocked = False
        try: _validate_promotable_abstraction(unsafe_promotion)
        except RecordError as exc: unsafe_promotion_blocked = exc.code == "memory_abstraction_not_sanitized"
        checks.append(("promote scrubbing covers every retained human text field", unsafe_promotion_blocked, "unsafe review rationale passed promotion scrub"))
        proposal_path = root / "memory-proposal.json"; write_canonical_json(proposal_path, memory_proposal); recorded_memory = record_memory_disposition(closure, proposal_path, "operator-selftest"); retry_count = reduce_engagement(closure)["event_count"]; record_memory_disposition(closure, proposal_path, "operator-selftest")
        closure_manifest_ref, closure_tsv_ref = register_test_corpus(
            closure,
            row_count=3,
            created_at="2026-07-10T00:21:04Z",
            documents=closure_documents,
        )
        nonblocking_closure = root / "closure-with-awaiting-operator"
        shutil.copytree(closure, nonblocking_closure)
        pending_action = _authority_action(
            "test-authority",
            lane_id="lane-nonblocking-close",
            value="operator-may-answer-later",
        )
        pending_action_digest = sha256_bytes(canonical_json_bytes(pending_action))
        append_event(
            nonblocking_closure,
            base_event(
                event_id="event-nonblocking-close-authority-request",
                engagement_id=closure.name,
                recorded_at="2026-07-10T00:21:04.100000Z",
                actor_role="orchestrator",
                actor_id="orchestrator-selftest",
                event_type="authority.requested",
                rationale="Leave one operator decision pending without representing executable work.",
                payload={
                    "request_id": "request-nonblocking-close",
                    "action_kind": "test-authority",
                    "action_digest": pending_action_digest,
                    "lane_id": "lane-nonblocking-close",
                    "request_status": "pending_authority",
                    "scope_hash": closure_state["scope_hash"],
                    "environment_ref": None,
                    "expires_at": None,
                },
                session_id="session-nonblocking-close",
                operation_class="notebook",
            ),
        )
        nonblocking_before = reduce_engagement(nonblocking_closure)
        nonblocking_closed = close_engagement(
            nonblocking_closure,
            "operator-selftest",
            "Only a nonblocking operator decision remains.",
            "2026-07-10T00:21:04.200000Z",
        )
        checks.append((
            "actual engagement closure is permitted when the only queued row awaits the operator and is explicitly nonblocking",
            len(nonblocking_before["work_queue"]) == 1
            and nonblocking_before["work_queue"][0]["class"] == "awaiting_operator"
            and nonblocking_before["work_queue"][0]["blocking"] is False
            and nonblocking_closed["authority_requests"]["request-nonblocking-close"]["status"] == "pending_authority"
            and all(item["blocking"] is False for item in nonblocking_closed["work_queue"]),
            str({"before": nonblocking_before["work_queue"], "after": nonblocking_closed["work_queue"]}),
        ))
        budget_closure = root / "budget-closure"; shutil.copytree(closure, budget_closure); _append_kernel_event(budget_closure, base_event(event_id="event-budget-closure-bounded", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.500000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="coverage.status_changed", rationale="The bounded closure records two queue disposals against a frozen three-row corpus denominator.", payload={"entity_id": closure.name, "status": "budget_bounded", "disposed_count": 2, "enumerated_count": 3, "corpus_enumeration_ref": closure_manifest_ref}, evidence_refs=[closure_manifest_ref, closure_tsv_ref], state_changes=[{"dimension": "coverage", "entity_id": closure.name, "previous": "blocked", "current": "budget_bounded"}])); budget_closed = close_engagement(budget_closure, "operator-selftest", "Cleanup, budget-bounded coverage, reports, and memory are terminal.", "2026-07-10T00:21:05Z")
        checks.append(("budget-bounded is terminal coverage accepted by closure only with its frozen denominator and an empty blocking queue", budget_closed["coverage"] == "budget_bounded" and budget_closed["coverage_counts"]["enumerated_count"] == 3 and budget_closed["coverage_counts"]["corpus_enumeration_ref"] == closure_manifest_ref, str(budget_closed)))

        close_escape = root / "close-with-blocking-work"; shutil.copytree(closure, close_escape)
        append_event(close_escape, base_event(event_id="event-close-escape-prior", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.100000Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="Introduce one explicit unresolved branch after terminal coverage.", payload={"prior_id": "prior-close-escape", "prior_statement": "A branch remains unresolved.", "strength": "strong", "reason": "adversarial closure repro"}))
        close_escape_hypothesis = json.loads(json.dumps(hypothesis["payload"])); close_escape_hypothesis.update({"hypothesis_id": "hypothesis-close-escape", "origin_type": "operator_prior", "origin_ref": "event-close-escape-prior", "status": "queued"}); close_escape_hypothesis.pop("candidate_ref", None)
        append_event(close_escape, base_event(event_id="event-close-escape-hypothesis", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.200000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Leave one blocking hypothesis on the record.", payload=close_escape_hypothesis, entity_refs=["event-close-escape-prior"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-close-escape", "previous": None, "current": "queued"}]))
        append_event(close_escape, base_event(event_id="event-close-escape-hypothesis-selected", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.250000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Select the unresolved closure-control branch.", payload={"hypothesis_id": "hypothesis-close-escape", "status": "selected", "reason": "execute the closure-control branch", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The closure-control branch is selected.", "unresolved_questions": [], "next_route": close_escape_hypothesis["next_experiment"]}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-close-escape", "previous": "queued", "current": "selected"}]))
        append_event(close_escape, base_event(event_id="event-close-escape-hypothesis-running", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.300000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Begin the closure-control branch while leaving its first attempt unrecorded.", payload={"hypothesis_id": "hypothesis-close-escape", "status": "running", "reason": "begin the closure-control branch", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The branch is running and has no attempt yet.", "unresolved_questions": [], "next_route": close_escape_hypothesis["next_experiment"]}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-close-escape", "previous": "selected", "current": "running"}]))
        append_event(close_escape, base_event(event_id="event-close-escape-observation", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.310000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Record one source observation for a candidate that must remain queued.", payload={"entity_id": "observation-close-escape", "entity_type": "observation", "status": "recorded"}))
        append_event(close_escape, base_event(event_id="event-close-escape-routing", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.320000Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Route the closure-control observation into one bounded candidate.", payload={"entity_id": "routing-close-escape", "source_observation_ref": "event-close-escape-observation", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "assessed"}, entity_refs=["event-close-escape-observation"]))
        close_escape_candidate = base_event(event_id="event-close-escape-candidate", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.330000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Leave one valid proposed candidate queued at the closure gate.", payload={"candidate_id": "candidate-close-escape", "source_observation_ref": "event-close-escape-observation", "routing_review_ref": "event-close-escape-routing", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-close-escape-observation", "event-close-escape-routing"], state_changes=[{"dimension": "search", "entity_id": "candidate-close-escape", "previous": None, "current": "queued"}]); close_escape_candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}; append_event(close_escape, close_escape_candidate)
        close_escape_before = (close_escape / "events.jsonl").read_bytes()
        try:
            close_engagement(close_escape, "operator-selftest", "Attempt to close around blocking work.", "2026-07-10T00:21:05Z")
            close_escape_code = None
        except RecordError as exc:
            close_escape_code = exc.code
        close_escape_state = reduce_engagement(close_escape)
        close_escape_running_item = next((item for item in close_escape_state["work_queue"] if item["class"] == "hypothesis_running_unattempted" and item["entity"]["id"] == "hypothesis-close-escape"), None)
        close_escape_candidate_item = next((item for item in close_escape_state["work_queue"] if item["class"] == "candidate_undisposed" and item["entity"]["id"] == "candidate-close-escape"), None)
        close_escape_actions = {
            "hypothesis-close-escape": decorate_work_queue_item(close_escape_running_item, close_escape_state, close_escape)["next_action"]["action_id"] if close_escape_running_item else None,
            "candidate-close-escape": decorate_work_queue_item(close_escape_candidate_item, close_escape_state, close_escape)["next_action"]["action_id"] if close_escape_candidate_item else None,
        }
        checks.append(("engagement close refuses a real queued-selected-running zero-attempt hypothesis and a still-queued candidate", close_escape_code == "engagement_closure_work_remaining" and (close_escape / "events.jsonl").read_bytes() == close_escape_before and close_escape_running_item is not None and close_escape_candidate_item is not None and close_escape_actions == {"hypothesis-close-escape": "record_hunter_primary", "candidate-close-escape": "select_candidate"}, str((close_escape_code, close_escape_state["work_queue"], close_escape_actions))))

        override_reason = "Operator accepts the exact listed residual work and closes this synthetic fixture on the record."
        override_items = blocking_work_identities(project_current_terminal_work_state(close_escape_state, read_ledger(close_escape, "attempt"), coverage=close_escape_state["coverage"]))
        override_digest = sha256_bytes(canonical_json_bytes(override_items))
        override_session = _local_identity("operator")[1]
        override_payload = {
            "entity_id": closure.name,
            "terminal_kind": "engagement",
            "status": "closed",
            "reason": override_reason,
            "operator_id": "operator-selftest",
            "scope_hash": close_escape_state["scope_hash"],
            "blocking_items": override_items,
            "blocking_queue_digest": override_digest,
            **attempt_ledger_context(read_ledger(close_escape, "attempt")),
            "disposition_ref": close_escape_state["memory_disposition"]["disposition_ref"],
            "disposition_digest": close_escape_state["memory_disposition"]["disposition_digest"],
        }
        override_entity_refs = [close_escape_state["memory_disposition"]["disposition_ref"]]
        override_state_changes = [{
            "dimension": "engagement",
            "entity_id": closure.name,
            "previous": "blocked",
            "current": "closed",
        }]
        override_action = ending_override_action(
            engagement_id=closure.name,
            recorded_at="2026-07-10T00:21:05.500000Z",
            actor={"role": "operator", "id": "operator-selftest"},
            payload=override_payload,
            entity_refs=override_entity_refs,
            evidence_refs=[],
            state_changes=override_state_changes,
            session_id=override_session,
        )
        override_action_digest = sha256_bytes(canonical_json_bytes(override_action))
        override_events = read_ledger(close_escape, "event")
        override_challenge = operator_challenge_bytes(
            engagement_id=closure.name,
            scope_hash=close_escape_state["scope_hash"],
            ledger_hash=override_events[-1]["record_hash"],
            operation=f"override-ending:{override_action_digest}",
            operator_id="operator-selftest",
        )
        override_challenge_path = root / "ending-override-challenge.json"; override_challenge_path.write_bytes(override_challenge)
        override_argv = [sys.executable, str(Path(__file__).resolve()), "override-ending", "--engagement", str(close_escape), "--terminal-kind", "engagement", "--status", "closed", "--operator-id", "operator-selftest", "--session-id", override_session, "--recorded-at", "2026-07-10T00:21:05.500000Z", "--reason", override_reason]
        unsigned_env = {key: value for key, value in os.environ.items() if key not in {"HARNESS_OPERATOR_SIGNATURE_FILE", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"}}
        unsigned_override = subprocess.run(override_argv, env=unsigned_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(override_challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        override_env = {**unsigned_env, "HARNESS_OPERATOR_SIGNATURE_FILE": str(override_challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers_path)}
        signed_override = subprocess.run(override_argv, env=override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        overridden_state = reduce_engagement(close_escape)
        try:
            unsigned_override_code = json.loads(unsigned_override.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError):
            unsigned_override_code = None
        closed_retry_claim = root / "closed-override-retry-claim"; shutil.copytree(close_escape, closed_retry_claim)
        closed_retry_claim.joinpath("operator-note.txt").write_text("The engagement is complete.\n", encoding="utf-8")
        closed_retry_claim_argv = list(override_argv)
        closed_retry_claim_argv[closed_retry_claim_argv.index(str(close_escape))] = str(closed_retry_claim)
        closed_retry_claim_before = (closed_retry_claim / "events.jsonl").read_bytes()
        closed_retry_claim_cli = subprocess.run(closed_retry_claim_argv, env=override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try:
            closed_retry_claim_code = json.loads(closed_retry_claim_cli.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError):
            closed_retry_claim_code = None
        checks.append(("only an operator-signed first-class override can end with exact blocking identities while non-queue closure gates remain intact", unsigned_override.returncode != 0 and unsigned_override_code == "operator_signature_required" and signed_override.returncode == 0 and overridden_state["ending_overrides"][-1]["blocking_queue_digest"] == override_digest and overridden_state["ending_overrides"][-1]["blocking_items"] == override_items and overridden_state["ending_overrides"][-1]["operator_signature_challenge_digest"] == sha256_bytes(override_challenge) and overridden_state["ending_overrides"][-1]["operator_signer_fingerprint"].startswith("sha256:") and any(item["blocking"] for item in overridden_state["work_queue"]), unsigned_override.stdout + unsigned_override.stderr + signed_override.stdout + signed_override.stderr + str(overridden_state["ending_overrides"])))
        checks.append((
            "exact closed-override retry re-runs the local completion-claim precondition before reporting success",
            closed_retry_claim_cli.returncode != 0
            and closed_retry_claim_code == "completion_claims_unjustified"
            and (closed_retry_claim / "events.jsonl").read_bytes() == closed_retry_claim_before,
            closed_retry_claim_cli.stdout + closed_retry_claim_cli.stderr,
        ))
        closed = close_engagement(closure, "operator-selftest", "Cleanup, blocked coverage, reports, and memory are terminal.", "2026-07-10T00:21:05Z")
        checks.append(("closure requires one operator-reviewed memory disposition and accepts no_novel_lesson", missing_memory_blocked and recorded_memory["disposition"] == "no_novel_lesson" and retry_count + 1 == closed["event_count"] and closed["memory_disposition"]["disposition"] == "no_novel_lesson", str(closed)))
        checks.append(("memory disposition never writes Plane-1", not (closure / "skills").exists() and not (closure / "casebooks").exists(), "record-memory created Plane-1 content"))

        broker_id, broker_session = _local_identity("broker"); now_dt = datetime.now(timezone.utc); now_text = now_dt.isoformat(timespec="seconds").replace("+00:00", "Z"); current_environment = reduce_engagement(engagement)["active_environment_ref"]
        canonical_source = root / "canonical-public-source.txt"; canonical_source.write_text("canonical inert evidence\n"); canonical_artifact_path = engagement / "evidence" / "canonical-public.txt"; canonical_metadata = {"schema_version": 1, "artifact_id": "artifact-canonical-public", "engagement_id": engagement.name, "created_at": now_text, "producer": {"role": "broker", "id": broker_id}, "producer_session_id": broker_session, "operation_class": "notebook", "acquisition_method": "source_inspection", "target_refs": [], "environment_ref": current_environment, "sensitivity": "internal", "redaction_status": "not_needed", "contains_executable_capability": False, "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None, "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"}; canonical_metadata_path = root / "canonical-artifact-metadata.json"; canonical_metadata_path.write_bytes(canonical_json_bytes(canonical_metadata)); canonical_classification_path = root / "canonical-artifact-classification.json"
        command_classify_artifact(argparse.Namespace(engagement=engagement, metadata=canonical_metadata_path, source=canonical_source, planned_sha256=None, planned_size=None, relative_path=Path("evidence/canonical-public.txt"), recorded_at=now_text, actor_role="broker", actor_id=broker_id, session_id=broker_session, output=canonical_classification_path, model=None, provider=None, tool_version=[])); shutil.copyfile(canonical_source, canonical_artifact_path); command_register_artifact(argparse.Namespace(engagement=engagement, file=canonical_artifact_path, metadata=canonical_metadata_path, classification=canonical_classification_path))
        prior_attempts = {item["attempt_id"]: item for item in read_ledger(engagement, "attempt")}
        canonical_attempt_specs = (("attempt-canonical-primary", "attempt-primary", []), ("attempt-canonical-negative", "attempt-negative", ["attempt-canonical-primary"]), ("attempt-canonical-positive", "attempt-positive", ["attempt-canonical-primary"]), ("attempt-canonical-replay", "attempt-replay", ["attempt-canonical-primary"]))
        for new_id, source_id, controls in canonical_attempt_specs:
            attempt = {key: value for key, value in json.loads(json.dumps(prior_attempts[source_id])).items() if key not in {"sequence", "previous_hash", "record_hash"}}; attempt.update({"attempt_id": new_id, "recorded_at": now_text, "actor": {"role": "broker", "id": broker_id}, "environment_ref": current_environment, "evidence_refs": ["artifact-canonical-public"], "control_of": controls, "operation_class": "notebook", "execution_context": {"privilege_position": "authenticated-user", "impact_state": {"mode": "real-path", "synthesized_setup": []}}}); attempt["provenance"].update({"actor": {"role": "broker", "id": broker_id}, "session_id": broker_session}); append_attempt(engagement, attempt)
        canonical_review = claim_review("review-canonical-public", now_text, "supported", "F-canonical-public", None, "event-hypothesis-running"); canonical_review["proposed_finding_id"] = "F-canonical-public"; canonical_review["entity_ref"] = "F-canonical-public"; canonical_review["input_refs"] = ["attempt-canonical-primary", "attempt-canonical-negative", "attempt-canonical-positive", "attempt-canonical-replay", current_environment]; canonical_review["evidence_refs"] = ["attempt-canonical-primary", "attempt-canonical-negative", "attempt-canonical-positive", "attempt-canonical-replay", "artifact-canonical-public"]; canonical_review["control_applicability"] = [{"attempt_ref": "attempt-canonical-negative", "applicable": True, "rationale": "Matched negative branch."}, {"attempt_ref": "attempt-canonical-positive", "applicable": True, "rationale": "Known-positive detector check."}, {"attempt_ref": "attempt-canonical-replay", "applicable": True, "rationale": "Fresh-state replay."}]; canonical_review["independence"]["reviewer_id"] = "reviewer-external-canonical"; canonical_review["input_hash"] = compute_review_input_hash(engagement, canonical_review, build_reference_index(engagement)); canonical_review_path = root / "canonical-review.json"; canonical_review_path.write_bytes(canonical_json_bytes(canonical_review))
        canonical_event = base_event(event_id="event-canonical-claim-supported", engagement_id=engagement.name, recorded_at=now_text, actor_role="broker", actor_id=broker_id, event_type="claim.adjudicated", rationale="Record an external independent supported verdict without self-filing.", payload={"entity_id": "F-canonical-public", "status": "supported", "review_ref": canonical_review["review_id"], "reviewer_id": "reviewer-external-canonical", "review_digest": sha256_file(canonical_review_path)}, review_refs=[canonical_review["review_id"]], state_changes=[{"dimension": "claim", "entity_id": "F-canonical-public", "previous": None, "current": "supported"}], session_id=broker_session, operation_class="notebook"); canonical_event_path = root / "canonical-review-event.json"; canonical_event_path.write_bytes(canonical_json_bytes(canonical_event))
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-review-v1", str(canonical_review_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); review_signature = Path(str(canonical_review_path) + ".sig")
        review_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "record-review", "--engagement", str(engagement), "--file", str(canonical_review_path), "--event", str(canonical_event_path), "--actor-id", broker_id, "--session-id", broker_session, "--signature", str(review_signature), "--allowed-signers", str(allowed_signers_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if review_cli.returncode != 0: raise RecordError("canonical_review_subprocess_failed", review_cli.stdout + review_cli.stderr)
        review_timing = json.loads(review_cli.stdout).get("staging_timing_ms", {})
        checks.append((f"canonical review staging completes within its fixed prewrite budget (copy={review_timing.get('copy_snapshot')}ms, staged={review_timing.get('staged_transaction')}ms, remaining={review_timing.get('remaining_before_live_commit')}ms)", review_timing.get("declared_budget") == REVIEW_STAGING_TIMEOUT_SECONDS * 1000 and isinstance(review_timing.get("remaining_before_live_commit"), (int, float)) and review_timing["remaining_before_live_commit"] > 0, str(review_timing)))
        forged_event = json.loads(json.dumps(canonical_event)); forged_event["event_id"] = "event-forged-reviewer"; forged_event["payload"]["reviewer_id"] = "forged-reviewer"; forged_path = root / "forged-review-event.json"; forged_path.write_bytes(canonical_json_bytes(forged_event)); forged_reviewer_blocked = False
        forged_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "record-review", "--engagement", str(engagement), "--file", str(canonical_review_path), "--event", str(forged_path), "--actor-id", broker_id, "--session-id", broker_session, "--signature", str(review_signature), "--allowed-signers", str(allowed_signers_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: forged_reviewer_blocked = forged_cli.returncode != 0 and json.loads(forged_cli.stdout)["error"]["code"] == "canonical_review_binding_invalid"
        except (json.JSONDecodeError, KeyError): forged_reviewer_blocked = False
        # The preceding hermetic subprocess checks can exceed the production authority window on
        # slower hosts. Bind the synthetic filing request to its actual application time instead of
        # reusing the earlier review timestamp.
        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        canonical_finding = json.loads(json.dumps(finding1)); canonical_finding.update({"finding_id": "F-canonical-public", "revision": 1, "supersedes_revision": None, "recorded_at": now_text, "change_reason": "File the separately adjudicated canonical review.", "claim_state": "supported"}); canonical_finding["adjudication"] = {"review_ref": canonical_review["review_id"], "justification": "Canonical independent review supports the bounded claim."}; canonical_finding["scope_provenance"]["provenance"].update({"actor": {"role": "reviewer", "id": "reviewer-external-canonical"}, "session_id": canonical_review["independence"]["reviewer_session_id"], "model": canonical_review["independence"]["reviewer_model"], "provider": canonical_review.get("provenance", {}).get("provider")}); canonical_finding["scope_provenance"]["environment_ref"] = current_environment
        for claim_name in ("mechanism", "reachability"): canonical_finding["claims"][claim_name]["evidence_refs"] = ["artifact-canonical-public"]
        for impact in canonical_finding["claims"]["impact_claims"]: impact["evidence_refs"] = ["artifact-canonical-public"]
        canonical_finding["proof"].update({"primary_attempt_refs": ["attempt-canonical-primary"], "negative_control_refs": ["attempt-canonical-negative"], "positive_control_refs": ["attempt-canonical-positive"], "replay_refs": ["attempt-canonical-replay"], "evidence_refs": ["artifact-canonical-public"]})
        canonical_finding["classification"]["severity"] = {"label": "informational", "system": "none", "vector": None, "score": None, "rationale": "The synthetic workflow check claims no security severity."}
        canonical_finding["privilege_context"] = {"claimed_position": "authenticated-user", "execution_position": "authenticated-user", "evidence_refs": ["attempt-canonical-primary"]}
        canonical_finding["state_provenance"] = {"mode": "real-path", "evidence_refs": ["attempt-canonical-primary"], "synthesized_setup": []}
        for mapping in canonical_finding["proof"]["claim_proofs"]: mapping.update({"attempt_refs": ["attempt-canonical-primary"], "artifact_refs": ["artifact-canonical-public"], "control_refs": ["attempt-canonical-negative", "attempt-canonical-positive"], "replay_refs": ["attempt-canonical-replay"]})
        canonical_finding_path = root / "canonical-finding.json"; canonical_finding_path.write_bytes(canonical_json_bytes(canonical_finding)); finding_digest = sha256_file(canonical_finding_path)

        v2_source = root / "v2-finding-source"; shutil.copytree(engagement, v2_source)
        def prepare_v2_request(target_engagement: Path, request_name: str, proposal: dict[str, Any], request_time: str, *, action_executor: str | None = None, request_environment: object = ..., expires_at: str | None = "2099-07-10T00:00:00Z") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            request_state = reduce_engagement(target_engagement); metadata = request_state["claim_adjudications"][proposal["finding_id"]]; proposal_digest = sha256_bytes(canonical_json_bytes(proposal))
            target_value = {"type": "finding", "id": proposal["finding_id"], "expected_revision": metadata["expected_filing_revision"], "claim_state": metadata["status"], "adjudication_event_ref": metadata["event_ref"], "adjudication_review_ref": metadata["review_ref"], "resolves_review_refs": [], "file_digest": proposal_digest}
            action_value = _authority_action("revise-finding", action_version=3, lane_id=finding_revision_lane_id(target_value), executor_id=action_executor or broker_id, session_id=broker_session, file_digest=proposal_digest, operator_id="operator-selftest", proposal=proposal, target=target_value)
            relative = f"authority/requests/{request_name}.action.json"; atomic_write(target_engagement / relative, canonical_json_bytes(action_value)); action_value_digest = sha256_bytes(canonical_json_bytes(action_value))
            environment_value = request_state["active_environment_ref"] if request_environment is ... else request_environment
            request_event = base_event(event_id=f"event-{request_name}", engagement_id=request_state["engagement_id"], recorded_at=request_time, actor_role="broker", actor_id=broker_id, event_type="authority.requested", rationale="Request one fully bound v2 finding revision.", payload={"request_id": request_name, "action_kind": "revise-finding", "action_digest": action_value_digest, "action_path": relative, "lane_id": action_value["lane_id"], "request_status": "pending_authority", "scope_hash": request_state["scope_hash"], "environment_ref": environment_value, "expires_at": expires_at}, session_id=broker_session, operation_class="notebook")
            return action_value, target_value, request_event

        v2_clock = datetime.now(timezone.utc); v2_request_time = v2_clock.isoformat(timespec="seconds").replace("+00:00", "Z"); v2_resolution_time = (v2_clock + timedelta(seconds=1)).isoformat(timespec="seconds").replace("+00:00", "Z"); v2_apply_time = (v2_clock + timedelta(seconds=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
        v2_valid = root / "v2-finding-valid"; shutil.copytree(v2_source, v2_valid); v2_action, v2_target, v2_request_event = prepare_v2_request(v2_valid, "request-v2-finding", canonical_finding, v2_request_time, expires_at=None); append_event(v2_valid, v2_request_event); v2_pending_state = reduce_engagement(v2_valid)
        v2_pending_classes = [(item["class"], item["entity"]["id"]) for item in v2_pending_state["work_queue"]]
        v2_digest = sha256_bytes(canonical_json_bytes(v2_action)); append_event(v2_valid, base_event(event_id="event-resolution-v2-finding", engagement_id=v2_pending_state["engagement_id"], recorded_at=v2_resolution_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact v2 proposal after its request time.", payload={"request_id": "request-v2-finding", "request_event_ref": v2_request_event["event_id"], "action_digest": v2_digest, "resolution": "approved", "resolved_at": v2_resolution_time}, entity_refs=[v2_request_event["event_id"]], session_id=broker_session, operation_class="authority"))
        v2_partial_path = v2_valid / "findings/F-canonical-public/rev-1.json"; atomic_write(v2_partial_path, canonical_json_bytes(canonical_finding)); append_event(v2_valid, base_event(event_id="event-F-canonical-public-r1-commit", engagement_id=v2_pending_state["engagement_id"], recorded_at=v2_apply_time, actor_role="broker", actor_id=broker_id, event_type="record.committed", rationale="Simulate a same-digest v2 crash after commit but before activation.", payload={"record_path": "findings/F-canonical-public/rev-1.json", "record_digest": v2_target["file_digest"], "record_type": "finding-v3", "record_id": "F-canonical-public", "record_revision": 1, "authority_request_ref": "request-v2-finding"}, session_id=broker_session, operation_class="authority"))
        command_settle_approved_revision(argparse.Namespace(engagement=v2_valid, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=v2_apply_time, authority_request_id="request-v2-finding", lane_id=v2_action["lane_id"], executor_id=broker_id, session_id=broker_session)); v2_applied_state = reduce_engagement(v2_valid); v2_applied_event = read_ledger(v2_valid, "event")[-1]
        checks.append(("atomic settlement applies a live nullable-expiry v2 target, resumes a same-digest partial commit, and propagates exact resolutions", v2_pending_state["authority_requests"]["request-v2-finding"]["target"] == v2_target and v2_pending_state["authority_requests"]["request-v2-finding"]["expires_at"] is None and ("finding_revision_pending", "F-canonical-public") not in v2_pending_classes and ("claim_unadjudicated", "F-canonical-public") in v2_pending_classes and ("awaiting_operator", "request-v2-finding") in v2_pending_classes and v2_applied_state["findings"]["F-canonical-public"]["adjudication_event_ref"] == v2_target["adjudication_event_ref"] and v2_applied_event["payload"].get("resolves_review_refs") == [], str({"pending": v2_pending_classes, "finding": v2_applied_state["findings"].get("F-canonical-public")})))

        precommit_retry = root / "v3-finding-precommit-retry"; shutil.copytree(v2_source, precommit_retry); retry_action, retry_target, retry_request = prepare_v2_request(precommit_retry, "request-v3-precommit", canonical_finding, v2_request_time, expires_at=None); append_event(precommit_retry, retry_request); retry_state = reduce_engagement(precommit_retry); retry_digest = sha256_bytes(canonical_json_bytes(retry_action)); append_event(precommit_retry, base_event(event_id="event-resolution-v3-precommit", engagement_id=retry_state["engagement_id"], recorded_at=v2_resolution_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve exact precommit retry fixture.", payload={"request_id": "request-v3-precommit", "request_event_ref": retry_request["event_id"], "action_digest": retry_digest, "resolution": "approved", "resolved_at": v2_resolution_time}, entity_refs=[retry_request["event_id"]], session_id=broker_session, operation_class="authority")); retry_path = precommit_retry / "findings/F-canonical-public/rev-1.json"; atomic_write(retry_path, canonical_json_bytes(canonical_finding)); command_settle_approved_revision(argparse.Namespace(engagement=precommit_retry, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=v2_apply_time, authority_request_id="request-v3-precommit", lane_id=retry_action["lane_id"], executor_id=broker_id, session_id=broker_session)); retry_events = read_ledger(precommit_retry, "event"); checks.append(("retry after revision bytes but before record commit activates once", len([event for event in retry_events if event.get("event_type") == "record.committed" and event.get("payload", {}).get("record_id") == "F-canonical-public"]) == 1 and len([event for event in retry_events if event.get("event_type") == "finding.revised" and event.get("payload", {}).get("finding_id") == "F-canonical-public"]) == 1, str(retry_events[-2:])))

        unrelated_orphan = root / "v3-finding-unrelated-orphan"; shutil.copytree(v2_source, unrelated_orphan); orphan_action, _, orphan_request = prepare_v2_request(unrelated_orphan, "request-v3-orphan", canonical_finding, v2_request_time, expires_at=None); append_event(unrelated_orphan, orphan_request); orphan_state = reduce_engagement(unrelated_orphan); append_event(unrelated_orphan, base_event(event_id="event-resolution-v3-orphan", engagement_id=orphan_state["engagement_id"], recorded_at=v2_resolution_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve exact orphan-boundary fixture.", payload={"request_id": "request-v3-orphan", "request_event_ref": orphan_request["event_id"], "action_digest": sha256_bytes(canonical_json_bytes(orphan_action)), "resolution": "approved", "resolved_at": v2_resolution_time}, entity_refs=[orphan_request["event_id"]], session_id=broker_session, operation_class="authority")); orphan_expected = unrelated_orphan / "findings/F-canonical-public/rev-1.json"; atomic_write(orphan_expected, canonical_json_bytes(canonical_finding)); unrelated_path = unrelated_orphan / "findings/F-unrelated/rev-1.json"; unrelated_finding = copy.deepcopy(canonical_finding); unrelated_finding["finding_id"] = "F-unrelated"; atomic_write(unrelated_path, canonical_json_bytes(unrelated_finding)); orphan_before = (unrelated_orphan / "events.jsonl").read_bytes(); allowed_path_code = None
        try: reduce_engagement(unrelated_orphan, allowed_record_orphans={"findings/F-canonical-public/rev-1.json"})
        except RecordError as exc: allowed_path_code = exc.code
        orphan_apply_time = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        settlement_code = None
        try: command_settle_approved_revision(argparse.Namespace(engagement=unrelated_orphan, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=orphan_apply_time, authority_request_id="request-v3-orphan", lane_id=orphan_action["lane_id"], executor_id=broker_id, session_id=broker_session))
        except RecordError as exc: settlement_code = exc.code
        orphan_ledger_equal = (unrelated_orphan / "events.jsonl").read_bytes() == orphan_before
        checks.append((f"precommit recovery allows only the supplied path; unrelated orphan rejection={settlement_code}, ledger_equal={orphan_ledger_equal}", allowed_path_code == "orphan_immutable_record" and settlement_code is not None and orphan_ledger_equal, str({"allowed_path_reduction": allowed_path_code, "settlement": settlement_code, "ledger_equal": orphan_ledger_equal})))

        expiry_deadline_dt = v2_clock + timedelta(seconds=3)
        expiry_deadline = expiry_deadline_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        expiry_settlement_dt = v2_clock + timedelta(seconds=120)
        expiry_settlement_time = expiry_settlement_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        v2_expired = root / "v2-finding-expired"; shutil.copytree(v2_source, v2_expired)
        expiry_action, _, expiry_request = prepare_v2_request(v2_expired, "request-v2-expired", canonical_finding, v2_request_time, expires_at=expiry_deadline)
        append_event(v2_expired, expiry_request)
        append_event(v2_expired, base_event(event_id="event-resolution-v2-expired", engagement_id=reduce_engagement(v2_expired)["engagement_id"], recorded_at=v2_resolution_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact revision until its objective deadline.", payload={"request_id": "request-v2-expired", "request_event_ref": expiry_request["event_id"], "action_digest": sha256_bytes(canonical_json_bytes(expiry_action)), "resolution": "approved", "resolved_at": v2_resolution_time}, entity_refs=[expiry_request["event_id"]], session_id=broker_session, operation_class="authority"))
        early_expiry_event = base_event(event_id="event-authority-expired-request-v2-expired-early", engagement_id=reduce_engagement(v2_expired)["engagement_id"], recorded_at=v2_apply_time, actor_role="broker", actor_id=broker_id, event_type="authority.expired", rationale="An approval cannot expire before its recorded deadline.", payload={"request_id": "request-v2-expired", "request_event_ref": expiry_request["event_id"], "action_digest": sha256_bytes(canonical_json_bytes(expiry_action)), "expires_at": expiry_deadline, "status": "expired"}, entity_refs=[expiry_request["event_id"]], session_id=broker_session, operation_class="notebook")
        try:
            _append_kernel_event(v2_expired, early_expiry_event)
            early_expiry_code = None
        except RecordError as exc:
            early_expiry_code = exc.code

        class _ExpiredSettlementClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return expiry_settlement_dt

        expired_args = argparse.Namespace(engagement=v2_expired, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=expiry_settlement_time, authority_request_id="request-v2-expired", lane_id=expiry_action["lane_id"], executor_id=broker_id, session_id=broker_session)
        with patch(f"{__name__}.datetime", _ExpiredSettlementClock), patch(f"{__name__}.emit"):
            stale_settlement_code = None
            try:
                command_settle_approved_revision(argparse.Namespace(**{**vars(expired_args), "recorded_at": v2_apply_time}))
            except RecordError as exc:
                stale_settlement_code = exc.code
            before_expiry_events = len(read_ledger(v2_expired, "event"))
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as executor:
                settlement_results = list(executor.map(lambda _: command_settle_approved_revision(expired_args), range(2)))
        expired_state = reduce_engagement(v2_expired)
        expiry_events = [event for event in read_ledger(v2_expired, "event") if event["event_type"] == "authority.expired" and event["payload"].get("request_id") == "request-v2-expired"]
        expired_revision_item = next(item for item in expired_state["work_queue"] if item["class"] == "finding_revision_pending" and item["entity"]["id"] == "F-canonical-public")
        after_expiry_action = decorate_work_queue_item(expired_revision_item, expired_state, v2_expired)["next_action"]
        checks.append(("atomic settlement rejects early and stale-time expiry, serializes concurrent retries to one event, writes no finding bytes, and reopens a new request action", early_expiry_code == "approved_authority_expiry_invalid" and stale_settlement_code == "authority_settlement_time_not_current" and settlement_results == [0, 0] and len(expiry_events) == 1 and len(read_ledger(v2_expired, "event")) == before_expiry_events + 1 and expired_state["authority_requests"]["request-v2-expired"]["status"] == "expired" and not (v2_expired / "findings/F-canonical-public/rev-1.json").exists() and after_expiry_action["action_id"] == "request_finding_revision_authority", str({"early": early_expiry_code, "stale": stale_settlement_code, "results": settlement_results, "events": expiry_events, "next": after_expiry_action})))

        v2_duplicate = root / "v2-finding-duplicate"; shutil.copytree(v2_source, v2_duplicate); duplicate_first_action, _, duplicate_first_event = prepare_v2_request(v2_duplicate, "request-v2-first", canonical_finding, v2_request_time); append_event(v2_duplicate, duplicate_first_event); changed_proposal = copy.deepcopy(canonical_finding); changed_proposal["change_reason"] = "A different digest cannot open the same active generation."; _, _, duplicate_second_event = prepare_v2_request(v2_duplicate, "request-v2-second", changed_proposal, v2_request_time); duplicate_replay_blocked = False
        try: append_event(v2_duplicate, duplicate_second_event)
        except RecordError as exc: duplicate_replay_blocked = exc.code == "duplicate_active_finding_revision_request"
        checks.append(("reducer replay rejects a second active v2 request for the same generation even with a different proposal digest", duplicate_replay_blocked, "duplicate active generation reduced"))

        def rejected_v2_case(name: str, proposal: dict[str, Any], *, action_executor: str | None = None, request_environment: object = ...) -> str | None:
            case_engagement = root / name; shutil.copytree(v2_source, case_engagement); _, _, request_event = prepare_v2_request(case_engagement, f"request-{name}", proposal, v2_request_time, action_executor=action_executor, request_environment=request_environment)
            try: append_event(case_engagement, request_event)
            except RecordError as exc: return exc.code
            return None
        future_proposal = copy.deepcopy(canonical_finding); future_proposal["recorded_at"] = (v2_clock + timedelta(seconds=10)).isoformat(timespec="seconds").replace("+00:00", "Z")
        early_proposal = copy.deepcopy(canonical_finding); early_proposal["recorded_at"] = "2026-07-10T00:00:00Z"
        principal_code = rejected_v2_case("v2-impossible-principal", canonical_finding, action_executor="broker-impossible")
        environment_code = rejected_v2_case("v2-null-environment", canonical_finding, request_environment=None)
        future_code = rejected_v2_case("v2-future-proposal", future_proposal)
        temporal_code = rejected_v2_case("v2-early-proposal", early_proposal)
        checks.append(("v2 admission rejects impossible principals, non-current environment, future proposals, and pre-reference chronology", principal_code == "revise_finding_v2_principal_binding_invalid" and environment_code == "revise_finding_v2_principal_binding_invalid" and future_code == "revise_finding_v2_proposal_from_future" and temporal_code == "revise_finding_v2_reference_from_future", str({"principal": principal_code, "environment": environment_code, "future": future_code, "temporal": temporal_code})))

        unsafe_path_codes: list[str | None] = []
        for unsafe_name, make_unsafe in (("v2-symlink-parent", lambda path: os.symlink("../reviews", path / "findings/F-canonical-public")), ("v2-directory-leaf", lambda path: (path / "findings/F-canonical-public/rev-1.json").mkdir(parents=True))):
            unsafe_engagement = root / unsafe_name; shutil.copytree(v2_source, unsafe_engagement); _, _, unsafe_request = prepare_v2_request(unsafe_engagement, f"request-{unsafe_name}", canonical_finding, v2_request_time); make_unsafe(unsafe_engagement); unsafe_code = None
            try: append_event(unsafe_engagement, unsafe_request)
            except (OSError, RecordError) as exc: unsafe_code = exc.code if isinstance(exc, RecordError) else "os_error"
            unsafe_path_codes.append(unsafe_code)
        checks.append(("v2 admission rejects symlinked parents and non-regular destination leaves before projecting target debt", all(code is not None for code in unsafe_path_codes), str(unsafe_path_codes)))

        v2_locked = root / "v2-finding-locked-recheck"; shutil.copytree(v2_source, v2_locked); locked_action, _, locked_request = prepare_v2_request(v2_locked, "request-v2-locked", canonical_finding, v2_request_time); append_event(v2_locked, locked_request); locked_before_events = len(read_ledger(v2_locked, "event")); locked_blocked = False
        try:
            with patch(f"{__name__}._require_async_authority", return_value=None): command_revise_finding(argparse.Namespace(engagement=v2_locked, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=v2_apply_time, authority_request_id="request-v2-locked", lane_id=locked_action["lane_id"], executor_id=broker_id, session_id=broker_session))
        except RecordError as exc: locked_blocked = exc.code == "approved_authority_request_required"
        checks.append(("revise-finding revalidates approved authority under the held lock before any destination write", locked_blocked and not (v2_locked / "findings/F-canonical-public/rev-1.json").exists() and len(read_ledger(v2_locked, "event")) == locked_before_events, "stale authority wrote or committed a revision"))

        v2_wrong_operator = root / "v2-finding-wrong-operator"; shutil.copytree(v2_source, v2_wrong_operator); wrong_operator_action, _, wrong_operator_request = prepare_v2_request(v2_wrong_operator, "request-v2-wrong-operator", canonical_finding, v2_request_time); append_event(v2_wrong_operator, wrong_operator_request); append_event(v2_wrong_operator, base_event(event_id="event-resolution-v2-wrong-operator", engagement_id=reduce_engagement(v2_wrong_operator)["engagement_id"], recorded_at=v2_resolution_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact v2 proposal for principal binding testing.", payload={"request_id": "request-v2-wrong-operator", "request_event_ref": wrong_operator_request["event_id"], "action_digest": sha256_bytes(canonical_json_bytes(wrong_operator_action)), "resolution": "approved", "resolved_at": v2_resolution_time}, entity_refs=[wrong_operator_request["event_id"]], session_id=broker_session, operation_class="authority")); wrong_operator_before = len(read_ledger(v2_wrong_operator, "event")); wrong_operator_blocked = False
        try:
            with patch(f"{__name__}._require_async_authority", return_value=None): command_revise_finding(argparse.Namespace(engagement=v2_wrong_operator, file=canonical_finding_path, resolve_review=None, operator_id="operator-impossible", recorded_at=v2_apply_time, authority_request_id="request-v2-wrong-operator", lane_id=wrong_operator_action["lane_id"], executor_id=broker_id, session_id=broker_session))
        except RecordError as exc: wrong_operator_blocked = exc.code in {"approved_authority_request_required", "approved_revision_action_record_invalid"}
        checks.append(("revise-finding binds the active signed-scope operator under lock before mutation", wrong_operator_blocked and not (v2_wrong_operator / "findings/F-canonical-public/rev-1.json").exists() and len(read_ledger(v2_wrong_operator, "event")) == wrong_operator_before, "wrong operator wrote or committed a revision"))

        v2_conflict = root / "v2-finding-conflict"; shutil.copytree(v2_source, v2_conflict); conflicting_finding = copy.deepcopy(canonical_finding); conflicting_finding["change_reason"] = "Pre-existing unactivated bytes conflict with the requested proposal."; conflicting_path = v2_conflict / "findings/F-canonical-public/rev-1.json"; atomic_write(conflicting_path, canonical_json_bytes(conflicting_finding)); conflict_state = reduce_engagement(v2_conflict, allowed_record_orphans={"findings/F-canonical-public/rev-1.json"}); append_event(v2_conflict, base_event(event_id="event-v2-conflicting-commit", engagement_id=conflict_state["engagement_id"], recorded_at=v2_request_time, actor_role="broker", actor_id=broker_id, event_type="record.committed", rationale="Commit an unactivated conflicting revision for admission testing.", payload={"record_path": "findings/F-canonical-public/rev-1.json", "record_digest": sha256_bytes(canonical_json_bytes(conflicting_finding)), "record_type": "finding-v3", "record_id": "F-canonical-public", "record_revision": 1}, session_id=broker_session, operation_class="authority")); _, _, conflict_request = prepare_v2_request(v2_conflict, "request-v2-conflict", canonical_finding, v2_request_time); conflict_code = None
        try: append_event(v2_conflict, conflict_request)
        except RecordError as exc: conflict_code = exc.code
        checks.append(("v2 admission rejects a conflicting unactivated expected revision", conflict_code == "revise_finding_v2_conflicting_unactivated_revision", str(conflict_code)))

        legacy_null = root / "legacy-finding-null-authority-fields"; shutil.copytree(v2_source, legacy_null); legacy_apply_time = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); legacy_lane = "lane-legacy-null-fields"; legacy_action = _authority_action("revise-finding", lane_id=legacy_lane, executor_id=broker_id, session_id=broker_session, file_digest=finding_digest, operator_id="operator-selftest", recorded_at=legacy_apply_time); legacy_action_digest = sha256_bytes(canonical_json_bytes(legacy_action)); legacy_state = reduce_engagement(legacy_null); legacy_request_id = "request-legacy-null-fields"
        append_event(legacy_null, base_event(event_id="event-request-legacy-null-fields", engagement_id=legacy_state["engagement_id"], recorded_at=legacy_apply_time, actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="authority.requested", rationale="Preserve the pre-v2 authority request for historical replay.", payload={"request_id": legacy_request_id, "action_kind": "revise-finding", "action_digest": legacy_action_digest, "lane_id": legacy_lane, "request_status": "pending_authority", "scope_hash": legacy_state["scope_hash"], "environment_ref": None, "expires_at": None}, session_id="session-legacy-null-fields", operation_class="notebook")); append_event(legacy_null, base_event(event_id="event-resolution-legacy-null-fields", engagement_id=legacy_state["engagement_id"], recorded_at=legacy_apply_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the historical action record.", payload={"request_id": legacy_request_id, "request_event_ref": "event-request-legacy-null-fields", "action_digest": legacy_action_digest, "resolution": "approved", "resolved_at": legacy_apply_time}, entity_refs=["event-request-legacy-null-fields"], session_id=broker_session, operation_class="authority")); legacy_activation_blocked = False
        try: command_revise_finding(argparse.Namespace(engagement=legacy_null, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=legacy_apply_time, authority_request_id=legacy_request_id, lane_id=legacy_lane, executor_id=broker_id, session_id=broker_session))
        except RecordError as exc: legacy_activation_blocked = exc.code == "historical_finding_action_not_activatable"
        low_level_legacy_blocked = False
        fresh_legacy_filing = base_event(event_id="event-fresh-legacy-filing", engagement_id=legacy_state["engagement_id"], recorded_at=legacy_apply_time, actor_role="operator", actor_id="operator-selftest", event_type="finding.revised", rationale="Attempt a fresh old-contract activation with the marker but without authenticated v3 authority.", payload={"finding_id": "F-canonical-public", "finding_revision": 1, "status": "supported", "finding_digest": finding_digest, "adjudication_review_ref": canonical_review["review_id"], "adjudication_review_digest": sha256_bytes(canonical_json_bytes(canonical_review)), "adjudication_event_ref": canonical_event["event_id"], "supersedes_revision": None, "change_reason": "Old contract must not append.", "filing_contract_version": 1}, finding_refs=["F-canonical-public"], review_refs=[canonical_review["review_id"]])
        try: _append_kernel_event(legacy_null, fresh_legacy_filing)
        except RecordError as exc: low_level_legacy_blocked = exc.code == "historical_finding_action_not_activatable"
        raw_legacy_blocked = False
        try: append_ledger_record(legacy_null, "event", fresh_legacy_filing)
        except RecordError as exc: raw_legacy_blocked = exc.code == "finding_activation_requires_kernel_admission"
        legacy_null_state = reduce_engagement(legacy_null)
        checks.append(("historical target-null authority remains replayable but public, kernel, and raw append paths cannot activate a new finding", legacy_activation_blocked and low_level_legacy_blocked and raw_legacy_blocked and legacy_null_state["authority_requests"][legacy_request_id]["target"] is None and "F-canonical-public" not in legacy_null_state["findings"], str(legacy_null_state["authority_requests"][legacy_request_id])))

        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        action, _, request_event = prepare_v2_request(engagement, "request-canonical-finding", canonical_finding, now_text, expires_at=None); action_digest = sha256_bytes(canonical_json_bytes(action)); request_id = "request-canonical-finding"; append_event(engagement, request_event)
        append_event(engagement, base_event(event_id="event-resolution-canonical-finding", engagement_id=engagement.name, recorded_at=now_text, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve only the digest-bound canonical revision.", payload={"request_id": request_id, "request_event_ref": request_event["event_id"], "action_digest": action_digest, "resolution": "approved", "resolved_at": now_text}, entity_refs=[request_event["event_id"]], session_id=broker_session, operation_class="authority"))
        partial_destination = engagement / "findings/F-canonical-public/rev-1.json"; atomic_write(partial_destination, canonical_json_bytes(canonical_finding)); partial_commit = base_event(event_id="event-F-canonical-public-r1-commit", engagement_id=engagement.name, recorded_at=now_text, actor_role="broker", actor_id=broker_id, event_type="record.committed", rationale="Commit immutable operator-authorized finding revision.", payload={"record_path": "findings/F-canonical-public/rev-1.json", "record_digest": finding_digest, "record_type": "finding-v3", "record_id": "F-canonical-public", "record_revision": 1, "authority_request_ref": request_id}, session_id=broker_session, operation_class="authority"); append_event(engagement, partial_commit)
        revise_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "revise-finding", "--engagement", str(engagement), "--file", str(canonical_finding_path), "--operator-id", "operator-selftest", "--recorded-at", now_text, "--authority-request-id", request_id, "--lane-id", action["lane_id"], "--executor-id", broker_id, "--session-id", broker_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if revise_cli.returncode != 0: raise RecordError("canonical_finding_subprocess_failed", revise_cli.stdout + revise_cli.stderr)
        canonical_state = reduce_engagement(engagement)
        checks.append(("canonical public review and finding revision preserve reviewer, broker, adjudication, and filing separation", forged_reviewer_blocked and canonical_state["findings"]["F-canonical-public"]["revision"] == 1 and canonical_state["findings"]["F-canonical-public"]["status"] == "supported" and read_ledger(engagement, "event")[-1]["actor"] == {"role": "broker", "id": broker_id}, str(canonical_state["findings"].get("F-canonical-public"))))
        def approve_action(request_name: str, lane: str, action_value: dict[str, Any]) -> None:
            relative = f"authority/requests/{request_name}.action.json"; atomic_write(engagement/relative, canonical_json_bytes(action_value)); digest = sha256_bytes(canonical_json_bytes(action_value)); current_state = reduce_engagement(engagement)
            append_event(engagement, base_event(event_id=f"event-request-{request_name}", engagement_id=engagement.name, recorded_at=now_text, actor_role="broker", actor_id=broker_id, event_type="authority.requested", rationale="Exercise an exact canonical authority path.", payload={"request_id": request_name, "action_kind": action_value["action_kind"], "action_digest": digest, "action_path": relative, "lane_id": lane, "request_status": "pending_authority", "scope_hash": current_state["scope_hash"], "environment_ref": current_state["active_environment_ref"], "expires_at": "2099-07-10T00:00:00Z"}, session_id=broker_session, operation_class="notebook")); append_event(engagement, base_event(event_id=f"event-resolution-{request_name}", engagement_id=engagement.name, recorded_at=now_text, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve exact synthetic transition.", payload={"request_id": request_name, "request_event_ref": f"event-request-{request_name}", "action_digest": digest, "resolution": "approved", "resolved_at": now_text}, entity_refs=[f"event-request-{request_name}"], session_id=broker_session, operation_class="authority"))
        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); prior_action = _authority_action("record-operator-prior", lane_id="lane-prior-public", executor_id=broker_id, session_id=broker_session, operator_id="operator-selftest", recorded_at=now_text, prior_id="prior-public", prior_statement="Synthetic operator direction, not claim evidence.", strength="weak", reason="Exercise canonical prior authority."); approve_action("request-prior-public", "lane-prior-public", prior_action); command_record_operator_prior(argparse.Namespace(engagement=engagement, prior_id="prior-public", prior_statement="Synthetic operator direction, not claim evidence.", strength="weak", operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical prior authority.", authority_request_id="request-prior-public", lane_id="lane-prior-public", executor_id=broker_id, session_id=broker_session))
        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); cleanup_proposal = {"entity_id": "cleanup-public", "status": "not_applicable", "cleanup_obligations": [{"obligation_id": "cleanup-public", "kind": "synthetic_local", "status": "not_applicable", "artifact_refs": [], "rationale": "No live effect exists.", "closed_at": now_text}]}; cleanup_path = root/"cleanup-public.json"; cleanup_path.write_bytes(canonical_json_bytes(cleanup_proposal)); cleanup_action = _authority_action("record-cleanup", lane_id="lane-cleanup-public", executor_id=broker_id, session_id=broker_session, operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical cleanup authority.", **cleanup_proposal); approve_action("request-cleanup-public", "lane-cleanup-public", cleanup_action); command_record_cleanup(argparse.Namespace(engagement=engagement, file=cleanup_path, operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical cleanup authority.", authority_request_id="request-cleanup-public", lane_id="lane-cleanup-public", executor_id=broker_id, session_id=broker_session))
        public_state = reduce_engagement(engagement); reopened = True; operator_reopen_record = None
        if public_state["active_blockers"]:
            now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); reopen_action = _authority_action("reopen", lane_id="lane-reopen-public", executor_id=broker_id, session_id=broker_session, operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical reopening authority."); approve_action("request-reopen-public", "lane-reopen-public", reopen_action); command_reopen(argparse.Namespace(engagement=engagement, operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical reopening authority.", authority_request_id="request-reopen-public", lane_id="lane-reopen-public", executor_id=broker_id, session_id=broker_session)); reopened = not reduce_engagement(engagement)["active_blockers"]; operator_reopen_record = read_ledger(engagement, "event")[-1]
        checks.append(("canonical public prior, cleanup, and reopening transitions use exact one-use async authority", public_state["authority_requests"]["request-prior-public"]["status"] == "approved" and public_state["authority_requests"]["request-cleanup-public"]["status"] == "approved" and any(item["prior_id"] == "prior-public" for item in public_state["operator_priors"]) and any(item["obligation_id"] == "cleanup-public" for item in public_state["cleanup"]["obligations"]) and reopened and operator_reopen_record is not None and operator_reopen_record["event_type"] == "engagement.reopened" and operator_reopen_record["payload"]["operator_id"] == "operator-selftest" and operator_reopen_record["operation_class"] == "authority", "public authority transition missing"))
    return checks


def run_self_test(engagement_globals: dict[str, object]) -> int:
    globals().update(engagement_globals)
    checks: list[tuple[str, bool, str]] = []

    schema_problems = validate_schema_documents()
    checks.append(("new Draft 2020-12 schemas pass metaschema and local-ref validation", not schema_problems, str(schema_problems)))

    suite = validate_fixture_suite()
    checks.append(("valid/invalid fixture suite uses the canonical validator", not suite["failures"], str(suite["failures"])))
    reference_suite = validate_reference_fixture_suite()
    checks.append(("missing/wrong-type/cross-engagement/stale references fail", not reference_suite["failures"], str(reference_suite["failures"])))
    finding_case = next(case["record"] for case in load_json(Path(__file__).resolve().parents[1] / "fixtures" / "engagement-records" / "suite.json")["cases"] if case["id"] == "finding-v3-minimum")
    dispatch_ok = resolve_schema_name(finding_case) == "finding-v3"
    mismatch_caught = False
    try:
        resolve_schema_name(finding_case, "attempt-v2")
    except RecordError as exc:
        mismatch_caught = exc.code == "schema_dispatch_mismatch"
    checks.append(("record identity/version dispatch is authoritative", dispatch_ok and mismatch_caught, "caller-selected schema overrode dispatch"))
    ids = {case["id"] for case in suite["results"] if case["passed"]}
    for required in ("finding-v3-unknown-property", "finding-v3-duplicate-claim-id", "finding-v3-incomplete-claim-proof-map", "finding-v3-required-positive-control-missing", "finding-v3-empty-per-claim-proof", "finding-v3-positive-control-not-bound-per-claim", "attempt-v2-confirmed-outcome", "artifact-missing-conditional", "review-missing-conditional", "engagement-event-unknown-type", "state-snapshot-unknown-property", "environment-preflight-unknown-property", "report-manifest-unknown-property", "memory-disposition-unknown-property", "migration-manifest-unknown-property", "research-telemetry-unknown-property"):
        checks.append((f"negative fixture rejected: {required}", required in ids, "missing/failed fixture"))

    telemetry_fixture = load_json(Path(__file__).resolve().parents[1] / "fixtures" / "engagement-records" / "suite.json")
    calibration_record = json.loads(json.dumps(next(case["record"] for case in telemetry_fixture["cases"] if case["id"] == "research-telemetry-rich")))
    template_row = calibration_record["candidates"][0]; calibration_record["candidates"] = []
    for index_number in range(30):
        row = json.loads(json.dumps(template_row)); row["candidate_id"] = f"candidate-{index_number:02d}"; row["funnel_history"][0]["source_ref"] = f"event-eligible-{index_number:02d}"; row["funnel_history"][1]["source_ref"] = f"event-selected-{index_number:02d}"; row["funnel_history"][2]["source_ref"] = f"review-outcome-{index_number:02d}"; row["outcome"]["review_ref"] = f"review-outcome-{index_number:02d}"; row["review_refs"] = [row["outcome"]["review_ref"]]; calibration_record["candidates"].append(row)
    calibration_record["denominator"] = {"eligible_count": 30, "exported_count": 30, "complete": True}; calibration_record["classification"] = "calibration"; calibration_record["calibration_eligibility"] = {"eligible": True, "reasons": []}; calibration_score = score_telemetry(calibration_record)
    checks.append(("eligible ex-ante probabilities produce offline Brier and reliability telemetry only", calibration_score["brier_score"] == 0.0625 and calibration_score["small_sample"] is False and calibration_score["automatic_actions"] == [] and calibration_score["bandit_enabled"] is False, str(calibration_score)))

    canonical = canonical_json_bytes({"b": 2, "a": 1})
    checks.append(("canonical JSON is sorted and newline terminated", canonical == b'{"a":1,"b":2}\n', repr(canonical)))

    with tempfile.TemporaryDirectory(prefix="engagement-record-selftest-") as tmp:
        duplicate = Path(tmp) / "duplicate.json"
        duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
        caught = False
        try:
            load_json(duplicate)
        except RecordError as exc:
            caught = exc.code == "duplicate_json_key"
        checks.append(("duplicate JSON keys fail closed", caught, "duplicate key accepted"))

    # A record schema whose only property points at an unregistered URI must not degrade to success.
    broken = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://example.invalid/broken", "$ref": "https://example.invalid/missing"}
    broken_failed = False
    try:
        from jsonschema import Draft202012Validator
        list(Draft202012Validator(broken, registry=build_registry()).iter_errors({}))
    except Exception:
        broken_failed = True
    checks.append(("unresolved schema references fail closed", broken_failed, "missing $ref accepted"))

    duplicate_id_failed = False
    duplicate_schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://example.invalid/duplicate", "type": "object"}
    try:
        build_registry({"one.schema.json": duplicate_schema, "two.schema.json": duplicate_schema})
    except RecordError as exc:
        duplicate_id_failed = exc.code == "duplicate_schema_id"
    checks.append(("duplicate schema IDs fail closed", duplicate_id_failed, "duplicate $id accepted"))

    unavailable = subprocess.run(
        [sys.executable, "-S", str(Path(__file__).resolve()), "validate", "--schema-documents"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
    )
    try:
        unavailable_payload = json.loads(unavailable.stdout)
        unavailable_ok = unavailable.returncode != 0 and unavailable_payload.get("error", {}).get("code") == "validator_unavailable"
    except json.JSONDecodeError:
        unavailable_ok = False
    checks.append(("missing validator emits structured fail-closed output", unavailable_ok, unavailable.stdout + unavailable.stderr))
    checks.extend(state_self_test())
    quarantine_test = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("quarantine-self-test.py"))],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    checks.append((
        "quarantine health, mutation, measurement, KB, and dynamic casebook exclusions fail closed",
        quarantine_test.returncode == 0
        and "QUARANTINE SELF-TEST: PASS" in quarantine_test.stdout,
        quarantine_test.stdout + quarantine_test.stderr,
    ))

    for label, ok, detail in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" :: {detail}"))
    failed = [label for label, ok, _ in checks if not ok]
    print(f"RUN-ENGAGEMENT SELF-TEST: {'PASS' if not failed else 'FAIL'}")
    return 0 if not failed else 1
