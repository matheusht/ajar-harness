# NR2-COMPOSITE — C1 x C3 x C4 one-run composite harness (read-only, Wave D)

Proves the COMPOSITE capability (cloned-repo delivery x MCP agent steering x poisoned bundle)
in a single driver reusing the real artifacts:

- malrepo/ — the C1 malicious repo config (angular.json with outputPath ../victim-out [M3],
  cli.cache.path [D2], i18n.locales ../../escaped-locale [E1-C1], schematics route payload
  [D1]; .yarnrc/.npmrc registry redirect [W1 channel]) — copied from chain-demos/
- kp-m2rt.mjs — the real serializeOptions (option VALUES verbatim) — copied from steering-demo/
- node_modules/@babel + evil-locale.js — the chain4 bundle-embedding closure — copied from
  findings/E1-C1/evidence/chain4/
- secret-outside/secret.ts — the C3 out-of-roots exfil target

Hops: HOP1 C1 delivery (config consumed silently) · HOP2 C3 steering + serializeOptions
verbatim + path.join traversal read (out-of-roots exfil) · HOP3 C4 loadLocaleData +
Babel transform + bundle prepend · HOP4 fuse (SECRET/C1CFG into the AST) · HOP5 execution
(DOM stub) · HOP6 composite result.

Run: node composite-driver.cjs  → "ONE-RUN COMPOSITE DEMONSTRATED = true"
All three markers must be true (C1_DELIVERY, C3_EXFIL, C4_PWNED).
