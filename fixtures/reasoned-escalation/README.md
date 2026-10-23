# Reasoned escalation acceptance

Run `python tools/reasoned-escalation-e2e.py --output <new-dir>` from the portable harness checkout
with the repository's pinned Python dependencies installed (`jsonschema==4.26.0`) and macOS
`/usr/bin/ssh-keygen` available. The script makes a separate signed, inert local engagement and uses
public `run-engagement.py` and work-queue commands. It saves its inputs, command results, and
reduced state under the output directory. Private signing keys live in a temporary directory and
are removed on normal exit; only public signer files and signatures remain. No live target is contacted.
The positive case admits the notebook `selected → running` transition only. It does not launch a
hunter, record an attempt, prove impact, or override the separate live-execution hold.

Freeze these failure modes before implementation:

| Case | Expected result |
| --- | --- |
| Direct owned-canary route with a current observation, signed scope, allowed rung, named safe signal, control plan, and independent causal review | Review is recorded; the exact route may enter `running` without a fabricated lower-rung attempt. This is permission to test, not impact confirmation. |
| Evidence predates active scope/environment, or scope/environment changes after review | Route is held with a specific stale-evidence/authority reason; no run transition. |
| Route cites an evidence ID absent when proposed | Proposal is refused before any ledger append. |
| Requested effect exceeds the signed ceiling or names an unscoped surface | Route is held; other queue items remain available. |
| Safe-signal card or signed benign objective is absent | Route is held. |
| No discriminating test or control plan | Route is held. |
| Independent reviewer finds a broken output-to-precondition edge or overclaimed impact | Route is held, even when proposal prose asks for admission. |
| Review is absent, reused, stale, or from the proposal's own run/model | No higher-impact run transition. |
| Wrong route digest, review ref, or second use of a selected action | Broker/kernel refuses the mutation. |
| Primary result without a full-path proof | No larger finding is confirmed by route admission. |

The positive and negative cases must preserve the original ledgers and command output so a
separate reviewer can recompute each outcome.
