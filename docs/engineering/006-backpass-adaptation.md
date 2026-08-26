# Adapting `backpass` — what was taken, what was refused, and the measured result

**Date:** 2026-08-23. **Source:** Kun Chen, *"Your AGENTS.md is a Neural Net"*, and
`github.com/kunchenguid/backpass` @ `de65698` (v0.1.2), read as source rather than as README.
**Tool:** `tools/transcript_distill.py`. **Verdict: ADAPT, narrowly.**

## What the post actually claims

The neural-net framing is an analogy used as a process template, not a mechanism. The post's own
hinge is *"Now swap the nouns"*; nothing is differentiated and no gradient is computed. Strip the
metaphor and the method is four ordinary disciplines: evidence from transcripts not recollection;
batch before updating; small steps; hold a token budget.

**The post presents no evidence.** No benchmark, no A/B, no before/after. Every number in it is a
property of the pipeline (96–99% distillation, 5,000-token budget, ≤5 edits), never of the outcome.
The screenshot offered as evidence shows a run with an evidence tally of zero.

## What backpass does, from its code

**Zero evaluation.** A grep for `holdout|baseline|regression|benchmark|evaluat|A/B` over `src/`,
`bin/`, README and CHANGELOG returns only unrelated hits. Nothing computes a loss, compares runs, or
scores an edit after it lands. The one thing measured about a proposal is **token count**
(`src/tokens.js:10-15`). "Loss" is a naming convention.

Four README-versus-code gaps, most severe first:

| README | code |
|---|---|
| "Every claim must carry a verbatim quote… the single most important defence against a model confabulating influence" | never checks the quote against the transcript — `analyze.js:40` accepts any string ≥8 chars |
| "a new instruction needs evidence from at least two independent sessions" | enforced against a **self-reported integer** (`proposal.js:65`) |
| "Analysis never writes. `apply` is the only writing command" | false for `bootstrap`, which auto-accepts every edit with no flag (`bootstrap.js:112`) |
| a gap is "retired" when covered | Sørensen–Dice bigram similarity ≥0.6 — *similar words were written*, not that the mistake stopped |

Genuinely solid, and better than `deepsec`: the model never supplies patch text. It edits a staging
copy; backpass Myers-diffs it and cuts hunks from the original, SHA-fingerprinting the repo either
side.

## Taken, and refused

**Taken:** evidence from transcripts not recollection; the ≥N-sessions batching rule; near-duplicate
clustering.

**Refused, and the refusals are the design:**

1. **Writing doctrine.** Here `AGENTS.md`/`CLAUDE.md` **is** the evaluator. `docs/decisions/0003`
   requires an evaluator change to *re-run the incumbent before any candidate is judged*; a review
   click is not that. The tool has no write path to any tracked file, enforced by `DENY_WRITE` plus
   a self-test, not by a docstring.
2. **The REMOVE step and its zero-sum budget.** `tools/kb.py:21` — a negative records that **we**
   failed to find something. Deleting a unit for accumulating negatives is the D-09 error: three
   covered-dry runs against hardened targets retire the family, and the fourth target ships it
   unguarded.
3. **The model's self-report about which instruction helped.** That is the shape that produced the
   fabricated `claim_state: supported` field.

**Mined instead: the operator's own corrections** — external ground truth in the user's words, not
the agent grading itself. Every candidate carries a quote the tool **re-reads from the source
transcript and verifies**, which is the check backpass documents and does not perform.

## The measured result, on 61 real sessions

| | |
|---|---|
| `type: "user"` rows | 16,484 |
| of those, tool results wearing the user role | **13,814** |
| human-typed operator turns after filtering | 1,543 |
| correction signals matched | 60 |
| dropped by redaction (fails closed) | 21 |
| dropped, quote unverifiable | 5 |
| clean, genuine corrections | **34** |
| **candidates at N≥2** | **0** |

**The 34 corrections are real and the clustering still returns nothing.** They do not group because
each correction names a different specific thing, even when the underlying lesson repeats — "speak
simple technical English", "revert the merges you did at main, i didn't allow you to", "we agreed it
was medium".

That is a measured negative on backpass's core mechanism, on real data: **Sørensen–Dice bigram
clustering cannot group semantically-identical lessons expressed in different words.** The evidence
is there; the clustering step is the weak link. Closing that gap needs a semantic step, which means a
model, which is the confabulation surface refused above — so it would need its own gate before it
could be trusted.

## The instrument lesson, again

The first filter kept every `type: "user"` row and excluded three prefixes it guessed at. On real
data it returned 4 candidates and **all 4 were machine text** — compaction preambles and injected
slash-command prompts. The fix was structural discriminators taken from the rows themselves
(`toolUseResult`, `isSidechain`, `promptSource`, `entrypoint`), not better prose patterns.

A filter validated only against an imagined layout can be 100% wrong on real data and still look
like it ran. That is the third instance in this repository this month.

## Disclosure

Backpass sends transcript content to a model API. Engagement transcripts are Plane-3 material and
some engagements sit under disclosure obligations, so **running backpass unmodified over this
repository's sessions would be a policy breach**. `transcript_distill.py` never leaves the machine
and drops any candidate matching a host, IP, token, bearer, JWT, private key, or engagement
identifier — 21 of 60 signals were dropped that way. Fails closed: an unreadable transcript yields
zero candidates, never a pass.
