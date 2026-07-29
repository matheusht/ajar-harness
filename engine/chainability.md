# engine/chainability.md — does this finding compound into something worse?

> Pairs with `engine/regrade.md` and `engine/pocinator.md` (both siblings in the Post-stage family) and
> `engine/whitebox-analysis.md` §1, which names this Stage 5 in the funnel and states the pipeline's
> own governing philosophy: stage numbers "show the development progression if anything," not a fixed
> waterfall. This is the third Post-adjacent stage to get a dedicated doc — proven load-bearing twice
> in one session on the same finding (the Cosmos `iavl` negative-`Version` state-sync crash): once as a
> 5-angle pass dispatched during report drafting, once as an independent 4-angle re-exhaustion the
> operator explicitly requested afterward, specifically to be certain nothing had been missed.

## 0. The three-way distinction

> Regrade asks: "Is the finding real?"
> Pocinator asks: "Does this specific PoC/package actually prove the exact claim we're about to
> report?"
> Chainability asks: "Does this finding compound with something else into something worse, or is its
> scope exactly what's already claimed?"
> Escalation (`engine/escalation.md`) asks: "How hard do I push a *confirmed* finding toward its true
> ceiling, and how do I do it without reward-hacking the severity upward?"

Chainability is one input to escalation, not the whole of it. The escalation-specific anti-reward-hack
keystone — the **marginal-contribution critique** (severity = the delta the bug adds vs the world
without it, never the total bad outcome nearby) — lives in `engine/escalation.md` §1, kept there rather
than added to the canonical six angles below, which promote only on repeated cross-instance evidence.

None of these three are redundant with each other. A finding can be real (regrade), proven by a sound
PoC (pocinator), and still have an impact story that's either narrower or wider than what's written —
that's chainability's job, and only chainability's. Skipping it because "regrade and pocinator already
passed" is the same category error `pocinator.md` §0 already warns against for skipping pocinator
because regrade passed: each stage validates a different thing about the same finding.

## 1. Where it sits

```
... -> Stage 4.25 post-confirmation verification -> Stage 5 chainability -> Stage 5.25 novelty/
    paper-review -> Stage 5.5 reachability dossier -> /goal advisory generation
    -> Post: triage -> regrade -> pocinator -> filing
```

That's chainability's canonical position: before the report is even drafted. In practice, both real
passes this session ran *after* regrade and pocinator, as a final sweep once the report already
existed, triggered by the operator wanting certainty before treating the finding as done. Per
`whitebox-analysis.md` §1's own framing, this is not a violation of the pipeline — a candidate can jump
back to any earlier stage from any later one, and the reverse is just as legitimate: running Stage 5
late, as a final check before closing something out, is a normal use of the funnel's fluidity, not an
exception to it. Run it at least once before treating any finding as advisory-ready, wherever it
actually lands in the sequence you followed.

## 2. Why angles, not a fixed checklist

Same argument `pocinator.md` §2 makes about PoC-domain rules, one level over: a crash finding's
chainability angles (does it corrupt state on retry, does it repeat) look nothing like a proof-forgery
finding's (does relabeling extend to nested structures, does it chain into a second protocol layer). A
fixed checklist would either miss what matters for a given finding's shape or be too generic to catch
anything real. What generalizes across finding shapes is not the literal questions but the *shape* of
the questions — six recurring angle-shapes (§3), each instantiated concretely for the specific finding
at hand, then checked against real code or real behavior, never reasoned about in the abstract.

**The six in §3 are a starting baseline, not a closed or domain-limited set.** They're written
generically on purpose, but the only real chainability practice on record so far happened on one
finding in one domain (a Cosmos blockchain engagement), so treat their worked examples as illustration,
not scope. The orchestrator is expected to add engagement- or finding-specific angles beyond these six
whenever its own judgment says something might escalate further or might have been missed — a web-app
finding, an LLM-agent finding, and a blockchain finding will each surface angles the other two never
would, the same way Stage 1's sink vocabulary differs per domain (`whitebox-analysis.md` §2). An
ad-hoc angle stays local to the engagement that invented it until it's proven out as a real, grounded
check more than once, across separate instances — only then does it earn a permanent place in this
doc's canonical list, the same evidence bar that built `pocinator.md`'s own twelve lenses one real pass
at a time. Don't wait for permission to invent a new angle; do wait for repeated evidence before
promoting one into the baseline everyone inherits.

## 3. The six recurring angle-shapes (the current baseline — extend freely, promote sparingly)

Each grounded in a real check from this session's two passes on the `iavl` negative-`Version` finding,
not invented.

1. **Persistence-of-effect on retry/reentry.** Does the triggered effect leave residual state that
   changes what happens the next time the same path is exercised — corruption, an easier second
   trigger, a different failure mode? Checked whether the crash mid-import corrupts on-disk state:
   traced that orphaned node blobs written before the panic are invisible to the fresh-import
   precondition check on restart, so a retry starts clean. Closed negative, but a real, minor
   consequence (an unreferenced-disk-space leak) surfaced along the way and got recorded honestly even
   though it didn't change the verdict.
