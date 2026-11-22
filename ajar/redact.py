"""Deterministic secret redaction and subprocess environment scrubbing.

Scrubs authentication headers, cookies, JWTs, PEM/hex private keys, cloud and API
tokens, signed URLs, and RPC endpoint keys before any text or binary artifact is
stored in `run.db` or `artifacts/`.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Any, Mapping

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
        "CCACHE_DIR",
        "CCACHE_BASEDIR",
        "CCACHE_NOHASHDIR",
        "CCACHE_COMPILERCHECK",
        "SCCACHE_DIR",
        "SCCACHE_SERVER_UDS",
        "RUSTC_WRAPPER",
        "CMAKE_C_COMPILER_LAUNCHER",
        "CMAKE_CXX_COMPILER_LAUNCHER",
        "SDKROOT",
        "DEVELOPER_DIR",
        "MACOSX_DEPLOYMENT_TARGET",
        "PKG_CONFIG_PATH",
        "CPATH",
        "C_INCLUDE_PATH",
        "CPLUS_INCLUDE_PATH",
        "LIBRARY_PATH",
        "AJAR_RUN_DIR",
        "AJAR_RUN_ID",
    }
)

_DARWIN_SDKROOT_CACHE: str | None = None


def _resolve_darwin_sdkroot() -> str:
    """Resolve macOS SDK path once via xcrun when raw clang is invoked without SDKROOT."""
    global _DARWIN_SDKROOT_CACHE
    if _DARWIN_SDKROOT_CACHE is not None:
        return _DARWIN_SDKROOT_CACHE
    import subprocess
    import sys

    if sys.platform != "darwin":
        _DARWIN_SDKROOT_CACHE = ""
        return ""
    try:
        cp = subprocess.run(
            ["/usr/bin/xcrun", "--show-sdk-path"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        sdk = cp.stdout.strip() if cp.returncode == 0 else ""
        _DARWIN_SDKROOT_CACHE = sdk if (sdk and pathlib.Path(sdk).is_dir()) else ""
    except OSError:
        _DARWIN_SDKROOT_CACHE = ""
    return _DARWIN_SDKROOT_CACHE


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


def scrub_json_value(value: Any, extra_literals: tuple[str, ...] = ()) -> Any:
    """Recursively scrub strings inside a JSON-serializable Python structure without touching JSON delimiters."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return scrub_text(value, extra_literals=extra_literals)
    if isinstance(value, Mapping):
        return {
            scrub_text(str(k), extra_literals=extra_literals): scrub_json_value(v, extra_literals=extra_literals)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [scrub_json_value(item, extra_literals=extra_literals) for item in value]
    return scrub_text(str(value), extra_literals=extra_literals)


def _sanitize_path_entries(existing_path: str) -> str:
    kept: list[str] = []
    for part in existing_path.split(os.pathsep):
        if not part:
            continue
        p = pathlib.Path(part)
        if p.is_symlink() and not p.exists():
            continue
        kept.append(part)
    return os.pathsep.join(kept) if kept else "/usr/local/bin:/usr/bin:/bin"


def _prepend_path_dirs(existing_path: str, extra_dirs: list[pathlib.Path]) -> str:
    parts = [p for p in _sanitize_path_entries(existing_path).split(os.pathsep) if p]
    seen = set(parts)
    prefix: list[str] = []
    for d in extra_dirs:
        s = str(d)
        if s and s not in seen and d.is_dir():
            prefix.append(s)
            seen.add(s)
    return os.pathsep.join(prefix + parts) if (prefix or parts) else "/usr/local/bin:/usr/bin:/bin"


def _resolve_rustup_toolchain_bin(rhome: pathlib.Path, preferred_tc: str = "") -> tuple[str, pathlib.Path | None]:
    settings = rhome / "settings.toml"
    tdir = rhome / "toolchains"
    resolved_tc = preferred_tc.strip()
    if not resolved_tc and settings.is_file():
        m = re.search(
            r'^\s*default_toolchain\s*=\s*"([^"]+)"',
            settings.read_text(encoding="utf-8", errors="ignore"),
            re.MULTILINE,
        )
        if m:
            resolved_tc = m.group(1).strip()
    if resolved_tc and (tdir / resolved_tc).is_dir():
        bin_dir = tdir / resolved_tc / "bin"
        return resolved_tc, (bin_dir if bin_dir.is_dir() else None)
    if tdir.is_dir():
        tchains = sorted(d.name for d in tdir.iterdir() if d.is_dir())
        if tchains:
            stable = [n for n in tchains if n.startswith("stable")]
            picked = stable[0] if stable else tchains[0]
            bin_dir = tdir / picked / "bin"
            return picked, (bin_dir if bin_dir.is_dir() else None)
    return "", None


def _preserve_rust_toolchain_env(
    src: Mapping[str, str],
    clean: dict[str, str],
    isolated_home: pathlib.Path | None,
) -> None:
    """Keep `rustup`/`cargo` working offline when `HOME` is isolated, without exposing `credentials.toml`."""
    caller_home = src.get("HOME", "").strip()
    extra_bins: list[pathlib.Path] = []
    home_rustup = (pathlib.Path(caller_home) / ".rustup") if caller_home else None

    candidates: list[pathlib.Path] = []
    if "RUSTUP_HOME" in clean:
        candidates.append(pathlib.Path(clean["RUSTUP_HOME"]))
    if home_rustup is not None:
        candidates.append(home_rustup)
    candidates.extend([pathlib.Path("/usr/local/rustup"), pathlib.Path("/usr/share/rust/.rustup")])

    seen_rhomes: set[str] = set()
    preferred_tc = clean.get("RUSTUP_TOOLCHAIN", "").strip()
    for cand in candidates:
        cand_str = str(cand)
        if cand_str in seen_rhomes or not cand.is_dir():
            continue
        seen_rhomes.add(cand_str)
        settings = cand / "settings.toml"
        tdir = cand / "toolchains"
        has_tchain = tdir.is_dir() and any(d.is_dir() for d in tdir.iterdir())
        has_default = settings.is_file() and "default_toolchain" in settings.read_text(
            encoding="utf-8", errors="ignore"
        )
        if has_tchain or has_default:
            if "RUSTUP_HOME" not in clean:
                clean["RUSTUP_HOME"] = cand_str
        tc_name, tc_bin = _resolve_rustup_toolchain_bin(cand, preferred_tc)
        if tc_name and not clean.get("RUSTUP_TOOLCHAIN"):
            clean["RUSTUP_TOOLCHAIN"] = tc_name
        if tc_bin is not None:
            extra_bins.append(tc_bin)
            if cand == home_rustup and "RUSTUP_HOME" not in src:
                clean["RUSTUP_HOME"] = cand_str

    if "CARGO_HOME" in clean:
        cbin = pathlib.Path(clean["CARGO_HOME"]) / "bin"
        if cbin.is_dir():
            extra_bins.append(cbin)
    elif caller_home:
        src_cargo = pathlib.Path(caller_home) / ".cargo"
        if src_cargo.is_dir():
            home_cargo_bin: pathlib.Path | None = None
            if isolated_home is not None:
                iso_cargo = isolated_home / ".cargo"
                iso_cargo.mkdir(parents=True, exist_ok=True)
                for sub in ("bin", "registry", "git"):
                    target_sub = src_cargo / sub
                    link_sub = iso_cargo / sub
                    if link_sub.is_symlink() and not link_sub.exists():
                        link_sub.unlink(missing_ok=True)
                    if target_sub.is_dir() and not link_sub.exists():
                        try:
                            link_sub.symlink_to(target_sub.resolve())
                        except OSError:
                            pass
                if (iso_cargo / "bin").is_dir():
                    home_cargo_bin = iso_cargo / "bin"
            if home_cargo_bin is None and (src_cargo / "bin").is_dir():
                home_cargo_bin = src_cargo / "bin"
            if home_cargo_bin is not None:
                extra_bins.append(home_cargo_bin)

    if extra_bins or "RUSTUP_HOME" in clean or "CARGO_HOME" in clean:
        clean["PATH"] = _prepend_path_dirs(clean.get("PATH", "/usr/local/bin:/usr/bin:/bin"), extra_bins)
        clean.setdefault("CARGO_NET_OFFLINE", "true")


def scrubbed_subprocess_env(
    *,
    base_env: Mapping[str, str] | None = None,
    overrides: Mapping[str, str] | None = None,
    tmp_dir: os.PathLike[str] | str | None = None,
    run_dir: os.PathLike[str] | str | None = None,
) -> dict[str, str]:
    """Build a clean subprocess environment stripped of ambient host credentials."""
    src = os.environ if base_env is None else base_env
    clean: dict[str, str] = {}
    for key in SAFE_SUBPROCESS_ENV_KEYS:
        if key in src:
            clean[key] = src[key]
    clean["PATH"] = _sanitize_path_entries(clean.get("PATH", "/usr/local/bin:/usr/bin:/bin"))
    clean.setdefault("LANG", "C.UTF-8")
    clean["PAGER"] = "cat"
    clean["GIT_TERMINAL_PROMPT"] = "0"
    if not clean.get("SDKROOT"):
        sdk = _resolve_darwin_sdkroot()
        if sdk:
            clean["SDKROOT"] = sdk
    if run_dir is not None:
        rpath = pathlib.Path(run_dir).resolve()
        clean.setdefault("AJAR_RUN_DIR", str(rpath))
        clean.setdefault("AJAR_ARTIFACTS_DIR", str(rpath / "artifacts"))
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
