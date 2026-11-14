# Protected application and combined-access capture

The native boundary now permits a protected capture over a nonempty subset of the
current worker resources, defaulting to all of them. Application subjects are the
signed base URLs; source and binary subjects remain frozen input paths. Each
capture reserves a separate lab, stages the exact instrument/candidate/probe and
binds its execution and actual target request observations to the auxiliary grant
and environment nonce. The public result includes `network_request_ids`; the
controller derives experiment account/effect bindings from those observations.

The auxiliary lab has its own host account resolver and gateway. Private account
values do not enter the relay, probe command, bootstrap or controller records.
An application capture refuses while a parent target request is in flight. Until
that capture finishes, new parent target requests are refused while the main
network authority watcher remains live. Source-only capture does not impose this
application exclusion.

A new local lab does not reset a remote application. Any capture selecting an
application reports `clean_start:false` and
`remote_application_reset_unverified`. Known local cleanup can settle the
auxiliary reservation while the live parent retains application ownership.
Unknown target results or lost parent authority preserve the application hold;
they never become a remote reset. A source-only subset of a combined grant can
still report its separately created local input as clean.

Native setup and local client mechanics select exactly one account-free `read`
effect covering the selected resources and environment. They do not select the
first of ambiguous effects or require permission to execute code on the remote
application. Actual target requests retain their separately admitted effect.
Higher-rung review admission remains the controller's responsibility.

## Repeat

Requirements: Python 3, OpenSSL and ssh-keygen. The boundary regression additionally
uses macOS sandbox-exec. From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_application_capture_e2e.py --output /tmp/application-capture.json
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_target_accounts_e2e.py --output /tmp/application-accounts.json
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_engagement_native_boundary_e2e.py --output /tmp/application-boundary.json
```

Expected: six application capture scenarios, seven account scenarios and 23
boundary scenarios pass. `before.json` preserves the failure-first result.
`after.json`, `accounts-regression.json` and `boundary-regression.json` identify
exact exercised source hashes. All receipt digests are listed in `manifest.json`.

The capture workflow starts actual disposable loopback HTTP receivers, runs the
real private stdio relay and executes the pinned Python probe as an owned local
subprocess. The controller, gateway and account resolver are real. Native model
and container peers are explicitly simulated. Checks cover A/B account attribution,
experiment request provenance, subsequent capture under retained parent authority,
combined/source-only selection, empty/outside/duplicate resources before admission,
parent/capture request exclusion, main-gate recovery and revocation with uncertain
target effect retention. Temporary fixtures and owned relays are removed.

No external provider, external research target, Docker daemon or SSH host was
contacted. This establishes orchestration and capture provenance, not container
containment, native provider behavior, application reset, clean independent remote
replay, a multiday soak or fresh-target research acceptance.
