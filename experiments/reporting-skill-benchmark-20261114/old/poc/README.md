# PoC — BTC PSBT sighash scope bypass

`module/` is the pinned `coins/bitcoin` root package (files byte-identical to 89c5153f) plus the
`doginals` package it imports. Unrelated subpackages are omitted.

    sh stage.sh

Prints the cells for six arms and the binary SHA-256s. Go 1.23+; no network calls in the harnesses
(Go may fetch btcd/btcutil on first build).
