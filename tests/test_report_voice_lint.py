#!/usr/bin/env python3
"""Unit & regression test suite for report_voice_lint.py v2 (ajar-report-voice-lint/2).

Verifies all 12 Judge-4 precision fixes, Blind-Judge-2 LLM-tell detectors, draft slug gate,
Rule #15 GFM mid-paragraph hard-wrapped prose line-break gate, and Rule #16 canonical
required-sections, section-ordering, and GHSA Patched Versions top-metadata gate.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
SCRIPT_DIR = (
    _HERE / "ajar-advisory-skill-v2" / "scripts"
    if (_HERE / "ajar-advisory-skill-v2" / "scripts").is_dir()
    else _HERE.parent / "skills" / "security-advisory-report" / "scripts"
)
SKILL_ROOT = SCRIPT_DIR.parent
sys.dont_write_bytecode = True
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import report_voice_lint as linter  # noqa: E402

BASE_CLEAN_GHSA_TIER_S = """# proxy: missing length check in `do_SOCKS()` overflows heap buffer

- **Ecosystem / Package:** `c / curl`
- **Affected Versions:** `v7.69.0 .. v8.3.0` (verified on `master` at `4a4b63daaa12`)
- **Patched Versions:** `v8.4.0`
- **Severity:** High
- **CWE:** CWE-122 (Heap-based Buffer Overflow)

### Summary

In libcurl `v7.69.0 .. v8.3.0` (`4a4b63daaa12`), `do_SOCKS()` in `lib/socks.c:942` copies an overlong hostname into the negotiation buffer when `CURLPROXY_SOCKS5_HOSTNAME` resolves locally, overflowing the heap allocation.

### Details

Introduced in commit `31882f9100ab` ("socks: switch to state machine", 2020-02-11), `do_SOCKS()` checks `hostname_len > 255` before deciding whether to resolve locally or remotely. When the handshake buffer is smaller than 600 bytes, `libcurl` falls back to local resolution without re-checking length. Sibling path `Curl_socks4a()` rejects names above 255 bytes immediately. Stock `curl` CLI builds allocate a 100 KiB buffer by default and are unaffected unless `--limit-rate` shrinks the transfer buffer below 65541 bytes.

### PoC

Verified on Linux x86_64 with `-O2` and `-fsanitize=address`.

```sh
#!/bin/sh
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
python3 -m http.server 0 --directory "$work" >/dev/null 2>&1 &
srv=$!
trap 'kill "$srv" 2>/dev/null || true; rm -rf "$work"' EXIT
curl --socks5-hostname 127.0.0.1:1080 --limit-rate 1024 http://example.com/ || true
```

### Impact

Applications using `libcurl` with `CURLPROXY_SOCKS5_HOSTNAME` and small transfer buffers suffer a heap buffer overflow on redirect to an attacker-controlled host. Deployments without SOCKS5 proxies are unaffected.

### Suggested Fix

Reject hostnames longer than 255 bytes before falling back, matching `Curl_socks4a()`. Verified against `tests/runtests.pl` suites 700 to 728.

```diff
--- a/lib/socks.c
+++ b/lib/socks.c
@@ -940,6 +940,8 @@ CURLcode do_SOCKS(struct Curl_easy *data)
   if(socks5_resolve_local && hostname_len > 255)
     return CURLE_PROXY;
```

### Workarounds

Avoid `CURLPROXY_SOCKS5_HOSTNAME` or keep `CURLOPT_BUFFERSIZE` at or above 65541 bytes until upgraded.

