# KP-E10 kill-pair verdict — D1 SSR/prerender production-server execution

## Verdict: SURVIVES (narrow) — production-runtime reach confirmed; severity delta bounded by the unchanged input channel

The SSR production-execution mechanism is **real and empirically confirmed**, with **two corrections**
(compiling payload shape; eager-vs-lazy import path). The severity amplifier is **narrow**: the
production execution is a genuine reach widening over D1-as-filed, but the marginal delta is capped
by the unchanged attacker-influence channel.

## Evidence — every hop verified

1. **Raw interpolation:** `packages/schematics/angular/module/index.ts:135` —
   `` `{ path: '${options.route}', loadChildren: ... }` `` — confirmed.
2. **Insertion:** `utility/ast-utils.ts:599-665` `addRouteDeclarationToModule` — the route literal is
   inserted as an element of the `routes: Routes` array (standalone-variable form) or the inlined
   `RouterModule.forChild([...])` argument — confirmed.
3. **Module-scope shape:** routing module template has `RouterModule.forChild(routes)` at module scope;
   the generated module is referenced by the app router via `loadChildren: () => import(...)`.
4. **SSR bootstrap:** `packages/angular/ssr/src/routes/ng-routes.ts:605-640`
   `getRoutesFromAngularRouterConfig` → `platformServer([...])` + application bootstrap — the app's
   router config (including the injected routing module when `--module` targets the app routing
   module) is imported during route extraction at build/startup — confirmed.
5. **Production bundle:** the routing module source compiles into the SSR bundle; the deployed SSR
   server imports the app at request time — the module evaluates in the production process.

## The decisive empirical test (kill angle 1 — does the payload even parse?)

- **The original D1 demo payload is INVALID TypeScript.** `x'; (globalThis as any).__pwned = 'MARKER-D1'; const s = '`
  emitted inside the routes array produces **6 syntax errors** (TS 6.0.3: 1005 ',' expected; 1136
  Property assignment expected; 1128 Declaration or statement expected) — the file does not compile,
  the build breaks, **nothing ships**. The D1 PoC was text-only, never compile-validated.
- **A compiling, executing payload exists.** The `comma-exec` shape —
  `x' }, { path: 'y', loadChildren: (() => { <code>; return () => import('./x'); })() } , { path: '` —
  produces a **valid routes array with 0 syntax errors**; esbuild (the CLI's actual transpiler,
  v0.28.2 at the pin) transforms it cleanly, and importing the module **executes the payload at
  module scope** (`globalThis.__pwned = 'KP-E10-MARKER'`, exit 0, empirically confirmed).
- The CLI application build does not type-check (esbuild transpile-only), so the Routes-array type
  errors (`loadChildren: number`-shaped) do not gate the build — the payload survives into the bundle.

## Kill arguments and their fate

1. **"The demo payload is invalid TS — the injection breaks the build."** → *Partially succeeds*:
   the as-demonstrated payload is a build-break, not code-exec. *Fails to kill the class*: the
   comma-exec shape compiles and executes (empirically confirmed). Correction applied: the PoC must
   use a compiling payload.
2. **"SSR route extraction is gated to prerendered/static routes — the injected dynamic route is
   never extracted."** → *Fails*: route extraction bootstraps the APP and reads the router config;
   module-scope code in an eagerly imported routing module (`--module app` case) executes during
   extraction regardless of whether the injected route is matched. For the lazy case (generated
   module's own routing file), execution occurs when a request renders the injected path server-side.
3. **"The developer must commit and deploy the generated file; without that the code never reaches
   production — the deployment decision, not the bug, is what ships the code."** → *Partially
   succeeds*: the deployment precondition is real. *Fails to kill*: in the world without D1 the same
   influenced `--route` value produces a benign string — with D1 it produces executable statements.
   The attacker's capability (code in the app's module graph) is created by the bug, and it
   demonstrably reaches the production runtime — a reach widening over D1-as-filed (dev build/serve).
