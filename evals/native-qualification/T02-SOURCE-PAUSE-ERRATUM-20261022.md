# T02 source pause erratum — 22 October 2026

The manifest-pinned [`t02-source/README.md`](t02-source/README.md) says T04
requires a "first-test interruption and resume." Keep that pinned file and
its source manifest byte-identical: the sentence describes the earlier T04
preflight, not the current [#160 contract](https://github.com/matheusht/redteam-harness/issues/160).

The current T04 check pauses once after material workspace **and target** state
exist, then resumes the same native session under the remaining allowance or
records a declared reconstruction. It does not require the first completed
vulnerability test, per-operation admission, or a particular tool-action
boundary. The [current operator preflight](T04-UNHINTED-PREFLIGHT.md#deliberate-pause-and-continuation)
defines the pause and evidence to retain.

This correction changes no historical receipt or source pin. The live native
run, independent original-effect observation, fresh review, and adoption
decision remain pending.
