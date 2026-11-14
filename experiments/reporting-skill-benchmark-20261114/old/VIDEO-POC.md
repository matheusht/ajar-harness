# Video PoC plan (policy: working video PoC provided on request)

Target 90–120 s, single take. Show, in this order:

1. `git -C go-wallet-sdk rev-parse HEAD` → `89c5153f…` (the pinned checkout).
2. `sh submissions/btc-psbt-sighash-override/poc/stage.sh`
3. Arm 2 (the one that matters): the hostile PSBT, no caller options — three probes, each
   `digest_is_constant_01=true` and `attacker_tx_script_0x33_sig_valid=true`.
4. Arm 1: `S-0x83` (allowlisted seller type) hits the same constant; `S-0x01` control `false`.
5. Arm 3: P2WPKH — `still_valid=true` after the output moves to `0x22…`; `0x01` control `false`.
6. Arm 4: `NONE` — `still_valid=true`; control `false`.
8. Arm 6: `panic=runtime error: index out of range [99] with length 1` from both entries.
7. Ten seconds on source: `psbt_tx.go:1643-1645` (override), `:667/:683` (declared sighash),
   `:670-673`/`:1600-1609` (swallowed errors).

Recording command:

    cd /path/to/engagement
    sh submissions/btc-psbt-sighash-override/poc/stage.sh | tee /tmp/video-cells.txt

All offline (`GOPROXY=off`), synthetic keys, no broadcast. Keep each cell readable on screen.
