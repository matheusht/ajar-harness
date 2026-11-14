# Startup owner publication — 14 November 2026

The before receipt records five missing-API failures. The after receipt records
five passing checks using installed Codex 0.166.0, OMP 18.20.0 and Bun on macOS.
No prompt, real provider inference or target operation was dispatched.

The model owner is published immediately after process creation and kernel identity
capture, before native initialization can wait. The Codex bridge publishes its
own preparation receipt before writing its private handshake. A callback failure
stops the recorded owner and attaches the actual receipt and cleanup readback to
the raised exception. Accepted model startup publishes a null session, then the
same process identity with its fresh native session. Recovery accepts a bridge-only
preparation receipt and refuses an empty owner.

Repeat on macOS with the pinned CLIs and Bun installed:

```sh
python3 evals/native-qualification/smoke/check_native_startup_ownership.py \
  --output /private/results/native-startup-ownership.json
```

`owner_observer` is a trusted host callback. NativeExecutor additionally requires
`profile_sha256` when the callback is supplied. Its bridge receipt has no `process`
field until a model owner is created. Constructor exceptions expose `owner_receipt`
and `cleanup_result`; missing identity is never proof of cleanup. A session
publication rejection propagates to the caller, which still owns normal runtime
cleanup. These checks do not establish Linux tool isolation or engagement recovery.
