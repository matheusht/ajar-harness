# Optional owned application reset: failure-first workflow

Written before implementation, 14 November 2026. Base: `09d0bfc5`.
This is an engineering fixture specification, not a research target or permission
to reset an existing deployment. No provider, downloaded image, local daemon
change, impact artifact or policy activation is required by the local checks.

## Contract and expected successful workflow

An operator signs an optional owner profile, explicit reset effect and a logical
HTTP origin under `.invalid`. Its target is a separate, disposable `Environment`
container; it is never the native client lab. The profile fixes the baseline ID,
unprivileged application command, service port and immutable environment image.
No arbitrary reset script or worker-supplied state assertion is accepted.

The existing capture operation accepts optional
`starting_state:{"app-main":"baseline-1"}`. Under its existing resource lease,
the host prepares a fresh target container, starts the signed application, and
binds the exact logical origin to a private socket connector launched through the
exact container ID. The target has no direct network or host mounts. All HTTP
traffic still passes the existing effect/account gateway. A request body, URL,
header or redirect cannot change the connector's destination.

The owner records protected observations before capture dispatch. Probe execution
binds these observations and the target generation. A fresh reviewer has a distinct
native session, client lab and target generation with the same baseline. Cleanup
observes exact target and client absence. The journal remains the only durable
state owner. An ordinary application URL without this capability keeps the existing
limited capture behavior.

## Failure cases required before implementation

| Case | Inputs/action | Required result |
| --- | --- | --- |
| Missing authority | No owner profile, reset permission or reset effect | Requested reset refused before target creation; ordinary limited capture unchanged. |
| Changed signed data | Change baseline ID, command, profile/image digest or access identity | Refuse before effect; original signatures/records unchanged. |
| Remote masquerade | Owner profile names a public production URL | Refuse; only a separately signed owned `.invalid` origin is eligible. |
| Wrong identity | Replace daemon, container ID, nonce, profile or generation | No request or cleanup touches the substituted/unrelated resource. |
| Wrong origin | Request a different host, port, scheme, access or redirect | No connection to the target or another host; refusal recorded. |
| False reset output | Target/helper prints a successful reset marker without replacement | Marker does not create a protected start receipt or clean replay. |
| Client-only reset | Recreate native client lab while target survives | Application still has no verified clean start. |
| External state | Image declares volumes or a host bind/persistent mount/network appears | Owner configuration validation fails; no reset claim. |
| Startup failure | Signed command exits before the target accepts requests | Capture has an explicit execution failure, not readiness/security success. |
| Lease/revocation | Expire/revoke before creation, launch, connection or probe | Deny new effects; cleanup remains bounded to known owned resources. |
| Competing work | In-flight parent request or another worker owns the application | Reset/capture cannot overlap; independent source work continues. |
| Generation reuse | Reuse start receipt for another capture or after intervening request | No clean-start admission from stale evidence. |
| Reset after probe | Receipt is produced after experiment dispatch | Experiment cannot adopt it as its starting state. |
| Partial reset/loss | Lose controller before/after create or before receipt adoption | Read back exact recorded resources; adopt once or retain unknown; never blindly repeat probe. |
| Cleanup failure | Resource still running, wrong ID, unavailable owner/SSH | Hold application and cleanup obligation; no false clean closeout. |
| Replay mismatch | Baseline/account/effective config differs across effect and replay | Results not comparable; reviewer cannot confirm. |
| Valid replay | Same baseline and effect, new reviewer/client/target generation | Protected replay eligible; independent measurement review remains required. |
| Combined access | Source plus one/multiple applications | Every application requires its own matching start receipt; source-only subset unchanged. |
| Credentials | Synthetic target authentication reflected in response | Existing target filter refuses publication; owner gets no provider credential. |

## Runnable evidence tiers

1. Local composition: actual owned HTTP server, actual private socket relay and
   journal; simulated Docker lifecycle is explicitly labeled. Exercise the public
   owner/capture interface and negative inputs. It proves framing and composition,
   not Docker isolation or a reset of a real deployment.
2. Opt-in actual Docker: an already installed digest-pinned engineering image with
   a harmless stateful counter. Observe mutations, fresh container identity and
   baseline state, immutable inputs, separate native client, origin-bound requests,
   lease revocation, exact cleanup and recovery. No pulls or default daemon use.
3. Joined native workflow follows on the integrated Linux head and remains distinct
   from the operator-owned fresh-target research acceptance.

Each result records command, environment prerequisites, exact source/input hashes,
expected/observed outcomes, proof tier and cleanup. Save a failing pre-implementation
result before code, then the same affected scenarios after implementation.

## Runnable commands

```sh
python3 evals/native-qualification/smoke/check_application_owner_e2e.py --output /private/results/application-owner.json
python3 evals/native-qualification/smoke/check_application_reset_e2e.py --output /private/results/application-reset.json
```

Both require Python 3; the signed workflow also requires `ssh-keygen` and OpenSSL.
The first uses an actual counter/stdio connector with simulated container ownership.
The second adds signed input parsing, the real journal/capture path, fresh reviewer
replay, two applications with source access, cleanup failure and no-reexecution
recovery. The result retains actual counter bytes, target/start/request identities,
cleanup states and source hashes. Expect `status: passed`; target processes are
owned by the fixture and stopped before return. No provider or Docker is contacted.

For a disposable Docker host with an already installed Python image:

```sh
python3 evals/native-qualification/smoke/check_application_owner_docker_e2e.py \
  --endpoint unix:///var/run/docker.sock --image-id sha256:REPLACE_WITH_INSTALLED_IMAGE_ID \
  --output /private/results/application-owner-docker.json
```

This opt-in check exercises the production owner, actual fixed-origin requests,
mutation, distinct target recreation and exact cleanup/recovery. It performs no
image pull, changes no Docker settings and preserves preexisting resources. It
does not include a native model or research task. Retain its actual result before
claiming Docker qualification; the local simulated results do not supply it.
