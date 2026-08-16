# unproven/ — where every finding starts, AND where partials live

A finding is written here. It has no status field. It has a location.

It moves to `../findings/` only by running:

    ./.venv/bin/python tools/finding_lifecycle.py promote unproven/<FINDING_ID> \
        --engagement . --actor orchestrator

That runs seven gates. Any one of them can block. A finding that does not pass stays here.

- Hunters write here and may not move anything.
- Only the orchestrator promotes.
- Any role may demote, at any time, with a reason.

## Partials belong here. This is not a draft folder.

An audit on 2026-08-16 measured three post-gate engagements: the gates blocked **zero** promotions
out of twelve, and this directory was **empty** in two of the three. One hundred per cent promote,
zero partial.

That is how a rigorous pipeline loses deep findings — not by rejecting them, but by having nowhere
to put an incomplete one. A three-stage chain with two stages proven has real value. If the only
two states are "passes seven gates" and "a line in a hardening note", that value is gone.

**Write the partial.** Declare the stages in `finding.json`:

```json
"stages": [
  {"n": 1, "claim": "...", "state": "proven",  "evidence": "attempt://..."},
  {"n": 2, "claim": "...", "state": "argued",  "blocked_by": "scope-ceiling",
   "what_would_close_it": "the one act that would settle it"}
]
```

`state` is `proven` · `argued` · `refuted`. A partial is any package with a non-`proven` stage. It
never claims severity above what its proven stages support, and it is not promoted.

What it buys: it survives the round, a later run can read it, its proven stages go into
`../primitive-registry.md`, and `what_would_close_it` is a next action instead of a shrug.

If a stage is blocked only by AUTHORIZATION, also open a row in `../ceiling-requests.md`. The
operator's standing instruction is that scope widens when that is what a ceiling needs — but only
they widen it, and only when asked.

Doctrine: `engine/finding-lifecycle.md` §5b, §5c. Check a package without moving it with
`finding_lifecycle.py gates <dir>`.
