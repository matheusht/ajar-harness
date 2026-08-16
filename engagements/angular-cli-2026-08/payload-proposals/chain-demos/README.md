# chain-demos/ — chainstorm demo artifacts (E2)

| Artifact | Chain | Proves | Reproduce |
|---|---|---|---|
| `malrepo/` + `goodrepo/` + `run-chain1.mjs` + `chain1-results-*.json` + `chain1-README.md` | C1 | cloned-repo delivery chain: registry redirect (.npmrc/.yarnrc native), W1 dist-tags carrier, M3 delete + case-guard, D2 purge, E1-C1 write, D1 defaults route — 9/9 both modes | `node run-chain1.mjs` (needs the compiled lib/ modules; registry-server.mjs local) |
| `c2shape/` | C2 | config-as-data CI shape in-lab: PR config drives escaped delete + purge + locale write (3/3; negative clean) | see c2shape/ |
| `INT2-VERDICT.md` | C3 | real-agent H2 follow estimate (MEDIUM-HIGH) + the steering mechanics | findings/M2/evidence/steering-demo/ |
| `chain1-fixture-spec.md` | C1 | the original fixture spec | — |
| `chain2-wire2-spec.md` | C2 | the operator-gated private-fork demo spec | — |

W1 cmd.exe execution rung: environment-blocked (Windows) — the fixture wires the hop via the registry log + compiled carrier.

**E2-D3 KILL-PAIR UPDATE (DR3-03):** the composite harness (next-phase-demos/nr2-composite/) is re-labeled a **capability-fusion artifact** — it does NOT add security evidence beyond the individual chains (the HOP2 steering hop is simulated; a marker false-positive (empty-secret tautology in the C3_EXFIL check) was found and must be fixed before any further use: the check must require a NON-EMPTY secret match). The per-chain verdicts are unaffected.
