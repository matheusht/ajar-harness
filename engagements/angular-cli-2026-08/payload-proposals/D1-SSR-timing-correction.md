# Next-phase kill-pair — D1 SSR runtime demo (read-only, adversarial)

**Kill target:** the E2-D2/NR2-02 SSR runtime demo's per-request execution framing, and the doctrine
question (the #33074/#33076 REJECTED family).

## The demo (re-audited, /tmp/nr2-d1ssr/)

- `server.mjs`: on EVERY request does `await import(routesFile.href + '?t=' + Date.now())` — a
  **cache-bust** so each request re-imports and re-executes the routes chunk, then reports
  `markerFired` (the D1 comma-exec IIFE sets `globalThis.__pwned` at module eval).
- `routes-malicious.mjs`: the generated routes array containing the injected entry
  `{ path: 'y', loadChildren: (() => { globalThis.__pwned = ...; return () => import(...); })() }`
  — the IIFE runs at routes-module evaluation (object-literal construction).

## Kill argument 1 — lazy-chunk simulation vs real Angular SSR (KILLED as framed, mechanism SURVIVES)

**Where the payload actually lands (verified at the pin):** `ng generate module --route X --module app`
→ `module/index.ts:80-108` `addRouteDeclarationToNgModule` → `buildRoute` (`:133-136`:
`{ path: '${options.route}', loadChildren: () => import('...') }`) → `addRouteDeclarationToModule`
(`utility/ast-utils.ts:599+`) inserts the entry into the **PARENT routing module** (`--module app`
→ `app-routing.module.ts`). The parent routing module is **statically imported** by AppModule →
bundled into the server bundle → evaluated during `platformServer().bootstrapModule()` module-graph
eval.

**Real execution semantics (empirically verified this lane, /tmp/nr2-d1ssr/boot-once2.mjs):**
- Boot: the routes module evaluates ONCE (IIFE fires, marker set) — `BOOT-EVAL marker set: true`.
- Requests: **0 re-executions across 3 requests** under real ESM caching — the marker does NOT
  re-fire (`reExecutions: 0`). The runtime `import()` of the same module URL returns the cached
  instance; ESM module-graph eval is once-per-process.
- The demo's per-request firing is a **simulation artifact**: `?t=Date.now()` defeats the ESM
  cache. Real Angular SSR (esbuild/application-builder bundling) does not cache-bust module URLs at
  runtime.

**Corrected timing:** the payload executes **once at SERVER BOOT** (module-eval of the parent routes
module). If the payload ever landed inside a genuinely lazy chunk (a child module imported via the
parent's `loadChildren`), it would execute once at first chunk load (first server-side render of
that route), then ESM-cached — still **not per-request**.

**Quantified delta:** execution frequency — demo claims N-per-request; real = 1-per-boot (per pod
start/deploy; ESM-cached thereafter). For the D1 payload class (static code injection, no request
context) the delta is immaterial to impact: boot-time execution still places attacker code in the
production SSR process with the app environment, persistent for the process lifetime, re-armed on
every restart. The per-request re-execution amplifier (relevant only to request-context-sensitive
payloads — e.g., per-request exfil reading request data) is **KILLED**; no such payload is
demonstrated or claimed in D1.

## Kill argument 2 — the doctrine (REJECTED family) — UNCHANGED, demo does not alter it

- #33074/#33076 were closed not-a-vuln 2026-04-28 under the config-trust doctrine; the report's
  delta framing (CLI-`--route` FLAG reach vs pure config file + validity + persistence +
  production SSR runtime execution) is the standing counter.
- The demo adds EXECUTION evidence (the marker fires in a Node SSR-like process) — it does not
  change the doctrine calculus either way. The filing must keep the delta-first framing; the demo
  is evidence FOR the "production runtime execution" leg, not a doctrine escape.

## SURVIVING CLAIM (after the kill)

- The D1 payload executes in the production SSR process at server boot (real; module-eval of the
  statically-bundled parent routes module; persistent for the process lifetime; re-arms per boot).
- Per-request re-execution: KILLED (simulation artifact).
- Severity unchanged (Low-Medium; the report's CVSS C:N dev-machine baseline + conditional
  production confidentiality).

## VERDICT: SURVIVES-NARROWED with the corrected timing

## Report correction (exact fix text for the parent orchestrator)

`D1-route-codegen-injection/REPORT.md` E10 block, the parenthetical:

OLD:
> (eager `--module` case at build/startup; lazy case at server-side render of the injected route)

NEW:
> (the injected route entry lands in the PARENT routing module — statically bundled, module-eval at
> SERVER BOOT once per process, ESM-cached thereafter, NOT per-request; a payload inside a genuinely
> lazy chunk would fire once at first chunk load, then cached — still not per-request. The E2-D2
> demo's per-request framing was a cache-busting simulation artifact; the E2-D3 boot-once kill-pair
> test confirms 0 re-executions under real ESM semantics)

## Evidence

- `/tmp/nr2-d1ssr/boot-once2.mjs` + its output (`reExecutions: 0` across 3 requests) — this lane's
  empirical test.
- `/tmp/nr2-d1ssr/{server.mjs, routes-malicious.mjs, routes-benign.mjs, server-*.log}` — the demo
  being killed.
- Pin source: `packages/schematics/angular/module/index.ts:80-160` (route entry → parent routing
  module), `utility/ast-utils.ts:599+` (insertion point).
- All under /tmp — cleanup-listed scratch; nothing in the engagement was modified (read-only lane).
