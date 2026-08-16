# humanized-D2-draft.md

**DRAFT — operator re-authors before filing. Source pin `d827ba9005b86b23d05ee7c62c0823367aa245c1` (2026-08-13). Date: 2026-08-15.**

## D2 — `ng cache clean` deletes any directory via `cli.cache.path`

**One-line summary**
The workspace config's `cli.cache.path` is taken as-is and force-deleted recursively by `ng cache clean`, with no containment check and no confirmation, so a crafted project makes a routine troubleshooting command remove an arbitrary directory.

**What the user sees**
You run `ng cache clean` in a project whose config points the cache elsewhere, and a directory you did not mean to touch is gone. The command is documented as the standard fix for a broken project, which is exactly when people run it.

**Why it matters**
Absolute paths are accepted unchanged, relative paths can `..` out of the workspace, and the same uncontained base path is also used by `purgeStaleBuildCache`, which fires automatically on every default local build across 9 builder entry points. So the deletion does not even need the explicit command. The developer has to run the command (or a build) inside the crafted project, so it is the same trust channel as M3: a cloned or attacker-authored project.

**Reproduction sketch**

