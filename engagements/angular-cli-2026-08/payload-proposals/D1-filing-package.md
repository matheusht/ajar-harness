# D1 Filing Package — `--route` codegen injection (angular-cli-2026-08, finding D1)

**Status:** PROMOTED (2026-08-15) · gates G0-G6 CLEAR · engagement kernel attempts on file
(attempt-d1-001-primary / attempt-d1-002-control-ns) · prepared 2026-08-15 (chainstorm Wave D D-R2).
**For the operator's humanized re-authoring.** Delta-first; the REJECTED-family doctrine is the
single biggest framing risk — a mechanism-first writeup gets dismissed.

---

## 1. Claim (one sentence)

`ng generate module --route <value>` interpolates the `--route` option into the generated routing
module with **no validation and no escaping** (`packages/schematics/angular/module/index.ts:129-136`
`buildRoute`, raw interpolation into a single-quoted string; the module option schema declares a
plain string with no `pattern`), so a value containing a quote breaks out of the string literal and
injects statements that **execute at module evaluation** — demonstrated with the CLI's own
transpiler (comma-exec shape, 0 transpile errors, `(globalThis).__pwned` marker at module scope).

## 2. Comma-exec PoC (evidence)

- `findings/D1-route-codegen-injection/evidence/comma-exec-check.mjs` — compiles the exact
  `buildRoute` output with the tree's own esbuild (the CLI transpiler): 0 syntax errors, executes
  at module eval in a vm context. **Correction history:** the ORIGINAL demo payload was invalid TS
  in the routes-array context (build-break as denial, not exec); the comma-exec shape (`,` +
  statement + `,`) is the verified compiling payload.
- `findings/D1-route-codegen-injection/evidence/module-index.ts` — the pinned source slice with the
  exact sink lines.
- Replay: `node evidence/comma-exec-check.mjs` (read-only, uses the lab's esbuild).

## 3. SSR reach (E10/KP-E10, Wave-B scoped)

- The injected module is the app's routing config → ships in the SSR bundle → **executes in the
  deployed production SSR server process**: route discovery (`@angular/ssr`
  `extractRoutesAndCreateRouteTree` → `platformServer` bootstrap, ng-routes.ts:621-640/632/796;
  eager `--module` case at build/startup, lazy case at server-side render of the injected route).
- **Wave-B scoping (D1KP):** module-scope execution **with the app's own trust** — no privilege or
  sandbox-escape delta beyond the app itself; the delta vs base = validity + silence + persistence +
  production runtime execution.
- **Severity: Low-Medium STANDS** (CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N, dev-machine
  baseline). No E1-C1-style venue-split raise: the SSR venue requires an ACTIVE generator invocation
  carrying the attacker value, whereas E1-C1's SSR venue needs only a passive build — the invocation
  precondition keeps D1's reach conditional. Documented exception: a **CI-generate shape** (a CI job
  running `ng generate` with externally derived args, e.g. `--route "$PR_TITLE"`) warrants a Medium
  CI venue — same framing as W1's CI-token venue; operator decision at filing.

## 4. REJECTED-family framing (must be stated in the filing)

- Adjacent family disclosed + **REJECTED**, not fixed: **#33074** (SSR manifest code injection via
  `baseHref`) and **#33076** (build-time code injection via unescaped `server` entry path), both
  triaged `severity6: security`, both closed 2026-04-28 as not-a-vuln under the maintainers'
  config-trust doctrine. The `server` entry sink is unchanged at the pin
  (application-code-bundle.ts:345-366) — same doctrine applies to D1 by analogy.
- **The delta:** the value does NOT need to live in a committed config — `--route` is an invocation
  argument reachable from scaffolding services, IDE extensions, and CI automation that derive
  generator args from external input; and it lands in PRODUCTION SERVER code, not a build artifact.
- **The discriminator (concrete, verified):** the component generator's class-name validation
  (`utility/validation.ts` `validateClassName`, identifier regex) REJECTS the same payload shape;
  the module generator has no equivalent gate on `route`.
- **Schema-fix counterfactual (strongest remediation evidence):** a pattern on the route option
  would have rejected the payload at option validation — verified. Fix covers all three
  schematics-defaults merge levels (global → workspace → project) plus the flag, since the merge
  transform runs BEFORE `validateOptionsWithSchema` (E1-R4/L7).

## 5. Delta-first opening (D1FD, ~200 words, for the humanized report)

> Angular CLI's `ng generate module --route` writes the `--route` option into the generated routing
> module with **no validation and no escaping** (`packages/schematics/angular/module/index.ts:135-136`
> — raw interpolation into a single-quoted string; the option schema declares a plain string with no
> pattern). A route value containing a quote breaks out of the string literal and injects statements
> that **execute at module evaluation** — a compiling, type-check-free payload is demonstrated with
> the CLI's own transpiler (comma-exec shape; `(globalThis).__pwned` marker verified at module scope,
> 0 transpile errors). The injected module is the app's routing config, so the code ships in the SSR
> bundle and **executes in the deployed production SSR server process** (route discovery →
> `platformServer` bootstrap, ng-routes.ts:632/796).
>
> Two adjacent reports on this exact family (#33074 baseHref, #33076 server-entry) were triaged
> `severity6` and closed as not-a-vuln under a config-trust doctrine. This finding's delta is that
> the value does **not** need to live in a committed config: `--route` is an **invocation argument**
> reachable from scaffolding services, IDE extensions, and CI automation that derive generator args
> from external input — and it lands in **production server code**, not a build artifact. The
> discriminator is concrete: the component generator's class-name validation rejects the same
> payload shape; the module generator has no equivalent gate on `route`.

## 6. Evidence inventory (for the filing bundle)

| Item | Location | Note |
|---|---|---|
| PoC driver + marker proof | `findings/D1-route-codegen-injection/evidence/comma-exec-check.mjs` | run with the tree's esbuild; 0 errors; marker at module scope |
| Sink source | `findings/D1-route-codegen-injection/evidence/module-index.ts` | `buildRoute` at :129-136, pin slice |
| Full report | `findings/D1-route-codegen-injection/REPORT.md` | mechanism, trust boundary, impact, negative control, novelty, remediation |
| Adjudications | `findings/D1-route-codegen-injection/reviews/` (KP-D1, KP-E10, R6-E7, D1KP) | kill-pair history: defaults channel killed, SSR reach widened, persistence, app-trust scoping |
| Kernel attempts | `attempt-d1-001-primary` / `attempt-d1-002-control-ns` | real-path (replicated buildRoute output) + negative control |
| Filing opening | `payload-proposals/D1-filing-opening.md` | delta-first lede + severity recheck |
| Viability note | `payload-proposals/D1-filing-viability.md` | doctrine risk + filing options |
| FILING-COVER / SEQUENCE | `payload-proposals/FILING-COVER.md`, `FILING-SEQUENCE.md` | operator sequence (after W1 CI-token / M3 / E1-C1) |

## 7. Filing notes

- Novelty: exact sink NOVEL; family disclosed+REJECTED (cite #33074/#33076 WITH the rejection
  status); foxllb cluster (5 issues incl. #33073) — active independent researcher, co-credit risk.
- Severity: Low-Medium, dev-machine baseline; CI-generate venue = operator decision (Medium).
- No wire-2 needed for this finding; the PoC is fully local.
