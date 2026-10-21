# Owned same-image PHP 8.4.27 qualification

This receipt records one bounded `linux/amd64` lifecycle completed on 21 October 2026. The controller built and registered a fresh image before its first execution. The same immutable image then passed runtime admission, both Kanboard application arms, and the owned managed first, reviewer, and resume workflow.

The image ID was `sha256:4aae0f3a516cd2fcde717e5f2ac055105a04e3a5bb81afe6c484f0c3953b769f` in every admitted stage.

## Result

- Runtime admission passed with PHP `8.4.27-r0`, OpenCode `v2.0.32`, `--pull=never`, and no runtime network.
- The preserved Kanboard observer passed `32/32` checks. Both archive hashes were verified before the first arm. Both arms reported the fresh image ID, and the inner Docker baseline was restored.
- The owned managed workflow passed `80/80` checks across first, reviewer, and resume stages. Its selected boundary reported the same image ID.
- Provider calls, model calls, live target contacts, external credentials, and engagements were all zero. Live admission remained disabled.
- Cleanup removed the task image and seven registered build-cache records. It left no unresolved task cache records and restored the byte-identical Docker baseline.

## Evidence files

- `inputs.json` records source, image, archive, historical, and private-receipt hash pins.
- `result.json` contains the sanitized admitted result and claim limits.
- `run-command.txt` contains the exact redacted command form. Set its three environment variables to task-owned paths before replay.
- `verify.py` checks the public bytes, schemas, source pins, same-image relationships, zero-contact limits, cleanup result, and secret scan. Run `python3 verify.py --self-test` from this directory.

Raw build output, proxy values, CA bytes, extracted source, container and network identifiers, ports, capability material, databases, server logs, and managed transcripts are not public evidence.

## Historical boundary

PR #182's sealed image `sha256:241dd8f788c62d5c9ef87bdab07ce1f05aca7db0199d532a68b5910c7397f7de` was removed. Its receipt still requires that exact image and was not relabeled or replayed with this image.

The earlier managed-only run on `sha256:76af9c070c17a94c3804f4729abef7e417a1b3404b0b0bc16a6f0691b18c2263` passed its owned workflow but did not first pass same-image application parity. It remains excluded from readiness evidence.

## Limits

This result qualifies only the recorded current-runtime image for the owned offline application and managed workflow. It does not qualify a provider or model route, live TLS, a receiver, a target, hosted CI, default adoption, issue #165, or retirement work. Live OpenCode admission remains blocked.
