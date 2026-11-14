# Native boundary: accounts, frozen guidance and unused preparation

This followup to [the initial boundary](../m5-native-boundary-20261114/README.md)
connects the independently checked account resolver and network journal API to the
actual NativeBoundary composition. It also consumes the engagement's frozen
method/protocol and supplies the explicit no-execution cleanup fact used by the
controller's separate preparation-cancellation operation.

## Implemented behavior

A worker with application access receives a target account resolver only on its
lab gateway. Provider traffic never uses that resolver. The host selects the
private reference file through `OSLIT_ACCOUNT_BINDINGS`; the reference must be
outside controller records, every recorded worker workspace, source/binary input
paths and native tool bundles. Missing account credentials fail before environment
preparation. Public selectors name signed access/account IDs; secrets remain in
host memory and do not enter native environments, bootstrap material or records.

Every admitted target request saves its original controller grant and environment
nonce before connection. A response uses that same pair even after lease renewal
or revocation. Completed request identities are removed from the boundary's
in-memory inflight map; immutable journal observations retain their history.
The integrated worker context renews and publishes its new grant under the same
controller lock used by authorization and dispatch guards. The HTTP workflow
pauses between journal renewal and in-memory publication to exercise the former
gateway-watch race. Revoked/uncertain requests produce the protected unknown result and selected-target
hold. Shutdown closes network gates before clearing account credentials/cookies.

The worker bootstrap now copies `methodology.md` and `protocol.md` from verified
frozen inputs, with no repository-file fallback on resume. Missing guidance
prevents execution. The controller owns the original file hashes and their export.

A boundary that explicitly never admitted environment execution can report
`execution_admitted:false, cleanup:verified` only after closing its owned gates and
credential bindings and removing its owned staging directories. It does not claim
that a process was observed absent. An admitted execution without an owner,
failed gate closure or failed directory cleanup remains unresolved. The controller
must independently validate and persist cancellation; this boundary fact alone
does not settle a dispatch or refund allowance.

## Repeatable workflows

On macOS with Python 3, OpenSSL, ssh-keygen and sandbox-exec:

```sh
python3 evals/native-qualification/smoke/check_native_target_accounts_e2e.py --output /tmp/native-target-accounts.json
python3 evals/native-qualification/smoke/check_engagement_native_boundary_e2e.py --output /tmp/native-boundary-integration.json
```

Expected: seven account scenarios and 23 boundary scenarios pass. `account-after.json`
and `boundary-after.json` bind the exact exercised source bytes. Failure receipts
precede the corresponding integration/fix; their snapshots differ intentionally.
The account workflow creates actual owned loopback HTTP receivers and exercises
the real gateway, account resolver and signed controller journal. Native model,
environment and proxy-relay peers are explicitly simulated. It verifies account
A/B/anonymous routing, selector stripping, no secret in records, original-grant
attribution after renewal, unknown effect retention after revocation, reference
isolation and missing credentials before execution. Temporary fixture inputs and
listeners are removed. The boundary workflow additionally exercises actual local
certificates and the host network sandbox, but those are not Docker containment
qualification.

No external model provider, research target, Docker daemon or SSH host was contacted.
This does not establish native application research acceptance, a remote reset,
clean application replay, full multiday operation or production qualification.
Application-only protected capture remains a separate followup with explicitly
unverified remote reset and retained parent ownership.