Reported-by: Researcher Name <security@ajar.com> (Ajar Labs)
"""


class TestReportVoiceLintV2(unittest.TestCase):
    def _lint_text(
        self,
        content: str,
        *,
        suffix: str = ".md",
        tier: str | None = "S",
        channel: str = "ghsa",
        filename: str | None = None,
    ) -> linter.FileLintReport:
        with tempfile.TemporaryDirectory() as td:
            name = filename if filename is not None else f"draft{suffix}"
            p = pathlib.Path(td) / name
            p.write_text(content, encoding="utf-8")
            return linter.lint_file(p, tier=tier, channel=channel)

    def test_01_fp1_http_bls_jvm_tokens_not_flagged_but_ajar_hooks_gates_flagged(self) -> None:
        """Case 1 (FP-1): H1..H3 (HTTP) & G1..G2 (BLS12-381 / JVM G1) pass; hook H6 / gate G3 fail."""
        doc = BASE_CLEAN_GHSA_TIER_S.replace(
            "Deployments without SOCKS5 proxies are unaffected.",
            "HTTP/2 (`H2`) to `H1` and `H3` downgrade proxies using BLS12-381 `G1` and `G2` pairing groups under JVM G1 are unaffected.",
        )
        rep = self._lint_text(doc, tier="S", channel="ghsa")
        self.assertTrue(rep.passed, f"Unexpected issues: {rep.issues}")
        self.assertEqual(rep.warnings, [], f"Unexpected warnings: {rep.warnings}")
        self.assertEqual(len(rep.harness_leaks), 0)

        bad_doc = BASE_CLEAN_GHSA_TIER_S + "\nVerified via epistemic hook H6 and SQL gate G3 (G1-G5).\n"
        bad_rep = self._lint_text(bad_doc, tier="S", channel="ghsa")
        self.assertFalse(bad_rep.passed)
        self.assertGreaterEqual(len(bad_rep.harness_leaks), 2)

    def test_02_fp2_english_verb_steers_and_org_credit_allowed(self) -> None:
        """Case 2 (FP-2): English verb 'steers' + 1-line Reported-by (Ajar Labs) pass; Workspace Steers fails."""
        doc = BASE_CLEAN_GHSA_TIER_S.replace(
            "Deployments without SOCKS5 proxies are unaffected.",
            "When a redirect header steers traffic to an untrusted origin, stock Linux builds remain unaffected.",
        )
        rep = self._lint_text(doc, tier="S", channel="ghsa")
        self.assertTrue(rep.passed, f"Issues: {rep.issues}")
        self.assertEqual(rep.warnings, [], f"Warnings: {rep.warnings}")
        self.assertEqual(len(rep.harness_leaks), 0)

        bad_doc = BASE_CLEAN_GHSA_TIER_S + "\nGuided by Workspace Steers, Active Steers, and `ajar steer add` (`found_autonomously_by_ajar`).\n"
        bad_rep = self._lint_text(bad_doc, tier="S", channel="ghsa")
        self.assertFalse(bad_rep.passed)
        self.assertGreaterEqual(len(bad_rep.harness_leaks), 3)

    def test_03_fp3_legitimate_technical_nouns_allowed(self) -> None:
        """Case 3 (FP-3): underscore (0x5f), Double Ratchet, Substrate, cryptographic primitives, log sink pass."""
        doc = BASE_CLEAN_GHSA_TIER_S.replace(
            "Deployments without SOCKS5 proxies are unaffected.",
            "Header names with an ASCII underscore (`0x5f`) or underscores in Substrate Double Ratchet cryptographic primitives and log sinks are unaffected.",
        )
        rep = self._lint_text(doc, tier="S", channel="ghsa")
        self.assertTrue(rep.passed, f"Issues: {rep.issues}")
        self.assertEqual(len(rep.slop_hits), 0, f"Slop hits: {rep.slop_hits}")
        self.assertEqual(len(rep.harness_leaks), 0, f"Harness leaks: {rep.harness_leaks}")

        bad_doc = BASE_CLEAN_GHSA_TIER_S.replace(
            "Deployments without SOCKS5 proxies are unaffected.",
            "This bug underscores the risk when an exploit primitive reaches a vulnerable sink.",
        )
        bad_rep = self._lint_text(bad_doc, tier="S", channel="ghsa")
        self.assertFalse(bad_rep.passed)
        self.assertGreaterEqual(len(bad_rep.slop_hits), 1)
        self.assertGreaterEqual(len(bad_rep.harness_leaks), 1)

    def test_04_fp4_mailing_list_rfc5322_4space_repro_unfenced_diff_lowercase_c_starter(self) -> None:
        """Case 4 (FP-4): Plain-text mailing-list with RFC 5322 headers, canonical Setext sections, 4-space sh, unfenced diff, C starters, POSIX --."""
        email_txt = """From: Researcher Name <security@ajar.com>
To: security@example.org
Date: Mon, 24 Nov 2026 01:00:00 +0000
Subject: [SECURITY] socks: heap overflow in do_SOCKS() on local hostname fallback

In libcurl v7.69.0 .. v8.3.0 (commit 4a4b63daaa12), do_SOCKS() in
lib/socks.c:942 copies an overlong hostname into the negotiation buffer
when CURLPROXY_SOCKS5_HOSTNAME falls back to local resolution.

Affected versions: v7.69.0 .. v8.3.0
Patched versions:  v8.4.0
Introduced in:     31882f9100ab ("socks: state machine", 2020-02-11)
Affected configs:  CURLPROXY_SOCKS5_HOSTNAME with buffer < 65541 bytes

Analysis
--------
do_SOCKS() checks hostname_len > 255 before choosing remote vs. local
DNS resolution. parse_socks_state() then shrinks the handshake window
when --limit-rate caps CURLOPT_BUFFERSIZE below 65541 bytes.
do_SOCKS() falls back to local resolution without re-running the 255
byte check, unlike Curl_socks4a(). Stock CLI runs without --limit-rate
are unaffected. Invoke curl -- http://example.com/ to test end-of-flags.

PoC
---
Tested on Linux x86_64 with -O2 and -fsanitize=address.

    #!/bin/sh
    set -eu
    work=$(mktemp -d)
    trap 'rm -rf "$work"' EXIT
    curl --socks5-hostname 127.0.0.1:1080 -- http://example.com/ || true

Impact
------
Applications enabling CURLPROXY_SOCKS5_HOSTNAME with transfer buffers
below 65541 bytes suffer a heap buffer overflow on HTTP redirect.

Suggested Fix
-------------
Reject overlong hostnames before local fallback, matching Curl_socks4a().
All tests in tests/data/test700..728 pass.

--- a/lib/socks.c
+++ b/lib/socks.c
@@ -940,6 +940,8 @@ CURLcode do_SOCKS(struct Curl_easy *data)
   if(socks5_resolve_local && hostname_len > 255)
     return CURLE_PROXY;

Workarounds
-----------
Keep CURLOPT_BUFFERSIZE at or above 65541 bytes until upgraded.

Reported-by: Researcher Name <security@ajar.com> (Ajar Labs)
"""
        rep = self._lint_text(email_txt, suffix=".txt", tier="S", channel="mailing-list")
        self.assertTrue(rep.passed, f"Issues: {rep.issues}")
        self.assertEqual(rep.warnings, [], f"Warnings: {rep.warnings}")
        self.assertTrue(rep.has_reproducer_block)
        self.assertTrue(rep.has_diff_or_patch)
        self.assertEqual(rep.em_dash_count, 0)
        self.assertEqual(rep.severe_runons_over_50, 0)
        self.assertEqual(rep.missing_sections, [])
        self.assertEqual(rep.out_of_order_sections, [])
        self.assertEqual(rep.mechanical_score_100, 100)

    def test_05_fp5_compact_tier_s_and_6_section_ghsa_both_pass_strict(self) -> None:
        """Case 5 (FP-5a): Both full-header GHSA Tier S and concise ~125w 6-section Tier S pass strict at 100/100."""
        rep6 = self._lint_text(BASE_CLEAN_GHSA_TIER_S, tier="S", channel="ghsa")
        self.assertTrue(rep6.passed, f"Issues: {rep6.issues}")
        self.assertEqual(rep6.warnings, [], f"Warnings: {rep6.warnings}")
        self.assertEqual(rep6.mechanical_score_100, 100)

        concise_s = """# x509: NULL dereference in `X509_STORE_CTX_init()` on empty store

