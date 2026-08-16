# KP-M2RT verdict — M2 run_target amplifier: SURVIVES with 2 mechanism corrections

## Verified LIVE (real pin-source bundles)
1. Option VALUES pass verbatim: serializeOptions (real code) emits `--tsConfig=/tmp/evil/tsconfig.json`,
   `--browser=/etc/hosts`, `--outputPath=/tmp/outside/dist`; GenericTargetStrategy.execute forwards them to
   executeNgCommand; child argv shows them verbatim (NG-ARGV proof). executeNgCommand = spawn shell:false,
   cwd-only, no value checks (host.ts:171-228 source-verified).
2. CORRECTION-1 (exfil mechanism): the builder normalizes string options with `path.join(workspaceRoot, value)`
   (options.ts:201 tsConfig, :595-598 browser/main). `path.join` does NOT let an ABSOLUTE value pass through —
   it PREFIXES: join(ws, '/etc/passwd') = ws/etc/passwd. The actual escape is RELATIVE `..` traversal, which
   join normalizes upward: join(ws, '../outside/secret.ts') = ws-parent/outside/secret.ts — LIVE-verified with
   file existence + content read (SECRET = 42). So the exfil channel = relative traversal via tsConfig/browser/
   main/polyfills (parseable TS/JS/JSON content embedded in the build output).
3. CORRECTION-2 (fileReplacements NOT a channel): serializeOptions stringifies array items; object items become
   `--fileReplacements=[object Object]` (LIVE output) — the CLI receives a string, not objects; options.ts:208-222
   would iterate string chars / throw. The A3 report's fileReplacements channel is NOT reachable through run_target.
4. outputPath uses `path.resolve` (options.ts:324-331) — absolute overrides; application builder write is
   isSubDirectory-contained (index.ts:284); legacy/extract-i18n outputPath uncontained (M3 family).

## Required report corrections (parent orchestrator to apply in M2 REPORT DEEP-PHASE AMPLIFIER section)
- Replace "fileReplacements[].with/browser/main/polyfills/tsConfig with absolute paths read arbitrary files"
  with: "browser/main/polyfills/tsConfig string options with RELATIVE .. traversal escape the workspace root
  via path.join and read out-of-roots parseable files into the build (live-verified); fileReplacements object
  arrays are mangled by serializeOptions ([object Object]) and are NOT a channel through run_target."
- Keep: option-VALUE channel (verbatim pass-through), silent-steer delta, shell-less promotion trigger,
  outputPath write on legacy/extract-i18n (M3-covered).
- Delta holds: relative traversal needs NO attacker file placement inside roots (the out-of-roots file is a
  sibling/ancestor) — still requires the agent to be steered, and the R7 cap (agent has shell) still bounds
  the marginal delta to silent-steer for standard clients.
