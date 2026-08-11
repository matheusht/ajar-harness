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

## The two ladder questions

The reward ladder is flat except for two mechanisms. Answer both early, even if the answer is
"no path found yet", and revisit as recon proceeds.

**Q-A — What would an unrecoverable total shutdown of the entire Obyte network require?**
> 

**Q-B — What would executing a transaction from another user's account, without their private key,
require?**
> 

## The DoS coordination question

Out of scope: temporary disruption a fix resolves **without** network coordination.
In scope: disruption whose resolution **requires** network coordination.

| Availability candidate | Resolvable without coordination? | Therefore |
|---|---|---|
| | | |