2. **Repeatability and backoff.** Can the same mechanism be re-triggered, and does anything rate-limit,
   ban, or cool down the attacker between attempts? This is the angle that produced this session's real
   `amplifier_found`: no persistent bad-peer memory across a process restart, combined with state sync
   unconditionally re-attempting whenever local height reads zero, means a single malicious peer can
   *durably* deny bootstrap to a targeted node, not just crash it once.
3. **Composition with other findings already surfaced in this engagement.** Does this finding's
   vulnerable window overlap with a separately-found mechanism for a combined effect worse than either
   alone? Checked whether the crash's window overlapped with a separately-confirmed mempool
   lock-contention finding from earlier in the same engagement. Closed negative, and closed precisely:
   traced the actual reactor code showing the mempool reactor sits in a no-op mode for the entire
   duration state sync is in progress, so the two mechanisms' windows are provably disjoint on a single
   node, not merely assumed unrelated.
4. **Population/reach beyond the originally-assumed victim class.** Does the precondition apply to a
   narrower or broader population than first stated? Confirmed validators catching up after downtime
   go through the identical vulnerable path with no special protection tied to validator status —
   this sharpened the existing report's impact language rather than opening a new verdict category on
   its own.
5. **Fan-out/propagation to multiple victims from one attacker action.** Can a single crafted artifact
   reach victims the attacker never directly connected to, via gossip, relay, or re-broadcast? Checked
   the actual snapshot-discovery reactor code directly: snapshot responses are never relayed to other
   peers, so reaching additional victims requires a direct connection to each one. Closed negative,
   confirmed by reading the real reactor code, not assumed from general p2p intuition.
6. **Sibling-pattern recurrence nearby.** Does the identical root-cause shape, not just a related
   concern, recur in an adjacent field or code path, providing a second route to the same or a worse
   outcome? The independent second pass found and closed four of these — a sibling numeric field with
   the identical missing-lower-bound shape, concurrent-restore races, chunk-ordering attacks, and the
   same pattern checked in a structurally different codebase's own equivalent code — all genuine
   negatives, each closed by reading the actual guarding logic, not by assuming the pattern doesn't
   recur elsewhere.

## 3b. Real disclosed chains (cross-instance corpus — candidates, promote per §0)

