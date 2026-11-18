# Corpus-enumeration conformance fixture

Two synthetic npm packages exercise the frozen-denominator contract without carrying engagement
data. The conformance checker packages these directories into local tarballs, pins their SHA-1s, and
runs the production enumerator. One package declares an `exports` map; the other deliberately does
not, so the fixture proves that manifest-only enumeration cannot hide published deep entrypoints.

The `fixture-main` package is marked `out-of-scope` in `expected.json`. Its entrypoints must remain
present in the denominator: triage outcome is a row value, never a pre-enumeration filter.