### Summary

On `master` at `9f8e7d6c5b4a` (unreleased), `X509_STORE_CTX_init()` in `crypto/x509/x509_vfy.c:2140` dereferences `store->objs` before checking `store == NULL`, crashing callers that pass a standalone certificate chain.

### Details

Introduced in commit `1a2b3c4d5e6f` ("x509: cache issuer lookup", 2026-04-02), the new fast path reads `store->objs` ahead of the existing `if (store == NULL)` guard at line 2148. Released `3.3.x` builds are unaffected.

### PoC

```sh
#!/bin/sh
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cc -O2 repro.c -lcrypto -o "$work/repro" && "$work/repro"
```

### Impact

Direct callers passing `store = NULL` to `X509_STORE_CTX_init()` crash with a deterministic NULL dereference, whereas `SSL_CTX` callers are unaffected.

### Suggested fix

Move the `store->objs` read below the `store == NULL` check. Verified with `make test TESTS=test_verify`.

```diff
--- a/crypto/x509/x509_vfy.c
+++ b/crypto/x509/x509_vfy.c
@@ -2139,7 +2139,7 @@ int X509_STORE_CTX_init(X509_STORE_CTX *ctx, X509_STORE *store,
-    if (sk_X509_OBJECT_num(store->objs) == 0)
+    if (store != NULL && sk_X509_OBJECT_num(store->objs) == 0)
```

### Workarounds

Pass a valid empty `X509_STORE_new()` handle instead of `NULL` until patched.
"""
        rep_concise = self._lint_text(concise_s, tier="S", channel="ghsa")
        self.assertTrue(rep_concise.passed, f"Concise 6-section S issues: {rep_concise.issues}")
        self.assertEqual(rep_concise.warnings, [], f"Concise 6-section S warnings: {rep_concise.warnings}")
        self.assertEqual(rep_concise.mechanical_score_100, 100)
        self.assertGreaterEqual(rep_concise.prose_word_count, 90)
        self.assertLess(rep_concise.prose_word_count, 165)

    def test_06_fp5_low_dry_and_immunefi_modes_pass_strict(self) -> None:
        """Case 6 (FP-5b/c/d): --tier low, --tier dry, and --channel immunefi pass 100/100."""
        low_md = """## Missing zero-address check in `setTreasury()`

- **Severity:** Low
- **Target:** `contracts/Vault.sol:88`

### Description

In `Vault.sol:88` at commit `a1b2c3d4e5f6`, `setTreasury(address next)` updates `treasury` without rejecting `address(0)`. Only the `TIMELOCK_ADMIN` multisig can call `setTreasury()`, and user principal remains withdrawable.

### Impact

Impact is confined to protocol fee burn until the next timelock transaction restores a valid treasury address.

### Recommendation

Revert with `ZeroAddress()` when `next == address(0)` inside `setTreasury()`.
"""
        rep_low = self._lint_text(low_md, tier="low", channel="customer")
        self.assertTrue(rep_low.passed, f"Low issues: {rep_low.issues}")
        self.assertEqual(rep_low.warnings, [], f"Low warnings: {rep_low.warnings}")
        self.assertEqual(rep_low.mechanical_score_100, 100)

        dry_md = """# Security Review Summary: `vault-core` (`a1b2c3d4e5f6`)

Prepared by: Ajar Labs

### Security Review Summary

We reviewed `vault-core` at commit `a1b2c3d4e5f6` across `Vault.sol`, `ShareMath.sol`, and `WithdrawalQueue.sol`. Zero exploitable vulnerabilities were identified within the authorized scope.

### Verified Guards

Share-rounding calculations in `ShareMath.sol:42-96` round in favor of the pool on both deposit and redeem paths. `WithdrawalQueue.sol:144` enforces per-epoch nonces before external token transfers, preventing reentrant claim replay.

### Limitations and Unresolved Paths

Cross-chain bridge relayer off-chain signing daemons were outside repository scope and remain unverified. Dynamic fork simulations against unannounced governance upgrades were blocked by missing mainnet deployment parameters. This summary records bounded engineering evidence on commit `a1b2c3d4e5f6`; it does not certify the software or warrant the absence of defects. Review again before modifying `ShareMath.sol` or enabling cross-chain settlement.
"""
        rep_dry = self._lint_text(dry_md, tier="dry", channel="customer")
        self.assertTrue(rep_dry.passed, f"Dry issues: {rep_dry.issues}")
        self.assertEqual(rep_dry.warnings, [], f"Dry warnings: {rep_dry.warnings}")
        self.assertEqual(rep_dry.mechanical_score_100, 100)

        immunefi_md = """# VaultRouter: unchecked `minSharesOut` in `rebalance()` drains idle USDC buffer

### Quantified Summary & Activation Status

On Ethereum mainnet at block `21000000`, `VaultRouter.rebalance()` at `0x1111111111111111111111111111111111111111` (`contracts/VaultRouter.sol:212`, commit `deadbeef1234`) forwards `0` as `minAmountOut` when swapping idle reserves through Uniswap V3. Because `rebalance()` is callable by any unprivileged address whenever `idleRatio() > 1500` bps, a sandwich transaction extracts up to the pool's idle buffer. Live on-chain exposure is bounded to `412,800 USDC` currently held in `VaultRouter` (principal staked in `CoreVault` is isolated and unaffected). The contract is live and unpaused.

