# R8 — Preview deploy metadata race: attacker-chosen channelId/comment number

- **Engagement:** angular-dev-infra-2026-08 · **Pinned commit:** `04230133d395dfb032d782b8e63b4fcbbd406aa5`
- **Attribution:** `angular/dev-infra` — the action contract (`pack-and-upload-artifact` + `upload-artifacts-to-firebase`) passes artifact-derived values into privileged deploy sinks with zero validation. Consumer wiring (same-job build+pack) is the documented usage pattern.

## One sentence on why it is real

The fork-controlled bazel build and `pack-and-upload-artifact` run in the **same job** (consumer wiring, verified); a background daemon spawned by fork code during the build overwrites the deterministic metadata path between the inject and tar steps (race empirically proven: injected value survives 0/60 trials vs a continuous overwriter), so the uploaded artifact carries attacker-chosen pull-number/revision — and the trusted `workflow_run` deploy job extracts them with zero validation into the Firebase channelId and the sticky-comment issue number.

## Mechanism (source → sink → path)

1. `angular/angular` `.github/workflows/adev-preview-build.yml` (public, fork-triggerable `pull_request`): single job `adev-build` — steps: `pnpm bazel build //adev:build.production` (fork-controlled BUILD files/genrules execute; a genrule can daemonize a process) → `pack-and-upload-artifact@04230133…`. No isolation between fork code and the pack action.
2. `target-pack-action.yml`: `copy` step builds `$RUNNER_TEMP/pack-and-upload-tmp-dir` (deterministic path); `inject` step runs `inject-artifact-metadata.js` writing the metadata filename (fixed, per constants.ts) (metadata filename; fixed constants.ts value); `pack` step tars the directory. The attacker daemon continuously overwrites the file between inject and tar.
3. Local replication (verbatim inject logic + tar): 60 attacker trials → injected value survives **0/60**; atomic overwriter wins 37/40 (3/40 torn); control (no attacker) → 20/20 injected survives. Inject→tar gap is 0–5 ms but irrelevant — the overwriter is continuous.
4. the consumer deploy workflow (`workflow_run: completed`, permissions `pull-requests: write` + `FIREBASE_PREVIEW_SERVICE_TOKEN`): `upload-artifacts-to-firebase` extracts `unsafe-pull-number` via `extract-artifact-metadata.ts` — reads the file, trims, sets output. **No numeric/format validation, no integrity binding to the triggering PR.**
5. Deploy action `action.yml:103`: `channelId: pr-${{github.repository}}-${{steps.artifact-info.outputs.unsafe-pull-number}}-${{inputs.workflow-artifact-name}}`; `:112`: sticky-comment `number: ${{steps.artifact-info.outputs.unsafe-pull-number}}`.

## Impact (honest ceiling)

- **Confirmed capability:** attacker-chosen pull-number (any integer) + revision string reach the privileged deploy job's Firebase channel deploy and PR comment.
- **Effect 1 — preview-channel content substitution:** picking a victim PR's number makes the attacker's deploy target the victim's channel (`pr-angular_angular-<N>-adev-preview` on Firebase site `ng-dev-previews-fw`); last deploy wins → attacker content served at the victim's preview URL on Angular's official preview infrastructure (phishing/malware hosting surface on `*.web.app`).
- **Effect 2 — bot comments on arbitrary issues:** sticky comment with the workflow bot identity on any issue/PR number, with attacker-chosen text + preview URL (spam/social engineering).
- **NOT possible:** secret exfiltration from the deploy job, code execution in the deploy job, production-channel deploy (fixed `pr-` prefix can never equal `live`).
- **Preconditions/caps:** (a) the current consumer wiring omits the action's required inputs `angular-robot-key`/`triggering-label` — the chain is **dormant today**; the identical vulnerable structure ran end-to-end in July 2026 (working-era consumer pin); (b) a maintainer must apply the preview trigger label (label removal step is ineffective for the current run — it gates on the immutable trigger-time payload); (c) one-shot per labeled run (label is removed after the first run).

## Controls and why they do not hold

- `permissions: read-all` on the build job — limits the GitHub token, not process persistence on the runner.
- `remove-preview-label` step — removes the label for non-Googler authors, but all later steps gate on the **trigger-time payload** (`contains(github.event.pull_request.labels.*.name, inputs.triggering-label)`), so the current run proceeds with the label present.
- No validation in `extract-artifact-metadata.ts` — reads + trims + sets output.
- No integrity binding (hash/signature) between the artifact bytes and the PR number.

## Negative controls (byte-identical harness)

- No-attacker control: 20/20 runs carry the injected value (decoy `66666` clobbered by inject) — proves the harness correctly detects injected content and that only a live concurrent writer flips the outcome.
- Validation-absence check: `extract-artifact-metadata.ts` source read — no numeric/format/range validation.

## Replay / contamination

- Independent fresh-context refuter re-reproduced the race (0/60) and re-verified every link (same-job wiring, unvalidated extraction, channelId/comment wiring) — verdict: NOT REFUTED.

## Severity / category

- **Low** (CVSS 5.3, see vector below). Category: Product Vulnerability / repo-configuration in-scope. Not SCC (no source/artifact/package compromise, no secret exfil; bounded to preview-host content + comments).
- CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:N/I:L/A:N = 3.1 (Low). AC:H = the dormant-wiring + maintainer-label preconditions; UI:R = requires a maintainer to visit the substituted preview or the comment to land.

## Remediation

1. Validate the extracted pull-number (strict integer + range) and revision (git SHA shape) in `extract-artifact-metadata.ts`.
2. Bind the artifact to the triggering PR server-side (compare artifact metadata against the `workflow_run` payload's PR number) in the deploy workflow.
3. Stop the label-removal gate relying on trigger-time payload; check live label state at each step.
4. Move the pack step into a separate job from the fork-controlled build (or sign the metadata file with a key the deploy job verifies).

## Unresolved caveats

- Current consumer wiring state (dormant vs active) — consumer-side drift; verified dormant at angular/angular main as of 2026-08-13, active in July 2026.
- Firebase channel overwrite semantics (last-write-wins) — standard Firebase hosting behavior, not live-verified.
- Consumer-side attribution boundary: the same-job wiring is the consumer's config; the flaw is dev-infra's action contract.
