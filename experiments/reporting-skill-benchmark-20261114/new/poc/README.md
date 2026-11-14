# PoC — BTC PSBT sighash scope bypass

`module/` is the pinned `coins/bitcoin` root package (source files byte-identical to 89c5153f by `cmp`; `go.sum`
is added for the build) plus the `doginals` package it imports. Unrelated subpackages are omitted.

    sh stage.sh

Prints the cells for eight arms and the binary SHA-256s. Go 1.23+; no network calls in the harnesses
(Go may fetch btcd/btcutil on first build).
