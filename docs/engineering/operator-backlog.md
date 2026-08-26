# Operator backlog — things only the operator can do

Started 2026-08-16. These accumulated across a long working session and were scattered across
commits, PR bodies and chat. A blocked item nobody wrote down is indistinguishable from a finished
one, which is the same failure mode the disposition ledger exists to fix one level up.

Ordered by what unblocks the most. Check items off in place; do not delete them, so a later reader
can see what was waiting and for how long.

---

## P0 — Disposition pairs

**Status:** OPEN. Operator holds the data; deferred by the operator on 2026-08-16 ("I can tell you
about the disposition pairs but NOT now").

**Blocks:** Phase 11 entirely. It is the only external calibration this harness will ever have.

**Why it outranks everything else:** every audit run in August 2026 was the harness grading itself.
Two separate investigations into whether we are too rigorous both terminated in the same place — no
outside verdict to check against. One graded pair exists (Klever: we said **critical**, vendor graded
**high** 7.7, delta **+1**). `calibrate` refuses to issue a verdict below 5 graded pairs, on purpose.

**What a pair is:** two severity labels for the same finding — ours and theirs. The ledger subtracts
them.

| direction | meaning |
|---|---|
| negative | we called it LOWER than the program did → we under-call → the excess-rigor thesis confirmed from outside |
| zero | we agreed → calibrated |
| positive | we called it HIGHER → we over-call |

**What to supply, per finding** — partial rows are useful, `pending` and `unknown` are legitimate:

```
finding | our band | their band | outcome | report id
```

Known to exist and unrecorded: 2 Klever High, 1 Klever Medium, 2 Vercel Critical/High, plus
duplicates across gemini-cli and angular-dev-infra.

**Duplicates count and are worth recording.** A duplicate is the program confirming the bug is REAL
and that someone filed it first. It usually has no `their band`, which is correct — it records as
`outcome: duplicate`, `novelty: duplicate`, validates DETECTION, and contributes nothing to the
delta.

**Record with:**
```
./.venv/bin/python tools/disposition_ledger.py record --engagement engagements/<id> \
  --finding <id> --program "<program>" --our <band> [--theirs <band>] \
  --outcome <accepted|duplicate|pending|...> --novelty <novel|duplicate|unknown> \
  --report-id <id> --their-rating "<their own words, e.g. P2 / S4>" \
  --source-kind operator_report --confidence operator_recall
```

---

## P1 — File the packages that are ready

**Status:** OPEN.

**As of 2026-08-16, 12 of 12 finding packages clear all seven gates:**

| engagement | packages clear |
|---|---|
| `angular-dev-infra-2026-08` | 3/3 (F13, R8, V1) |
| `angular-cli-2026-08` | 7/7 |
| `obyte-ocore-2026-08` | 2/2 (001, 003) |

**AI is barred from filing** in every one of these programs. This is the harness's single largest
throughput loss: 12 of 13 engagements that ever produced a report sit at "drafted, operator files",
and drafts land 0-2 days after scope then wait 28-36 days.

Filing also feeds P0 — a filed report is a future disposition pair.

---

## P2 — Scope decisions

- **obyte Q-1 and Q-2** (`engagements/obyte-ocore-2026-08/QUARANTINE.md`). Both wallet-layer, outside
  the declared DLT surfaces. Q-1 is a remote, zero-cost, repeatable wallet crash; Obyte has
  historically treated wallet issues as severe. Widen scope, forward as hardening, or drop.
- **Q-04 scope** — blocks Phase 4. Direction already decided (D-08: static analysis may CONFIRM,
  never KILL). What is open is which language and which engine. Recommendation: TypeScript first,
  since angular-cli and gemini-cli are live and CodeQL is licensed for both.
- **Ceiling requests.** `engagements/*/ceiling-requests.md` is new and empty. The standing
  instruction is that scope widens when a ceiling needs it — the first real row will be the
  dev-infra Supply-Chain top-band chain, which needs a wire 2/4 confirm to probe. Watch for it.

---

## P3 — Kernel activation for `angular-cli-2026-08`

**Status:** OPEN. `scope.md` §14 is signed (in-session, 2026-08-14) and the run is authorized.

The signed initialization challenge was deliberately **not** copied from `angular-dev-infra-2026-08`
— a challenge signature covers one engagement's exact bytes, and reusing it would assert an
attestation never made over this scope. Generate a fresh challenge and sign it with the private half
of the `matheusht` key. See `engagements/angular-cli-2026-08/signers/OPERATOR-SIGNING.md`.

---

## P4 — Housekeeping with real consequences

- **`spotify-backstage-2026-07/90-final-dispositions.md` is stale.** Three generations of "final"
  severity exist for the same findings (`90-`, the confirmation dossiers, `93-symmetric-reaudit.md`)
  and nothing reconciles them. `93` is the filing table. Anyone reading the file *named* "final
  dispositions" would file `F-F1` at High on a label that came from the fabrication script.
- **Spotify's 11 quarantined findings** still need re-adjudication with real reviewers, or an
  explicit decision to drop them.
- **`engagements/gemini-cli` is a nested git repository.** Files written inside it are invisible to
  the outer repo — that is how two disposition records were silently lost on 2026-08-16. Its
  engagement records are still stranded there.
- **`.git/index.lock` goes stale repeatedly.** Cleared by hand five times on 2026-08-15/16, once
  31 hours old with no owning process. Something in the tooling dies mid-write.

---

## Answered, kept for the record

- **Q-07 — which gate graduates first.** Answered 2026-08-16: oracle-negative re-confirmation, on
  standby at N=40. Preregistered at `fixtures/preregistration/phase2-oracle-negative-standby.json`.
  Nothing is removed; the run stops blocking and every override is captured live.
- **CodeQL licence.** Answered 2026-08-16 from the terms themselves: it restricts by CODEBASE type,
  not by business model. Licensed for OSI-licensed codebases hosted on GitHub, including automated
  and CI database generation — so it covers every OSS VRP target and NOT the private commercial
  ones. Phase 7 scopes to OSS.
- **DeepSec as a CodeQL substitute.** Answered 2026-08-16 by reading its source: `MatcherPlugin`
  is `match(content, filePath)` — one file's text is the entire input. 200 regex matchers, no
  parser, no dataflow. It is a candidate finder plus an LLM reviewer, so using it as the confirmer
  would be a model confirming a model, which D-08 forbids.
