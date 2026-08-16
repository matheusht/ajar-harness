Title: Angular CLI code generation: `--route` option injected into generated routing code, executes in the production SSR server

**Report as (Google OSS VRP vulnerability type):** Code injection via generated code (option value interpolated into generated source without escaping) — form category: **Code Injection** (fallback: Other).

Hi Angular CLI team,

I found that `ng generate module --route <value>` writes the route value straight into the generated routing module with no validation and no escaping, and a crafted value executes code in the production SSR server. Full details below. The fix is a one-line schema pattern.

**Product / version**
- @angular/cli + @schematics/angular, commit d827ba9005 (2026-08-13). I checked the sink against current main on 2026-08-15; it is unchanged.

**Severity**
- Low-Medium. CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N (dev-machine baseline).

**Summary**

`packages/schematics/angular/module/index.ts:135-136` builds the route entry as `{ path: '${options.route}', loadChildren: ... }`. Raw interpolation into a single-quoted string, and the option schema declares `route` as a plain string with no `pattern`. A value containing a quote breaks out of the literal, and the injected statements compile and execute at module evaluation.

I confirmed the payload with the CLI's own transpiler (esbuild, no type-check gate on transpile-only builds): a comma-exec shape compiles with zero errors and sets `(globalThis).__pwned` at module scope. It ran in a vm context.

The generated module is the app's routing configuration. Its parent routing module is statically bundled into the server bundle, so the payload executes in the deployed production SSR process at server boot. Once per process, ESM-cached after that, re-armed on every restart. It runs with the app's own trust; I'm not claiming a sandbox escape or a privilege jump, because there isn't one.

**Steps to reproduce**

1. Replay the verified driver (built with the tree's esbuild):
   `node findings/D1-route-codegen-injection/evidence/comma-exec-check.mjs`
   Expected: zero transpile errors, and `(globalThis).__pwned` set at module evaluation.
2. End to end with the CLI (same chain, source-verified):
   `ng new vuln-app && cd vuln-app && ng generate module admin --module app --route "<quote-breakout payload>"`
   Inspect `src/app/app-routing.module.ts`; the route entry carries injected statements instead of a plain path string. Building or SSR-booting the app executes them.

The exact payload string is in the evidence driver. I want to flag honestly that the earlier demo payload in this finding's history was invalid TS in the routes-array context; the comma-exec shape is the verified compiling one, and the driver reflects the correction.

**Impact**

Proved: quote-breakout into the generated routing module; the payload compiles and executes at module scope; production SSR execution at server boot via module evaluation of the statically bundled parent routes module.

Where I stopped: the input usually originates from the developer's own invocation, an IDE extension, a scaffolding service, or CI automation passing external values into generator arguments. I did not demonstrate remote exploitation. Per-request re-execution does not happen; the payload fires once per server process, then the module is cached.

**Why this differs from the rejected reports**

Two adjacent reports on this family were triaged `severity6` and closed as not-a-vuln on 2026-04-28 under a config-trust doctrine: #33074 (baseHref) and #33076 (unescaped server entry). I'm citing them with that status, not as fixed. The delta here is twofold. The value does not need to live in a committed config; `--route` is an invocation argument reachable from scaffolding services, IDE extensions, and CI automation. And it lands in production server code, not a build artifact. The discriminator is concrete: the component generator's class-name validation rejects the same payload shape, while the module generator has no equivalent gate on `route`.

**Remediation**

Validate `route` with a restricted pattern in the option schema (reject quotes and control characters), or serialize with `JSON.stringify` instead of raw interpolation. I verified the counterfactual: a schema pattern on the merged options rejects this payload at option validation. The fix should cover all three schematics-defaults merge levels (global, workspace, project) plus the flag, because the merge transform runs before `validateOptionsWithSchema`.

**References**
- #33074, #33076: adjacent family (option string to generated code), triaged severity6, closed not-a-vuln 2026-04-28

Happy to retest once you've had a look. I can also provide the compiled driver or a demo app if that helps.