4. **Marginal-contribution critique (the severity bound):** the input precondition is unchanged —
   attacker-influenced `--route` value on a repo the attacker does not control (script/IDE/
   scaffolding-service channel). The production execution runs the injected code with the app's own
   production identity (same class as the app's own code). **Severity stays Low-Medium; the Reach
   statement widens** (production SSR/prerender runtime, per-request process, prod env access).

## Corrections to the claim (fold back into D1)

1. The D1 PoC payload must be replaced with a compiling shape (comma-exec) — the original demo text
   is invalid TS and yields a build break.
2. SSR production execution applies to the eager-import case (`--module` targeting the app routing
   module) at extraction/build time AND at request time; the lazy case (generated module's own
   routing file) executes server-side only when the injected route is requested.
3. The routing-module insertion adds a `loadChildren: () => import(...)` reference that is valid —
   no other correction.

## Staleness

No security fix on either side at the pin or the current released tag (`git log` — feature/refactor
only on `module/index.ts`, `ast-utils.ts`, `ng-routes.ts`). Not stale.

## Confidence

High — every hop source-verified; the compile/execute behavior empirically confirmed against the
tree's own TypeScript (6.0.3) and esbuild (0.28.2); the kill of the severity delta rests on the
marginal-contribution critique with the input channel unchanged.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Kill-pair review completed: all five chain hops verified at the pin (module/index.ts:135 raw interpolation; ast-utils.ts:599-665 routes-array insertion; routing template module-scope forChild; ng-routes.ts:605-640 platformServer bootstrap; bundle -> production SSR process). Decisive empirical tests: TS 6.0.3 parse of the original D1 payload = 6 syntax errors (build-break); comma-exec payload = 0 syntax errors, esbuild 0.28.2 transform OK, module import executes the payload (globalThis marker set, exit 0). Kill arguments engaged: demo-payload invalidity (partial kill -> correction), static-only extraction gate (failed), deployment-decision shipping (failed as a kill), marginal-contribution severity bound (applied: Low-Medium unchanged, Reach widened). Read-only: no tree modifications, no builds, no network."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "read module/index.ts:125-140, ast-utils.ts:599-700, ng-routes.ts:600-640, module routing template",
      "result": "passed",
      "summary": "all five chain hops verified at the pin"
    },
    {
      "command": "node parse test: TS 6.0.3 diagnostics over 8 payload shapes in the routes-array context",
      "result": "passed",
      "summary": "original-d1 = 6 syntax errors (invalid); crafted-B/C invalid; full-breakout 0 syntax errors (var redeclare -> runtime SyntaxError); comma-exec = 0 syntax errors, valid array element with module-scope IIFE"
    },
    {
      "command": "node execute test: esbuild 0.28.2 transform + dynamic import of the comma-exec module",
      "result": "passed",
      "summary": "esbuild transform OK; import executed the payload (globalThis.__pwned = KP-E10-MARKER, exit 0)"
    }
  ],
  "validationOutput": [
    "D1-as-demonstrated payload is invalid TS (6 syntax errors) - PoC text never compile-validated; must be corrected to a compiling shape",
    "comma-exec payload compiles (esbuild) and executes at module scope (empirically confirmed)",
    "SSR route extraction bootstraps the app (platformServer) - eagerly imported injected modules execute at extraction/build time; lazy modules execute on server-side render of the injected route",
    "CLI application build is transpile-only (no type-check gate) - Routes-array type errors do not block the payload",
    "Severity stays Low-Medium; Reach widens to the deployed production SSR/prerender runtime"
  ],
  "residualRisks": [
    "Windows or exotic bundler configurations not tested (POSIX node/esbuild used)",
    "The exact production-deployment chain (real SSR server wiring) is standard Angular deployment behavior, not re-run here",
    "Payload crafting is required - a random injection string breaks the build rather than executing"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only kill-pair review; zero files modified.",
  "reviewFindings": [
    "no blockers - verdict: SURVIVES (narrow) with two corrections to the D1/E10 claim (compiling payload shape; eager-vs-lazy SSR import path)"
  ],
  "manualNotes": "Fold back into D1: replace the PoC with the comma-exec payload; widen Reach with the SSR/prerender production-execution line; keep severity Low-Medium (input channel unchanged). The finding's own demo text should not be re-used as a PoC without the compile correction."
}
```
