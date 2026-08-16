# member-e/ — E1-C1 member E: translation-path read (compiled demo, N1-F)

**Claim:** workspace-controlled translation `file.path` values are UNVALIDATED
(`normalizeTranslationFileOption` accepts arbitrary strings; `ensureValidSubPath` guards ONLY
`subPath` fields — i18n-options.ts:128/176, never the translation path) → `loadTranslations`
(i18n-options.ts:249) calls `loader(path.join(workspaceRoot, file.path))` → `createTranslationLoader`
(load-translations.ts:25) does raw `fs.readFileSync(path)`.

**Demo (real compiled pin-source code; esbuild bundle of load-translations.ts + i18n-options.ts):**
- HOP1 (attack): `i18n.locales.fr.translation = '../evil/outside.xlf'` → content of an OUT-OF-WORKSPACE
  file read, parsed with the real XLIFF parser, and landed in the build's translation table
  (`READ-OUTSIDE-WORKSPACE = true`; marker `MARKER-ATTACKER-TRANSLATION-N1F-7c9f2e` present in the
  translation map — the message value the i18n inliner substitutes into the localized output).
- HOP2 (negative control): in-workspace `benign.xlf` loads normally (`benign-message-id` present).

**Severity:** LOW (read-only, config-trust channel; the same workspace value is already code-exec in
the cloned-repo precondition — the delta is silent read of out-of-workspace files into the build).

**Files:** entry.ts (driver), entry.cjs (bundle), outside.xlf + benign.xlf (fixtures), OUTPUT.txt
(transcript). Pin: d827ba9005. Replay: `node entry.cjs` (needs node_modules/@angular/localize resolvable
— symlinked to the lab tree in the original run).
