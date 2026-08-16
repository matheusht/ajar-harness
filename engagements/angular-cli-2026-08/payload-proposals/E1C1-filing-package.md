# E1-C1 FILING PACKAGE — i18n locale-key bypass of `ensureValidSubPath` (webpack stack)

- **Finding:** `findings/E1-C1-i18n-locale-key-escape/` (finding #7, PROMOTED 2026-08-15, gates 7/7 CLEAR, 6 independent adjudication reviews)
- **Pin:** `d827ba9005b86b23d05ee7c62c0823367aa245c1` (HEAD 2026-08-13)
- **Assembled:** 2026-08-15 (chainstorm Wave B complete; venue-split severity corrected per E2-B2/ECKP)
- **Status:** FILE-READY — delta-first openings (corrected), venue-split severity, novelty, evidence inventory

## 1. Members (family, one root cause)

| Member | Mechanism | Venue | Severity | Evidence |
|---|---|---|---|---|
| A2 | `output-paths.ts:17` (webpack twin) — key-derived subPath escapes the output base (`join` + `mkdirSync recursive`) | write | browser-build integrity | evidence/entry*.mjs, ws/ |
| A3 | `i18n-webpack.ts` process-bundle path — same key-derived subPath into output writing | write | browser-build integrity | evidence/i18n-webpack-stub.mjs |
| B | string-form `sourceLocale` — same bypass class (unvalidated string becomes subPath) | write | browser-build integrity | evidence/entry*.mjs |
| C | `i18n-webpack.ts:52-58` createRequire ancestor walk → `findLocaleDataPath` → Babel-transform → bundle | **read + embed + EXECUTION (client bundle AND legacy-SSR server process)** | browser Low-Med / legacy-SSR MEDIUM | evidence/member-cd/, evidence/chain4/ |
| E | `i18n-options.ts:258-262` + `createTranslationLoader` — unvalidated translation-path read | read | LOW | source-verified (E2-B2/ECCS) |
| F | `augment-index-html.ts:267-270` `emitRaw` — baseHref written UNESCAPED → script tag into production index.html (BOTH stacks — widest venue) | HTML injection | Low-Medium, filing-relevant | source-verified (E2-B2/ECCS); compiled demo recommended pre-filing |
| A1 | application-builder esbuild write escape — **REFUTED** (generateFullPath `isSubDirectory` re-contains; throws) | — | negative control | RV-C1-A review |
| D | SSR manifest runtime import — **REFUTED as demonstrated** (app-builder containment fails the build first) | — | negative control | RV-C1-A review |

Root cause: `ensureValidSubPath` (`i18n-options.ts:69`, `/^[\w-]*$/`) guards ONLY explicit `subPath` options (L128/L176) — never the locale KEY itself (L163) nor string-form `sourceLocale` (L103-104). The key becomes the default subPath verbatim (L194).

## 2. Venue-split severity (corrected — the E1-C1 REPORT is authoritative)

| Venue | Severity | Vector | Notes |
|---|---|---|---|
| Browser (webpack client bundle) | **Low-Medium** | CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N (4.0) | integrity + limited disclosure; no exec in the build process |
| Legacy-SSR (server bundle, webpack stack) | **MEDIUM** | CVSS:3.1/AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H (6.3) | attacker-authored JS executes in the SSR Node process (RCE-equivalent in the app runtime) |

**SUPERSESSION NOTE (filing-critical):** the E2-R4/R7-era figure **HIGH 7.3 (AV:N/AC:H/PR:N/UI:N)** is **superseded** by the Wave-B kill-pair correction (E2-B2/ECKP): honest preconditions are local attacker-file placement (or a resolving malicious package) AND the dev must run the localized build → **AV:L + UI:R → 6.3 Medium**. A calculator-variant (ECRV: 8.1 under AV:N/UI:N) is recorded for the operator but **the filing must use 6.3**; the `E1C1-filing-openings.md` draft still carries the 7.3 wording in Opening A — do NOT copy it verbatim.

## 3. Delta-first opening (corrected for 6.3)

> **Unvalidated i18n locale identifiers execute attacker-authored JavaScript inside your production SSR server.**
>
> A single unvalidated workspace value — the **key** of an `i18n.locales` entry in `angular.json` (or the string-form `sourceLocale`) — is used verbatim as an output subpath and as a module-resolution specifier during a localized build on the **legacy webpack stack** (`ensureValidSubPath` guards only the explicit `subPath` options, never the key — the mitigation exists but is keyed to the wrong field). A deep-dot key walks `createRequire(projectRoot + '/')` up the module tree; the resolved file is read, Babel-transformed, and prepended to the server output bundle. On a localized legacy-stack deployment, that content executes **in the SSR Node process of the production app** — demonstrated end-to-end in the lab (attacker locale-data runs at bundle load and persists a marker; benign negative clean; `evidence/chain4/ssr-venue/`).
>
> We are aware of the config-trust doctrine applied to this family (#33073/#33074/#33076, closed same-day 2026-04-28 without fix). We ask you to hold that precedent against the delta: those reports concern **file content landing in the built dist** — a build-integrity class. This finding is **attacker-authored JavaScript executing in a production server process** — arbitrary code execution in the application runtime, driven by a value the build accepts silently and without validation. The same one-line fix closes both classes: validate locale keys and string-form `sourceLocale` with the existing `ensureValidSubPath` regex at `createI18nOptions` (keys L163, sourceLocale L103-104). The mechanism is **NOVEL** (no public disclosure of the locale-key channel; web-checked E1-R8), and the server venue is restricted to the legacy webpack stack — the application builder's `generateFullPath` containment (the negative control) proves the fix pattern exists in the codebase.
>
> (Browser venue variant: a malicious locale key silently embeds an attacker-chosen file into every localized client bundle — dev-server entry unshift and production prepend both live-verified; 5-dot and 4-dot dependency-confusion variants on file. Filed at Low-Medium under the documented trust-channel doctrine, for family completeness.)

## 4. Novelty

- **NOVEL mechanism** — no issue/PR/advisory discloses the locale-key → subPath-escape / `findLocaleDataPath` module-load channel (web-checked E1-R8/NOV-E1C1: 6 query families, 90 candidates, zero hits; chain-combination NOVEL per C4G).
- **Adjacent disclosed CLASS (must cite):** the foxllb cluster — #33073 (webpack browser builds copy external local files into dist via CSS url() — the local-file-into-dist class), #33074 (SSR manifest code injection via baseHref — D1-adjacent), #33076 (build-time code injection via unescaped server entry path) — all `severity6`, all closed same-day 2026-04-28 without fix under the config-trust doctrine. Member F (baseHref raw HTML) is the closest sibling to #33074 — cite the cluster and lead with the runtime-execution delta.
- D1's filing must cite #33074/#33076; E1-C1 must cite #33073 + the cluster.

## 5. Evidence inventory (all self-reproducing)

| Path | Contents | Self-reproduce |
|---|---|---|
| `evidence/entry*.mjs`, `evil.js`, `i18n-webpack-stub.mjs`, `ws/` | KP-C1 write-escape + resolution drivers, fixtures | yes (entry2/entry3 have scratch-path caveats documented) |
| `evidence/member-cd/` | KP-C1-CD live artifacts: driver-c/d.mjs, i18n-options.bundle.mjs, manifest.bundle.mjs, evil.js, project | yes (canonical C-member proof) |
| `evidence/chain4/` | demo.cjs (browser execution), check4dot.mjs (4-dot dependency-confusion), neg.cjs (discriminator), README.md, **materialized @babel 8 closure (~20MB, no network)** | **yes — all three drivers + ssr-venue verified running from the dir** |
| `evidence/chain4/ssr-venue/` | server-main.js + build-server-bundle.cjs + evil/benign locale + neg | yes — `[ATTACKER-EXEC] SSR-VENUE-7f3c1e` at boot; negative clean |
| `evidence/chain4/killpair-delivery/` | repo/ (npm-prune empirical inputs) + resolution tests | yes (E2-R7 kill-pair) |
| `reviews/` | 6 claim_adjudication reviews (RV-C1-A..F; A refuted A1/D → re-scope) | on file |
| kernel | attempts 22-24 (primary/control/replay), hypothesis closed (events 40-42) | consistent |

## 6. Remediation (choke-point)

1. Validate locale keys AND string-form `sourceLocale` with the existing `ensureValidSubPath` regex at `createI18nOptions` — one change covers members A2/A3/B/C (+ E's read path by extension).
2. Extend to the localize schema (`pattern` on `locales` propertyNames) and enforce schema validation on the build path's i18n block (the BCP-47 pattern is currently unenforced).
3. Member F: HTML-escape baseHref or validate against a URL-safe pattern at `augment-index-html.ts` (emitRaw is the discriminator).
4. Regression test: malicious locale key → build fails at option normalization; explicit-subPath control stays.

## 7. Filing notes

- Sequence: per `payload-proposals/FILING-SEQUENCE.md` — E1-C1 after W1 CI-token / M3 / D2, with the SSR venue leading.
- Doctrine counter: runtime execution vs build-integrity class (Opening A above).
- Preconditions (scope honesty): legacy webpack stack only; attacker file at the landing path OR a resolving malicious package; localized build required; no arbitrary-path read (Babel-bound); no app-builder write escape; member D refuted.
- Wave-D residue: compiled demo for member F (baseHref → emitted index.html with injected script) recommended before filing.
- Operator decisions: (a) record the SSR venue separately in finding.json or keep the single browser vector; (b) taxonomy note (low_medium vs SEV_WORDS) unchanged.
