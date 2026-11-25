# Paired harness comparison — scaffold

**Status, 9 November 2026: preparation only. No engagement or comparison run is authorized by this folder.**
Matheus asked for a scaffold and explicitly said not to run it. This is a study plan,
not a target-local signed `engagements/<id>/scope.md`. The [scope proposal](scope.md)
remains unsigned. Neither side has a scored result.

## Decision

The study asks which harness finds more distinct, real security defects under the
same target, model, time, and resource allowance. It also counts false claims and
human help. Product features, source implementation, synthetic checks, and prior
disclosures do not answer this question. The [protocol](protocol.md) states the
checks that must pass before the comparison can run or produce a score.

## Pinned inputs and open selections

| Input | Candidate identity | Status |
| --- | --- | --- |
| This harness | `matheusht/redteam-harness` commit `b2c0076d03f2955db9235a9ac3477441b82d7cc3` | Merged source; native E2E remains unqualified. |
| 0 | `0sec-labs/0` commit `63e057d63f7f3a57ec0c0848a15373afbf791695`, CLI version `0.28.4` | Source inspected; this comparison has not run. |
| Pilot target | Kanboard `v1.2.49`, commit `f0f7d27007f5a788f14416c548421efd740b7bce`, source archive SHA-256 `3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf` | Existing [observer preflight](../native-qualification/README.md) passed. It did not qualify either harness on this comparison. |
| Observer control | Kanboard `v1.2.50`, commit `a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3`, source archive SHA-256 `44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56` | Fixed-path control for the known defect, not a claim that this release has no other defects. |
| Target runtime | `kanboard/kanboard@sha256:e22b60748cdd75e4ec85501715ec2a2f9fafbd2f97f01117f18eac5dbcc19ba9`, PHP 8.4.16 | Accepted observer image. The native research image differs and needs fresh parity. |
| Researcher brief | Existing [ordinary brief](../native-qualification/RESEARCHER-BRIEF.md) | Candidate starting text. Freeze one neutral brief and identical target access for both arms. |
| Model | **Unselected.** Native admits keyless `opencode/deepseek-v4.1-flash-free` and keyed `opencode-go/deepseek-v4.1-flash`. | 0 has a keyed OpenCode API adapter. Its access to either exact native provider route and model is unverified. No matched-model claim exists. |

The Kanboard image and observer are pinned in the [existing case preparation](../native-qualification/README.md).
The known advisory, fix, and observer answer stay outside both researcher inputs.
The case is public and may be in model training data. A solve on it is not proof of
novel discovery. A second independent target is not yet selected; this pilot alone
cannot decide general research superiority.

The candidate 0 route is `0 scan --target` with the vulnerable source passed by
`--repo`. It needs a running local application. The native route has its own
workspace and optional protected target path. The coordinator must prove that
both arms receive the same source, live entry paths, actor capabilities, and
initial state before comparing research results. Differences in their own
research tools remain part of each harness and must be recorded.

## Before any future run

1. Recheck both harness commits, clean source trees, target archive hashes, image
   digest, model identity, provider entitlement, and enabled tools. Freeze the
   resulting manifest before either arm sees a target.
2. Prepare separate disposable target copies. Create a target-local scope with
   the exact actors, effects, limits, cleanup, and signature. Bind each harness
   to that same authority. This folder grants no target or provider access.
3. Prove that both harnesses can use the exact same model and target with equivalent
   effective limits. Check the provider endpoint, account entitlement, model
   revision or provider receipt, fallback policy, and the live target route. If
   these cannot be matched, record the difference and stop the matched claim.
4. Complete the native E2E gate in [protocol.md](protocol.md) before scoring.
   A synthetic Docker receipt does not satisfy this gate.
5. Use this one case only for a method pilot. Select and freeze an independent
   multi-target roster before claiming which harness finds more across targets.
   Freeze the hidden observer answers, grading method, order, budgets, and the
   [record templates](records.md) before the first scored call. Separate the
   grader from each researcher context.

No target source, runtime, scope signature, approval, provider credential, or
result file is created here. The source checkouts and observer snapshots must
stay outside the portable harness repository when the target-local engagement is
prepared. The two Daybreak Blue Codex chats can inspect and refine this scaffold;
they must not execute a run under this request.
