# FINAL NOVELTY STATEMENT — angular-cli-2026-08 VRP filing (consolidated 2026-08-15)

All issue states below were re-verified live via the GitHub API on 2026-08-15 (this lane);
per-finding title searches were re-run where cheap and found no new disclosures beyond the cited set.

---

## D1 — `--route` codegen injection (Low-Medium)

- **Verdict:** NEAR-MISS (exact sink NOVEL; adjacent family disclosed and REJECTED).
- **Citations:** angular/angular-cli **#33074** (Security: SSR manifest code injection via baseHref, closed 2026-04-28) and **#33076** (Security: build-time code injection via unescaped server entry, closed 2026-04-28) — both closed same-day as not-a-vuln under the config-trust doctrine. Both by reporter foxllb.
- **Duplicate risk:** a triager who has seen #33074/#33076 will read this as the same family. Low for the exact `--route` sink (not disclosed there).
- **Delta line:** the schematics `--route` option interpolates unvalidated into generated TS, the comma-exec payload is valid (their two disclosures concern different sinks), and the injected code ships into production SSR.

## D2 — `ng cache clean` / purge deletion (Medium)

- **Verdict:** NOVEL. No issue/PR/advisory discloses `cli.cache.path`-driven arbitrary deletion.
- **Citations:** none found (title searches 2026-08-15: zero security hits; #22851 is the feature PR, #33321 adjacent worktree-cache discussion).
- **Duplicate risk:** negligible. #33321 is the nearest topic and is functional.
- **Delta line:** an unvalidated config path reaches force-recursive delete through 9 builder entrypoints, firing silently on every default build.

## D3 — branch-manager fork guard (Low)

- **Verdict:** CO-DISCOVERED class, angular-cli instance undisclosed; forward chain NOVEL.
- **Citations:** angular/components **#33632** (open, created 2026-08-05: "github.event.repository.fork check is ineffective in pull_request_target workflows") and **#33653** (open, created 2026-08-09: "ci: correct fork check in pull_request_target workflow") — an independent reporter found the same guard-defect class, and a class-fix PR is pending in components.
- **Duplicate risk:** HIGH and timing-sensitive. The components class-fix may sweep into angular/cli; file this promptly, cite both, and frame the angular-cli instance (guard line unfixed at main, verified 2026-08-15).
- **Delta line:** in angular-cli the ineffective guard leaves the robot-key budget channel ungated and quantified (a single attacker exceeds the 5,000 req/hr installation budget).

## M2 — MCP best-practices roots-escape residual (Low-Medium)

- **Verdict:** residual channel NOVEL; the prompt-injection tool-output class has a disclosed, triaged precedent.
- **Citations:** angular/angular-cli **#32766** (closed 2026-03-14, "Indirect Prompt Injection via Unsanitized Code Comments in Angular CLI MCP Server", OWASP MCP-01) — maintainers responded won't-fix ("you need to already have a hook... implies already compromised"). The input-level roots fix landed via #33653 in angular/cli (MCP roots, closed 2026-07-24, in the pin); the createRequire ancestor-walk residual is undisclosed.
- **Duplicate risk:** medium-low; the fix is in the pin, so the residual must be filed with the fix cited and the residual shown live (re-PoC at the pin).
- **Delta line:** the residual reads out-of-roots package metadata into the agent context at priority 0.9, and the run_target option-value channel bypasses the restricted host for shell-less clients.

## M3 — outputPath deletion + case-guard (Medium)

- **Verdict:** NOVEL (delete path). Write-side fixes exist; the delete path and the case-guard are unfixed at main.
- **Citations:** angular/angular-cli **#32873** (closed 2026-03-27, "prevent deleting parent directories of project root" — a delete-guard PR that was proposed and NEVER merged: disclosed-but-unfixed); **#33312**/bd413b0eb (2026-06-04, main-only write-path containment); **#33479** (closed 2026-06-27, "prevent OS command injection in ssr-dev-server builder" — the CI-execution RCE class, fixed and in the pin).
- **Duplicate risk:** low-medium; a triager could argue the #32873 PR covers it. Counter: that PR was rejected, and the DELETE path + case-insensitive root-guard bypass are still live at main (byte-identical, verified 2026-08-15).
- **Delta line:** a malicious outputPath deletes arbitrary directories including the workspace root itself on case-insensitive filesystems, bypassing the only guard.

## W1 — win32 dist-tags injection (Low-Med dev / 8.1 HIGH CI-venue)

- **Verdict:** FIX-BYPASS / regression framing (the exact class was triaged severity6); the registry-VALUE channel and the CI-token venue are novel.
- **Citations:** angular/angular-cli **#32509** (closed 2026-02-19, "Command Injection via child_process.spawn with shell:true on Windows") — severity6; **#32892** (closed 2026-03-29, "prevent CWE-78 OS command injection across all Windows package managers") — the full fix, REJECTED. The quote-wrap added by 85e3ce2e0 (2026-02-23) bypasses #32509's scope; #32678 fixed the git executor only.
- **Duplicate risk:** HIGH as a mechanism report (the maintainers have seen the sink and rejected the full fix). The filing MUST open with the delta, not the mechanism.
- **Delta line:** registry-controlled dist-tags VALUES (not the specifier construction) are unvalidated, the update path is manager-independent (npm default), and on a fork-PR Windows CI job the injected cmd.exe inherits GITHUB_TOKEN/ACTIONS_RUNTIME_TOKEN/OIDC with zero user interaction.

## E1-C1 — i18n locale-key bypass (Low-Med 4.0 / Medium 6.3 legacy-SSR)

- **Verdict:** NOVEL mechanism; adjacent local-file-into-dist class disclosed.
- **Citations:** angular/angular-cli **#33073** (closed 2026-04-28, "webpack browser builds copy external local files into dist via CSS url()", foxllb) — the same class of local-file-content-into-bundle, different mechanism; closed same-day without fix. #33859/#33866 (2026-08) are functional inliner refactors.
- **Duplicate risk:** low; the locale-key/subPath mechanism is undisclosed (verified 2026-08-15, zero hits).
- **Delta line:** unvalidated locale keys bypass the existing subPath guard, write outside the output base, and ship attacker-authored JS into the client bundle and the legacy-SSR server process, where it executes at boot.

---

**Cross-cutting:** the foxllb cluster (#33073-#33077, 2026-04-28) is an active independent reporter on the config-to-dist/codegen surface. Every filing must cite the cluster where adjacent. No other public disclosures of any of the seven exact mechanisms were found in the 2026-08-15 re-checks.
