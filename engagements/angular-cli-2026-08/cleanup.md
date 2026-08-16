# cleanup.md — artifact ledger (chain-of-custody)

Every artifact the harness creates is recorded here with a revert action and status. Unresolved
cleanup **blocks pattern promotion**. Redact secrets always.

| Artifact | Type | Created (when) | Canary id | Revert action | Status |
| --- | --- | --- | --- | --- | --- |
| `upstream/angular-cli` clone (44 MB blob-filtered) + `node_modules` (916 MB) | target clone | 2026-08-14 | delete tree (closure) | open |
| `.lab-cache/` (angular-cli-distdir 7 archives + lab script) | lab cache | 2026-08-14 | delete (closure) | open |
| `/tmp/deepsec` (tool) + `/tmp/deepsec-scan-cli` (workspace + 960 MB copy) + `/tmp/deepsec-process.log` + `/tmp/deepsec-report-cli` | scanner tooling | 2026-08-15 | delete (closure); key file `/tmp/deepsec-scan-cli/opencode-key` is a CREDENTIAL — delete at closure | open |
| `/tmp/mcp-poc/` `/tmp/del-poc/` `/tmp/cache-poc/` `/tmp/purge-poc/` | PoC harnesses (evidence copies retained in findings packages) | 2026-08-14/15 | delete (closure) | open |
| `tmp/pending-records/` | staged kernel record payloads | 2026-08-15 | **DELETED 2026-08-15** (replayed into the kernel) | closed |
| `legacy/quarantine/event-tail-*.bin` (both engagements) | quarantined ledger tails (audit) | 2026-08-15 | retain for audit; delete only after operator review | open |

## Canary disposal
Every canary issued gets an id and a disposal state (`live / revoked / expired`). Persistence,
memory-bleed, and residual poisoned content are themselves part of what we measure — track them.

| `/tmp/caseguard-poc/` (compiled delete-output-dir.mjs + driver) | M3 case-guard PoC scratch (copied into findings/M3/evidence-caseguard/) | 2026-08-15 | delete (closure) | open |
| `/tmp/deepsec-resume-e1.log` | deep phase deepsec resume log | 2026-08-15 | delete (closure) | open |
| `upstream/dev-infra/` (re-clone at pin 04230133) | L3 attribution source (dev-infra clone was cleaned) | 2026-08-15 | delete (closure); NOT a credential | open |
| `/tmp/mcp-poc2/` (if created by X4) | M2 re-PoC scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/i18n-kp/` (copied into unproven/E1-C1/evidence/) | E1-C1 locale-key escape PoC scratch | 2026-08-15 | delete (closure) | open |
| `/tmp/extract-poc/` | KP-X1 extract-i18n write PoC scratch (verification output) | 2026-08-15 | delete (closure) | open |
| `/tmp/a7test/`, `/tmp/a6/` | R3 verification scratch (architect/schema PoCs) | 2026-08-15 | delete (closure) | open |
| `/tmp/globtest/`, `/tmp/mcp-poc2/`, `/tmp/caseguard-poc/` | R1/R3 verification scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/c3b/` (steering harness — copied to findings/M2/evidence/steering-demo/) | Chain 3 steering demo scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/c4a/`, `/tmp/c4h/` (Chain 4 demos — copied to findings/E1-C1/evidence/chain4/) | Chain 4 bundle demo + dependency-confusion scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/chain1/` (copied to payload-proposals/chain-demos/) | Chain 1 e2e fixture scratch | 2026-08-15 | delete (closure) | open |
| `/tmp/int2/` (INT2 verdict copied) | Chain 3 real-agent test scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/demo-c1/`, `/tmp/c2shape/` (copied to payload-proposals/chain-demos/) | E2-R9 demo hardening scratch | 2026-08-15 | delete (closure) | open |
| `/tmp/ssr-venue/` (copied to findings/E1-C1/evidence/chain4/ssr-venue/) | E1-C1 SSR venue runtime demo scratch | 2026-08-15 | delete (closure) | open |
| `/tmp/w1poc/` (copied to payload-proposals/w1poc/) | W1 win32 spawn-string PoC scratch | 2026-08-15 | delete (closure) | open |
| `/tmp/d3poc/` (copied to payload-proposals/d3-budget-math/) | D3 budget-math artifact scratch | 2026-08-15 | delete (closure) | open |
| `/tmp/kp-m3d2-verdict.md`, `/tmp/kp-m3`, `/tmp/kp-purge*`, `/tmp/kp-ctl` | M3+D2 Wave-B kill-pair scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/nr2-mf/`, `/tmp/nr2-d1ssr/`, `/tmp/nr2-composite/` (copied to payload-proposals/next-phase-demos/) | Wave D demos (member-F, D1 SSR, composite) scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/n1f/` (copied to findings/E1-C1/evidence/member-e/) | N1-F member-E demo scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/n1c/`, `/tmp/n1d/`, `/tmp/n1f/`, `/tmp/n1g/` (copied to evidence/payload dirs) | Next-phase N1 demos scratch | 2026-08-15 | delete (closure) | open |

| `/tmp/n4c/` (copied to findings/M2/evidence/steering-demo/shape-B/) | Chain 3 stealth-shape real-agent run scratch | 2026-08-15 | delete (closure) | open |
| `/tmp/c1cd/` (chain4 member C/D verification scratch — copied to findings/E1-C1/evidence/chain4/member-cd/) | E1-C1 member C/D scratch | 2026-08-15 | delete (closure) | open |
