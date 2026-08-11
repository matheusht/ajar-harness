# progress.md — obyte-ocore-2026-08

Newest first.

## 2026-08-11 — bootstrap

Engagement created from `_TEMPLATE`. `scope.md` signed by the operator in session. Program rules
transcribed to `program-policy.md` (Immunefi / Obyte Foundation, **Primacy of Rules**).

- **Target:** `github.com/byteball/ocore` — Obyte DAG core library, Node.js.
- **Scope:** blockchain/DLT only. The nine Autonomous Agent repositories are a **separate, deferred**
  scope; if opened later, prioritise by most-recently-updated. A finding in ocore's AA *engine* is in
  scope; a finding in an individual AA's *own* logic is not.
- **Freshness:** verified 2026-08-11 — no prior obyte/byteball/ocore work anywhere in this repository.
- **Environment:** local only. No mainnet, no public testnet, no live node. Program-prohibited.
- **PoC:** required for every severity. A source-only finding is not submittable.

### Not yet done — the operating agent fills these

- [ ] clone + pin the ocore commit, record the identity here
- [ ] local multi-node network stood up, synthetic genesis, locally generated keys
- [ ] environment preflight (Node version, install, existing test suite) — record blockers verbatim
- [ ] `recon-signals.md` activation table completed, baseline controls captured
- [ ] the two ladder questions answered (total shutdown / spend-without-key)
- [ ] the DoS coordination question settled for the availability surface
