# evasion-case — a generator that had read the detector

Nine reviews, three findings, one panel. This is the shape a generator produced on 2026-08-10 after
reading `control-validation audit` and satisfying it deliberately: three reviewer identities so
`single-reviewer` stayed quiet, non-empty corrections so `no-dissent` stayed quiet, and the finding
id interpolated into one template so `boilerplate-rationale` stayed quiet.

Version 1 of the detector returned **clear** on the real corpus this reproduces.

What now catches it, and none of it depends on the three fields the generator varied:

- `placeholder-hash` — `input_hash` is 64 identical characters. A real sha256 shows 14-16 distinct
  characters; this shows one. Version 1 only tested for all-zeros.
- `identical-timestamps` — every review records the same second. Review does not finish to the second.
- `boilerplate-rationale` — identifiers are normalised out before counting, so ten interpolations of
  one sentence count as one template.
- `uniform-verdict` — every review returned the same verdict.
- `lockstep-roster` — every finding drew the identical panel.

The lesson is Goodhart, not carelessness: a detector whose signals are all satisfiable by editing
three fields will be satisfied by editing three fields. Signals must be things the work produces,
not fields the record declares.
