# pattern-candidates.md — local, unpromoted observations

Capture repeated *shapes* you notice during this engagement that might generalize into a Plane-1
`skills/patterns/` card. This file is **engagement-local and append-only** — it is NOT a promotion.
Promotion is manual and scrubbed: candidate here → operator-reviewed `record-memory` disposition →
sanitized `casebooks/<id>/` PR → pattern card update. A `promote` disposition proposes that later PR;
it never writes Plane-1. `defer` and `no_novel_lesson` are equally valid terminal outcomes.

Keep entries abstract enough to survive scrubbing later: describe the shape, not the secret. Link
evidence by id (`finding://`, `attempt://`), never paste transcripts or live values.

## Format per candidate
- **observed shape:** the repeated thing (one sentence — the structure, not the payload)
- **seen on:** surfaces / endpoints (abstract)
- **evidence:** `finding://...  attempt://...`
- **why it may generalize:** what makes this bigger than this target
- **why it may NOT:** the honest counter — target-specific quirk? already covered by a card?
- **candidate destination:** existing pattern card to extend, or a proposed new `pattern.<id>`
- **lesson kind:** `positive | negative | refutation | reward_hacked_proof | environment_failure | mixed`
- **held counterexample (if any):** where the SAME class was enforced correctly here (strengthens the card)
- **sanitization:** target identifiers, credential values, and harmful recipes removed; evidence IDs retained
- **promotion status:** `local` → `proposed` → `promoted` / `dropped`

## Entries

### PC-1 — detection-action early-exit keyed on an attacker-visible state field
- **observed shape:** a post-approval-change detector early-returns when `requested_reviewers`/`requested_teams` is non-empty, before its detection logic runs; the field is visible in the event payload and its emptiness is not verified as a precondition for the check's purpose.
- **seen on:** composite action consumed by CI of three consuming repos (`pull_request_target` synchronize events).
- **evidence:** `attempt://` n/a (source-level kill); kernel hypothesis `hypothesis-f3-c1` (exhausted).
- **why it may generalize:** any “detector” action whose skip conditions are attacker-observable fields (pending review requests, label sets, actor) can be left permanently un-fired; the skip path must be part of the threat model, not an optimization.
- **why it may NOT:** here the platform denies the unprivileged attacker the ability to set the field (review requests need write/triage) AND the action's only effect is a re-review request — zero enforcement delta vs branch-protection stale-approval dismissal. Both facts were required for the kill; the shape alone is not a finding.
- **candidate destination:** extend `pattern.ui-only-policy-enforcement` / new `pattern.detector-skip-precondition`.
- **lesson kind:** `refutation` (two independent kills with new signal: platform permission model + marginal-contribution zero-delta).
- **held counterexample:** the sha-equality check (main.ts:134) correctly catches re-authored trees; only the early-exit path bypasses it.
- **sanitization:** target/repo names abstracted; no payloads.
- **promotion status:** `local`

### PC-2 — integrity hash computed but never compared on the CI publish path
- **observed shape:** `DirectoryHash.compute` is stored on the package object and hard-fails on the interactive path (`assertIntegrityOfBuiltPackages` → exit 2), but the CI publish tool computes the same hash and never compares it — the field is dead weight on the only automated path.
- **seen on:** release/publish tooling (`ng-dev` interactive + composite action CI path).
- **evidence:** `hypothesis-f6-cb` (exhausted, real-but-capped).
- **why it may generalize:** “the check exists somewhere in the codebase” ≠ “the check runs on the path that ships artifacts”; grep for the assert function, not the hash function.
- **why it may NOT:** attacker influence on the CI artifact feed was refuted (same-run artifact binding + secret-gated workflow_call); caps it at a hardening gap here.
- **candidate destination:** extend `pattern.verification-root-not-anchored`.
- **lesson kind:** `mixed` (real gap, capped).
- **held counterexample:** interactive publish hard-fails before npm write.
- **sanitization:** none needed.
- **promotion status:** `local`

