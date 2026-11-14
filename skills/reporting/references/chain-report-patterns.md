# Chain-report patterns

Use this with `reporting.vulnerability-report-writing` when the finding is a chain: stage A's
output satisfies stage B's precondition, and the combination reaches a consequence neither
reaches alone.

The model is a **primitive ledger**, not a research narrative. Each stage is a contract:

```text
carried primitive + constraint envelope
  -> operation
  -> new primitive + new constraint envelope
```

The reader should be able to stop after the summary and the chain overview and still know the
entry condition, the stage count, the terminal capability, and the weakest link.

## What the strongest public chains do

### 1. Result card before mechanism

QEMU opens with the mechanism, the demonstrated result, and an 11-row field table:

- `MADBugs/qemu/WRITEUP.md` §Overview: integer overflow in `virtio-gpu` gives host read/write;
  "A guest VM opens Calculator.app on the macOS host"; then affected software, ZDI, introduced
  commit, fixed version, patch commit, tested build, attack surface, impact, ASLR status, host
  modifications, and discovery method.
- `MADBugs/freebsd-one-two-three/WRITEUP_FreeBSD-One.md:1-9`: target, environment, and "Remote
  root shell from network access alone. No credentials, no SSH, no local access."

Copy: one concrete demonstrated result, one stable field block, artifact hash, date.

Do not copy: audience justification ("most popular frontend") or bounty figures as the
load-bearing credibility clause.

### 2. Scope and handoff contract

WP2Root states what it covers before any exploit detail:

- `MADBugs/wp2root/writeups/FULL_CHAIN_WRITEUP.md` §Scope: "This document covers the native-code
  half of this package after the WordPress chain has already produced an eval endpoint."
- It then gives a mode-family table mapping entry flag -> payload -> end result.

Copy: covered stage range, assumed prior state, out-of-scope work, and platform substitutions. A
reader must not attribute an earlier-stage failure to the stage under test.

### 3. Whole-chain map in two representations

QEMU pairs a chain diagram with a one-paragraph summary and five phases
(`MADBugs/qemu/WRITEUP.md` §Exploitation Strategy). WP2Root uses an arrow chain plus a
phase/state/attacker-controlled-object table (`§8.1`).

Copy: one diagram or ASCII graph for shape, one table for state and cost. The table answers
"what does the attacker control now?"

The table must remain self-sufficient if the diagram is removed.

### 4. Causal hierarchy, not a CVE list

QEMU's relationship section is the model:

- Vulnerability 1 (`calc_image_hostmem`) is the root cause.
- Vulnerabilities 2 and 3 (`set_scanout`, `transfer_to_host_2d`) are consequences: they trust
  logical dimensions instead of allocation size.
- The upstream patch fixes only V1, which makes V2 and V3 unreachable.

Copy: `root` or `consequence`, what each link consumes, whether it is independently
triggerable, and what the patch closes.

A flat list of bugs loses the only information a maintainer needs: which bug to fix.

### 5. Six-field stage card

QEMU Phase 1 gives exact constants (`width=0x40000001`, `height=128`, BGRA8888). Phase 2 states
the obstacle and what the stage must produce. The VNC race note is a model abort condition:
flush before request and the client hangs indefinitely.

Use:

```markdown
### S2 — Turn the OOB write into a host read

- **Precondition:** S1 completed; resource 42 has `stride=4`, `hostmem=512`.
- **Action:** `SET_SCANOUT(x=OOB_OFFSET/4)`, `RESOURCE_FLUSH`, then VNC request.
- **Success marker:** `Mach-O at +0x6c000 sizeofcmds=0x6b8`.
- **Failure signature:** VNC timeout, no framebuffer update, or QEMU SIGSEGV.
- **Abort:** reset scanout to `x=0`; restart the VM if the VNC timer consumed the dirty flag.
- **Hand-off:** the leak gives the shared-cache slide, but not an executable address, so S3
  needs a writable dispatch pointer.
```

The six fields force the writer to separate what was done from what it proved.

### 6. Primitive ledger with a constraint envelope

IonStack's GhostLock description is the standard:

- a single constrained store `*(uint64_t *)target = W0_BASE`;
- the qword before the target must read as an unlocked spinlock;
- the address is constrained, the value is constrained, and the write is one-shot.

Route of Root enumerates the 14-byte OOB write's degrees of freedom: packet size selects the
cache, offset is one of two values, and only some bytes are controlled.

Copy: primitive, input, output type, consumer, constraint envelope, failure mode. "Arbitrary"
is a claim that must survive a list of length, alignment, direction, value, and address checks.

### 7. Failure ledger

QEMU §Challenges has seven issues, each with root cause and fix: no initial read primitive,
read-only `__DATA_CONST` GOT, TLS cache defeating the obvious hijack, VNC stall, 16x16 minimum
scanout, 15-byte command limit, SPICE crash.

Copy only dead ends that change how the surviving chain is built. Format:
`Symptom | Root cause | What we do instead | What it means for you`.

Do not include a chronological attempt log. A constraint that changes whether the proof runs is
not an attempt-log entry.

### 8. Reliability with denominators

- PHP: `10/10` under full ASLR on two versions, with a per-run address ledger.
- Coruna: ~89% on an idle M-series machine; the mechanism is scheduler jitter on the
  compiler-thread wakeup, and the knob and window are stated.
