"""Unit and integration tests for Weeks 1–2 Hunt Bottlenecks (B1–B5) and `ajar-platform-graph/2`."""

from __future__ import annotations

import pathlib
import sqlite3
import tempfile
import unittest

from ajar.repomap import REPOMAP_EDGE_CAP, _extract_regex_symbols, build_repomap


class TestRepomapB1(unittest.TestCase):
    def test_edge_cap_sorts_by_weight_desc_and_preserves_z_subsystem(self) -> None:
        self.assertEqual(REPOMAP_EDGE_CAP, 25_000)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            # Create many low-weight edges in `a_*` files referencing a shared symbol defined in 9 files (IDF = 1/3).
            for idx in range(9):
                (root / f"a_def_{idx:02d}.py").write_text("def shared_helper():\n    return 1\n", encoding="utf-8")
            for idx in range(15):
                (root / f"a_caller_{idx:02d}.py").write_text(
                    f"def a_fn_{idx:02d}():\n    return shared_helper()\n",
                    encoding="utf-8",
                )

            # High-weight `z_*` edge referencing 3 unique symbols (summed IDF = 3.0).
            (root / "z_sink.py").write_text(
                "def z_critical_alpha():\n    return 1\n"
                "def z_critical_beta():\n    return 2\n"
                "def z_critical_gamma():\n    return 3\n",
                encoding="utf-8",
            )
            (root / "z_caller.py").write_text(
                "def z_entry():\n"
                "    return z_critical_alpha() + z_critical_beta() + z_critical_gamma()\n",
                encoding="utf-8",
            )

            conn = sqlite3.connect(":memory:", isolation_level=None)
            conn.row_factory = sqlite3.Row
            try:
                res = build_repomap(conn, root, max_edges=10)
                self.assertEqual(res["edges_indexed"], 10)
                self.assertGreater(res["edges_total"], 10)

                rows = conn.execute(
                    "SELECT src_file, dst_file, symbol, weight FROM repomap_edges"
                ).fetchall()
                self.assertEqual(len(rows), 10)

                # Highest-weight `z_caller.py -> z_sink.py` edge must survive capping and appear first!
                self.assertEqual(rows[0]["src_file"], "z_caller.py")
                self.assertEqual(rows[0]["dst_file"], "z_sink.py")
                self.assertAlmostEqual(float(rows[0]["weight"]), 3.0, places=3)
                self.assertEqual(rows[0]["symbol"], "z_critical_alpha")

                # Edges must be deduplicated per (src_file, dst_file) and strictly sorted by (-weight, src, dst).
                pairs = [(str(r["src_file"]), str(r["dst_file"])) for r in rows]
                self.assertEqual(len(pairs), len(set(pairs)))
                sort_keys = [(-float(r["weight"]), str(r["src_file"]), str(r["dst_file"])) for r in rows]
                self.assertEqual(sort_keys, sorted(sort_keys))
            finally:
                conn.close()

    def test_multiline_c_cpp_and_new_language_symbol_extraction(self) -> None:
        c_src = """\
extern int
forward_proto(int a,
              int b);

static const char *
internal_helper(const char *buf,
                size_t len)
{
    return buf;
}

const struct node *
resolve_entry(struct table *t,
              int idx)
{
    return 0;
}
"""
        c_syms = _extract_regex_symbols("src/parser.c", ".c", c_src)
        by_name = {str(s["name"]): s for s in c_syms}
        self.assertNotIn("forward_proto", by_name)
        self.assertIn("internal_helper", by_name)
        self.assertTrue(by_name["internal_helper"]["file_local"])
        self.assertIn("resolve_entry", by_name)
        self.assertFalse(by_name["resolve_entry"]["file_local"])

        cpp_src = """\
class FrameDecoder : public BaseDecoder {
public:
    int run();
};

std::string
FrameDecoder::decode_payload(const uint8_t *data,
                             size_t len)
{
    return "";
}
"""
        cpp_syms = _extract_regex_symbols("src/decoder.cpp", ".cpp", cpp_src)
        cpp_names = {str(s["name"]) for s in cpp_syms}
        self.assertIn("FrameDecoder", cpp_names)
        self.assertIn("decode_payload", cpp_names)

        java_src = """\
public final class TokenVerifier {
    public static boolean verifySignature(byte[] sig) {
        return true;
    }
}
"""
        java_names = {str(s["name"]) for s in _extract_regex_symbols("TokenVerifier.java", ".java", java_src)}
        self.assertEqual(java_names, {"TokenVerifier", "verifySignature"})

        php_src = """\
<?php
final class SessionGuard {
    public static function checkSession($tok) {
        return true;
    }
}
function parse_cookie($raw) {
    return $raw;
}
"""
        php_names = {str(s["name"]) for s in _extract_regex_symbols("guard.php", ".php", php_src)}
        self.assertEqual(php_names, {"SessionGuard", "checkSession", "parse_cookie"})

        move_src = """\
module vault::treasury {
    public struct VaultCap has key {}
    public entry fun withdraw_funds(amount: u64) {}
}
"""
        move_names = {str(s["name"]) for s in _extract_regex_symbols("treasury.move", ".move", move_src)}
        self.assertEqual(move_names, {"treasury", "VaultCap", "withdraw_funds"})

        zig_src = """\
pub const FrameHeader = packed struct {
    len: u32,
};
pub export fn parseHeader(buf: []const u8) !FrameHeader {
    return undefined;
}
"""
        zig_names = {str(s["name"]) for s in _extract_regex_symbols("frame.zig", ".zig", zig_src)}
        self.assertEqual(zig_names, {"FrameHeader", "parseHeader"})


if __name__ == "__main__":
    unittest.main()
