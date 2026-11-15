# Codex executor admission regression — 2026-11-15

This evidence isolates the `turn/start` admission-lock cycle with the existing controlled Codex peer. The peer withholds its turn response until a background executor sender enters the same dispatch guard. The check also confirms the transport `turn/start` write is guarded and, after the fix, a revoked second send never reaches the transport or peer.

## Results

- `red.json`: captured before the production change on baseline `1d2f9a66`. The controlled peer waited for the executor sender; `Runtime.invoke` returned `native_response_timeout`; the sender entered only after the response wait ended. This is the expected red result, not a passing runtime result.
- `green.json`: captured after the local fix. All focused assertions passed: guarded write, background admission before the response, response after release, and revoked send refused before peer receipt.
- Both runs use a controlled subprocess peer and local lock. They make no model/provider calls and do not qualify the real native backend or execution boundary.

## Reproduction

From the repository root, on the pre-fix source version, run:

```sh
python3 evals/native-qualification/smoke/check_native_runtime_adapters.py \
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
