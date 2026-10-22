# Native origin ingress build

This optional capture route uses Linux `SOCK_SEQPACKET` and per-message
`SO_PASSCRED`/`SCM_CREDENTIALS`. It cannot use curl's Unix stream transport:
`SO_PEERCRED` authenticates the connection opener but cannot rule out a passed
connection file descriptor. The gate, client and ingress are three modes of one
small source-built binary. No binary is checked in.

For `prepare --origin-ingress`, `tools/native_research.py` requires local
`go1.26.4`, verifies the pinned source SHA-256 values, then builds the exact
requested `linux/amd64` or `linux/arm64` target with:

```sh
GO111MODULE=off GOTOOLCHAIN=local CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
  go build -trimpath -buildvcs=false -ldflags=-buildid= \
  -o ORIGIN_BINARY tools/native_origin/protocol.go tools/native_origin/main_linux.go
```

Use `GOARCH=arm64` for `linux/arm64`. The prepared plan records the resulting
artifact digest and ELF machine. Start refuses a missing, modified, writable or
wrong-platform binary. A missing Go toolchain blocks only this opt-in origin
route; ordinary capture remains held on origin. Provider-free source tests run
with `GO111MODULE=off go test ./tools/native_origin`; cross-builds alone do not
prove Docker mount behavior, PID visibility or native request provenance.
