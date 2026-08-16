# D1 — `--route` option injected unescaped into generated routing code (codegen injection)

- **Engagement:** angular-cli-2026-08 · **Pinned commit:** `d827ba9005b86b23d05ee7c62c0823367aa245c1`
- **Origin:** deepsec cross-scan finding (slug `other-code-injection-c1e42f5ba1`), verified by the orchestrator against source + replicated output.
- **Surface:** `packages/schematics/angular/module/index.ts:129-136` (`buildRoute`) + the module option schema (no pattern on `route`)
- **Status:** PROMOTED (2026-08-15) — **cascading-phase adjudications (all kill-pair/QA reviewed):**
  - **KP-D1 (kill):** the workspace schematics-defaults channel is an *alternative trigger surface*,
    NOT a severity amplifier — its precondition (attacker-authored project + dev runs a command
    inside it) is already code-exec-equivalent via npm lifecycle scripts at the mandatory `npm
    install`, and the payload is no stealthier than a `postinstall` (visible in the committed
    config). Reach note only: a fix should cover both the `--route` flag and the config default.
  - **E10/KP-E10 (reach widens):** the injected top-level code **executes on the SSR/prerender
    production server** — route discovery (`@angular/ssr` `extractRoutesAndCreateRouteTree` →
    `platformServer` bootstrap, ng-routes.ts:621-640) imports the app router config (eager
    `--module` case at build/startup; lazy case at server-side render of the injected route), and
    the payload ships in the SSR bundle → executes in the deployed production SSR process with its
    environment. Severity unchanged (identical input channel); Reach widened. The CVSS `C:N`
    baseline reflects the dev-machine case; production confidentiality impact is conditional on the
    payload shipping in a deployed SSR bundle.
  - **R6-E7 (persistence):** `addRouteDeclarationToModule` (ast-utils.ts:599-670) appends with NO
    dedupe — regeneration with identical options re-emits a payload instance (caps: identical
    options required, drift discards via MergeConflictException; the config-default channel is
    killed, direct-args only). The application-generator `title` sibling sink is **KILLED** (the
    application schema `name` pattern excludes breakout characters, enforced on the nested call via
    the engineHost schema-validation transform).

## One sentence on why it is real

`buildRoute()` interpolates the user-supplied `--route` option raw into a single-quoted string inside the generated routing module — a route value containing `'` breaks out of the string literal and injects statements that execute at module scope whenever the generated app is built, served, or SSR-rendered; the option schema declares `route` as a plain string with no pattern, and no other validation or escaping exists.

## Mechanism

```ts
function buildRoute(options: ModuleOptions, modulePath: string) {   // module/index.ts:129-136
  ...
  return `{ path: '${options.route}', loadChildren: ${loadChildren} }`;   // :135-136
}
```
Option schema: plain string, no pattern, no escaping. The returned declaration is written into the app routing module via `addRouteDeclarationToNgModule` → `addRouteDeclarationToModule` (ast-utils.ts:599-670; no-dedupe append, wildcard-aware).

**PoC correction (cascading kill-pair KP-E10, 2026-08-15):** the original demo payload
(`x'; (globalThis as any).__pwned = 'MARKER-D1'; const s = '`) is **invalid TS inside the routes
array** (6 syntax errors — as-demonstrated it breaks the build rather than executing). The class
survives with the **comma-exec payload shape**, empirically confirmed with the tree's own toolchain
(esbuild 0.28.2 — the CLI's transpiler; transpile-only builds have no type-check gate):

```ts
// generated routing module (buildRoute + routes-array insertion):
const routes: Routes = [
  { path: 'x' }, { path: 'y', loadChildren: (() => { (globalThis).__pwned = 'KP-E10-MARKER';
      return () => import('./y/y.module'); })() }, { path: '', loadChildren: () => import('./admin/admin.module').then(m => m.AdminModule) }
];
```
The payload produces a valid routes array (0 errors), survives transpile, and **executes at module
import** (marker set — empirically confirmed; QA-D1 independently re-verified with the repo's
esbuild). The statements execute when the module is imported — see Reach below. Contrast: the
component generator's `name` is gated by `validateClassName` (identifier regex — aborts on
non-identifier chars); the module generator's `route` has no equivalent gate.

## Trust boundary crossed

`--route` (CLI/schematic option) → generated routing module source → executed at module scope with
the developer's privileges on build/serve and in the deployed SSR process (Reach). Attacker-influence
paths: scaffolding web services, IDE extensions, CI automation, or any generator invocation whose
args derive from external input; alternatively the workspace schematics-defaults surface
(`@schematics/angular:module.route` in a cloned project's config — reach note, severity delta ≈ 0
per KP-D1).

