# D2 filing opening (delta-first, for the operator's humanized re-authoring)

**One sentence:** a workspace-config value (`cli.cache.path`) is taken verbatim into an
unconditional, silent, recursive force-delete that fires on every default Angular build — no
containment, no confirmation, and no user action beyond building a project from a crafted repo.

**The delta first (what the as-filed manual command missed):** `ng cache clean` deleting an
arbitrary directory is a developer-typed command. The amplified mechanism — `purgeStaleBuildCache`,
consuming the same uncontained `getCacheBasePath` from `cli.cache.path` — fires **automatically on
every `ng build` / `ng serve` / `ng test` / extract-i18n / ng-packagr invocation** across **nine
builder entrypoints**, with no output line and no confirmation. A crafted repository (cloned repo,
or a fork-PR workspace processed by a trusted CI build) sets `cli.cache.path` and the deletion
happens by itself. The fix must land at the shared chokepoint: two byte-identical copies of
`getCacheBasePath` (cache/utilities.ts + normalize-cache.ts) are the entire surface.

**Cross-platform, silent, and keystone for two chains:** it deletes on case-sensitive and
case-insensitive filesystems alike (the macOS root-delete variant is M3's case-guard amplifier); it
is the keystone hop of the cloned-repo delivery chain (Chain 1) and of the config-as-data CI
sabotage shape (Chain 2) — the full-checkout wipe candidate.

**Novelty:** no public issue, PR, or advisory discloses the `cli.cache.path` / purge deletion (the
`ng cache` feature PR is #22851; adjacent worktree-cache discussion only). Demonstrated with the
real CLI command and the compiled purge module at the pinned commit.

**Severity:** Medium — availability/data-loss only, config-controlled value, no privilege gain.
