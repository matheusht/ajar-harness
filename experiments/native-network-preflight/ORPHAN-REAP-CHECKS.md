# Direct checker orphan reaping — failure checks before edit

Scope: check_v2_connect.py harness only. Runtime v2_connect.py remains unchanged.
No Docker/provider/CI call. Existing assertion still means the parent-loss gateway
exits without an observer kill; forced cleanup must never turn that check green.

Cloud reproduction supplied by coordinator: gateway emitted owner_lost then
authority_ended and exited status 0, but stayed zombie under Linux PID 1. kill(pid,0)
reports a PID for a zombie and falsely failed the cleanup check (27/28). Preserve
that cloud failure and its three focused reproductions; do not alter runtime stop.

Before spawning an owner/grandchild on Linux, enable PR_SET_CHILD_SUBREAPER on the
checker process. If unavailable, fail the harness explicitly; never silently fall
back to the known false zombie-presence oracle. On import, do not enable it.
After owner termination, use bounded waitpid(exact_gateway_pid, WNOHANG) to reap
only the adopted gateway and record actual exit status. Never waitpid(-1) or reap
unrelated children. A still-running gateway at the bound fails the original check;
only then may exact-PID SIGKILL + bounded reap run as separately recorded cleanup.
Non-Linux keeps a bounded real PID-absence check and meaningful failure/cleanup.

Failure checks:
- Normal gateway exit after actual parent SIGKILL passes only without forced kill;
  Linux records adopted/reaped exact PID and exit status, expected status 0.
- A zombie is reaped, not killed or treated as a runnable process.
- Adoption/prctl failure, unknown child or timeout remains explicit failure.
- A gateway that needs SIGKILL remains a failed assertion even if cleanup succeeds.
- Every existing direct TLS/limits/restart/deadline/parent-stop check still runs;
  source hashes stable, temporary key/capability removed and owned processes gone.
- Run full owned offline checker on available host. This host is macOS: Linux
  kernel branch requires a fresh coordinator/cloud Linux run; do not claim it from
  macOS or mock prctl. No Docker substitute.

The checker change does not edit the upstream backpressure predicate. Analysis of
that separate Linux failure remains provisional until cloud ledger evidence arrives.

Review strengthening before edit: preserve the existing "already exited" assertion
as process-exit evidence, and additionally require Linux adopted/reaped exit code 0
with a separate "exited cleanly" check. A nonzero/crash exit must fail overall even
when PID cleanup succeeded. Non-Linux lacks an adopted-child wait status and keeps
its bounded absence check. Both checks happen before any forced cleanup; forcing
SIGKILL cannot create a graceful pass. Expected full counts: 29 on Linux, 28 here
on macOS; Linux still requires actual cloud execution.
