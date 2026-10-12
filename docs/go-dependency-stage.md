# One-use Go dependency staging

`stage-go-dependencies` is a broker-only, exact-action operation. It is for the
Go 1.23.0 linux/amd64 toolchain and a reviewed module graph. It never contacts
a target or runs target code. The only network implementation is the operation's
own HTTPS GET transport; the existing `network-policy-v1` parser admits
`target_fetch` only and is not used for dependency hosts.

The signed scope must contain its fresh-third-party-confirmation rule and an
exact `harness revision required` SHA matching the running checkout. The action
must bind that SHA, its own capability-file SHA256, the current scope hash,
engagement, broker identity and session, ready environment, clean source commit,
private destination, exact URLs and redirect chains, raw SHA256 and Go H1 pins,
and budgets. A signed `resolve-authority --resolution approved` for the exact
request digest is the fresh confirmation. The reducer validates the typed
`dependency.stage_spent` event before the first request. A stopped or crashed
run remains spent and needs a new exact action and signature.

An action lists one official Go release metadata response before the matching
Go archive, the seven declared module triples (`.mod`, `.info`, `.zip`), and
triples for every reviewed transitive. Unknown graph edges stop offline
verification; they are never fetched automatically. The release metadata must
confirm the preapproved archive SHA256 and size before its GET. Each module
`.mod` and `.zip` must match its preapproved Go H1, and every response must
match its raw SHA256. The action may list exact official CDN redirects; an
unlisted redirect stops before following it. The ceiling is 100 requests,
600 MiB total, 256 MiB for the Go archive, 64 MiB per module ZIP, and 30 minutes.
Smaller per-action limits remain binding.

The downloader uses this Cloud task's exact internal HTTPS egress sidecar,
`http://proxy:8080`, and refuses a changed `HTTPS_PROXY` setting. The sidecar
is only a route: the operation still permits only the exact signed official
upstream URLs, disables automatic redirects, and validates upstream TLS.

Downloads, extracted toolchain, module cache, and redacted receipt stay under
the engagement's owner-only `sandbox/dependency-retrieval/<request-id>/`.
The receipt records hosts, hashed paths, status, counts, hashes, and the stop
reason, without raw URL paths. The verified Go binary runs only in a private
offline check with `GOTOOLCHAIN=local`, `GOPROXY=off`, `GOSUMDB=off`, closed
inherited file descriptors, and inherited seccomp rules denying `socket`,
`socketpair`, and `connect`. That check uses a generated private module file,
not target source. The synthetic E2E proves socket denial in a child process.

The operation is intentionally unavailable to an engagement whose signed
scope still pins a different harness commit. Reattest that harness revision
through the operator's signed scope flow before requesting an action. The
existing third-party trip-wire requires fresh exact approval for contact; it
does not by itself grant a reusable network allowance. A changed source,
preflight, scope, code digest, URL, redirect, checksum, or budget needs review
and a new action. A `target_fetch` permission cannot substitute for this flow.

Verification without real network contact:

```sh
python3 tools/dependency-stage-e2e.py --output /tmp/dependency-stage-e2e
python3 tools/run-engagement.py --self-test
python3 tools/check-conformance.py
```

The synthetic fixture uses an in-memory transport and a disposable signed
engagement. It does not prove that the Cloud sidecar can reach official hosts;
the first approved contact must still pass the Cloud egress policy and exact
redirect checks. If connectivity fails, the action remains spent.
