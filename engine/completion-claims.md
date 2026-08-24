# Completion-claim gate

`tools/completion_claims.py` makes prose that says `covered-dry` or `coverage_dry` a
verifiable claim. It recursively admits only regular, UTF-8 Markdown through the existing
record-kernel lock, takes two complete Markdown-tree and reducer/event snapshots, and rejects
any change between them. Generated views are excluded only from matching claims; they remain in
both tree snapshots.

The claim is clear only when the current reducer state is `coverage_dry` and its current-scope
coverage review is linked, or when the exact immutable bytes match a canonical, opaque
grandfather pin. Pins use full `sha256:` digests for both the POSIX path and exact content bytes.
The path digest binds the first validated scope hash *and* the immutable genesis event record
hash, so it cannot be replayed into a separately initialized engagement with identical scope
text. The checked-in pin manifest is canonical and has no CLI, environment, or manifest-path
override. A whole-tree byte-identical clone intentionally retains that genesis record and is
therefore indistinguishable from its source. The converse is deliberate: copying or moving a
claim to another relative path, or placing it in an independently attested engagement, loses the
pin.

Writers call the bound API while holding their lock immediately before writing. Admission returns
an immutable tree/state token, rechecked immediately before render publication or the closure
ledger append. This is a cooperative-lock contract: POSIX cannot atomically publish six separate
view files, or prevent a process that ignores `.record-kernel.lock` from changing the tree in the
interval after a check and before a filesystem syscall. The public CLI is read-only, requires an
already-existing `.record-kernel.lock`, and reports only stable codes and a scope-salted opaque
diagnostic prefix on failure.