## Impact (honest)

- **Confirmed:** quote-breakout code injection into the generated routing module (comma-exec
  payload demonstrated); arbitrary code runs in the project's module graph.
- **Reach (E10/KP-E10):** production SSR/prerender execution — the payload ships in the SSR bundle
  and executes in the deployed production server process (eager `--module` case at build/startup,
  lazy case at server-side render).
- **Capped:** the generated code runs with the same trust as the project the developer is
  generating into; the input usually originates from the developer's own invocation or a scripted/
  IDE/CI-args channel (D1-as-filed). The workspace schematics-defaults channel is an alternative
  trigger surface whose severity delta ≈ 0 under the attacker-authored-project precondition (npm
  lifecycle scripts already execute at install; the payload is visible in the committed config) —
  kept as a reach note so a fix covers both surfaces.
- Not claimed: remote exploitation or privilege escalation.

## Negative control

- The component generator's class-name validation (`utility/validation.ts` `validateClassName`) REJECTS the same payload shape (identifier regex) — the discriminator: the module generator simply lacks an equivalent validation for `route`.

## Replay / staleness

- Output replicated via the exact `buildRoute` logic (source-cited) and re-verified with the tree's own esbuild (comma-exec shape). `route` has been a plain string since the option's introduction; no security fix touches `module/index.ts` at the pin (git log: feature/refactor only). Not stale.

## WAVE-B SCOPING (E2-B2/D1KP): app-trust execution

The SSR-execution venue is module-scope execution of the injected statements **with the app's own trust** — no privilege or sandbox-escape delta beyond what the app itself has; the delta vs the base finding is validity + silence + persistence + the production runtime execution. The schema-fix counterfactual (a pattern on the route option would have rejected the payload at option validation — verified) is the strongest remediation evidence.

## Severity / category

- **Low-Medium** (codegen injection; scripted/IDE/CI-args input channel; production-SSR reach
  conditional on deployment). CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N (dev-machine baseline;
  production confidentiality impact conditional on the payload shipping in a deployed SSR bundle).
  Category: Product Vulnerability (schematic codegen). Operator re-review before filing.

## DEEP-PHASE NOVELTY (E1-R1/L9 + E1-R2/L9c correction): NEAR-MISS — adjacent family disclosed + **REJECTED** (not fixed); exact sink novel

- Two Google-triaged security reports (label `severity6: security`, both closed 2026-04-28): **#33074** (SSR manifest code injection via `baseHref`) and **#33076** (build-time code injection via unescaped `server` entry path) — the SAME family (option/config string → generated code), different sinks. **CORRECTION (L9c): both were closed as not-a-vuln under the maintainers' config-trust doctrine — the family is disclosed+REJECTED, not disclosed+fixed.** The `server` entry sink shape is unchanged at the pin (application-code-bundle.ts:345-366, unescaped `'${mainServerEntryPointJsImport}'` in the virtual-module template; zero isSubDirectory/validation) — the same doctrine that rejected #33076 applies to D1's route sink by analogy.
- The schematics `--route` option (D1's sink) is NOT disclosed in either report — the exact sink is novel; the family carries a documented won't-fix rejection.
- **Filing requirement:** D1's report must cite #33074/#33076 as adjacent precedent **with the rejection status** (not "fixed"); the filing argument must be the delta (CLI-flag reach + production-SSR execution + unescaped quotes → comma-exec, vs the rejected config-trust framing).
- Resolved (E1-R2/L9c): the pin's `server` entry path handling carries NO validation D1's route sink lacks (application-code-bundle.ts:345-366 unescaped; #33076's sink unchanged at pin) — D1's uniqueness against the family stands, with the REJECTED-doctrine framing above.

## Remediation

1. Validate `route` with a restricted pattern in the option schema (e.g. reject quotes/control chars) and/or serialize with `JSON.stringify(route)` instead of raw interpolation.
2. Audit all schematic options interpolated into generated sources (the `59e5e967a` family — `safely-comment-out` fix was one instance; `route` is a sibling; the R10-D1 sweep confirmed `route` is the unique breakout-capable raw-option sink across all 18 template-interpolation members).
3. When fixing, cover ALL THREE schematics-defaults merge levels (global config, workspace config, project config) plus the `--route` flag — `getSchematicDefaults` merges global → workspace → project and the merge transform runs BEFORE `validateOptionsWithSchema`, so a schema pattern (reject quotes/control chars) on the MERGED options rejects poisoned defaults from every level in one change; do not gate on the flag only (E1-R4/L7 verified: the global channel is reachable when no --route flag is given; the write precondition for the global config is user-action/code-exec — cap holds).
