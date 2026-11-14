# Cleanup

The package has no host-side effects beyond build caches.

- `poc/stage.sh` creates a single work directory with `mktemp -d`, copies `poc/module/` and the
  eight arm sources into it, builds and runs there, and removes the directory on exit through
  `trap 'rm -rf "$WORK"' EXIT`. Nothing is written inside the package or the repository.
- The script never touches the network from its own code. The Go toolchain may populate its build
  cache and module cache on the first build; that is the only residue. Remove it with
  `go clean -cache` if the host must be returned to its prior state.
- No transaction is signed against a real key, no key material exists outside the synthetic WIF in
  the arm sources, and no transaction is broadcast. There is no node, RPC endpoint, or wallet
  service in the harness.
- Each arm builds its own in-memory transaction and prints cells to stdout. There is no state file,
  no daemon, and no listening port.
- To stop mid-run, interrupt the script; the trap still removes the work directory. A failed arm
  exits non-zero without leaving a process behind.
- Arm 6 triggers a real `index out of range` panic in the SDK; the arm's closure recovers it and
  prints the cell, so the process exits zero and the script continues. Nothing outside the process
  observes the panic. No host state changes.

If the package is unpacked from the zip, deleting the unpacked directory removes everything the PoC
created, apart from the Go caches noted above.
