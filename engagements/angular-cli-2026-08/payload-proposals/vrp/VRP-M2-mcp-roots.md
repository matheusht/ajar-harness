Title: Angular CLI MCP server reads files outside the declared roots and injects the content into the agent as high-priority instructions

**Report as (Google OSS VRP vulnerability type):** Path traversal / information disclosure (MCP tool reads outside declared roots) + agent-context injection — form category: **Path Traversal** (fallback: Information Disclosure).

Hi Angular CLI team,

I found that the MCP `get_best_practices` tool resolves `@angular/core/package.json` with a `createRequire` ancestor walk and reads the guide file with a raw `readFile`, never re-checking the resolved path against the declared roots. The content comes back annotated `priority: 0.9, audience: assistant`, which is the strongest instruction channel the protocol has. Full details below.

## Product and version

- @angular/cli, pinned commit d827ba9005 (2026-08-13). The input-level roots check is fixed at this commit (34e1e0bb5, 2b060630c, 24fd8fce2); the ancestor-walk residual I'm filing is live at the pin.

## Severity

- Low-Medium. CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N (4.0 base; the read is bounded to the resolved package dir, 1 MB cap).

## Summary

`isAllowedWorkspacePath` checks the workspacePath input against the declared roots and rejects out-of-roots inputs. That check does not constrain what `createRequire(workspacePath).resolve('@angular/core/package.json')` finds. In a hoisted layout the resolution walks up past the roots, lands on an ancestor's `@angular/core`, and `getVersionSpecificBestPractices` reads that package's `angular.bestPractices.path` with a raw `readFile`. The content is returned to the agent as `{ type: 'text', annotations: { audience: ['assistant'], priority: 0.9 } }`.

Related, same surface: the `run_target` tool passes option values verbatim to `ng` with no roots check on the values, and a relative `..` traversal in a path option reads an out-of-roots file into the build artifact. I demonstrated the full chain: repo-derived content steered the option value, and an unprepared agent followed the instruction when the traversal was hidden (a symlinked build entry; the anomaly never appears in the tool call).

## Steps to reproduce

The re-PoC is in the report evidence (mcp-server.cjs built from the pin, stdio client):

1. Workspace at `/tmp/poc/ws` (declared root), no local `@angular/core`.
2. Hoisted attacker package at `/tmp/poc/node_modules/@angular/core` with `angular.bestPractices.path = "guide.md"` containing a marker.
3. Call `get_best_practices` with `workspacePath = /tmp/poc/ws` (in-roots, passes the input check).
4. The tool returns the attacker guide byte-for-byte at priority 0.9.

The out-of-roots input form is correctly rejected (negative control).

## Impact

What I proved: the residual read outside the declared roots at the pin, the byte-for-byte content return, and the full steering chain through run_target (including an unprepared agent following a hidden traversal). What I did not prove: no demonstrated shell-less MCP client population in my lab; for shell-capable agents the delta is stealth, not new capability. The read is bounded to the resolved package directory.

## Prior art and the delta

- The input channel was fixed upstream (the three commits above, and #33653 was the fix PR). The residual ancestor-walk channel is undisclosed.
- #32766 (2026-03-16, severity6) disclosed the tool-output prompt-injection class (OWASP MCP-01) and was closed as won't-fix with an "already compromised" argument. My counter: the steering hook here is metadata and stealth, not a malicious visible component; the combination (priority-0.9 channel + run_target option values + hidden traversal) is undisclosed.

## Remediation

1. Scope the `createRequire` resolution to `workspace/node_modules` (paths option), or re-check the resolved package path against the roots before reading.
2. Apply `checkPath`-style containment to path-bearing run_target option values.
3. Restrict run_target option keys to the target schema's defined options.

Happy to provide the full harness if useful. The steering evidence (shape-B) is in the report bundle.
