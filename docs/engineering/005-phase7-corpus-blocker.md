# Phase 7 — measured before building, and it is blocked

**Date:** 2026-08-23. **Tool:** `tools/reachability_corpus.py` (re-runnable).

`docs/research/static-analysis-and-knowledge-base-plan.md` sets two ground rules for Workstream A:
**"measure before we build"** and **"report the denominator."** This does both, before anyone
installs a multi-gigabyte engine.

## Result

| | |
|---|---|
| adjudicated packages found | 24 |
| **usable as reachability ground truth** | **0** |
| confirmed positives | 0 |
| adjudicated negatives | 0 |

The experiment cannot run. Neither of its two deciding numbers is computable.

## Three blockers, in order of how hard they are to fix

**1. The finding schema has no source or sink field.** `schemas/finding.schema.json` carries
`objective`, `surface`, `severity`, `oracle_verdict` and 19 others. It carries **no** `source` and
**no** `sink`. The claimed path exists only as prose inside `proof`. So not one adjudicated finding
in this repository can be turned into a dataflow query without a human re-reading it and writing the
tuple by hand.

This is the concrete blocker, it explains all 13 non-quarantined exclusions, and it is the cheapest
to fix: add the fields, require them for findings whose claim is a reachability claim, and the
corpus starts accumulating from the next engagement.

**2. Eleven of 23 confirmed findings are quarantined.**
`spotify-backstage-2026-07/QUARANTINE-synthetic-adjudication.md` records that its adjudications were
produced by a script with the verdict already decided. Measuring an engine's agreement with a
fabrication measures nothing. Excluding them is not optional, and it removes nearly half the corpus.

**3. The adjudicated-negative side is empty — one case repository-wide.** The plan says plainly that
"a confirm-only corpus cannot measure a false positive." With n=1 the **contradiction rate** is
uncomputable, and it is the number that would tell us the engine and our adjudications disagree.

Even ignoring 1 and 2, twelve positives cannot separate the plan's own decision bands: one case
moves the rate by 8 points and the bands are 20% and 50% apart.

## The language finding, which changes the plan

The plan chose **Go**, "the language of most of our engagements — Cosmos, Klever, Kubernetes,
gVisor." Those engagements produced **zero promoted findings**; they went covered-dry. The usable
corpus is TypeScript 4, JavaScript 2, CI/config 2, unknown 4. **Go is empty.**

The roadmap's later instruction — TypeScript first — is right, and for a reason the plan did not
have: it is where our adjudicated findings actually are.

## A note on the instrument

The first version of this tool excluded cases on a "not dataflow-shaped" regex over the package
text, and threw out 11 of 13 — including `D1-route-codegen-injection`, an injection finding labelled
"authorization configuration" because its prose mentions permissions.

Shape is now reported as a **hint** and never used to exclude. A classifier that decides the corpus
has to be better than the thing it measures, and a regex over prose is not.

## What unblocks Phase 7

1. **Add `source` and `sink` to the finding schema**, required when the claim is a reachability
   claim. Cheap, and everything else waits on it.
2. **Record adjudicated negatives as packages**, not only as prose in a quarantine or triage file.
   The refuted side is where the contradiction rate lives.
3. **Re-run this tool after each engagement.** When positives reach ~20 with ~5 negatives, install
   the engine — and not before.

No outcome here is a failure; the plan fixed that in advance. A measured "not yet" cost one command
instead of a month of engine integration.
