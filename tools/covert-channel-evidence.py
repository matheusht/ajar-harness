#!/usr/bin/env python3
"""Covert-channel decode-evidence scanner — E-track E3 (defensive / evidence side, hermetic core).

The defensive mirror of E1/E2/E3: given RAW captured flow text (ephemeral, pre-redaction, inside the
Tollbooth boundary), detect hidden/covert/encoded channels and surface a SANITIZED evidence signal —
which channel was present, and whether decoding surfaces an EXPECTED BENIGN canary. It emits NO raw
content and NO secrets; only the channel type + a boolean. It is a SENSOR, never a judge (no verdict
key); the oracle/broker adjudicate.

This is the hermetic core of "E3 Tollbooth decode evidence". Only the live traffic SOURCE (the
operator-gated Tollbooth container) is external; here it is exercised with synthetic flows. Richer
covert decoding (GLOSSOPETRAE conlang/glyph) would attach arms-length later. Decoders are reused from
the harness's own stdlib converters.

Usage:
  python3 tools/covert-channel-evidence.py --self-test
  python3 tools/covert-channel-evidence.py --flows raw_flows.json --expect-canary benign-preamble-canary
    (flat hermetic shape or native Tollbooth traffic export)
"""

import argparse
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(modname, filename):
    path = os.path.join(ROOT, "tools", filename)
    spec = importlib.util.spec_from_file_location(modname, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_obf = _load("_obf", "obfuscation-converter.py")
_cov = _load("_cov", "covert-channel-converter.py")
_steg = _load("_steg", "stego-converter.py")

ZW_CHARS = {"​", "‌", "‍", "﻿"}
B64_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
FORBIDDEN_KEYS = ("verdict", "confirmed", "allow", "authorizes")


def detect_channels(text):
    ch = []
    if any(c in ZW_CHARS for c in text):
        ch.append("zero-width")
    if any(c in _cov._HOMO_INV for c in text):
        ch.append("homoglyph")
    if any(c in _cov._SCRIPT_INV for c in text):
        ch.append("constructed-script")
    for m in B64_RE.findall(text):
        try:
            if _obf.decode("base64", m).isprintable():
                ch.append("base64-likely")
                break
        except Exception:
            pass
    return ch


def _decode_candidates(text):
    cands = [text]
    try:
        cands.append(_steg.extract(text))
    except Exception:
        pass
    for name in ("homoglyph", "token-break", "constructed-script"):
        try:
            cands.append(_cov.decode(name, text))
        except Exception:
            pass
    for name in ("base64", "base32", "hex", "rot13"):
        try:
            cands.append(_obf.decode(name, text))
        except Exception:
            pass
    for m in B64_RE.findall(text):
        try:
            cands.append(_obf.decode("base64", m))
        except Exception:
            pass
    return cands


def scan_flow(flow, expect_canary, flow_index):
    """Return a SANITIZED evidence record for one raw flow — no raw text, no secrets."""
    if not isinstance(flow, dict):
        raise ValueError("flow must be a JSON object")
    text = flow.get("text", "")
    if not isinstance(text, str):
        raise ValueError("flow text must be a string")
    decoded_present = any(expect_canary in c for c in _decode_candidates(text)) if expect_canary else None
    return {
        "kind": "covert_evidence",       # sensor signal, NON-authoritative
        "authoritative": False,
        "flow_ref": f"flow-{flow_index}",  # Positional; never copy a caller-supplied reference.
        "channels_detected": detect_channels(text),
        "decoded_expected_canary_present": decoded_present,
    }


def scan(flows, expect_canary):
    return [scan_flow(flow, expect_canary, index) for index, flow in enumerate(flows)]


def normalize_flow_export(export):
    """Accept flat hermetic flows and native Tollbooth traffic without retaining raw metadata."""
    if not isinstance(export, dict):
        raise ValueError("flow export must be a JSON object")
    if "traffic" not in export:
        flows = export.get("flows", [])
        if not isinstance(flows, list):
            raise ValueError("flows must be a JSON array")
        return flows
    traffic = export["traffic"]
    if not isinstance(traffic, list):
        raise ValueError("traffic must be a JSON array")
    flows = []
    for flow in traffic:
        if not isinstance(flow, dict):
            raise ValueError("traffic entries must be JSON objects")
        contents = []
        for direction in ("request", "response"):
            section = flow.get(direction)
            if section is None:
                continue
            if not isinstance(section, dict):
                raise ValueError(f"{direction} must be a JSON object")
            content = section.get("content")
            if content is not None:
                contents.append(
                    content if isinstance(content, str)
                    else json.dumps(content, sort_keys=True, ensure_ascii=False)
                )
        flows.append({"text": "\n".join(contents)})
    return flows


def _golden_flows(canary):
    return [
        {"text": _cov.encode("homoglyph", f"see {canary}")},
        {"text": _steg.embed("an ordinary carrier", canary)},
        {"text": _obf.encode("base64", f"see {canary}")},
        {"text": "ordinary clean text nothing hidden here at all"},
    ]


def self_test():
    canary = "benign-preamble-canary"
    results = scan(_golden_flows(canary), canary)
    by = {r["flow_ref"]: r for r in results}
    checks = [
        ("homoglyph flow detected + decoded", "homoglyph" in by["flow-0"]["channels_detected"]
         and by["flow-0"]["decoded_expected_canary_present"]),
        ("zero-width stego flow detected + decoded", "zero-width" in by["flow-1"]["channels_detected"]
         and by["flow-1"]["decoded_expected_canary_present"]),
        ("base64 flow detected + decoded", "base64-likely" in by["flow-2"]["channels_detected"]
         and by["flow-2"]["decoded_expected_canary_present"]),
        ("clean flow is clean", by["flow-3"]["channels_detected"] == []
         and not by["flow-3"]["decoded_expected_canary_present"]),
    ]
    blob = json.dumps(results)
    sanitized = (canary not in blob                      # no raw decoded payload echoed
                 and "carrier" not in blob               # no raw flow text echoed
                 and not any(k in blob for k in FORBIDDEN_KEYS))
    fails = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    print(f"  {'ok  ' if sanitized else 'FAIL'} evidence is sanitized (no raw text/canary, no judge key)")
    with tempfile.TemporaryDirectory(prefix="covert-flow-fifo-") as temp:
        fifo = os.path.join(temp, "flows.json")
        os.mkfifo(fifo)
        try:
            result = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--flows", fifo],
                capture_output=True, text=True, timeout=2, check=False,
            )
        except subprocess.TimeoutExpired:
            result = None
        fifo_ok = result is not None and result.returncode == 2 and "regular file" in result.stderr
        print(f"  {'ok  ' if fifo_ok else 'FAIL'} FIFO input is rejected promptly")
        if not fifo_ok:
            fails.append("FIFO input blocks or is not rejected")
    with tempfile.TemporaryDirectory(prefix="covert-flow-ref-") as temp:
        path = os.path.join(temp, "flows.json")
        secret_ref = "Authorization: Bearer sk_test-do-not-emit"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"flows": [{"ref": secret_ref, "text": "ordinary clean text"}]}, fh)
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--flows", path],
            capture_output=True, text=True, timeout=3, check=False,
        )
        output = json.loads(result.stdout) if result.returncode == 0 else []
        ref_ok = output == [{
            "kind": "covert_evidence", "authoritative": False, "flow_ref": "flow-0",
            "channels_detected": [], "decoded_expected_canary_present": None,
        }]
        no_secret = secret_ref not in result.stdout
        print(f"  {'ok  ' if ref_ok and no_secret else 'FAIL'} output reference is positional and contains no raw ref")
        if not (ref_ok and no_secret):
            fails.append("raw flow reference escaped into sanitized output")
    with tempfile.TemporaryDirectory(prefix="covert-native-flow-") as temp:
        path = os.path.join(temp, "traffic.json")
        encoded = _obf.encode("base64", f"see {canary}")
        native = {"total": 1, "traffic": [{
            "flow_id": "raw-secret-flow-id", "is_llm_api": True,
            "request": {"content": encoded, "headers": {"Authorization": "Bearer fake-secret"}},
            "response": {"content": "ok"},
        }]}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(native, fh)
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--flows", path, "--expect-canary", canary],
            capture_output=True, text=True, timeout=3, check=False,
        )
        output = json.loads(result.stdout) if result.returncode == 0 else []
        native_ok = (
            len(output) == 1 and output[0].get("flow_ref") == "flow-0"
            and "base64-likely" in output[0].get("channels_detected", [])
            and output[0].get("decoded_expected_canary_present") is True
            and "raw-secret-flow-id" not in result.stdout and encoded not in result.stdout
            and canary not in result.stdout and "fake-secret" not in result.stdout
        )
        print(f"  {'ok  ' if native_ok else 'FAIL'} native Tollbooth export is decoded without echoing raw fields")
        if not native_ok:
            fails.append("native Tollbooth export was not decoded or raw fields escaped")
    with tempfile.TemporaryDirectory(prefix="covert-invalid-flow-") as temp:
        path = os.path.join(temp, "flows.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"flows": [{"text": 7}]}, fh)
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--flows", path],
            capture_output=True, text=True, timeout=3, check=False,
        )
        invalid_ok = result.returncode == 2 and "flow text must be a string" in result.stderr
        print(f"  {'ok  ' if invalid_ok else 'FAIL'} malformed flow text is rejected cleanly")
        if not invalid_ok:
            fails.append("malformed flow input crashes instead of returning a clean error")
    if fails or not sanitized:
        print("COVERT-CHANNEL-EVIDENCE: FAIL")
        return 1
    print("COVERT-CHANNEL-EVIDENCE: PASS")
    return 0


def main():
    ap = argparse.ArgumentParser(description="covert-channel decode-evidence scanner (E-track E3)")
    ap.add_argument("--flows", help="path to a raw-flows JSON (ephemeral; pre-redaction)")
    ap.add_argument("--expect-canary")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if a.flows:
        try:
            fd = os.open(a.flows, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd) as fh:
                if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                    raise OSError("flow input is not a regular file")
                flows = normalize_flow_export(json.load(fh))
            evidence = scan(flows, a.expect_canary)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"invalid flow input: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(evidence, indent=2))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
