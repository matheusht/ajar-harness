## Wire-2 decision record — Chain 2 CI-sabotage demo

- **Decision:** APPROVED / DENIED / DEFERRED (date + operator)
- **Confirmation text:** <verbatim or substantive excerpt naming fork/workflow/payload/cleanup>
- **Act executed:** <run ID(s) from the Actions UI / API> · <date · time>
- **Repo:** <operator>/chain2-cisabot (private, throwaway) · **Workflow:** ci-sabot.yml
- **Payload branches:** pr/p1-caseguard · pr/p2-escape · pr/p3-locales
- **Runners:** macos-latest (case-guard hop) + ubuntu-latest (control)
- **Result summary per hop:** P1 case-guard: <MARKER-DELETED / MARKER-INTACT> · P2 escape: <deleted/overwritten> · P3 locales: <file landed outside output base>
- **Runner fs semantics observed:** <case-insensitive APFS confirmed on macos-latest / not>
- **Cost consumed:** <quota-minutes>
- **Evidence archived:** <paths under findings/…/wire2/…; benign logs + fs probes>
- **Cleanup obligation:** cleanup.md entry <id> — status: OPEN until `gh repo delete` + local clone removal executed, then CLOSED by operator
- **No-secrets attestation:** contents: read only; zero repo secrets; no env credentials; no npm auth (verified from the archived workflow file)
- **Filing delta:** M3 CI-sabotage framing — runner rung: <CLOSED / REMAINS REASONED-NOT-RUN>; report line updated accordingly

