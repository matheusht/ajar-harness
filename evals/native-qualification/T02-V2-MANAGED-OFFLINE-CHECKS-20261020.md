# T02 managed CONNECT + owned-response E2E checks — 20 October 2026

This is one offline integration rehearsal for #158. It uses the exact T05
`v2_connect.py`/`native_run.py`, the pinned derived OpenCode V2/PHP 8.4.26
image, and only the harmless three-file PHP fixture. CONNECT's dummy destination
is an owned loopback TLS responder. No official provider, hidden Kanboard case,
external target, real credential or hosted CI participates. An owned response
can prove native routing and tool execution, never model judgment or billing.

Before code or execution, fail on any of these conditions:

1. **Source/identity.** Pin the exact T05 source SHA values, including
   `tools/docker_session_runtime.py` imported by `producer_stop.py`, image ID, relay,
   config, fixture and runner. Create the relay, researcher, reviewer and resume
   containers stopped, with one nonce and exact Docker binding hashes. Seal one
   mode-0600 producer manifest outside every writable mount before NativeRun
   starts them. No late replacement or second pool is accepted.
   The archived source must import the stop boundary without falling back to
   live-tree files. An inspect error other than exact resource absence is not
   cleanup evidence; preserve the error, skip uncertain-resource deletion and
   fail the run while checking the other exact owned resources.
2. **Verified offline TLS.** Use a short-lived local test CA and certificate
   valid only for `opencode.ai`, mounted read-only to the three V2 producers;
   `SSL_CERT_FILE` points to that CA. The private key stays host-only and is
   removed with the temporary run directory. Verify TLS hostname and CA rather
   than disabling validation. CONNECT must report `dummy=true` and the fixed
   `opencode.ai:443` authority. The responder accepts only loopback clients,
   records bounded request shape and returns synthetic OpenAI-compatible SSE.
   Before V2 inference, a harmless researcher-container CONNECT probe must
   receive 200 through the relay and increment the same host tunnel ledger;
   this proves the owned path is reachable without treating a later DNS failure
   as provider behavior. The relay's internal address is reserved from Docker's
   inspected subnet while stopped and checked again after T05 starts it;
   Docker leaves a created container's `IPAddress` blank, so never construct
   the proxy URL from that pre-start field.
   A failed handshake or native request is a failed check, not a reason to
   switch to plain HTTP or a provider call.
3. **One allowance across roles.** The first researcher, a fresh reviewer with
   a separate native store, and the exact-session resume all attempt the model
   route through the same relay/capability, pool file and original deadline.
   The owned responder must see each accepted request; a capped attempt must
   leave its denial in the one host ledger. After the three native role turns,
   harmless CONNECT probes may consume the remaining declared tunnel slots;
   a reviewer-container attempt at the fixed authority then must be rejected
   without a new tunnel or owned response. Native session and usage snapshots
   are taken before/after each role. Disabled delegation is documented as
   disabled. Opaque TLS does not reveal HTTP count to the host pool.
   An owned external receiver must be reachable from the relay but not directly
   from a researcher container by literal IP; a DNS failure alone cannot pass.
4. **Harmless native effect and independent check.** First, the host checks
   that original `index.php` prints `before` and `check.php` fails. The owned
   response asks V2 to inspect/edit `message.php` and run all three `php -l`
   commands plus `php check.php` and `php index.php`; native tool trace must
   show the calls completed. A separate host-owned copy/recheck must print
   `after` and `check passed`, with only `message.php` changed. Stop the first
   process, but retain its sealed container ID until global stop; T05 must
   re-inspect it. Verify that no OpenCode process remains there and the stopped
   native store passes `PRAGMA quick_check` before the precreated resume
   container opens the same session. Reviewer and resume processes remain idle
   until their turns, so there is one native DB writer. Preserve a stopped-store
   copy and failing SQL if that read fails. The same session and source bytes
   survive resume. If the mock tool-call format is not accepted, stop and
   record the exact mismatch.
5. **Stop and cleanup.** Request run stop; provider-only admission closure may
   precede producer freeze, but run-state `REVOKED` follows verified exact
   producer stop. A host send queued before stop and a fresh post-stop send must both
   fail the same final dispatch guard without touching an owned receiver,
   even if the transport tunnel cap was separately exhausted. Preserve a sanitized host
   ledger and native/session/app observations, then remove only nonce-owned
   containers, networks, temp CA/key, capability and workspace. Record exact
   IDs and independent absence; no raw prompt, request body, Authorization,
   password, cookie, token, signed URL or private key enters the receipt.

The runnable receipt must name its command, image/source pins, local CA setup,
inputs, expected and actual outputs, ledger, native sessions, stop order and
cleanup. If this E2E passes, the next live step still needs separately reviewed
T05 and CONNECT source plus a bounded official free-model allowance.

## Cloud amd64 base variant — checks before the source change

The existing Dockerfile defaults to the reviewed OpenCode 2.0.32 arm64 child.
An explicit amd64 build may select only the separately verified 2.0.32 amd64
child digest from the same official OCI index. A mutable tag, wrong child
architecture, changed version, or an unrecorded build argument fails before
the derived image is used. Record the index/child digest and the exact build
command; do not rewrite earlier arm64 receipts.

