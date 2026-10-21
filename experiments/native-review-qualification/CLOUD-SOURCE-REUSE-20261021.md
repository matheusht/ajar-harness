# Cloud review source reuse

This slice preserves the existing local handoff helper, its prewritten checks and
the exact synthetic inputs needed by `check_handoff.py`. It makes those previously
untracked bytes available to the cloud implementation without transferring native
stores, hidden application answers or engagement data. It does not implement
managed reviewer integration or establish a real review.

Run from the repository root with Python 3 and its standard library:

```sh
python3 experiments/native-review-qualification/T03-EXECUTABLE-HANDOFF-20261020/check_handoff.py
```

Expected and locally observed on 21 October: `handoff_checks_passed`, all six
named check groups pass, `provider_calls: 0`, `native_review: not_run`. The command
stages and challenges packets in a disposable directory and removes it on exit;
it does not execute the fixture application, Docker or a model. The copied source
and inputs match the original local bytes. The observer manifest remains
`26056e8abd33e6b55cfac99929e611b7f8bc8b9193bf914c589c4592c15f7f74`.
The saved command output is [result.json](cloud-source-reuse-20261021/result.json).

Included input groups are `T03-v1`, `T03-v2` and `T06-strong-lead`. These contain an
invented note-export application, synthetic roles and operator-authored setup
observations. Their original temporary-path provenance is retained with the
existing hashes. The manifest also names `T06-printed-success`; that group's
additional input files are intentionally absent in this minimal source slice.

The existing helper trusts only its pinned historical fixture manifest, and its
accepted actual-predecessor set is empty. Reuse its validation and evidence
semantics when implementing actual packets, without treating a prepared request
as a completed review or making the researcher its own evidence authority.

Read [the existing shared-run interface](T03-T02-SHARED-REVIEW-INTERFACE-20261020/INTERFACE.md)
and its prewritten checks before integration. Reuse the managed launcher's
presealed reviewer, shared allowance and stop ownership; the old arm64 offline
runner is not part of this transfer. The actual application observer has
[prewritten checks](../../evals/native-qualification/T02-APP-REQUEST-CAPTURE-CHECKS-20261020.md).
The latest operator requirements are in
[portable adaptive acceptance](../../evals/native-qualification/PORTABLE-RESEARCH-ACCEPTANCE.md).
