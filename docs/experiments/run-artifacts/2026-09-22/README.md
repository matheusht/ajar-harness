# Bounded research run artifacts — 2026-09-22

These portable artifacts retain exact prompts, model JSONL, stderr, usage,
scripted SDK states, board ledgers, grades and summaries. Every directory has an
`artifact-manifest.json` binding both the original target-local bytes and the
portable bytes. Personal home prefixes in runtime warnings were replaced with
`<redacted-user-home>`; the original raw files remain under `/tmp/redteam-pilots`
in the execution environment. No authorization header, cookie, password or API
key is present in the portable copy.

| Artifact | Calls | Status and admissible conclusion |
|---|---:|---|
| `preflight-no-tools` | 1 | Configuration probe before the frozen study allocation. It confirmed the requested CLI path and retained the unstable-feature warning; it is not a candidate result. |
| `framing-v1-static-development` | 13 | Static classification calibration only. It supplied probes and answer-signalling source comments, so it is not search or persistence evidence. |
| `framing-v2-active` | 18 | Nine active toy assignments selected and executed two bounded probes each. All nine typed verdicts matched the hidden oracle; no framing difference was observed. The fixed two-call schedule does not test adaptive persistence or stopping. |
| `communication-v2-exploratory` | 28 | Exploratory output comparison. Its calibration only echoed fields, final assemblers saw all sources, and the late-correction schedule was incomplete. It does not qualify the planned comparison. |
| `communication-v3-matched` | 24 | Matched three-case mechanism pilot with actual pre/post correction, canonical predecessor notice, exact calibration, and blind grades. Serial graded correct twice; direct zero times; board zero times (one ambiguous). This does not support default board adoption. |
| `recovery-v2-development` | 0 provider/model calls | Scripted approval/serialization development smoke. Its baseline arguments were invented and its cases did not exercise the named mechanics. |
| `recovery-v3-scripted` | 0 provider/model calls | Pinned SDK mechanics: late pending input and soft-cancel resume passed; replaying a pre-effect state duplicated an unreceipted local effect. This is not model reasoning or provider recovery evidence. |

The frozen study aggregate was **83 calls, 1,184,475 input tokens and 15,684
output tokens**, including development, calibration and grading. Including the
earlier configuration probe, all observed CLI activity was **84 calls, 1,198,152
input and 15,708 output tokens**. Both remain within the 100-call, 2,000,000-input
and 80,000-output ceiling. Cached input is
already included in each CLI `input_tokens` receipt and is not added twice.
Dollar cost is unavailable and remains unknown. Claude provider execution was
blocked by organization authentication, and Docker runtime qualification is a
separate result; neither is implied by these Codex CLI or scripted SDK runs.

Communication v3 billed the six shared worker-note calls once in the actual
aggregate. Its `analysis.json` also charges those same calls in full to both the
direct and board standalone estimates, so sharing does not make either deployed
arm look artificially cheap. Human coordination and total labor were not
measured.

## Reproduction boundaries

The frozen manifests intentionally bind their original source commits. Run from
an isolated checkout at the named commit; a current checkout with changed board
or kernel files must fail manifest verification.

```sh
# Active framing, frozen at e3a9f34b7682e3820fe0bec81ec2edbf418cdc08
git worktree add /tmp/replay-framing-v2 e3a9f34b7682e3820fe0bec81ec2edbf418cdc08
python3 /tmp/replay-framing-v2/tools/run_framing_v2.py --verify-only
python3 /tmp/replay-framing-v2/tools/run_framing_v2.py --output /tmp/replay-framing-v2-output

# Communication, frozen at 401b30c8c11002aa994ed2d99be21b10ff095c92
git worktree add /tmp/replay-communication-v3 401b30c8c11002aa994ed2d99be21b10ff095c92
SOURCE_PY=/absolute/path/to/source-checkout/.venv/bin/python
"$SOURCE_PY" \
  /tmp/replay-communication-v3/tools/run_communication_v3.py --verify-only
"$SOURCE_PY" \
  /tmp/replay-communication-v3/tools/run_communication_v3.py \
  --output /tmp/replay-communication-v3-output

# Scripted SDK mechanics, frozen at 6fbdf5c2d43f173ee88a18adcc520cb55cfc33ff
git worktree add /tmp/replay-recovery-v3 6fbdf5c2d43f173ee88a18adcc520cb55cfc33ff
/tmp/redteam-recovery-sdk/.venv/bin/python \
  /tmp/replay-recovery-v3/tools/run_recovery_v3.py --verify-only
/tmp/redteam-recovery-sdk/.venv/bin/python \
  /tmp/replay-recovery-v3/tools/run_recovery_v3.py \
  --output /tmp/replay-recovery-v3-output
```

The recovery command additionally requires the pinned SDK checkout
`f1f35031d364f9f0d8e94dda0853c92abefdccff` and its frozen `uv.lock`.
Reproduction spends new model calls for framing and communication; verification
only does not.
