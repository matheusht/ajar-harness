# unproven/ — where every finding starts

A finding is written here. It has no status field. It has a location.

It moves to `../findings/` only by running:

    ./.venv/bin/python tools/finding_lifecycle.py promote unproven/<FINDING_ID> \
        --engagement . --actor orchestrator

That runs six gates. Any one of them can block. A finding that does not pass stays here.

- Hunters write here and may not move anything.
- Only the orchestrator promotes.
- Any role may demote, at any time, with a reason.

Doctrine: `engine/finding-lifecycle.md`. Check a package without moving it with
`finding_lifecycle.py gates <dir>`.
