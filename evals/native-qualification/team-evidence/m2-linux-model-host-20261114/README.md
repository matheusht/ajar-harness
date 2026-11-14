# Linux model-host integration — 14 November 2026

A signed runtime profile can select a separate local Linux Docker model container. Its owner privately reuses the existing Environment for creation, immutable inputs, short renewable leases and exact cleanup. The existing laboratory remains the only target/tool environment. Model provider traffic crosses a separate stdio relay into the existing provider gate; Codex's executor sidecar stays inside the model container. No target mount, Docker socket or provider credential is placed in the laboratory.

The optional `model_host` object pins the local daemon, image, platform, nonroot model user and bounded resources. Versioned `native-runtime-owner-v2` receipts record the signed runtime and dispatch, host/boot, exact container, guardian start time, PID namespace and cgroup identity. The journal records an owner intent before container creation and admits only monotonic observations. A Linux profile cannot publish a Darwin v1 owner. Reopened recovery reconciles the same signed owner and retains the hold if exact cleanup is uncertain. Existing Darwin profiles and receipts retain their original contract.

A fixed bootstrap reads one bounded private stdin frame, checks executable/config pins, constructs the native environment, disables core dumps and execs the pinned model. Credential values remain in private memory and the pipe. Image/helper checks happen before credential resolution. The nonroot controller reads the root guardian's namespace through a fixed read-only root command inside the exact owned container; it matches the namespace to the host-visible guardian start time and cgroup. This avoids requiring a root controller or weakening failed identity checks.

OMP settings and its model catalog are separate native inputs. An optional OMP-only `model_catalog: {path, sha256}` pins a nonsecret catalog. Input admission freezes its bytes in the journal; recovery uses the frozen path. Linux stages it as `/input/model/models.yml` and bootstrap installs it in `/work/.model/models.yml`; the native host adapter also supports the optional catalog. Catalog drift, literal secrets and changed/symlinked native state reject. Provider credentials still use the existing private binding.

The scenario and failure cases were written before the implementation. `before.json` preserves the initial missing-mechanism failures. `boundary-before.json` records credential resolution preceding model-image validation. `owner-downgrade-before.json` records acceptance of a Darwin receipt for a Linux profile. `nonroot-namespace-before.json` records failure when direct host namespace readback is unavailable. `catalog-before.json` records the three missing catalog admission/bootstrap/staging paths. These are intermediate failure observations, not final source snapshots. `after.json` is the final contained result; `manifest.json` pins the final source and retained result files.

Repeat from the repository root with Python 3.11 or later and `ssh-keygen`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_linux_model_host_e2e.py --output /tmp/linux-model-host.json
```

Expected: `status: passed`, fourteen scenario families pass. These exercise signed input admission, immutable controller/journal ownership, private bootstrap subprocesses, controlled Codex/OMP protocol subprocesses, simulated model-container lifecycle, reopened settlement and unresolved cleanup controls. No Docker, external provider or target is contacted. Native catalog staging uses a controlled protocol peer, not the OMP distribution.

Adjacent final checks are retained for contract admission, native boundary, preparation recovery, preflight, runtime adapters and retained specialists. Run the correspondingly named scripts in `evals/native-qualification/smoke` with `--output /tmp/<name>.json` to reproduce. Some preexisting boundary checks use owned local HTTP receivers and certificate creation; Docker, SSH and inference remain simulated or absent.

Actual Linux container startup with pinned Codex/OMP, provider/tool network behavior, descendant containment, real controller/attach loss and hosted recovery remain separate acceptance work. This record does not establish provider inference, research acceptance, production readiness or multi-day operation. The private owner reuses the existing Environment lease guardian; its separate hosted evidence does not by itself prove this model integration.
