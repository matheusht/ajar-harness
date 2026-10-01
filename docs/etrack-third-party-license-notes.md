# E-track third-party tool license notes

The post-Phase-14 adversarial-input E-track
(`docs/post-phase14-evasion-obfuscation-tooling-plan.md`) references three external tools. **All three
are AGPL-3.0**. The current converters do not invoke, detect, or integrate with them. Any future
integration remains **arms-length only**: external CLIs via subprocess, never vendored, copied, linked,
or imported into this portable harness (Plane 1/2). Confirm AGPL obligations before any distribution or
hosted use.

| Tool | License (verified 2026-06-27) | Use in the E-track | Integration boundary |
| --- | --- | --- | --- |
| `elder-plinius/P4RS3LT0NGV3` | AGPL-3.0 | richer encoding/obfuscation transforms | referenced in plans; no converter integration |
| `elder-plinius/ST3GG` | AGPL-3.0 | stego embed (probe) + detect (defense) — **E2** | referenced in plans; no converter integration |
| `elder-plinius/GLOSSOPETRAE` | AGPL-3.0 | tokenizer/covert-channel transforms + decode evidence — **E3** | referenced in plans; no converter integration |
| `FlechetteLabs/Tollbooth` | AGPL-3.0 | read-only egress observer → second-witness traffic digest | unmodified external **container**; our `tollbooth-digest-adapter.py` consumes its export only |

## Rules

- **Never vendor or import.** No source from these repos enters this repository. `git`-cloning them into
  the tree is prohibited.
- **stdlib implementation.** Current converters use dependency-free stdlib transforms and do not check
  whether any external CLI is installed.
- **No payload corpora.** These tools are used as *transforms/detectors* (codecs, stego encoders,
  decoders), not as sources of harmful-content payload catalogs. See the E-track plan §3 scope decision.
- **Redaction still applies** to anything any of these tools touches before it enters a plane.

## E1 status

E1 wires **no** external tool. `tools/obfuscation-converter.py` uses only the Python stdlib
(`base64`, `codecs`). P4RS3LT0NGV3 remains a tool referenced by the plan, not an implemented adapter.

## E2 status

E2 wires **no** external tool. `tools/stego-converter.py` uses only the Python stdlib for zero-width
text steganography (embed/extract/detect). ST3GG is referenced in the plan; no adapter or CLI detection
is implemented.

## E3 status

E3 wires **no** external tool. `tools/covert-channel-converter.py` uses only the Python stdlib for
homoglyph / constructed-script / token-break channels. GLOSSOPETRAE is referenced in the plan; no
adapter or CLI detection is implemented. The **decode-evidence core is built** hermetically
(`tools/covert-channel-evidence.py`, golden-tested); only the live traffic *source* (the operator-gated
Tollbooth container) is deferred — see `docs/etrack-tollbooth-standup.md`.

## E4 status

E4 wires **no** external tool. `tools/encoding-robustness-eval.py` imports the harness's own stdlib
converters and runs them against a deterministic hermetic fake target. It is a **fixture** that proves
the safety-generalization-gap measurement plumbing; it is **not** evidence about real models, optimizes
nothing automatically, and emits no verdict. `evals/etrack/technique-memory.json` is append-only,
sanitized, advisory. `autonomous_gap_closure_count` stays 0.

## Tollbooth status (hermetic half only)

The redaction boundary is built and tested: `tools/tollbooth-digest-adapter.py` turns a Tollbooth-style
export into an allowlist-schema, secret-free `traffic_digest.json`, gated by a golden-secret self-test
(planted Bearer/JWT/Cookie/api-key/signed-URL secrets must not survive). **No Tollbooth container was
stood up.** The live half was **validated once in a sandbox** (operator-authorized): an unmodified `proxy`+`backend`
observer was built, run observe-only/ephemeral, exercised with a benign call, redacted end-to-end to a
secret-free digest, then fully torn down (containers/images/clone/CA removed; Docker returned to prior
state). Footprint + the confirmed native export shape are in `docs/etrack-tollbooth-standup.md`. Real
engagement footprint must still be measured on operator hardware. Nothing from Tollbooth was vendored.
