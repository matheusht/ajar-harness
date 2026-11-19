"""Deterministic secret redaction and subprocess environment scrubbing.

Scrubs authentication headers, cookies, JWTs, PEM/hex private keys, cloud and API
tokens, signed URLs, and RPC endpoint keys before any text or binary artifact is
stored in `run.db` or `artifacts/`.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Mapping

REDACTED = "<REDACTED>"
REDACTED_BYTES = b"<REDACTED>"

# Ordered from full multi-line blocks (PEM keys) down to token/header patterns.
_PEM_BEGIN = b"-----BEGIN " + b"(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
_PEM_END = b"-----END " + b"(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"

SECRET_PATTERNS_BYTES: tuple[tuple[str, re.Pattern[bytes], bytes], ...] = (
    (
        "private_key_block",
        re.compile(_PEM_BEGIN + rb"[\s\S]{1,16384}?" + _PEM_END),
        b"<REDACTED_PRIVATE_KEY>",
    ),
    (
        "private_key_header",
        re.compile(_PEM_BEGIN),
        b"<REDACTED_PRIVATE_KEY>",
    ),
    (
        "authorization_header",
        re.compile(
            rb"(authorization\s*[:=]\s*(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=-]{8,}",
            re.IGNORECASE,
        ),
        rb"\1<REDACTED>",
    ),
    (
        "bearer_token",
        re.compile(rb"(\bBearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
        rb"\1<REDACTED>",
    ),
    (
        "cookie_header",
        re.compile(rb"((?:set-cookie|cookie)\s*:\s*)[^\r\n]{8,}", re.IGNORECASE),
        rb"\1<REDACTED>",
    ),
    (
        "jwt",
        re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        REDACTED_BYTES,
    ),
    (
        "signed_url",
        re.compile(
            rb"([?&](?:x-amz-signature|x-amz-credential|x-goog-signature|signature|sig|token)=)"
            rb"[A-Za-z0-9%_~.-]{16,}",
            re.IGNORECASE,
        ),
        rb"\1<REDACTED>",
    ),
    (
        "provider_token",
        re.compile(
            rb"\b(?:"
            rb"gh[pousr]_[A-Za-z0-9]{20,}"
            rb"|github_pat_[A-Za-z0-9_]{22,}"
            rb"|AKIA[A-Z0-9]{16}"
            rb"|ASIA[A-Z0-9]{16}"
            rb"|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}"
            rb"|xox[baprs]-[A-Za-z0-9-]{16,}"
            rb"|AIza[0-9A-Za-z_-]{35}"
            rb")\b"
        ),
        REDACTED_BYTES,
    ),
    (
        "rpc_provider_url",
        re.compile(
            rb"(https?://[A-Za-z0-9.-]*(?:alchemy\.com|infura\.io|quicknode\.pro)/v[23]/)"
            rb"[A-Za-z0-9_-]{16,}",
            re.IGNORECASE,
        ),
        rb"\1<REDACTED>",
    ),
    (
        "hex_private_key_assignment",
        re.compile(
            rb"((?:private_key|priv_key|secret_key|mnemonic_seed)[\"']?\s*[:=]\s*[\"']?)"
            rb"(?:0x)?[0-9a-fA-F]{64}\b",
            re.IGNORECASE,
        ),
        rb"\1<REDACTED>",
    ),
    (
        "password_assignment",
        re.compile(
            rb"((?:password|passwd|pwd|api_key|apikey|client_secret)[\"']?\s*[:=]\s*[\"']?)"
            rb"(?!<REDACTED)(?!os\.environ|process\.env|std::env|getenv\(|os\.Getenv\(|/)[^\s,;\"'()]{8,}",
            re.IGNORECASE,
        ),
        rb"\1<REDACTED>",
    ),
)

SAFE_SUBPROCESS_ENV_KEYS: frozenset[str] = frozenset(
    {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "TZ",
        "USER",
        "LOGNAME",
        "SHELL",
        "CARGO_HOME",
        "RUSTUP_HOME",
        "RUSTUP_TOOLCHAIN",
        "GOPATH",
        "GOMODCACHE",
        "GOROOT",
        "NODE_PATH",
        "CC",
        "CXX",
    }
)


def detect_secret_classes(data: bytes) -> list[str]:
    """Return sorted secret pattern names matched in `data`."""
    found: set[str] = set()
    for name, pattern, _ in SECRET_PATTERNS_BYTES:
        if pattern.search(data):
            key = "private_key" if name.startswith("private_key") else name
            found.add(key)
    return sorted(found)


def scan_file_secret_classes(path: os.PathLike[str] | str) -> list[str]:
    """Scan a potentially large file in 1 MiB windows with 16 KiB overlap."""
    found: set[str] = set()
    overlap = b""
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            sample = overlap + chunk
            found.update(detect_secret_classes(sample))
            overlap = sample[-16384:]
    return sorted(found)


def scrub_bytes(data: bytes, extra_literals: tuple[str, ...] = ()) -> bytes:
    """Replace matched secret material and dynamic credential literals with `<REDACTED>`."""
    out = data
    for literal in extra_literals:
        if literal and len(literal) >= 6:
            out = out.replace(literal.encode("utf-8", errors="ignore"), REDACTED_BYTES)
    for _, pattern, replacement in SECRET_PATTERNS_BYTES:
        out = pattern.sub(replacement, out)
    return out


def scrub_text(text: str, extra_literals: tuple[str, ...] = ()) -> str:
    """Scrub secret patterns from UTF-8 text."""
    if not text:
        return text
    return scrub_bytes(text.encode("utf-8", errors="replace"), extra_literals=extra_literals).decode(
        "utf-8", errors="replace"
    )


def _preserve_rust_toolchain_env(
    src: Mapping[str, str],
    clean: dict[str, str],
    isolated_home: pathlib.Path | None,
) -> None:
    """Keep `rustup`/`cargo` working offline when `HOME` is isolated, without exposing `credentials.toml`."""
    caller_home = src.get("HOME", "").strip()
    if "RUSTUP_HOME" not in clean:
        candidates: list[pathlib.Path] = []
        if caller_home:
            candidates.append(pathlib.Path(caller_home) / ".rustup")
        candidates.extend([pathlib.Path("/usr/local/rustup"), pathlib.Path("/usr/share/rust/.rustup")])
        for cand in candidates:
            if not cand.is_dir():
                continue
            settings = cand / "settings.toml"
            tdir = cand / "toolchains"
            has_tchain = tdir.is_dir() and any(d.is_dir() for d in tdir.iterdir())
            has_default = settings.is_file() and "default_toolchain" in settings.read_text(
                encoding="utf-8", errors="ignore"
            )
            if has_tchain or has_default:
                clean["RUSTUP_HOME"] = str(cand)
                break

    if "RUSTUP_TOOLCHAIN" not in clean and "RUSTUP_HOME" in clean:
        rhome = pathlib.Path(clean["RUSTUP_HOME"])
        settings = rhome / "settings.toml"
        has_default = settings.is_file() and "default_toolchain" in settings.read_text(encoding="utf-8", errors="ignore")
        tdir = rhome / "toolchains"
        if not has_default and tdir.is_dir():
            tchains = sorted(d.name for d in tdir.iterdir() if d.is_dir())
            if tchains:
                stable = [n for n in tchains if n.startswith("stable")]
                clean["RUSTUP_TOOLCHAIN"] = stable[0] if stable else tchains[0]

    if isolated_home is not None and "CARGO_HOME" not in clean and caller_home:
        src_cargo = pathlib.Path(caller_home) / ".cargo"
        if src_cargo.is_dir():
            iso_cargo = isolated_home / ".cargo"
            iso_cargo.mkdir(parents=True, exist_ok=True)
            for sub in ("bin", "registry", "git"):
                target_sub = src_cargo / sub
                link_sub = iso_cargo / sub
                if target_sub.exists() and not link_sub.exists():
                    try:
                        link_sub.symlink_to(target_sub)
                    except OSError:
                        pass


def scrubbed_subprocess_env(
    *,
    base_env: Mapping[str, str] | None = None,
    overrides: Mapping[str, str] | None = None,
    tmp_dir: os.PathLike[str] | str | None = None,
) -> dict[str, str]:
    """Build a clean subprocess environment stripped of ambient host credentials."""
    src = os.environ if base_env is None else base_env
    clean: dict[str, str] = {}
    for key in SAFE_SUBPROCESS_ENV_KEYS:
        if key in src:
            clean[key] = src[key]
    clean.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    clean.setdefault("LANG", "C.UTF-8")
    clean["PAGER"] = "cat"
    clean["GIT_TERMINAL_PROMPT"] = "0"
    iso_home: pathlib.Path | None = None
    if tmp_dir is not None:
        iso_home = pathlib.Path(tmp_dir).resolve()
        t = str(iso_home)
        clean["TMPDIR"] = t
        clean["HOME"] = t
        clean["XDG_CACHE_HOME"] = os.path.join(t, ".cache")
        clean["XDG_CONFIG_HOME"] = os.path.join(t, ".config")
        clean["XDG_DATA_HOME"] = os.path.join(t, ".local", "share")
    _preserve_rust_toolchain_env(src, clean, iso_home)
    if overrides:
        for key, value in overrides.items():
            clean[key] = value
    return clean
