# chain4/ — E1-C1 member C: browser + legacy-SSR execution evidence (E2-R4/R9)

**Canonical self-reproducing drivers (run from THIS directory):**

| Driver | Proves | Run |
|---|---|---|
| `demo.cjs` | 5-dot locale-key escape → attacker module resolved + Babel-transformed → embedded in the localized chunk → **executes in the client bundle** (DOM stub: `window.__chain4 = CHAIN4-PWNED-9f3c1e`, `document.title`, `fetch` beacon) | `node demo.cjs` |
| `check4dot.mjs` | 4-dot dependency-confusion variant: the key resolves `project/node_modules/evilpkg/index.js` (repo-shipped package) → loaded; negatives (nonexistent → null, fr → null) | `node check4dot.mjs` |
| `neg.cjs` | Discriminator: benign locale in-package; malicious key OUTSIDE the package; explicit-subPath traversal REJECTED by ensureValidSubPath | `node neg.cjs` |
| `ssr-venue/` | **Legacy-SSR server execution** (the legacy-SSR venue, 6.3 Medium — the earlier 7.3 framing superseded by the Wave-B kill-pair correction): attacker locale-data inlined into the server bundle executes in the SSR Node process at bundle load (top-level; `[ATTACKER-EXEC] SSR-VENUE-7f3c1e`); benign negative clean | `node ssr-venue/server-main.js` |
| `killpair-delivery/` | E2-R7 empirical: npm install PRUNES committed node_modules/evilpkg (self-contained repo-file delivery killed); the malicious-DEPENDENCY shape survives | see repo/ inputs |

**Notes:**
- The `node_modules/@babel/` closure (core 8.0.1, parser 8.0.4, preset-env 8.0.2, template 8.0.0 + transitive) is materialized locally (no symlinks, ~20MB) from the lab's pinned pnpm store — self-contained, no network.
- `demo.mjs` is a superseded ESM variant (kept for reference; `demo.cjs` is canonical).
- Preconditions (declared): attacker-controlled file at the landing path OR a resolving malicious dependency; config-trust channel; legacy webpack stack for the SSR venue (application builder contained).
- Pin: d827ba9005b86b23d05ee7c62c0823367aa245c1.