### Trust Boundary & Broken Invariant

`VaultRouter.sol:212` computes `expectedOut` from the TWAP oracle in `quoteRebalance()`, yet passes literal `0` into `ISwapRouter.exactInputSingle()`. Neighboring `zapDeposit()` at `VaultRouter.sol:154` passes `expectedOut * 9950 / 10000`. That missing slippage parameter lets an unprivileged caller sandwich `rebalance()` in a single atomic bundle without holding governance roles.

### State Walkthrough

1. `Attacker` flash-borrows `5,000,000 USDC` and tilts the `USDC/WETH` pool spot price.
2. `Attacker` calls `VaultRouter.rebalance()`, which sells `412,800 USDC` with `amountOutMinimum = 0`.
3. `Attacker` back-runs the pool swap and repays the flash loan, netting `398,100 USDC` after fees (`~0.04 ETH` gas).

### PoC

```sh
#!/bin/sh
set -eu
forge test --match-test test_rebalance_zero_slippage -vv
```

### Impact

Any unprivileged MEV searcher can drain up to `412,800 USDC` of idle router reserves in one atomic transaction whenever `idleRatio() > 1500` bps. Staked principal in `CoreVault` remains isolated and unaffected.

### Remediation

Pause `VaultRouter` via `guardian.pauseRouter()` immediately to protect the `412,800 USDC` buffer. Then pass `expectedOut * (10000 - maxSlippageBps) / 10000` into `exactInputSingle()` and verify against `test/VaultRouter.t.sol`.

