# engine/routing.md — recon → activation signals → card selection

The connective tissue between recon and the loop. Recon does not hand the orchestrator a target; it
hands it a set of **activation signals**, and those signals select which `skills/patterns/` and
`skills/vulns/` cards come into play. This is what makes "the orchestrator chooses" a *recorded,
reviewable* skill instead of relying on the model's training intuition.

## The flow
```
recon observations
  → activation signals        (name what you saw; match against pattern cards' `activation` blocks)
  → matching pattern / vuln cards   (load the exact cards by id)
  → cross-engagement KB pass        (tools/kb.py — reorders and annotates; NEVER removes a card)
  → orchestrator chooses probes     (use, ignore, or override — but record why for strong signals)
  → loop + oracle               (engine/loop.md; adjudicate every result, default-skeptical)
  → pattern-candidates / casebook   (after the engagement, scrubbed promotion)
```

## Recon must emit activation signals (before card selection)
During recon (runbook step 3), for each surface, write down the concrete observations and which
pattern cards they activate. A signal is `strong | weak | negative`:
- **strong** — matches a card's `activation.strong`; load that card and plan its probes.
- **weak** — worth a cheap look; do not over-invest.
- **negative** — the *defense is present* here (matches `activation.negative`); record it as a likely
  **held** control and a positive-control candidate, not a finding.

A `negative` signal is as valuable as a strong one: a correctly-enforced sibling is the tell that an
unguarded sibling nearby is the bug (see `pattern.legacy-route-differential`).

## Not a checklist — guided, overridable
The orchestrator MAY use, ignore, or override an activated card. But for any **strong** signal on a
**high-impact** path, record one line on why if you skip it. The point is a reviewable reasoning trail,
not a rigid gate. Selection stays deterministic (load the exact card by id, per `AGENTS.md §3`); what
routing adds is *which* ids, justified by what recon saw.

## Where the signals come from / go
- **Cards** declare their `activation` block (`strong/weak/negative`) in front matter.
- **Casebooks** (`casebooks/<id>/recon-signals.yml`) hold worked examples — observation → activation —
  that seed and calibrate this step.
- **Fixtures** (`fixtures/*routing*`) assert the harness *would* activate the right cards for a known
  casebook (e.g. an owner-id field → `pattern.client-supplied-selector-authz`).

## The cross-engagement KB pass (Phase 8)

Every engagement before this one started cold. `memory/kb.jsonl` is the only memory that crosses
engagement boundaries; the within-run family registry in `engine/multi-round-orchestration.md` is a
different thing and is unchanged.

**Run this AFTER activation, never before.** The KB must not decide what you consider — it may only
reorder what recon already lit up, and annotate it with what a previous run proved. Running it first
would let a past loss suppress a card the current target's evidence activated, which is the feedback
trap `D-09` forbids.

```sh
# 1. what does the KB know about this target's shape?
./.venv/bin/python tools/kb.py query --language <lang> --framework <fw> --target <id>

# 2. reorder the activated set (fixture = {"context": {...}, "base": [{route, family, priority}]})
./.venv/bin/python tools/kb.py route --fixture <engagement>/routing-base.json
```

**What it may and may not do:**

- It **reorders** and **annotates**. It never removes a route, kills a candidate, or lowers a
  verdict (`D-09`). `tools/kb.py` asserts this: if the output route set ever differs from the input
  set, it aborts rather than returning a smaller list.
- The delta is bounded at ±1 and does not accumulate. Nine losses on one family still move it by
  one. ZSec's version multiplies a hardened target's priority down, which buries a target that later
  went soft; ours cannot.
- A `loser` entry records that **we** failed to find something — evidence about our search, not
  about the target. Read its `reopen_on` field before accepting the demotion. A materially new
  mechanism reopens anything, and that rule is unchanged from the family registry.
- An entry marked `control_is_proven` is a fact about the target rather than about us, so it earns a
  stronger annotation. It still earns no kill authority: a control is version-specific and may have
  changed since it was recorded.

**Writing back at close.** Promote a winner or a loser with `tools/kb.py add --file <entry>
--fixture <ablation fixture>`. Two rules bite:

1. A loss must **name the control that held**, with a `mechanism` and at least one `evidence` ref.
   "We looked and found nothing" is an absence of work, not a loss, and the schema rejects it.
2. The entry must **change a routing decision** or it is not promoted. The ablation gate re-runs
   routing with and without it; identical order means the entry is noise.

Entries are scrubbed to an abstract mechanism. Never write a target identifier into
`mechanism_class`, and omit `engagement` entirely when the source is under a disclosure obligation.

## Hard gates still apply
Routing changes *what you consider*, never the gates. The KB pass changes only the ORDER of what
routing already chose. Scope, `safe_signal`, Zone-2 human-confirm,
redaction, and oracle-before-`confirmed` are unchanged (`AGENTS.md §1`). A strong activation never
authorizes an impact artifact on its own.
