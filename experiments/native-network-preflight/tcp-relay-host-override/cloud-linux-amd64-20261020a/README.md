# Linux/amd64 relay cross-build

`tcp-relay-linux-amd64` was built twice from the pinned `tcp_relay.go` with the
offline flags recorded in `result.json`. Both builds were byte-identical.
`file` identified a statically linked Linux x86-64 ELF. The binary has not run
on the cloud executor, in Docker, or against a provider. The local arm64 relay
and its prior native checks remain separate evidence.