The six angles above were generalized from a single Cosmos `iavl` finding (see this doc's header). To
ground them in cross-domain evidence without inflating the canonical six, a corpus of real disclosed
multi-stage chains sits alongside as **candidates** — promote a new canonical angle only on repeated
cross-instance evidence (§0), never from one disclosure. Full corpus (32 chains):
`skills/reporting/research/hackerone-disposition-corpus.md` (bucket B). Representative recurring shapes:

- **SSRF → cloud-metadata → cluster/credential RCE.** One SSRF pivots through GCP/AWS instance metadata
  to a stolen kube-env / service-account token to an interactive root shell (H1 #341876, #455645). Angle:
  *does this SSRF reach a metadata endpoint, and does that token reach a control plane?*
- **Upload → image-processor RCE.** A renamed PostScript "image" reaches an outdated
  ImageMagick/Ghostscript delegate → OS command execution (H1 #403417, #365271, #422944). Angle: *does
  the upload validator check content, and what shells out downstream?*
- **Subdomain takeover → cookie-scope theft.** An expired CNAME lets an attacker serve trusted-origin
  content and harvest a shared-scope cookie (H1 #335330).
- **IDOR → mass account takeover.** A single client-supplied id substitution automated into a loop
  (H1 #1685970). Angle: *does this one-object IDOR generalize to every object, or to ATO?*

**Cross-domain memory-safety / OS chains (P0/ZDI corpus — `skills/oracles/references/project-zero-zdi-chain-corpus.md`, 22 disclosed chains, same candidate status).** The HackerOne shapes above are almost all web request→state; the harder chaining lives in memory-safety and OS boundaries these six angles were never tested against. Representative cross-domain shapes:

- **Sandbox/guest primitive → boundary desync → host/kernel takeover.** A UAF or TOCTOU reachable from
  an unprivileged sandbox (Chrome renderer, VM guest) chained through an info-leak (KASLR/ASLR defeat)
  to arbitrary host/kernel r/w (P0 `MSG_OOB` CVE-2025-38236 renderer→Linux-kernel; KVM EPYC
  CVE-2021-29657 and VirtualBox VMSVGA CVE-2025-30712 guest→host escapes). Angle: *does this in-sandbox
  primitive have a disclosed path to the leak+write it needs to cross the sandbox, or is the sandbox
  the real ceiling?*
- **Zero-click parse → decoder RCE → kernel-driver UAF.** An auto-processed attachment (SMS/RCS audio,
  iMessage image, radio frame) reaches a decoder RCE, then a driver bug for kernel (Pixel-9
  Dolby→BigWave CVE-2025-54957/36934; FORCEDENTRY CVE-2021-30860; AWDL CVE-2020-3843). Angle: *what
  does the target auto-decode with no user action, and what does that decoder hand the kernel?*
- **GPU userland → kernel LPE.** A mobile-GPU driver bug as the kernel-escape link after an
  app/renderer foothold (Mali CVE-2022-36449; Adreno CVE-2023-33106/33107). Angle: *does the sandbox
  reach the GPU driver, and is that the kernel boundary?*

Per-CVE severity can understate a chain: the Edge Pwn2Own set (CVE-2026-45492/45494/45495, individually
4.3/5.0/7.5) composed to a full sandbox escape — chaining is the point, not any one primitive.

## 4. Verdicts and routing

`bounded` · `amplifier_found` · `new_finding_spun_off` · `needs_more_evidence` · `blocked`

- **`bounded`** — investigated angles close cleanly; the finding's scope is exactly what's already
  claimed, nothing worse found. The majority outcome in both real passes (eight of nine angles
  checked landed here). A clean `bounded` verdict across several angles is a valuable, expected result,
  not a sign the pass wasn't thorough enough — see §6.
- **`amplifier_found`** — a real, code-confirmed mechanism makes the *consequence* worse than the base
  claim (wider durability, broader reach, compounding under repetition) without changing what the base
  finding actually is. Folds into the existing finding's report — its Impact section specifically —
  rather than becoming a new finding.
- **`new_finding_spun_off`** — investigation surfaces a genuinely distinct vulnerability, not a
  downstream consequence of the one being checked. Routes to a fresh Stage 0/2 candidate, logged
  separately, not folded into the current finding's report. Conflating two different root causes into
  one narrative is exactly the failure mode this verdict exists to prevent — a flagged-but-not-chased
  area belongs here, named plainly, not silently absorbed or silently dropped.
- **`needs_more_evidence`** — an angle is plausible but needs a concrete additional test before closing
  either way; names the specific next step. Mirrors regrade's and pocinator's own verdict of the same
  shape, for consistency across the Post-stage oracle family. No real instance of this verdict has
  occurred yet in this harness's practice — included for taxonomy symmetry and because it's a
  plausible real outcome (an angle whose resolution needs a heavier reproduction than was practical to
  build in the moment), flagged honestly as inferred, not observed, the same way `regrade.md` flagged
  its own `blocked` before any real instance existed.
- **`blocked`** — genuinely couldn't investigate a specific angle (environment, infrastructure, or
  artifact unavailable) — not a judgment on the finding either way. Also inferred, not yet observed.

No verdict here silently closes anything. `amplifier_found` updates the existing report.
`new_finding_spun_off` creates a new candidate rather than stretching the current one to cover
something it doesn't actually explain.

## 5. Scope boundary against regrade's `escalation_found`

Chainability's `amplifier_found` and regrade's `escalation_found` sound alike and are not the same
question — keep this boundary sharp, the same way `regrade.md` §5 keeps its own boundary against the
narrower CVSS-precedent-reviewer pattern. Regrade's `escalation_found` means the *original
investigation missed direct reach of the identical mechanism* — a second, unguarded occurrence of the
same vulnerable pattern the first pass should have already found; the finding was under-scoped from the
start. Chainability's `amplifier_found` means the mechanism was scoped correctly the whole time, but
its *downstream consequence* compounds — through repetition, missing backoff, or combination with
something else. One is a reach question about the original investigation's completeness; the other is
a consequence question about what happens after the mechanism fires once. If an angle turns up
something that looks like the first shape, that's a regrade-flavored finding and belongs there, not
folded into a chainability verdict just because it surfaced during a chainability pass.

## 6. Fresh eyes help, but this isn't regrade's hard non-negotiable

`regrade.md` §2 requires fresh, zero-prior-investment context as an absolute, because regrade's entire
value is anti-anchoring re-derivation — a same-context "regrade" isn't a regrade at all. Chainability
doesn't have that same structural requirement: a single pass, run with full context, can and did close
angles correctly. What this session actually observed is narrower but still real: a second, independent
pass on the identical finding found four additional angles the first pass hadn't thought to check, all
genuine and all correctly closed. Treat fresh eyes as a strong, evidence-backed recommendation for a
second pass on any high-value finding, not as regrade's kind of hard gate — the difference is that
chainability's failure mode is *incompleteness* (an angle nobody thought to ask), not *anchoring on a
conclusion already reached*, and a second pass is the direct remedy for the former without needing to
insist on zero context the way regrade does for the latter.

## 7. Model tier

Same reasoning as both sibling docs' own model-tier sections. Deciding whether a given angle's result
constitutes a real amplifier or a clean negative is a judgment call — belongs on the planning/reasoning
tier, not delegated wholesale to a faster model. The mechanical legwork underneath a specific angle —
tracing a call graph, running a check against real code, grepping for a sibling pattern in an adjacent
file — doesn't need the expensive tier to execute; it can be Helper-tier work feeding the
planning-tier verdict, per the Orchestrator/Hunter/Helper split (`CLAUDE.md` §2). `engine/roster.md`
doesn't assign chainability a tier at all; this doc self-declares one, the same way `pocinator.md` and
`regrade.md` each had to.
