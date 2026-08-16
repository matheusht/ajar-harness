# humanized-M3-draft.md

**DRAFT — operator re-authors before filing. Source pin `d827ba9005b86b23d05ee7c62c0823367aa245c1` (2026-08-13). Date: 2026-08-15.**

## M3 — `outputPath` in a project config can wipe directories outside the project

**One-line summary**
A malicious or crafted `outputPath` value in `angular.json` (or `--output-path` on the command line) makes `ng build` recursively delete the contents of any directory on the machine the developer can write to. The delete path was never given the containment check that was added to the write path in the same builder family.

**What the user sees**
You clone a project someone sent you, run `ng build`, and a directory you did not expect to be touched is empty afterwards. No error, no prompt, no confirmation. The build itself succeeds.

**Why it matters**
The new `@angular/build:application` builder rejects `outputPath` values that escape the workspace (the `8358805d3` fix), but that fix only covered the write path. The delete path, and both legacy webpack builders, still pass the value straight to a recursive `rm`. On macOS and Windows (case-insensitive filesystems) the one remaining guard, a string compare against the project root, can be bypassed with a case-variant path, which makes even the project root itself deletable. CI runners on macOS are affected the same way.

**Reproduction sketch**

