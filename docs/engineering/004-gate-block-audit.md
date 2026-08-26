# Gate-block audit — the first evidence about gate calibration

**Date:** 2026-08-21. **Tool:** `tools/gate_block_audit.py` (re-runnable, not a one-off).

## Why this exists

`docs/decisions/0011` states the problem plainly:

> "We have no evidence the gates are well-calibrated. We have evidence they have never had to say
> no... Agents iterate `gates` until clean and then `promote`, so a block never enters the record."

`docs/engineering/003-roadmap.md` repeats it: *"The gates have blocked ZERO promotions out of
twelve."* **That is now out of date.**

`exodus-2026-08` broke the pattern open by accident. Its record kernel was initialized on day 3 of a
three-day run, so 19 packages exist that were never iterated to clean. The blocks survived.

## The classification rule, fixed before counting

| class | the gate blocks on | bears on calibration? |
|---|---|---|
| **paperwork** | an **absent record** — no attempt cited, no review filed, no package written | **no** |
| **substance** | a **declared negative** — the package itself states reach or provenance was not established | **yes** |

Reporting these together as one "block rate" is the mistake the tool exists to prevent: it lets a
recording failure masquerade as rigor.

Paperwork blocks are **not harmless.** A finding that was never recorded is indistinguishable from
one that was never made. They are a defect in the run, not in the gates.

## Result

19 packages, 87 blocks, 1 clear.

| class | count | share |
|---|---|---|
| paperwork | 74 | **85%** |
| substance | 13 | 15% |
| unclassified | 0 | 0% |

**85% of every gate block in the largest engagement we have run is a recording failure.**

### Only 3 of 19 packages had a fair chance

"Fair chance" means the package cites an attempt that **resolves in the ledger** — the only honest
evidence the kernel was in use for it.

| package | blocks |
|---|---|
| `U-013-changepassphrase-wallet-destruction` | **clear, all seven gates** |
| `U-012-connected-origins-revocation-race` | G3 |
| `U-005-keyid-toctou-signing` | G3, G4 (G4 paperwork) |

Adding `obyte-ocore-2026-08` (1 fair-chance package, blocked on G6) gives the whole corpus:

**4 fair-chance packages. Substance blocks: G3 ×2, G6 ×1.**

## What this does and does not license

**Does:** the gates have now demonstrably said no on merit. `docs/decisions/0012` precondition 3
("the gates have demonstrably blocked something real") has its first evidence.

**Does not:** N=4 supports no rate. It identifies **where** substance blocks concentrate — G3
(execution position) and G6 (state provenance), the two gates that ask whether the proof starts from
an attacker position rather than from a constructed state. Neither G0, G1, G2 nor G4 produced a
single substance block in the entire corpus.

**A methodological note worth keeping.** The first version of the fair-chance filter used file
mtime. It counted a git checkout as work and admitted 11 packages that never touched the ledger.
mtime is a bad instrument for "was this worked while the kernel ran," the same way string length was
a bad instrument for "was a control named" in `tools/kb.py`. Both were caught by testing the
instrument against real data rather than a fixture shaped to the code.

## What follows

1. **Make kernel initialization a precondition for any write.** Nothing today refuses work on an
   uninitialized kernel — exodus produced 19 packages and 185 KB of evidence across two days with no
   kernel. Activating late is retroactively fatal to every finding made before it.
2. **Recover the 16 stranded packages** — 8 unpackaged, 8 packaged without a resolvable attempt.
   There is no backfill tool.
3. **Re-run this audit after each engagement.** The corpus grows; the number becomes a rate.
