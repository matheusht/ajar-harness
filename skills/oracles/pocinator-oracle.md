---
id: pocinator-oracle
type: oracle
description: Post-confirmation layer — does THIS specific PoC/package prove the exact claim we're about to report? (judgment, anti-reward-hacking)
---

# Pocinator oracle — "does this specific PoC actually prove the exact claim?"

The last adjudication layer before filing. Regrade asks whether the finding is real; this asks
whether the artifact standing in as evidence for it is faithful, sufficient, and scoped correctly.
Full doctrine, worked examples, and rationale: `engine/pocinator.md`. This card is the terse,
invocable version for an agent loading it by id mid-run.

## Required input: the claim tuple
Before applying any lens, extract (don't invent) this tuple from the finding/evidence records:

**target artifact/version · entrypoint · preconditions · mechanism · observable effect · negative
control · claimed impact/severity · package contents · run command/environment · expected observable
output**

If the tuple can't be extracted from existing records → `blocked`, immediately. Do not construct the
tuple yourself; that grades your own homework.

## Verdict set
`verified` · `needs_rework` · `claim_mismatch` · `reward_hacked` · `blocked`

- **`verified`** — proves the exact tuple, including any PoC-dependent severity claim.
- **`needs_rework`** — probably real, specific fixable gap named. Also the correct verdict when it's
  *unclear* whether something is `reward_hacked` — uncertainty is never itself grounds for that verdict.
- **`claim_mismatch`** — PoC is real and sound, proves something narrower/different than claimed.
- **`reward_hacked`** — a *definite, articulable* harness failure only (named mock dodging the real
  gate, traced emulator divergence, an assertion that structurally cannot fail). Not a hedge.
- **`blocked`** — genuinely can't decide (environment/artifact unavailable, tuple not extractable) —
  not a judgment on the PoC either way.

Any non-`verified` verdict routes back to Stage 4/4.25, never a silent kill. `claim_mismatch` routes
to severity/impact reasoning specifically, not to rebuilding the PoC. A *definite* `reward_hacked` on
a high-value finding earns a second independent pocinator pass before being treated as final.

## Lenses (apply what's relevant, not all of them mechanically)
1. **Real-artifact provenance** — actual published artifact/pinned commit, not a reimplementation.
2. **Public-entrypoint realism** — driven the way a real caller would, not a harness-only shortcut.
3. **Mock/stub justification** — for every mock: if this were real code, would the assertion still
   hold, or does the mock exist to dodge the real gate?
4. **Mechanism fidelity via negative control** — control diverges *through the claimed mechanism*,
   traced, not merely observed to differ.
5. **Observable effect, not a blind marker** — a real state change/response/artifact, not
   `exit 0` + a printed string. Even sink-instrumented automated checks aren't sufficient alone.
6. **Claim strength** — assertion matches report language exactly, for the PoC-dependent part of the
   claim only (broader CVSS/novelty precedent is out of scope here — that's the narrow
   CVSS-precedent-reviewer pattern, not a full `regrade-oracle` re-litigation).
7. **Clean-state reproducibility** — fresh checkout/extraction, not leftover dev-session state.
8. **Anomaly tracing** — any stray log/warning/stack trace traced to source, never hand-waved benign.
9. **Package hygiene** — review what would actually ship (re-extracted), no secrets/scratch files/
   internal records; no drift between working copy and packaged artifact.
10. **Self-attestation is not evidence** — re-derive independently; ideally a different context than
    whoever built the PoC.
11. **Optional differential** (when available) — patched version/fixed config/safe control strengthens
    confidence; not required, not every finding shape offers one.
12. **Counterfactual-novice framing** — ask explicitly: *where would a naive or reward-hacked
    verification stop and declare success here?* Sharper than "is this faithful?" alone.
13. **Precondition-state reachability** — the tuple names `preconditions`; this lens asks how they
    came to exist. Split the state the PoC starts from into **background setup** (a genesis, a funded
    account, a deployed contract) and the **impact-bearing state** — the specific condition the
    severity claim rests on. Background may be seeded; each seeded element needs a one-line reason
    why that state is ordinary. The impact-bearing state must have been REACHED by driving the
    target's own code, not written into storage, constructed in memory, or monkeypatched. Ask
    directly: *if I delete the setup script and drive the target normally, does this condition ever
    occur?* When the answer is no, the PoC demonstrates the sink and proves nothing about the reach.
    This maps to lifecycle gate **G6** (`state_provenance` in `attest.json`); use the same four
    words so the oracle and the gate agree: `real-path` · `none-required` · `synthesized` ·
    `not-established`.

## Real adjudicated non-findings (calibration anchors)
Grounds `claim_mismatch` and the deliberately-narrow `reward_hacked` in real disputed/rejected CVEs
where the *PoC or claimed impact* — not the finding's existence — was the problem. Full corpus:
`skills/oracles/references/rejected-disputed-cve-corpus.md`.

- **`claim_mismatch` — crash is real, claimed class isn't.** CVE-2013-3245 (VLC): "This PoC crashes
  VLC, indeed, but does not [prove code execution]" — sound PoC, proves DoS not the claimed RCE. Same
  shape: CVE-2006-6061 / CVE-2006-4434 (impact is at most a kernel/disk DoS, not the filed severity).
  This is lens 6 (claim strength) failing on the PoC-dependent part only.
- **`claim_mismatch` — the mechanism doesn't exist in the target.** CVE-2005-1588 (Quick.cart): filed
  as SQL injection against a product that "does not even use SQL." A PoC cannot prove a mechanism the
  target lacks — lens 4: the negative control must diverge *through the claimed mechanism*.
- **`reward_hacked` — the claim structurally cannot hold.** CVE-2023-32001 (curl): "We issued this CVE
  pre-maturely… there really is no safe measures around or protections for [it]" — withdrawn because
  the reported condition is not a defensible boundary at all. CVE-2018-14496 (Vivotek): filed as remote
  memory-corruption RCE; the vendor states the issue produces zero observable effect, "not even a
  crash." These are the *definite, articulable* failures the verdict is reserved for — an assertion
  with nothing behind it — never a hedge.

### Our own adjudicated non-findings (lens 13 anchors)
The synthesized-state class is the harness's most repeated self-inflicted false positive. Three
instances, all caught late and none by the PoC passing or failing:

- **`obyte-2026-08-004` (2026-08-11)** — the drive script wrote a `count>=30` settlement window that
  produced a 10.7%-of-supply fee. Every other gate passed: the PoC ran, the negative control ran, the
  privilege claim was honest, an independent reviewer reproduced it from raw output. It promoted, and
  the run's own escalation phase refuted it ten hours later — the real path measured `fee=17` at every
  step, because settlement runs with `count=1`. **`reward_hacked` on lens 13, `verified` on all
  others.** The reviewer reproduced the PoC faithfully; nobody asked whether its starting state exists.
- **`obyte` round-1 crash PoC (same engagement, same week)** — an empirically-crashing PoC killed on
  the same ground. The class recurred inside one engagement.
- **Kubernetes fake-client finding (earlier engagement)** — a controller-runtime fake client skipped
  apiserver validation of ResourceVersion immutability, so the harness "confirmed" a claim the real
  apiserver rejects. A cheap source-first regrade beat an expensive harness that lied.

**Reading:** an independent re-run is not a control for this. A faithful reviewer re-running a PoC
that begins mid-attack reproduces the same unreachable state and reports success. Only lens 13 or
gate G6 asks the question, so ask it explicitly rather than expecting replay to surface it.

## What this oracle is NOT for
Passing pocinator does not guarantee a report won't return as a duplicate — it verifies the PoC is
real and faithful to its claim, not that the finding is novel or undisclosed. Novelty is a separate,
upstream question.

## When required
Default-required for: any executable PoC/zip attached to a report, any high/critical candidate, any
model-built harness/emulator standing in for the real target, any finding whose severity claim
depends on what the PoC specifically demonstrates. Skippable only with an explicit operator note
recorded in the finding — never a silent skip.
