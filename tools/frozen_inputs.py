"""Shared frozen-input hashing used by campaigns and engagement-local artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def sha256_file(path: os.PathLike[str] | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def name_for(path: os.PathLike[str] | str, base: os.PathLike[str] | str = REPOSITORY_ROOT) -> str:
    relative = os.path.relpath(os.fspath(path), os.fspath(base))
    return relative.replace(os.sep, ":").replace(".json", "").replace(".py", "")


def spec_for(path: os.PathLike[str] | str, base: os.PathLike[str] | str) -> dict[str, str]:
    absolute = Path(path).resolve()
    relative = os.path.relpath(absolute, Path(base).resolve()).replace(os.sep, "/")
    return {"path": relative, "sha256": sha256_file(absolute)}


def emit(paths, base: os.PathLike[str] | str = REPOSITORY_ROOT) -> dict[str, dict[str, str]]:
    root = Path(base).resolve()
    block = {}
    for path in paths:
        absolute = Path(path) if os.path.isabs(os.fspath(path)) else root / os.fspath(path)
        block[name_for(absolute, root)] = spec_for(absolute, root)
    return block


def _manifest_base(manifest_path: Path, document: dict) -> Path:
    base_kind = document.get("frozen_inputs_base", "repository")
    if base_kind == "repository":
        return REPOSITORY_ROOT
    if base_kind == "manifest":
        return manifest_path.resolve().parent
    raise ValueError(f"unsupported frozen_inputs_base: {base_kind!r}")


def check_manifest(manifest_path: os.PathLike[str] | str) -> list[str]:
    """Return deterministic drift descriptions; malformed manifests fail closed as drift."""
    path = Path(manifest_path)
    try:
        document = json.loads(path.read_text())
        if not isinstance(document, dict):
            raise TypeError("manifest root must be an object")
        base = _manifest_base(path, document)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        return [f"manifest: unreadable {path}: {error}"]

    frozen = document.get("frozen_inputs")
    if not isinstance(frozen, dict) or not frozen:
        return ["manifest: missing or empty frozen_inputs"]

    drift = []
    for name in sorted(frozen):
        spec = frozen[name]
        if not isinstance(spec, dict) or set(spec) != {"path", "sha256"}:
            drift.append(f"{name}: malformed frozen-input spec")
            continue
        stored_path = spec.get("path")
        stored_hash = spec.get("sha256")
        if not isinstance(stored_path, str) or not stored_path or not isinstance(stored_hash, str):
            drift.append(f"{name}: malformed frozen-input values")
            continue
        absolute = base / stored_path
        try:
            if not absolute.is_file():
                drift.append(f"{name}: missing {stored_path}")
            elif sha256_file(absolute) != stored_hash:
                drift.append(f"{name}: drifted {stored_path}")
        except OSError as error:
            drift.append(f"{name}: unreadable {stored_path}: {error}")
    return drift