```diff
--- a/contracts/VaultRouter.sol
+++ b/contracts/VaultRouter.sol
@@ -212,7 +212,7 @@
-        amountOutMinimum: 0,
+        amountOutMinimum: minOut,
```
"""
        rep_imm = self._lint_text(immunefi_md, tier="M", channel="immunefi")
        self.assertTrue(rep_imm.passed, f"Immunefi issues: {rep_imm.issues}")
        self.assertEqual(rep_imm.warnings, [], f"Immunefi warnings: {rep_imm.warnings}")
        self.assertEqual(rep_imm.mechanical_score_100, 100)

    def test_07_fp6_stative_adjectives_not_counted_as_passive_voice(self) -> None:
        """Case 7 (FP-6): 'are unaffected', 'is confined', 'is disabled', 'is required' -> 0 passive hits."""
        paragraph = (
            "Stock Linux builds are unaffected. "
            "Impact is confined to non-default proxy configurations. "
            "Client authentication is required before TLS renegotiation. "
            "Automatic fallback is disabled on macOS builds."
        )
        sents = linter._split_sentences(paragraph)
        self.assertEqual(len(sents), 4)
        passive_hits = [s for s in sents if linter.PASSIVE_AUX_PARTICIPLE_RE.search(s)]
        self.assertEqual(passive_hits, [], f"Stative adjectives wrongly flagged as passive: {passive_hits}")

        # True passive voice MUST still be detected
        true_passive = "The heap buffer was allocated by the caller and is overwritten by memcpy."
        self.assertIsNotNone(linter.PASSIVE_AUX_PARTICIPLE_RE.search(true_passive))

    def test_08_fn1_local_path_leaks_after_diff_git_caught(self) -> None:
        """Case 8 (FN-1): Local host paths (<macos_home>, <linux_home>, /opt/antigravity) AFTER diff --git are caught."""
        fake_macos_path = "/" + "Users/researcher/private/run.log"
        fake_linux_path = "/" + "home/antigravity/secret.txt"
        raw_diff_leak = BASE_CLEAN_GHSA_TIER_S + (
            "\ndiff --git a/lib/socks.c b/lib/socks.c\n"
            "--- a/lib/socks.c\n"
            "+++ b/lib/socks.c\n"
            "@@ -1,2 +1,2 @@\n"
            "\n### Extra Note\n"
            f"See local log at {fake_macos_path} and {fake_linux_path}\n"
        )
        rep = self._lint_text(raw_diff_leak, tier="S", channel="ghsa")
        self.assertFalse(rep.passed)
        self.assertGreaterEqual(len(rep.local_path_leaks), 2)

    def test_09_fn2_raw_markdown_detected_in_mailing_list_mode(self) -> None:
        """Case 9 (FN-2): ### headings, ``` fences, `backticks`, and | tables | fail in --channel mailing-list."""
        bad_email = """Subject: [SECURITY] socks: overflow in do_SOCKS()

### Summary

In libcurl `v8.3.0`, `do_SOCKS()` overflows a heap buffer.

| OS | Affected |
| --- | --- |
| Linux | Yes |

```sh
mktemp -d
```
"""
        rep = self._lint_text(bad_email, suffix=".txt", tier="S", channel="mailing-list")
        self.assertFalse(rep.passed)
        self.assertGreaterEqual(rep.markdown_decoration_in_plaintext, 4)

    def test_10_fn3_table_cap_and_table_word_stuffing_enforced(self) -> None:
        """Case 10 (FN-3): Table limits enforced (0 on low, <=1 on S/M/C)."""
        low_with_table = """## Minor config note in `Vault.sol`

### Description

In `Vault.sol:88` at `a1b2c3d4`, `setFee()` allows zero fee values when called by governance.

### Impact

No user funds are at risk; stock deployments are unaffected.

| Param | Value |
| :--- | :--- |
| fee | 0 |

### Recommendation

Document zero-fee behavior in NatSpec comments.
"""
        rep_low = self._lint_text(low_with_table, tier="low", channel="customer")
        self.assertFalse(rep_low.passed)
        self.assertEqual(rep_low.table_count, 1)

        s_two_tables = BASE_CLEAN_GHSA_TIER_S + (
            "\n| A | B |\n|---|---|\n| 1 | 2 |\n\n### Matrix 2\n\n| C | D |\n|---|---|\n| 3 | 4 |\n"
        )
        rep_s = self._lint_text(s_two_tables, tier="S", channel="ghsa")
        self.assertFalse(rep_s.passed)
        self.assertEqual(rep_s.table_count, 2)

    def test_11_fn4_ajar_harness_v31_state_tokens_caught(self) -> None:
        """Case 11 (FN-4): verified_local, survived_falsify, peer_symmetry, native_ffi, outside_in, inside_out caught."""
        for tok in ("verified_local", "survived_falsify", "peer_symmetry", "native_ffi", "outside_in", "inside_out"):
            bad = BASE_CLEAN_GHSA_TIER_S + f"\nState transitioned via `{tok}` pass.\n"
            rep = self._lint_text(bad, tier="S", channel="ghsa")
            self.assertFalse(rep.passed, f"Token {tok} was not caught!")
            self.assertGreaterEqual(len(rep.harness_leaks), 1)

    def test_12_blind_judge2_llm_tells_caught(self) -> None:
        """Case 12 (Judge-2 LLM tells): Hop 1/Hops 2, rubric-echo bold lead-ins, Intended/Bypass pair, Orthogonally to."""
        # 12a: Hop 1 / Hops 2
        hop_doc = BASE_CLEAN_GHSA_TIER_S.replace(
            "Sibling path `Curl_socks4a()`",
            "After Hop 1 and Hops 2 complete, sibling path `Curl_socks4a()`",
        )
        rep_hop = self._lint_text(hop_doc, tier="S", channel="ghsa")
        self.assertFalse(rep_hop.passed)
        self.assertTrue(any("Hop" in h.rule for h in rep_hop.harness_leaks))

        # 12b: Rubric-echo bold paragraph lead-in
        echo_doc = BASE_CLEAN_GHSA_TIER_S.replace(
            "### Details\n\n",
            "### Details\n\n**Trust boundary and proxy precondition:** Default installs disable SOCKS5.\n\n",
        )
        rep_echo = self._lint_text(echo_doc, tier="S", channel="ghsa")
        self.assertFalse(rep_echo.passed)
        self.assertTrue(any("rubric-echo" in s.rule for s in rep_echo.slop_hits))

        # 12c: - Intended: / - Bypass: schema pair
        pair_doc = BASE_CLEAN_GHSA_TIER_S + "\n- Intended: check length.\n- Bypass: fallback skips check.\n"
        rep_pair = self._lint_text(pair_doc, tier="S", channel="ghsa")
        self.assertFalse(rep_pair.passed)
        self.assertTrue(any("Intended" in s.rule for s in rep_pair.slop_hits))

        # 12d: Orthogonally to
        ortho_doc = BASE_CLEAN_GHSA_TIER_S.replace(
            "Sibling path `Curl_socks4a()`",
            "Orthogonally to local DNS resolution, `Curl_socks4a()`",
        )
        rep_ortho = self._lint_text(ortho_doc, tier="S", channel="ghsa")
        self.assertFalse(rep_ortho.passed)
        self.assertTrue(any("Orthogonally" in s.rule for s in rep_ortho.slop_hits))

    def test_13_cli_json_schema_version_2(self) -> None:
        """Verify CLI --json emits schema 'ajar-report-voice-lint/2' and exits 0 on clean input."""
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "clean.md"
            p.write_text(BASE_CLEAN_GHSA_TIER_S, encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "report_voice_lint.py"),
                    str(p),
                    "--tier",
                    "S",
                    "--channel",
                    "ghsa",
                    "--strict",
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            data = json.loads(proc.stdout)
            self.assertEqual(data["schema"], "ajar-report-voice-lint/2")
            self.assertTrue(data["all_passed"])
            self.assertEqual(data["reports"][0]["missing_sections"], [])
            self.assertEqual(data["reports"][0]["out_of_order_sections"], [])

    def test_14_draft_ghsa_slug_caught_while_real_ghsa_id_passes(self) -> None:
        """Case 14 (Wave-4C): draft slugs (`ghsa-3a`, `ghsa-3b`, `GHSA-1`) fail; real 4-4-4 GHSA IDs pass."""
        clean_real_ghsa = BASE_CLEAN_GHSA_TIER_S.replace(
            "Deployments without SOCKS5 proxies are unaffected.",
            "Prior fixes in `GHSA-r87m-v37r-cwfh` and GHSA-385p-627f-43v2 left deployments without SOCKS5 proxies unaffected.",
        )
        rep_clean = self._lint_text(clean_real_ghsa, tier="S", channel="ghsa")
        self.assertTrue(rep_clean.passed, f"Real GHSA IDs wrongly flagged: {rep_clean.issues}")
        self.assertEqual(len(rep_clean.harness_leaks), 0)

        for slug in ("`ghsa-3a`", "(`ghsa-3b`)", "GHSA-1"):
            bad_doc = BASE_CLEAN_GHSA_TIER_S + f"\nSplit candidate tracked under {slug}.\n"
            rep_bad = self._lint_text(bad_doc, tier="S", channel="ghsa")
            self.assertFalse(rep_bad.passed, f"Draft slug {slug} was not caught!")
            self.assertGreaterEqual(len(rep_bad.harness_leaks), 1)

    def test_15_markdown_mid_paragraph_hard_wrap_caught(self) -> None:
        """Case 15: Markdown mid-paragraph & mid-bullet hard line breaks fail; separate bullets/tables/mailing-list pass."""
        expected_msg = (
            "Markdown prose contains hard mid-paragraph line breaks "
            "(GFM renders single \\n as <br>); put each paragraph and bullet item on a single line"
        )

        # 15a: Mid-paragraph hard wrap fails across all Markdown channels (`ghsa`, `h1`, `immunefi`, `customer`)
        wrapped_para = BASE_CLEAN_GHSA_TIER_S.replace(
            "copies an overlong hostname into the negotiation buffer when `CURLPROXY_SOCKS5_HOSTNAME` resolves locally, overflowing the heap allocation.",
            "copies an overlong hostname into the negotiation buffer\nwhen `CURLPROXY_SOCKS5_HOSTNAME` resolves locally,\noverflowing the heap allocation.",
        )
        for ch in ("ghsa", "h1", "immunefi", "customer"):
            rep_wrap = self._lint_text(wrapped_para, tier=None, channel=ch)
            self.assertFalse(rep_wrap.passed, f"Channel {ch} failed to reject mid-paragraph hard wrap!")
            self.assertEqual(rep_wrap.hard_wrapped_prose_lines, 2)
            self.assertTrue(any(expected_msg in iss for iss in rep_wrap.issues), f"Issues: {rep_wrap.issues}")

        # 15b: Multi-line hard-wrapped bullet item fails
        wrapped_bullet = BASE_CLEAN_GHSA_TIER_S.replace(
            "- **Affected Versions:** `v7.69.0 .. v8.3.0` (verified on `master` at `4a4b63daaa12`)",
            "- **Affected Versions:** `v7.69.0 .. v8.3.0`\n  (verified on `master` at `4a4b63daaa12`)",
        )
        rep_bullet = self._lint_text(wrapped_bullet, tier="S", channel="ghsa")
        self.assertFalse(rep_bullet.passed)
        self.assertEqual(rep_bullet.hard_wrapped_prose_lines, 1)
        self.assertTrue(any(expected_msg in iss for iss in rep_bullet.issues))

        # 15c: Separate bullets, pipe tables, fenced blocks, and separate blockquotes pass with 0 hard wraps
        clean_structures = (
            BASE_CLEAN_GHSA_TIER_S
            + "\n| Build | Status |\n| :--- | :--- |\n| `-O2` | Affected |\n| Stock CLI | Unaffected |\n\n"
            + "> Note: upstream `7.68.x` predates the state machine refactor.\n\n"
            + "> Note: backports apply cleanly to `8.3.x`.\n"
        )
        rep_struct = self._lint_text(clean_structures, tier="S", channel="customer")
        self.assertEqual(rep_struct.hard_wrapped_prose_lines, 0)
        self.assertTrue(rep_struct.passed, f"Unexpected issues on valid structures: {rep_struct.issues}")

        # 15d: 72-column hard-wrapped plain text in `--channel mailing-list` is NOT flagged
        mailing_wrapped = (
            "Subject: [SECURITY] socks: overflow in do_SOCKS()\n\n"
            "In libcurl v8.3.0 (4a4b63daaa12), do_SOCKS() in lib/socks.c:942\n"
            "copies an overlong hostname into the negotiation buffer during\n"
            "local fallback, overflowing the heap allocation.\n\n"
            "Analysis\n"
            "--------\n"
            "do_SOCKS() skips the 255-byte hostname check during local fallback,\n"
            "unlike Curl_socks4a().\n\n"
            "PoC\n"
            "---\n"
            "    #!/bin/sh\n"
            "    mktemp -d\n\n"
            "Impact\n"
            "------\n"
            "Clients with small buffers suffer a heap buffer overflow.\n\n"
            "Suggested Fix\n"
            "-------------\n"
            "Reject hostnames above 255 bytes before local resolution.\n\n"
            "Workarounds\n"
            "-----------\n"
            "Keep CURLOPT_BUFFERSIZE at or above 65541 bytes.\n"
        )
        rep_ml = self._lint_text(mailing_wrapped, suffix=".txt", tier=None, channel="mailing-list")
        self.assertEqual(rep_ml.hard_wrapped_prose_lines, 0)
        self.assertTrue(rep_ml.passed, f"Mailing-list 72-col prose wrongly flagged: {rep_ml.issues}")

        # 15e: Skill docs themselves contain zero mid-paragraph or mid-bullet hard line breaks
        for rel_doc in ("SKILL.md", "references/channel-formats-and-rubric.md"):
            doc_path = SKILL_ROOT / rel_doc
            self.assertTrue(doc_path.is_file(), f"Missing skill doc: {doc_path}")
            raw_doc_lines = doc_path.read_text(encoding="utf-8").splitlines()
            wraps = linter._detect_markdown_hard_wrapped_prose(raw_doc_lines, False)
            self.assertEqual(wraps, [], f"{rel_doc} contains hard-wrapped prose at lines {wraps}")

    def test_16_missing_required_sections_such_as_impact_or_workarounds_fails(self) -> None:
        """Rule #16a: Omitting required sections (Impact, Workarounds, etc.) fails closed across all channels."""
        # 16a: Old buggy 4-section GHSA omitting ### Impact and ### Workarounds MUST fail!
        old_4sec_ghsa = BASE_CLEAN_GHSA_TIER_S.split("### Impact")[0] + (
            "### Suggested Fix\n\n"
            "Reject hostnames longer than 255 bytes before falling back, matching `Curl_socks4a()`.\n\n"
            "```diff\n--- a/lib/socks.c\n+++ b/lib/socks.c\n@@ -940,3 +940,5 @@\n+  return CURLE_PROXY;\n```\n"
        )
        rep_ghsa = self._lint_text(old_4sec_ghsa, tier="S", channel="ghsa")
        self.assertFalse(rep_ghsa.passed)
        self.assertEqual(rep_ghsa.missing_sections, ["### Impact", "### Workarounds"])
        self.assertTrue(any("### Impact" in iss and "### Workarounds" in iss for iss in rep_ghsa.issues))

        # 16b: HackerOne (`h1`) valid 6-section passes; omitting ### Impact or ### Steps To Reproduce fails
        valid_h1 = BASE_CLEAN_GHSA_TIER_S.replace("### PoC", "### Steps To Reproduce")
        rep_h1_ok = self._lint_text(valid_h1, tier="S", channel="h1")
        self.assertTrue(rep_h1_ok.passed, f"Valid H1 failed: {rep_h1_ok.issues}")
        self.assertEqual(rep_h1_ok.warnings, [], f"Valid H1 warnings: {rep_h1_ok.warnings}")

        bad_h1 = valid_h1.split("### Impact")[0] + "### Suggested Fix\n\nApply the guard.\n\n### Workarounds\n\nNone.\n"
        rep_h1_bad = self._lint_text(bad_h1, tier="S", channel="h1")
        self.assertFalse(rep_h1_bad.passed)
        self.assertEqual(rep_h1_bad.missing_sections, ["### Impact"])

        # 16c: Immunefi omitting ### Impact fails
        bad_imm = (
            "# Router: slippage bypass in `rebalance()`\n\n"
            "### Quantified Summary & Activation Status\n\n"
            "At block `21000000`, `VaultRouter.rebalance()` (`VaultRouter.sol:212`) passes `0` slippage, exposing `412,800 USDC`.\n\n"
            "### Trust Boundary & Broken Invariant\n\n"
            "`rebalance()` omits `minAmountOut`.\n\n"
            "### State Walkthrough\n\n"
            "1. Caller sandwiches `rebalance()`.\n\n"
            "### PoC\n\n"
            "```sh\nforge test -vv\n```\n\n"
            "### Remediation\n\n"
            "Pass `minOut`.\n"
        )
        rep_imm_bad = self._lint_text(bad_imm, tier="M", channel="immunefi")
        self.assertFalse(rep_imm_bad.passed)
        self.assertEqual(rep_imm_bad.missing_sections, ["### Impact"])

        # 16d: Standalone mailing-list omitting Impact/Workarounds fails, whereas git format-patch & cover-letter pass
        bad_ml = (
            "Subject: [SECURITY] socks: overflow in do_SOCKS()\n\n"
            "In libcurl v8.3.0 (4a4b63daaa12), do_SOCKS() in lib/socks.c:942\n"
            "overflows a heap buffer on local fallback.\n\n"
            "Analysis\n--------\ndo_SOCKS() skips the 255-byte check.\n\n"
            "PoC\n---\n    #!/bin/sh\n    mktemp -d\n\n"
            "Suggested Fix\n-------------\nReject names over 255 bytes.\n"
        )
        rep_ml_bad = self._lint_text(bad_ml, suffix=".txt", tier="S", channel="mailing-list")
        self.assertFalse(rep_ml_bad.passed)
        self.assertEqual(rep_ml_bad.missing_sections, ["Impact", "Workarounds"])

        format_patch_commit = (
            "From 0123456789abcdef0123456789abcdef01234567 Mon Sep 17 00:00:00 2001\n"
            "From: Researcher Name <security@ajar.com>\n"
            "Date: Mon, 24 Nov 2026 01:00:00 +0000\n"
            "Subject: [PATCH 1/2] socks: check hostname length before local fallback\n\n"
            "In libcurl v8.3.0 (4a4b63daaa12), do_SOCKS() in lib/socks.c:942 skips\n"
            "the 255-byte hostname bound when falling back to local DNS resolution.\n\n"
            "Introduced in commit 31882f9100ab (\"socks: state machine\", 2020-02-11),\n"
            "parse_socks_state() shrinks the handshake buffer when --limit-rate caps\n"
            "CURLOPT_BUFFERSIZE below 65541 bytes, steering do_SOCKS() into the local\n"
            "resolver path without re-checking hostname_len. Curl_socks4a() already\n"
            "enforces the 255-byte ceiling upfront. Stock CLI runs with default\n"
            "100 KiB buffers are unaffected. Reject overlong hostnames before\n"
            "entering the local resolver fallback and add regression test728.\n"
            "Suites test700 through test728 pass under AddressSanitizer.\n\n"
            "Signed-off-by: Researcher Name <security@ajar.com>\n"
            "---\n"
            " lib/socks.c | 2 ++\n"
            " 1 file changed, 2 insertions(+)\n\n"
            "diff --git a/lib/socks.c b/lib/socks.c\n"
            "--- a/lib/socks.c\n"
            "+++ b/lib/socks.c\n"
            "@@ -940,3 +940,5 @@\n"
            "+  if(hostname_len > 255) return CURLE_PROXY;\n"
        )
        rep_patch = self._lint_text(format_patch_commit, suffix=".patch", tier="S", channel="mailing-list")
        self.assertTrue(rep_patch.passed, f"git format-patch commit failed: {rep_patch.issues}")
        self.assertEqual(rep_patch.warnings, [], f"git format-patch commit warnings: {rep_patch.warnings}")
        self.assertEqual(rep_patch.missing_sections, [])

        cover_letter = (
            "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
            "Subject: [PATCH 0/2] socks: tighten hostname bounds on local fallback\n\n"
            "In libcurl v8.3.0 (4a4b63daaa12), do_SOCKS() in lib/socks.c:942 omits\n"
            "the 255-byte check on local resolution fallback. Patch 1 adds the\n"
            "missing guard and Patch 2 adds regression coverage.\n"
        )
        rep_cover = self._lint_text(
            cover_letter, suffix=".txt", tier=None, channel="mailing-list", filename="0000-cover-letter.txt"
        )
        self.assertTrue(rep_cover.passed, f"Cover letter failed: {rep_cover.issues}")

        # 16e: Customer S, low, and audit findings omitting Impact all fail closed
        bad_cust_low = (
            "## Missing zero-address check in `setTreasury()`\n\n"
            "### Description\n\n"
            "In `Vault.sol:88` (`a1b2c3d4`), `setTreasury()` accepts `address(0)` from governance.\n\n"
            "### Recommendation\n\n"
            "Revert on `address(0)`.\n"
        )
        rep_cust_low = self._lint_text(bad_cust_low, tier="low", channel="customer")
        self.assertFalse(rep_cust_low.passed)
        self.assertEqual(rep_cust_low.missing_sections, ["### Impact"])

        bad_cust_audit = (
            "# Security Review Report: acme-http\n\n"
            "## Summary\n\n"
            "Review of `acme-http` at `a1b2c3d4` confirmed 1 finding in `src/acme_parser.c:4`.\n\n"
            "## Confirmed Findings\n\n"
            "### 1. [MEDIUM] Negative chunk length in `parse_chunk_length()`\n\n"
            "#### Root Cause\n\n"
            "`parse_chunk_length()` skips negative checks.\n\n"
            "#### Reproduction\n\n"
            "```sh\n#!/bin/sh\nmktemp -d\n```\n\n"
            "#### Suggested Fix\n\n"
            "Reject `raw_len < 0`.\n\n"
            "## Scope and Inspected Controls\n\n"
            "Covered 2 entrypoints at `a1b2c3d4`.\n"
        )
        rep_cust_audit = self._lint_text(bad_cust_audit, tier="audit", channel="customer")
        self.assertFalse(rep_cust_audit.passed)
        self.assertEqual(rep_cust_audit.missing_sections, ["#### Impact"])

    def test_17_renamed_poc_or_out_of_order_sections_fails_and_missing_patched_versions_fails(self) -> None:
        """Rule #16b: Renaming ### PoC to ### Verification, swapping Workarounds before Suggested Fix, or omitting Patched Versions fails."""
        # 17a: Renaming ### PoC -> ### Verification on GHSA fails and names both ### PoC and ### Verification
        renamed_poc = BASE_CLEAN_GHSA_TIER_S.replace("### PoC", "### Verification")
        rep_renamed = self._lint_text(renamed_poc, tier="S", channel="ghsa")
        self.assertFalse(rep_renamed.passed)
        self.assertEqual(rep_renamed.missing_sections, ["### PoC"])
        self.assertTrue(
            any("### PoC" in iss and "### Verification" in iss for iss in rep_renamed.issues),
            f"Expected alias diagnostic in issues: {rep_renamed.issues}",
        )

        # 17b: Placing ### Workarounds BEFORE ### Suggested Fix fails with exact out-of-order diagnostic
        before_fix, fix_and_after = BASE_CLEAN_GHSA_TIER_S.split("### Suggested Fix\n\n", 1)
        fix_chunk, workarounds_chunk = fix_and_after.split("### Workarounds\n\n", 1)
        workarounds_body, trailer = workarounds_chunk.split("\n\nReported-by:", 1)
        swapped_order = (
            before_fix
            + "### Workarounds\n\n"
            + workarounds_body
            + "\n\n### Suggested Fix\n\n"
            + fix_chunk
            + "Reported-by:"
            + trailer
        )
        with tempfile.TemporaryDirectory() as td:
            p_swap = pathlib.Path(td) / "swapped.md"
            p_swap.write_text(swapped_order, encoding="utf-8")
            proc_swap = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "report_voice_lint.py"),
                    str(p_swap),
                    "--tier",
                    "S",
                    "--channel",
                    "ghsa",
                    "--strict",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc_swap.returncode, 1, proc_swap.stdout + proc_swap.stderr)
            rep_swap = linter.lint_file(p_swap, tier="S", channel="ghsa")
            self.assertFalse(rep_swap.passed)
            self.assertEqual(rep_swap.missing_sections, [])
            self.assertEqual(rep_swap.out_of_order_sections, ["### Workarounds", "### Suggested Fix"])
            self.assertTrue(
                any("'### Workarounds' appears before '### Suggested Fix'" in iss for iss in rep_swap.issues),
                f"Unexpected order error: {rep_swap.issues}",
            )

        # 17c: Omitting Patched Versions when top GHSA metadata bullets are present MUST fail (exit 1)
        no_patched = "\n".join(
            ln for ln in BASE_CLEAN_GHSA_TIER_S.splitlines() if not ln.startswith("- **Patched Versions:**")
        ) + "\n"
        rep_no_patched = self._lint_text(no_patched, tier="S", channel="ghsa")
        self.assertFalse(rep_no_patched.passed)
        self.assertTrue(
            any("Patched Versions" in iss for iss in rep_no_patched.issues),
            f"Missing Patched Versions not reported: {rep_no_patched.issues}",
        )

        # Omitting Affected Versions when top GHSA metadata bullets are present also fails
        no_affected = "\n".join(
            ln for ln in BASE_CLEAN_GHSA_TIER_S.splitlines() if not ln.startswith("- **Affected Versions:**")
        ) + "\n"
        rep_no_affected = self._lint_text(no_affected, tier="S", channel="ghsa")
        self.assertFalse(rep_no_affected.passed)
        self.assertTrue(any("Affected Versions" in iss for iss in rep_no_affected.issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