Build on the amd64 executor with its configured proxy and TLS trust. Fail if
the pinned PHP 8.4.26 packages are unavailable. Inspect the derived image's
immutable ID, `linux/amd64`, `opencode --version`, `php -v`, and the required
`pdo_sqlite` and `gd` modules before creating a native producer. A build
failure leaves no usable image and requires exact owned-resource cleanup.

The first amd64 build failed at `apk add` with `server certificate not
trusted`. Before retrying, pass the executor's combined CA bundle as a
BuildKit secret mounted only for that networked `RUN` at apk's documented
`/etc/apk/ca.pem` trust path. Keep HTTPS certificate and hostname checks on.
An absent or wrong bundle in this proxy environment must fail the package
fetch without producing an image; do not use an insecure apk flag or change
repository URLs. Verify the secret mount is absent from the derived image and
that no CA bytes, proxy credential, or temporary trust path were committed to
its layers or ordinary receipt. Without a build secret, the local arm64 recipe
must retain apk's default system trust behavior.

The first CA-backed cloud runner attempt stopped at the created, network-none
host checker: the managed Docker client inserted upper- and lowercase
`HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY` despite no requested environment.
Before changing the runner, require each container role to explicitly request
empty values for these six names unless that role supplies its own exact value.
Also request empty upper- and lowercase `ALL_PROXY` and `FTP_PROXY`, which
Docker can inject from its client proxy configuration. Inspect the stopped
container before start: all ten values must match the
request, no inherited proxy URL or credential may remain, and any unfamiliar
proxy or credential variable still fails the existing critical-name check.
The researcher must keep its exact owned relay proxy and loopback exclusions;
the host checker, relay, and external receiver must not inherit managed proxy
access. A Docker client that ignores an explicit empty override, duplicate or
malformed requested names, changed image/mount, or extra critical variable
must fail before container start and trigger exact owned cleanup. Re-run the
source-only check and then the full cloud offline workflow; a source check
alone cannot establish Docker's actual environment override behavior.

Refresh the allowlisted source manifest and ZIP after the Dockerfile change;
every file must still pass size and SHA-256 checks before staging. Rerun both
cloud source checks and the Linux direct, upstream, and private-listener
transport suites. The offline managed native rehearsal must then use the new
image ID and amd64 relay, prove exact private peer and owned TLS route, stop
the producer before cleanup, and record exact Docker absence. An owned
response does not establish provider access, sidecar policy, or `--live-free`
eligibility; preserve the runner's intentional cloud peer challenge until
those boundaries have independent evidence.

## Internal relay address — checks before repair

The `998d10f` cloud run passed the stopped host-check environment readback,
then failed check 17 before `NativeRun`: this Docker daemon rejects `network
connect --ip` on an internal bridge whose subnet Docker assigned automatically.
The internal address only gives researchers a route to the relay; the fixed
security peer is the relay's separately reserved external address. A created
relay has no reliable dynamically assigned `IPAddress`, so its proxy address
must still be reserved before producer start.

Require an explicit observed private internal subnet in the cloud input tuple.
Before output/Docker, reject a missing, malformed, noncanonical, too-small,
non-RFC1918, or external-overlapping internal subnet. Preserve the old local
replay default. Create only the owned cloud internal bridge with that subnet,
read back `Internal=true` and its exact IPAM subnet, and reserve a usable
relay address different from network/broadcast before any researcher is
created. The OSLit network-only preflight created `172.18.0.0/16` and found
an empty gateway on this internal bridge, then removed the network and proved
the daemon baseline restored. An empty gateway is expected here; a changed
nonempty gateway fails this cloud preflight. No image was present, so that
preflight did not test static attachment.
Docker must accept its static `network connect --ip`; the stopped relay's
`IPAMConfig.IPv4Address` must equal the requested address, the researcher proxy
must name it, and a second inspect after start must report the same actual IP.
Any mismatch, conflict, or uninspectable state fails before inference and
triggers exact owned cleanup. Keep the external cloud peer fixed and
independently inspected. Re-run the full cloud offline workflow, not just a
source check. The deliberate kernel-observed peer gate remains.

## Cloud peer gate — checks before any removal

Use the pinned cloud image and source in an owned-only Docker challenge before
changing the runner. The host listener must observe the reserved relay address
`172.28.224.10` and a different address for an unrelated external container;
the internal-only researcher must not connect directly. The T05 listener must
admit the relay with its local capability and owned TLS receiver, then close
the unrelated container using that same capability and spoofed forwarding
headers before admission. That denial must add no ledger event, tunnel,
charged byte, or receiver hit. A NAT-collapsed or unobserved peer, any changed
denial counter, or incomplete exact cleanup keeps the gate in place.

Only after a reviewed, repeatable peer receipt passes, replace the runner's
cloud-only `cloud_kernel_peer_challenge_required` stop with a per-run wrong-peer
check before native inference. An external-only container must reach the host
listener with the same local capability yet be closed before admission; an
internal-only researcher must also fail a direct listener attempt. Compare
events, tunnels, charged and directional bytes, and owned-receiver hits before
and after each attempt, with relay positives around the negatives so a dead
listener cannot count as a pass. Treat an unavailable probe as a failure.
Keep the separate `--live-free` denial before output or Docker and verify it
with a complete cloud input tuple. Rebuild and audit the transfer bundle,
then run the full managed owned-response native edit, review, and resume
workflow on the cloud daemon. Require its fixture result, source and image IDs,
saved native trace, control checks, producer stop, and exact cleanup proof. A
source check or a pre-session pass alone does not qualify that native workflow.
