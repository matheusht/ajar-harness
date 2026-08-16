# G2 control-role fixture

This fixture isolates one distinction: a replay is not a negative control.

Both cases attest that a negative control exists. The rejected case cites the replay attempt in
both roles. The accepted case cites a separate `negative_control` attempt whose outcome is
`no_signal` and whose `control_of` points to the primary attempt.

Run from the repository root:

```sh
python3 fixtures/lifecycle-control-kind/demo.py
```

The command is hermetic: it reads only synthetic records, does not load secrets, and makes no
network requests. Its output is intentionally fixed and projector-safe.
