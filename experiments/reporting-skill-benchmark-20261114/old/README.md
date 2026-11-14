# BTC PSBT sighash override — old baseline

This is the pre-refactor report from the OKG engagement. The report body is
`report.md`; the PoC and captured output are unchanged from the original
package. `impact.md` is the severity/impact section extracted verbatim from the
same report.

## Run

```sh
sh poc/stage.sh
```

Expected output: `poc/expected.stdout`. The harness builds the eight arms with
Go 1.23+ and may fetch pinned dependencies from the Go module proxy on the
first build. No broadcasts and no live keys.
