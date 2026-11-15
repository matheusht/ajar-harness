# Codex executor admission regression — 2026-11-15

This evidence isolates the `turn/start` admission-lock cycle with the existing controlled Codex peer. The peer withholds its turn response until a background executor sender enters the same dispatch guard. The check also confirms the transport `turn/start` write is guarded and, after the fix, a revoked second send never reaches the transport or peer.

## Results

- `red.json`: captured before the production change on baseline `1d2f9a66`. The controlled peer waited for the executor sender; `Runtime.invoke` returned `native_response_timeout`; the sender entered only after the response wait ended. This is the expected red result, not a passing runtime result.
- `green.json`: captured after the local fix. All focused assertions passed: guarded write, background admission before the response, response after release, and revoked send refused before peer receipt.
- Both runs use a controlled subprocess peer and local lock. They make no model/provider calls and do not qualify the real native backend or execution boundary.

## Reproduction

From a checkout containing this regression, copy the fixed tree into an isolated
directory and restore only the two baseline runtime modules. The baseline commit
does not itself contain the new regression flags.

```sh
replay_dir=$(mktemp -d /tmp/oslit-admission-red.XXXXXX)
git archive HEAD | tar -x -C "$replay_dir"
git show 1d2f9a66:tools/native_runtime_codex.py > "$replay_dir/tools/native_runtime_codex.py"
git show 1d2f9a66:tools/native_runtime_transport.py > "$replay_dir/tools/native_runtime_transport.py"
python3 "$replay_dir/evals/native-qualification/smoke/check_native_runtime_adapters.py" \
  --admission-only --capture-admission-red --output /tmp/native-admission-red.json
```

On the fixed source version, run:

```sh
python3 evals/native-qualification/smoke/check_native_runtime_adapters.py \
  --admission-only --output /tmp/native-admission-green.json
```

## Source hashes

The JSON receipts include SHA-256 hashes for the helper and every `tools/native_runtime_*` source loaded for the run. Key exact inputs:

| Input | Red | Green |
| --- | --- | --- |
| `evals/native-qualification/smoke/check_native_runtime_adapters.py` | `sha256:8807538d963a33b4c01e145ecba48d3ec997654440269703183dd0b5caef7b17` | `sha256:8807538d963a33b4c01e145ecba48d3ec997654440269703183dd0b5caef7b17` |
| `tools/native_runtime_codex.py` | `sha256:238c35dd3818d1d3b1956ec6ae49176e95f03f99ba8c8796a0bb660742bed12c` | `sha256:6383f4067ca521c0013fe62e561855b1528ae14304fe402050f09e88255c57bc` |
| `tools/native_runtime_transport.py` | `sha256:9afba0a16025ab1bb7fa872c64c6e6baa65de8383ef79f3e4ac7b47e9c80bd72` | `sha256:e17ded9a16eb48084596a04a413075f37a04027125fd15542c3be767f620d99f` |

`red.json` identifies the baseline runtime hashes; `green.json` identifies the fixed runtime hashes. The helper and receipt schemas are otherwise the same.

## Hosted native run

GitHub Actions run [43751103990](https://github.com/matheusht/redteam-harness/actions/runs/43751103990) on commit `e93a4fd99de0c0429d9d91493eead2dda4b56123` completed successfully on 2026-11-15. All three jobs (`docker`, `native-linux (codex)`, `native-linux (omp)`) passed.

- Hosted Codex admission JSON passed all five guarded-send and revoked-send assertions.
- The hosted absent-profile check JSON passed at the actual Docker start refusal phase: the named profile was absent before setup; Docker recorded an AppArmor start error; exact requested profile configuration was observed; the container remained `created` and not running; cleanup was clean. The final absent-profile gate also passed. The reviewed profile setup then succeeded and cleanup reported `clean`.
- Codex joined native E2E passed 21/21 checks, including two invocations in one session, four requests to the controlled provider, zero external provider calls, policy readback, and verified cleanup.
- OMP joined native E2E passed 21/21 checks, including two invocations in one session, four controlled-provider requests, zero external provider calls, and verified cleanup.

These are hosted Linux/Docker observations with real native runtimes and a controlled simulated provider. They are not evidence of inference against an external provider. The per-run JSON files under `hosted/` preserve the sanitized results; the full downloaded workflow artifacts are kept at `/private/tmp/oslit-full-native-20261115/published-e93a4fd9/` in the active workspace environment.
