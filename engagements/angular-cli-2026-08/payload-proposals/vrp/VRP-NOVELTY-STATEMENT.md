# Novelty statement - consolidated for the Google OSS VRP filing (2026-08-15)

Checked via GitHub search API + web search across the campaign (L9 lanes, chain novelty lanes, N-phase refreshes). Per finding:

## D1 - route codegen injection
**Near-miss, exact sink novel.** Adjacent family disclosed + REJECTED: #33074 (SSR manifest code injection via baseHref) and #33076 (server-entry injection), both severity6, closed 2026-04-28 as not-a-vuln under the config-trust doctrine; sink unchanged at the pin. The `--route` schematic sink is not in either report. **Duplicate risk: low** (different sink; the doctrine rejection is the real risk, answered by the delta framing). Citations: #33074, #33076, #33075, #33077 (same-day cluster, reporter foxllb).

## D2 - cache-path deletion
**NOVEL.** Zero hits on `cli.cache.path`/`purgeStaleBuildCache` arbitrary deletion. Adjacent: #22851 (feature PR), #33321 (worktree-cache discussion), both non-security. **Duplicate risk: none found.**

## D3 - fork guard ineffectiveness
**Co-discovered, class public.** angular/components **#33632** (OPEN) independently reports the same `github.event.repository.fork` defect class; a components class-fix PR **#33653** is pending. The angular-cli instance (this filing) is not covered by either. **Duplicate risk: HIGH if delayed** (the components fix may sweep). File promptly, cite both. The forward condition (robot-key exposure if the action ever reads files) is undisclosed.

## M2 - MCP roots residual
**Residual channel NOVEL.** The input channel was fixed upstream (#33653/commits 34e1e0bb5, 2b060630c, 24fd8fce2); the ancestor-walk residual has no public issue. Adjacent: **#32766** (2026-03-16, severity6, OWASP MCP-01 tool-poisoning class, closed won't-fix with an "already compromised" argument) and the zoneless echo (the disclosed instance). **Duplicate risk: low for the residual; the #32766 doctrine rejection is the framing risk**, answered by the stealth-shape evidence.

## M3 - outputPath deletion
**NOVEL for the delete side.** The write side was fixed twice (#8358805d3, then #33312/bd413b0eb, 2026-06-04, main-only). The delete guard was PROPOSED and never merged (**#32873**). The case-guard bypass (case-insensitive filesystems) is undisclosed. #33479 (PR-triggered ng serve RCE class) was fixed at the pin and is context, not overlap. **Duplicate risk: low**; cite #32873/#33312 to preempt the "already fixed" dismissal.

## W1 - win32 dist-tags injection
**Fix-bypass, delta novel.** #32509 (2026-03, severity6) covered this sink class; the full fix #32892 was REJECTED; #32678 fixed the git executor only. The registry-controlled VALUE channel, the pre-gate timing, the manager-independent update path, and the CI-token venue are not in the prior discussion. **Duplicate risk: medium** (the class is known and won't-fix-adjacent); the zero-interaction CI-token delta is the counter. Cite #32509, #32892, #32678.

## E1-C1 - i18n locale-key escape
**NOVEL mechanism.** Zero hits on locale-key subPath escape / findLocaleDataPath module load / locale-key-as-confusion-vector. Adjacent class: #33073 (local file content into dist via CSS url(), severity6, closed same-day without fix, config-trust). **Duplicate risk: low**; the mis-keyed-guard discriminator + SSR execution are the deltas. Cite #33073.

## Cross-cutting notes for the operator

- The foxllb cluster (#33073-#33077, 2026-04-28) shows an active independent researcher on this surface. Filing in sequence reduces co-discovery risk; D3 has the hardest deadline.
- All seven statements were re-verified 2026-08-15; the D3 #33632/#33653 state should be re-checked at filing time (one GitHub search, minutes).