### PC-3 — self-referential integrity bootstrap in the toolchain updater
- **observed shape:** an update tool pins a downloaded binary's sha256 by computing it from the same download it later guards; the pinned hash mirrors whatever the (upstream-controlled) feed serves, so feed compromise is faithfully pinned as trusted.
- **seen on:** scheduled cron bot workflow that re-downloads browser toolchain binaries, recomputes sha256, commits, and opens a PR labeled `action: merge`.
- **evidence:** Round 1 verifier (F12a-C6; renovate-bump refuted, new lead); `hypothesis-f12a` n/a (recorded in rounds.md).
- **why it may generalize:** trust-on-first-use-without-anchor is the standard failure of toolchain updaters; the anchor must come from a second, independent channel.
- **why it may NOT:** the feed is Google/Mozilla-controlled — outside the unprivileged-attacker model here; real-but-not-attacker-reachable.
- **candidate destination:** extend `pattern.verification-root-not-anchored`.
- **lesson kind:** `refutation` (vector killed; residual hardening note).
- **held counterexample:** direct `http_archive` fetches in rules carry mandatory sha256 + allowlists.
- **sanitization:** none needed.
- **promotion status:** `local`

### PC-4 — committed-GCM “encryption” with public key/IV/tag (the F13 shape)
- **observed shape:** aes-256-gcm blobs committed alongside a key derived from the public org name (padEnd), a hardcoded IV, and the GCM tag committed in the same repo — integrity yes, confidentiality zero; every decrypt input is public.
- **seen on:** three composite-action credential blobs (GCP SA key, BrowserStack, SauceLabs).
- **evidence:** `attempt-f13-001..004`; kernel `hypothesis-f13` (running).
- **why it may generalize:** “we encrypted it” is a common false-safety belief; the check is whether ALL decrypt inputs are outside the public set.
- **why it may NOT:** credential liveness + IAM unverifiable offline; severity capped at disclosure.
- **candidate destination:** extend `pattern.information-disclosure` / new `pattern.committed-ciphertext-public-key`.
- **lesson kind:** `positive` (real disclosure, pending final adjudication).
- **held counterexample:** the GitHub App private keys ARE secret-sourced (workflow secrets, never committed) — the org enforces the correct pattern for its highest-value keys.
- **sanitization:** recovered secret VALUES never recorded; sha256 digests only.
- **promotion status:** `local`

### PC-5 — network-source verbatim file rewrite (the D3 shape)
- **observed shape:** a bot fetches content from a network page and writes parsed values VERBATIM into committed source files (single-quoted TS literal, YAML) with only a substring filter on the replacement and no escaping; a context-aware payload breaks out of the literal and executes (proven locally: computed-key IIFE, PWNED.txt, node --check PASS; YAML duplicate-key injection proven). Regeneration (esbuild_checked_in) ships the poisoned bundle; same-run bazel test executes the poisoned module.
- **seen on:** github-actions/update-models (glob dot:true covers .github/workflows/**; filter = replacement.includes('gemini')).
- **evidence:** lane D3 (16 hunters + 2 PoCs + reviewer reproduction).
- **why it may generalize:** any "sync from upstream/network source" tool that rewrites repo files must treat the network value as attacker data: validate shape, escape into the target language, pin the source, add tests. Absence of all four was the pattern.
- **why it may NOT:** end-to-end exploitation requires control of the Google-authored source page (no unprivileged path found); human merge gates on the bot PR and consumer pin-bumps.
- **candidate destination:** new `pattern.network-source-verbatim-rewrite` / extend `pattern.verification-root-not-anchored`.
- **lesson kind:** `positive` (primitive confirmed + PoC'd; capped at source control).
- **held counterexample:** the GitHub App private keys are secret-sourced (correct pattern) — the contrast is the lesson.
- **sanitization:** payloads abstracted; PWNED.txt artifact referenced, not reproduced.
- **promotion status:** `local`
### PC-6 — "private"-named repo is public (the D1 mislabel)
- **observed shape:** a distribution repo named dev-infra-private-ng-dev-builds is PUBLIC (anonymous 200, private:false) while the name implies private; it force-push-distributes pre-release builds consumed via commit pins by 6+ repos.
- **seen on:** angular/dev-infra-private-ng-dev-builds + sibling snapshot repos.
- **why it may generalize:** mislabeled repos defeat access-control expectations; the team's belief about who can read the channel may not match reality.
- **why it may NOT:** content is built from reviewed main; impact low; the mislabel is the finding.
- **candidate destination:** extend `pattern.information-disclosure` (repo-visibility misconfiguration class).
- **lesson kind:** `mixed`.
- **promotion status:** `local`
