# recon-signals.md — obyte-ocore-2026-08

Complete this before routing. One row per observation. A `negative` signal — a control that looks
correctly enforced — is recorded as likely-held and a positive-control candidate, never as a finding.

| # | Observation (file:line) | Cards it lights up | strong / weak / negative | Note |
|---|---|---|---|---|
| | | | | |

## Baseline controls — what the node refuses with no attack

Record before any attack. A finding means nothing without this.

| Control | Behaviour observed | Where enforced |
|---|---|---|
| | | |

## History-sweep shapes (fill from the commit sweep — SHAPES, never diffs)

A fixed bug marks a family. Record the abstract shape, then hunt for siblings. Any candidate that
maps to a shape here must be checked against the actual fix before promotion.

| # | Abstract shape | Family it marks | Sibling paths to check |
|---|---|---|---|
| | | | |

## The two $50k lanes — PROOF STRATEGY, not a feasibility verdict

Do not write "no path found". Write what proof would look like and what the condition decomposes
into. A lane with a written strategy and no path yet stays open.

**Q-A — unrecoverable total shutdown of the entire Obyte network**

- What would count as proof to a reviewer?
> 
- Sub-conditions (all order providers down? a consensus-rule violation that partitions permanently?
  a state no valid unit can extend?):
> 
- What must the local lab show?
> 

**Q-B — executing a transaction from another user's account, without their private key**

- What would count as proof to a reviewer?
> 
- Sub-conditions (signature verification, authentifier parsing, definition-language predicate,
  private spend proof — which of these could produce it, and how would each look?):
> 
- What must the local lab show?
> 

## The DoS coordination question

Out of scope: temporary disruption a fix resolves **without** network coordination.
In scope: disruption whose resolution **requires** network coordination.

| Availability candidate | Resolvable without coordination? | Therefore |
|---|---|---|
| | | |