- QEMU/UTM: the SPICE timer makes each unmapped-page read a ~7% chance of instant death; the
  buffer-first fill strategy turns that into zero observed crashes.

Copy: `n/N` per stage, the mechanism that makes the stage probabilistic, the environment variable
that moves the rate, the retry cost, and a `cosmetic` vs `material` label for post-success faults.

A global "8/8" is not a chain rate. A single favorable run is plausibility, not a rate.

### 9. Build-keyed offsets and environment planes

QEMU's offset table carries section and permissions:

| Symbol | Offset | Section |
|---|---|---|
| GOT[free] | `0x78060` | `__DATA_CONST` (r/o) |
| `_fast_path_cache` TLS thunk | `0x80020` | `__DATA` (r/w) |
| `_global_implementation` | `0x801B8` | `__DATA __common` (r/w) |

The r/o vs r/w annotation explains why the exploit targets the TLS thunk instead of the GOT.

Copy: `symbol | value | applies to | section | how obtained | stage`. State what happens on a
different build: re-derived, fails closed with a marker, or untested. If the chain is
address-targetless, name the discovery primitive per row and list the residual assumptions.

### 10. Claim boundary and residual assumptions

WP2Root is explicit about what "targetless" means: addresses are resolved at runtime, but the
chain still depends on PHP 8.1 NTS layouts, allocator behavior, readable ELF metadata, gadget
bytes, and the helper assumptions. It calls itself "self-resolving or address-targetless, not
version-agnostic."

Copy: a per-stage assumption table with `confirmed` / `inferred` / `assumed`, and one sentence
naming the weakest link. The last proven stage is the claim boundary.

### 11. Reproduction as a runbook

QEMU gives the exact QEMU configure flags, Alpine kernel extraction, cross-compiler, initramfs
build, run command, and a phase-labeled expected transcript. Coruna pins the WebKit commit, build
command, `DYLD_FRAMEWORK_PATH`, retry script, and the Lockdown Mode gotcha that silently disables
the JIT.

Copy: one fast path, then per-stage commands with expected observations. Put environment gotchas
in Requirements, not in a postscript; they are often the difference between "works" and "silently
doesn't".

### 12. Stage-closing impact, not a business essay

IonStack ends the final stage with the concrete capability: cleared seccomp, `CAP_FULL`, SELinux
permissive, root child out of the app sandbox. The harness still needs the three-link impact
sentence, but the chain walkthrough should close on an observable state, not on "critical risk".

## Proposed chain outline

```markdown
# [defect] in [symbol] chains to [terminal primitive] from [actor]

## Summary
Capability; non-requirements; chain shape and weakest link; demonstrated end state; ceiling.

## At a glance
Affected, tested, chain, primitive per stage, closed at, fragile stage, demonstrated,
not demonstrated, control, severity, artifact.

## Affected and tested
Per-build pins; config/flags that change the stage count.

## Chain overview
Table: # | Stage | Gains | Depends on | Class | Anchor | Proof.
Diagram if not a straight line or N > 4.

## Root cause
One anchor per link; one anchor per edge; invariant per link; root vs consequence; patch
reachability.

## Stage walkthrough
Six fields per stage: precondition, action, success marker, failure signature, abort, hand-off.

## Reproduction
Fast path; full runbook; per-stage expected output; tuning; troubleshooting; environment deltas;
cleanup.

## Evidence and controls
Stage matrix; stage-local control; refuted/absent rows; replay.

## Impact
Entry actor to terminal asset; which link carries the score; floor; unclosed ceiling.

## Boundaries and non-claims
Per-stage assumptions; weakest link; last proven stage.

## Dead ends and constraints
Only constraints that change the build or the reader's score.

## Layout, constants, and addresses
Build-keyed table; discovery method; residual assumptions.

## Novelty / duplicate check
Per-link prior art; whole-chain delta; what the combination removes.

## Suggested fix
Stage rows closed; residual path; root fix vs terminal check.
```

## Voice

- Stage headings are verb-first and literal. Mechanism names are fine if explained in the first
  sentence.
- Stage cards are declarative: goal, input, mechanism, proof, constraint, hand-off.
- First person is for choices and limits ("I used `pselect` because the frame depth matched"),
  not for narrating each step.
- Keep the technical detail local. The reader should be able to read one stage without holding
  the entire chain in working memory.
- Do not paste the research journey. A dead end earns its place only if it changes the surviving
  step.

## Source corpus

- `califio/publications`: `MADBugs/qemu/WRITEUP.md`, `MADBugs/wp2root/writeups/`,
  `MADBugs/coruna/Stage1-writeup.md`, `MADBugs/freebsd-one-two-three/`,
  `MADBugs/php/WRITEUP.md`, `MADBugs/nginx-CVE-2026-27654/blog.md`.
- V12 Security: `ghostscript/REPORT.md`, `misc/20260526-near-intents.md`,
  `thorchain/20260602/README.md`.
- NebuSec: `ionstack-part-2`, `ionstack-part-3`, `cve-2026-43501-route-of-root`.
- Harness: `submissions/btc-psbt-sighash-override/REPORT-final.md` (multi-arm evidence matrix),
  `submissions/aptos-multikey-verify-bypass/refactored-20261113/report.md` (cell-level controls).
