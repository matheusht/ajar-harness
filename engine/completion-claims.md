# Completion-claim gate

`tools/completion_claims.py` makes prose that declares an engagement, its scoped work, or its
testing complete a verifiable claim. It recognizes the canonical `covered-dry` / `coverage_dry`
forms in claim positions: standalone terminal-state lines/headings, verdict/disposition/status
fields, table cells, and assertions such as “we are coverage_dry.” Instructional mentions such as
“you cannot move coverage to `coverage_dry` while work remains” and glossary definitions are free.
Table cells containing only a terminal enum are deliberately treated as dispositions; explain an
enum in prose rather than putting it alone in a glossary table cell. This is a bounded grammar,
not a general natural-language classifier. The gate also recognizes bounded alternate grammar such as “the engagement is complete,” “all scoped surfaces
are exhausted,” and “no further testing remains.” It recursively scans regular text-like content
regardless of filename extension through the existing record-kernel lock. Files are hashed and
matched in fixed-size streaming chunks; normalized horizontal whitespace and a bounded overlap
keep phrases visible across chunk boundaries without loading large evidence artifacts into memory.
The gate takes two complete tree and reducer/event snapshots and rejects any change between them.
Exact kernel-owned ledgers,
state projections, the kernel lock, and generated views are excluded only from claim matching;
they remain in both immutable tree snapshots. The exact `verdict: coverage_dry` field of a
schema-valid coverage-review record is treated as historical reducer data after a legitimate
reopen; every free-text field in that record, including quoted canonical tokens, is still scanned.

The claim is clear only when the current reducer state is `coverage_dry` and its current-scope
coverage review is linked, or when the exact immutable bytes match a canonical, opaque
grandfather pin. Pins use full `sha256:` digests for both the POSIX path and exact content bytes.
The path digest binds the first validated scope hash *and* the immutable genesis event record
hash. That canonical record is the logical engagement identity: a byte-identical clone, and a
separately recreated root with the same basename, scope, and initial timestamp that produces the
same canonical genesis bytes, are intentionally equivalent. Without adding a nonce or changing
the record, the gate cannot and does not distinguish those cases. A different logical genesis
(for example, a different initial timestamp, engagement identifier, or scope) loses the pin. The
checked-in pin manifest is canonical and has no CLI, environment, or manifest-path override. The
converse is deliberate: copying or moving a claim to another relative path loses the pin.

Writers call the bound API while holding their lock immediately before writing. Admission returns
an immutable tree/state token, rechecked immediately before render publication or the closure
ledger append. This is a cooperative-lock contract: POSIX cannot atomically publish six separate
view files, or prevent a process that ignores `.record-kernel.lock` from changing the tree in the
interval after a check and before a filesystem syscall. The public CLI is read-only, requires an
already-existing `.record-kernel.lock`, and reports only stable codes and a scope-salted opaque
diagnostic prefix on failure.
