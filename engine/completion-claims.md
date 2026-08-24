# Completion-claim gate

`tools/completion_claims.py` makes prose that says `covered-dry` or `coverage_dry` a
verifiable claim. It recursively admits only regular, UTF-8 Markdown through the existing
record-kernel lock, takes two complete Markdown-tree and reducer/event snapshots, and rejects
any change between them. Generated views are excluded only from matching claims; they remain in
both tree snapshots.

The claim is clear only when the current reducer state is `coverage_dry` and its current-scope
coverage review is linked, or when the exact immutable bytes match a canonical, opaque
grandfather pin. Pins use full `sha256:` digests for both the scope-salted POSIX path and exact
content bytes. The checked-in pin manifest is canonical and has no CLI, environment, or
manifest-path override. A whole-tree byte-identical clone is intentionally indistinguishable
from its source: identity is not evidence, while scope-salted path and content hashes are. The
converse is deliberate: copying or moving a claim to another relative path, or placing it in an
independently attested engagement, loses the pin.

Writers call the bound API while holding their lock immediately before writing. The public CLI
is read-only, requires an already-existing `.record-kernel.lock`, and reports only stable codes
and a scope-salted opaque diagnostic prefix on failure.
