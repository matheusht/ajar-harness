#!/usr/bin/env python3
"""Build and verify a frozen package + entrypoint denominator from pinned npm tarballs.

This is an offline syntactic instrument. It executes neither package code nor a model. The output is
an external offline TSV with one row per (package, entrypoint) pair and a JSON freeze sidecar that is
compatible with tools/hash-campaign-inputs.py --check. Register reviewed outputs through the normal
engagement artifact path; this command never writes directly into governed engagement evidence.

Usage:
  python3 tools/corpus_enumeration.py build --pins package-pins.tsv --tarballs tarballs/ \
      --output corpus-enumeration.tsv --freeze corpus-enumeration.freeze.json
  python3 tools/corpus_enumeration.py verify --freeze corpus-enumeration.freeze.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import importlib.metadata
import json
import os
import re
import sys
import tarfile
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from frozen_inputs import sha256_file
from engagement_quarantine import (
    atomic_write_offline,
    quarantined_ancestor,
    read_safe_offline_file,
    read_safe_offline_tree,
    require_safe_offline_output,
)

try:
    import tree_sitter_javascript
    import tree_sitter_typescript
    from jsonschema import Draft202012Validator
    from tree_sitter import Language, Parser
except ImportError as dependency_error:  # Reported as a deterministic CLI error, never a traceback.
    Draft202012Validator = Language = Parser = None
    tree_sitter_javascript = tree_sitter_typescript = None
    DEPENDENCY_ERROR = dependency_error
else:
    DEPENDENCY_ERROR = None


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schemas" / "corpus-enumeration.schema.json"
TOOL_PATH = Path(__file__).resolve()
CAVEAT = "# coverage_semantics=visitation-not-understanding; necessary-not-sufficient-for-coverage"
COLUMNS = [
    "status",
    "package",
    "version",
    "dist.shasum",
    "entrypoint_path",
    "entrypoint_tag",
    "entrypoint_sha256",
]
PIN_COLUMNS = ["status", "package", "version", "dist.shasum"]
SOURCE_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
TYPE_ONLY_DECLARATIONS = {
    "ambient_declaration",
    "interface_declaration",
    "type_alias_declaration",
}
LEXICAL_SCOPE_NODES = {
    "abstract_class_declaration",
    "arrow_function",
    "class",
    "class_declaration",
    "function_declaration",
    "function_expression",
    "generator_function",
    "generator_function_declaration",
    "method_definition",
}
INVOKED_SCOPE_WRAPPERS = {
    "as_expression",
    "member_expression",
    "non_null_expression",
    "parenthesized_expression",
    "sequence_expression",
    "satisfies_expression",
    "subscript_expression",
}


class EnumerationError(Exception):
    pass


@dataclass(frozen=True)
class Pin:
    status: str
    package: str
    version: str
    tarball_sha1: str


@dataclass(frozen=True)
class Archive:
    pin: Pin
    path: Path
    source_bytes: bytes
    files: dict[str, bytes]
    manifest: dict[str, Any]


@dataclass(frozen=True)
class Row:
    status: str
    package: str
    version: str
    tarball_sha1: str
    entrypoint_path: str
    entrypoint_tag: str
    entrypoint_sha256: str

    def as_tsv(self) -> dict[str, str]:
        return {
            "status": self.status,
            "package": self.package,
            "version": self.version,
            "dist.shasum": self.tarball_sha1,
            "entrypoint_path": self.entrypoint_path,
            "entrypoint_tag": self.entrypoint_tag,
            "entrypoint_sha256": self.entrypoint_sha256,
        }


@dataclass(frozen=True)
class ExportMapping:
    subpath: str
    target: str
    sibling_subpaths: tuple[str, ...]


_PARSERS: dict[str, Any] | None = None


def _require_dependencies() -> None:
    if DEPENDENCY_ERROR is not None:
        raise EnumerationError(
            f"missing pinned parser dependency ({DEPENDENCY_ERROR}); install requirements-ci.txt"
        )


def _parser_versions() -> dict[str, str]:
    _require_dependencies()
    return {
        name: importlib.metadata.version(name)
        for name in ("tree-sitter", "tree-sitter-javascript", "tree-sitter-typescript")
    }


def _parsers() -> dict[str, Any]:
    global _PARSERS
    _require_dependencies()
    if _PARSERS is None:
        javascript = Language(tree_sitter_javascript.language())
        typescript = Language(tree_sitter_typescript.language_typescript())
        tsx = Language(tree_sitter_typescript.language_tsx())
        _PARSERS = {
            "javascript": Parser(javascript),
            "typescript": Parser(typescript),
            "tsx": Parser(tsx),
        }
    return _PARSERS


def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_pins(path: Path, data: bytes | None = None) -> list[Pin]:
    try:
        with io.StringIO((read_safe_offline_file(path) if data is None else data).decode("utf-8"), newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames != PIN_COLUMNS:
                raise EnumerationError(
                    f"pin header must be exactly {PIN_COLUMNS!r}; got {reader.fieldnames!r}"
                )
            pins = []
            seen = set()
            for line_number, raw in enumerate(reader, 2):
                if None in raw or any(value is None for value in raw.values()):
                    raise EnumerationError(f"malformed pin row at line {line_number}")
                status = raw["status"].strip()
                package = raw["package"].strip()
                version = raw["version"].strip()
                tarball_sha1 = raw["dist.shasum"].strip().lower()
                if not re.fullmatch(r"[a-z][a-z0-9_-]*", status):
                    raise EnumerationError(f"invalid status at line {line_number}: {status!r}")
                if not package or any(character.isspace() for character in package):
                    raise EnumerationError(f"invalid package at line {line_number}: {package!r}")
                if not version or any(character.isspace() for character in version):
                    raise EnumerationError(f"invalid version at line {line_number}: {version!r}")
                if not re.fullmatch(r"[0-9a-f]{40}", tarball_sha1):
                    raise EnumerationError(f"invalid dist.shasum at line {line_number}")
                identity = (package, version)
                if identity in seen:
                    raise EnumerationError(f"duplicate package pin: {package}@{version}")
                seen.add(identity)
                pins.append(Pin(status, package, version, tarball_sha1))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise EnumerationError("cannot read package pins") from error
    if not pins:
        raise EnumerationError("package pin file is empty")
    return pins


def _archive_member_path(name: str) -> str | None:
    if any(unicodedata.category(character) in {"Cc", "Zl", "Zp"} for character in name):
        raise EnumerationError(f"tarball member path contains a control character: {name!r}")
    normalized = PurePosixPath(name)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise EnumerationError(f"unsafe tarball member path: {name!r}")
    parts = normalized.parts
    if not parts or parts[0] != "package" or len(parts) == 1:
        return None
    return PurePosixPath(*parts[1:]).as_posix()


def _read_archive(path: Path, data: bytes) -> tuple[dict[str, bytes], dict[str, Any]]:
    files: dict[str, bytes] = {}
    total_size = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            members = archive.getmembers()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise EnumerationError(f"tarball has too many members: {path}")
            for member in members:
                relative = _archive_member_path(member.name)
                if relative is None or not member.isfile():
                    continue
                if relative in files:
                    raise EnumerationError(f"duplicate tarball member: {relative}")
                total_size += member.size
                if total_size > MAX_ARCHIVE_BYTES:
                    raise EnumerationError(f"tarball expands beyond {MAX_ARCHIVE_BYTES} bytes: {path}")
                if PurePosixPath(relative).suffix in SOURCE_SUFFIXES and member.size > MAX_SOURCE_BYTES:
                    raise EnumerationError(f"source file is too large to parse safely: {relative}")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise EnumerationError(f"cannot read tarball member: {relative}")
                files[relative] = extracted.read()
    except (OSError, tarfile.TarError) as error:
        raise EnumerationError(f"cannot read npm tarball {path}: {error}") from error
    if "package.json" not in files:
        raise EnumerationError(f"npm tarball has no package/package.json: {path}")
    try:
        manifest = json.loads(files["package.json"])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EnumerationError(f"invalid package.json in {path}: {error}") from error
    if not isinstance(manifest, dict):
        raise EnumerationError(f"package.json is not an object in {path}")
    return files, manifest


def discover_archives(
    pins: list[Pin], directory: Path, tree: dict[str, bytes] | None = None
) -> list[Archive]:
    try:
        tree = read_safe_offline_tree(directory) if tree is None else tree
    except (OSError, ValueError) as error:
        raise EnumerationError("cannot snapshot tarball directory") from error
    paths = sorted(
        relative for relative in tree
        if relative.endswith(".tgz") or relative.endswith(".tar.gz")
    )
    if not paths:
        raise EnumerationError("tarball directory contains no .tgz or .tar.gz files")

    by_identity: dict[tuple[str, str], tuple[Path, bytes, dict[str, bytes], dict[str, Any]]] = {}
    for relative in paths:
        path = directory / relative
        source_bytes = tree[relative]
        files, manifest = _read_archive(path, source_bytes)
        name = manifest.get("name")
        version = manifest.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise EnumerationError(f"package manifest lacks string name/version: {path}")
        identity = (name, version)
        if identity in by_identity:
            raise EnumerationError(f"multiple tarballs resolve to {name}@{version}")
        by_identity[identity] = (path, source_bytes, files, manifest)

    expected = {(pin.package, pin.version) for pin in pins}
    extra = sorted(set(by_identity) - expected)
    missing = sorted(expected - set(by_identity))
    if extra:
        raise EnumerationError(f"unpinned package tarballs present: {extra}")
    if missing:
        raise EnumerationError(f"pinned package tarballs missing: {missing}")

    archives = []
    for pin in pins:
        path, source_bytes, files, manifest = by_identity[(pin.package, pin.version)]
        actual_sha1 = _sha1_bytes(source_bytes)
        if actual_sha1 != pin.tarball_sha1:
            raise EnumerationError(
                f"tarball pin mismatch for {pin.package}@{pin.version}: "
                f"expected {pin.tarball_sha1}, got {actual_sha1}"
            )
        archives.append(Archive(pin, path.resolve(strict=False), source_bytes, files, manifest))
    return archives


def _export_mappings(
    value: Any,
    subpath: str = ".",
    sibling_subpaths: tuple[str, ...] = (".",),
    type_only: bool = False,
) -> Iterable[ExportMapping]:
    if value is None:
        return
    if isinstance(value, str):
        if type_only or _is_declaration_file(value):
            return
        yield ExportMapping(subpath, value, sibling_subpaths)
        return
    if isinstance(value, list):
        for item in value:
            yield from _export_mappings(item, subpath, sibling_subpaths, type_only)
        return
    if isinstance(value, dict):
        keys = list(value)
        subpaths = [key.startswith(".") for key in keys]
        if any(subpaths) and not all(subpaths):
            raise EnumerationError("exports map mixes subpath and condition keys")
        if all(subpaths):
            siblings = tuple(keys)
            for key, item in value.items():
                yield from _export_mappings(item, key, siblings, type_only)
        else:
            for condition, item in value.items():
                yield from _export_mappings(
                    item, subpath, sibling_subpaths, type_only or condition == "types"
                )
        return
    raise EnumerationError(f"unsupported exports-map value: {value!r}")


def _normalize_target(target: str) -> str:
    if not target.startswith("./"):
        raise EnumerationError(f"exports target is not package-relative: {target!r}")
    path = PurePosixPath(target[2:])
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise EnumerationError(f"unsafe exports target: {target!r}")
    return path.as_posix()


def _is_declaration_file(path: str) -> bool:
    return path.endswith((".d.ts", ".d.mts", ".d.cts"))


def _pattern_capture(pattern: str, value: str) -> str | None:
    parts = pattern.split("*")
    if len(parts) == 1:
        return "" if pattern == value else None
    expression = re.escape(parts[0]) + "(?P<wildcard>.*)"
    for part in parts[1:-1]:
        expression += re.escape(part) + "(?P=wildcard)"
    expression += re.escape(parts[-1])
    match = re.fullmatch(expression, value)
    return match.group("wildcard") if match is not None else None


def _subpath_rank(subpath: str) -> tuple[int, int, int]:
    pattern_index = subpath.find("*")
    return (pattern_index < 0, pattern_index, len(subpath))


def _mapping_selected(mapping: ExportMapping, public_subpath: str) -> bool:
    matching = [
        sibling
        for sibling in mapping.sibling_subpaths
        if _pattern_capture(sibling, public_subpath) is not None
    ]
    return bool(matching) and max(matching, key=_subpath_rank) == mapping.subpath


def _expand_export_mapping(mapping: ExportMapping, files: dict[str, bytes]) -> Iterable[str]:
    target = _normalize_target(mapping.target)
    if "*" not in target:
        if target not in files:
            raise EnumerationError(f"declared exports target is absent from tarball: {mapping.target}")
        if not _is_declaration_file(target):
            yield target
        return
    if "*" not in mapping.subpath:
        raise EnumerationError(
            f"exports target pattern has no matching subpath pattern: {mapping.target!r}"
        )
    for path in files:
        capture = _pattern_capture(target, path)
        if capture is None or _is_declaration_file(path):
            continue
        public_subpath = mapping.subpath.replace("*", capture)
        if _mapping_selected(mapping, public_subpath):
            yield path


def _declared_from_exports(exports: Any, files: dict[str, bytes]) -> set[str]:
    declared = set()
    for mapping in _export_mappings(exports):
        declared.update(_expand_export_mapping(mapping, files))
    return declared


def _resolve_legacy_main(raw_main: str, files: dict[str, bytes], seen: set[str] | None = None) -> str | None:
    seen = set() if seen is None else seen
    candidate = raw_main.removeprefix("./")
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise EnumerationError(f"unsafe main target: {raw_main!r}")
    normalized = path.as_posix().rstrip("/")
    if normalized in seen:
        return None
    seen.add(normalized)
    if normalized in files and not _is_declaration_file(normalized):
        return normalized
    if not PurePosixPath(normalized).suffix:
        for suffix in (".js", ".json", ".node"):
            if normalized + suffix in files:
                return normalized + suffix
    nested_manifest = normalized + "/package.json"
    if nested_manifest in files:
        try:
            nested = json.loads(files[nested_manifest])
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EnumerationError(f"invalid nested package.json at {nested_manifest}: {error}") from error
        nested_main = nested.get("main") if isinstance(nested, dict) else None
        if isinstance(nested_main, str):
            resolved = _resolve_legacy_main(f"{normalized}/{nested_main}", files, seen)
            if resolved:
                return resolved
    for filename in ("index.js", "index.json", "index.node"):
        joined = f"{normalized}/{filename}" if normalized else filename
        if joined in files:
            return joined
    return None


def declared_entrypoints(manifest: dict[str, Any], files: dict[str, bytes]) -> set[str]:
    if "exports" in manifest:
        return _declared_from_exports(manifest["exports"], files)
    main = manifest.get("main", "index.js")
    if not isinstance(main, str):
        raise EnumerationError("package main must be a string when present")
    resolved = _resolve_legacy_main(main, files)
    return {resolved} if resolved else set()


def _node_bytes(node: Any, source: bytes) -> bytes:
    return source[node.start_byte:node.end_byte]


def _runtime_export_statement(node: Any, source: bytes) -> bool:
    declaration = node.child_by_field_name("declaration")
    if declaration is not None and declaration.type in TYPE_ONLY_DECLARATIONS:
        return False
    if any(not child.is_named and child.type == "type" for child in node.children):
        return False
    clauses = [child for child in node.named_children if child.type == "export_clause"]
    if clauses:
        specifiers = [child for clause in clauses for child in clause.named_children]
        return any(
            not any(not child.is_named and child.type == "type" for child in specifier.children)
            for specifier in specifiers
        )
    return True


def _member_is_commonjs_export(text: bytes) -> bool:
    compact = re.sub(rb"\s+", b"", text)
    return bool(re.fullmatch(
        rb"(?:module(?:\.exports|\[['\"]exports['\"]\])(?:\.[A-Za-z_$][\w$]*|\[['\"][^'\"]+['\"]\])*"
        rb"|exports(?:\.[A-Za-z_$][\w$]*|\[['\"][^'\"]+['\"]\])+)",
        compact,
    ))


def _invoked_scope_node(node: Any, source: bytes) -> Any | None:
    current = node
    while current is not None:
        if current.type in LEXICAL_SCOPE_NODES:
            return current
        if current.type not in INVOKED_SCOPE_WRAPPERS or not current.named_children:
            return None
        if current.type == "member_expression":
            property_node = current.child_by_field_name("property")
            if property_node is None or _node_bytes(property_node, source) not in {b"call", b"apply"}:
                return None
            current = current.child_by_field_name("object")
        elif current.type == "subscript_expression":
            index_node = current.child_by_field_name("index")
            if index_node is None:
                return None
            index = _node_bytes(index_node, source).strip().strip(b"'\"")
            if index not in {b"call", b"apply"}:
                return None
            current = current.child_by_field_name("object")
        else:
            current = current.named_children[-1]
    return None


def _module_scope_commonjs_export(node: Any, source: bytes) -> bool:
    stack = [(node, False)]
    while stack:
        current, enter_scope = stack.pop()
        if current.type in LEXICAL_SCOPE_NODES and not enter_scope:
            continue
        if current.type == "assignment_expression":
            left = current.child_by_field_name("left")
            if left is not None and _member_is_commonjs_export(_node_bytes(left, source)):
                return True
        if current.type == "call_expression":
            function = current.child_by_field_name("function")
            arguments = current.child_by_field_name("arguments")
            function_text = re.sub(rb"\s+", b"", _node_bytes(function, source)) if function else b""
            named_arguments = arguments.named_children if arguments is not None else []
            if (
                function_text in {b"Object.assign", b"Object.defineProperties"}
                and named_arguments
                and _node_bytes(named_arguments[0], source).strip()
                in {b"exports", b"module.exports"}
            ):
                return True
            if function_text == b"Object.defineProperty" and len(named_arguments) >= 2:
                target = _node_bytes(named_arguments[0], source).strip()
                property_name = _node_bytes(named_arguments[1], source).strip().strip(b"'\"")
                if target in {b"exports", b"module.exports"} and property_name != b"__esModule":
                    return True
            invoked_scope = _invoked_scope_node(function, source) if function is not None else None
            if invoked_scope is not None:
                stack.append((invoked_scope, True))
        stack.extend((child, False) for child in reversed(current.named_children))
    return False


def has_static_runtime_export(path: str, source: bytes) -> bool:
    if _is_declaration_file(path):
        return False
    if path.endswith(".tsx"):
        parser_name = "tsx"
    elif PurePosixPath(path).suffix in {".ts", ".mts", ".cts"}:
        parser_name = "typescript"
    else:
        parser_name = "javascript"
    parser = _parsers()[parser_name]
    tree = parser.parse(source)
    if tree.root_node.has_error:
        raise EnumerationError(f"tree-sitter could not parse published source without errors: {path}")
    for statement in tree.root_node.named_children:
        if statement.type == "export_statement" and _runtime_export_statement(statement, source):
            return True
        if _module_scope_commonjs_export(statement, source):
            return True
    return False


def enumerate_rows(archives: list[Archive]) -> list[Row]:
    rows = []
    for archive in archives:
        declared = declared_entrypoints(archive.manifest, archive.files)
        undeclared = set()
        for path, source in archive.files.items():
            if path in declared or PurePosixPath(path).suffix not in SOURCE_SUFFIXES:
                continue
            if has_static_runtime_export(path, source):
                undeclared.add(path)
        entrypoints = [(path, "declared") for path in declared]
        entrypoints += [(path, "undeclared-published") for path in undeclared]
        if not entrypoints:
            raise EnumerationError(
                f"no importable entrypoint found for pinned package {archive.pin.package}@{archive.pin.version}"
            )
        for path, tag in entrypoints:
            rows.append(Row(
                archive.pin.status,
                archive.pin.package,
                archive.pin.version,
                archive.pin.tarball_sha1,
                path,
                tag,
                _sha256_bytes(archive.files[path]),
            ))
    return sorted(rows, key=lambda row: (row.package, row.version, row.entrypoint_path, row.entrypoint_tag))


def render_tsv(rows: list[Row]) -> bytes:
    import io

    output = io.StringIO(newline="")
    output.write(CAVEAT + "\n")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(row.as_tsv() for row in rows)
    return output.getvalue().encode()


def _relative(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve()).replace(os.sep, "/")


def _validate_freeze(document: dict[str, Any]) -> list[str]:
    _require_dependencies()
    try:
        schema = json.loads(SCHEMA_PATH.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return [f"cannot load corpus enumeration schema: {error}"]
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.absolute_path))
    ]


def _write_new(path: Path, content: bytes) -> None:
    try:
        atomic_write_offline(path, content, overwrite=False)
    except ValueError as error:
        raise EnumerationError("refusing unsafe or existing frozen artifact") from error


def _write_pair(output: Path, artifact: bytes, freeze: Path, manifest: bytes) -> None:
    """Publish the TSV then its commit marker.

    A process interruption between publications deliberately leaves the immutable TSV in place.
    Build resumes only when those bytes exactly equal a fresh enumeration of still-pinned inputs;
    avoiding a rollback unlink also prevents a stale parent FD from deleting governed evidence.
    """
    _write_new(output, artifact)
    _write_new(freeze, manifest)


def _manifest(
    rows: list[Row],
    output: Path,
    artifact_sha256: str,
    freeze: Path,
    pins: Path,
    pins_bytes: bytes,
    tarballs: Path,
    archives: list[Archive],
) -> dict[str, Any]:
    base = freeze.resolve().parent
    frozen_inputs = {
        "package-pins": {
            "path": _relative(pins, base),
            "sha256": _sha256_bytes(pins_bytes),
        },
        "enumerator": {
            "path": _relative(TOOL_PATH, base),
            "sha256": sha256_file(TOOL_PATH),
        },
        "schema": {
            "path": _relative(SCHEMA_PATH, base),
            "sha256": sha256_file(SCHEMA_PATH),
        },
    }
    for index, archive in enumerate(archives, 1):
        frozen_inputs[f"tarball:{index:04d}"] = {
            "path": _relative(archive.path, base),
            "sha256": _sha256_bytes(archive.source_bytes),
        }
    frozen_inputs["corpus-enumeration"] = {
        "path": _relative(output, base),
        "sha256": artifact_sha256,
    }
    document = {
        "schema_version": 1,
        "artifact_type": "corpus-enumeration",
        "frozen_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generated_by": {
            "tool": "tools/corpus_enumeration.py",
            "tool_sha256": sha256_file(TOOL_PATH),
            "mode": "syntactic",
            "model_involvement": False,
            "parser_versions": _parser_versions(),
        },
        "granularity": ["package", "entrypoint"],
        "columns": COLUMNS,
        "coverage_semantics": {
            "closes_on": "visitation",
            "does_not_establish": "understanding",
            "necessary_for_coverage": True,
            "sufficient_for_coverage": False,
        },
        "artifact": {
            "path": _relative(output, base),
            "sha256": artifact_sha256,
            "row_count": len(rows),
            "package_count": len({(row.package, row.version) for row in rows}),
        },
        "source": {
            "pins_path": _relative(pins, base),
            "tarballs_path": _relative(tarballs, base),
        },
        "frozen_inputs_base": "manifest",
        "frozen_inputs": frozen_inputs,
    }
    problems = _validate_freeze(document)
    if problems:
        raise EnumerationError(f"generated freeze manifest is schema-invalid: {problems}")
    return document


def build(args: argparse.Namespace) -> int:
    output = Path(args.output)
    freeze = Path(args.freeze)
    require_safe_offline_output(output);require_safe_offline_output(freeze)
    if output.resolve() == freeze.resolve():
        raise EnumerationError("artifact and freeze paths must differ")
    if output.is_symlink() or freeze.is_symlink():
        raise EnumerationError("artifact and freeze paths may not be symbolic links")
    if freeze.exists():
        existing = [str(path) for path in (output, freeze) if path.exists()]
        raise EnumerationError(f"refusing to replace existing frozen output: {existing}")
    pins_path = Path(args.pins).resolve()
    tarballs_path = Path(args.tarballs).resolve()
    if quarantined_ancestor(pins_path) or quarantined_ancestor(tarballs_path):
        raise EnumerationError("source evidence is quarantined")
    try:
        pins_bytes = read_safe_offline_file(pins_path)
        tarball_tree = read_safe_offline_tree(tarballs_path)
    except (OSError, ValueError) as error:
        raise EnumerationError("source evidence is unavailable or governed") from error
    pins = read_pins(pins_path, pins_bytes)
    archives = discover_archives(pins, tarballs_path, tarball_tree)
    rows = enumerate_rows(archives)
    artifact = render_tsv(rows)
    recovering = output.exists()
    if recovering and (
        not output.is_file()
        or read_safe_offline_file(output) != artifact
    ):
        raise EnumerationError(
            "refusing to freeze a pre-existing artifact that differs from fresh syntactic enumeration"
        )
    artifact_sha256 = _sha256_bytes(artifact)
    document = _manifest(
        rows,
        output,
        artifact_sha256,
        freeze,
        pins_path,
        pins_bytes,
        tarballs_path,
        archives,
    )
    manifest = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    try:
        sources_unchanged = (
            read_safe_offline_file(pins_path) == pins_bytes
            and read_safe_offline_tree(tarballs_path) == tarball_tree
        )
    except (OSError, ValueError):
        sources_unchanged = False
    if not sources_unchanged:
        raise EnumerationError("source evidence became quarantined during enumeration")
    if recovering:
        _write_new(freeze, manifest)
    else:
        _write_pair(output, artifact, freeze, manifest)
    print(f"frozen corpus enumeration: {len(rows)} entrypoints across {len(pins)} packages")
    print(f"artifact: {output}")
    print(f"freeze: {freeze}")
    print("coverage semantics: visitation, not understanding")
    return 0


def _read_artifact(path: Path, data: bytes | None = None) -> list[Row]:
    try:
        lines = (read_safe_offline_file(path) if data is None else data).decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise EnumerationError("cannot read enumeration artifact") from error
    if not lines or lines[0] != CAVEAT:
        raise EnumerationError("enumeration artifact is missing the visitation-not-understanding caveat")
    reader = csv.DictReader(lines[1:], delimiter="\t")
    if reader.fieldnames != COLUMNS:
        raise EnumerationError(f"enumeration header must be exactly {COLUMNS!r}")
    rows = []
    seen = set()
    for line_number, raw in enumerate(reader, 3):
        if None in raw or any(value is None for value in raw.values()):
            raise EnumerationError(f"malformed enumeration row at line {line_number}")
        if raw["entrypoint_tag"] not in {"declared", "undeclared-published"}:
            raise EnumerationError(f"invalid entrypoint tag at line {line_number}")
        if not re.fullmatch(r"[0-9a-f]{40}", raw["dist.shasum"]):
            raise EnumerationError(f"invalid dist.shasum at line {line_number}")
        if not re.fullmatch(r"[0-9a-f]{64}", raw["entrypoint_sha256"]):
            raise EnumerationError(f"invalid entrypoint SHA-256 at line {line_number}")
        identity = (raw["package"], raw["version"], raw["entrypoint_path"])
        if identity in seen:
            raise EnumerationError(f"duplicate package + entrypoint row at line {line_number}")
        seen.add(identity)
        rows.append(Row(
            raw["status"], raw["package"], raw["version"], raw["dist.shasum"],
            raw["entrypoint_path"], raw["entrypoint_tag"], raw["entrypoint_sha256"],
        ))
    if not rows:
        raise EnumerationError("enumeration artifact has no rows")
    return rows


def verify(args: argparse.Namespace) -> int:
    freeze = Path(args.freeze).resolve()
    if quarantined_ancestor(freeze):
        raise EnumerationError("frozen source evidence is quarantined")
    try:
        freeze_bytes = read_safe_offline_file(freeze)
        document = json.loads(freeze_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise EnumerationError("cannot read freeze manifest") from error
    problems = _validate_freeze(document)
    if problems:
        raise EnumerationError(f"freeze manifest is schema-invalid: {problems}")

    base = freeze.parent
    artifact_path = (base / document["artifact"]["path"]).resolve()
    pins_path = (base / document["source"]["pins_path"]).resolve()
    tarballs_path = (base / document["source"]["tarballs_path"]).resolve()
    frozen = document["frozen_inputs"]
    linked_inputs = [freeze, artifact_path, pins_path, tarballs_path]
    for spec in frozen.values():
        if isinstance(spec, dict) and isinstance(spec.get("path"), str):
            linked_inputs.append((base / spec["path"]).resolve())
    if any(quarantined_ancestor(path) for path in linked_inputs):
        raise EnumerationError("frozen source evidence is quarantined")

    stable_inputs: dict[str, bytes] = {}
    drift = []
    for name, spec in frozen.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
            drift.append(f"{name}: malformed frozen input")
            continue
        source_path = (base / spec["path"]).resolve(strict=False)
        try:
            source_bytes = read_safe_offline_file(source_path)
        except (OSError, ValueError):
            drift.append(f"{name}: input unavailable or governed")
            continue
        stable_inputs[name] = source_bytes
        if _sha256_bytes(source_bytes) != spec.get("sha256"):
            drift.append(f"{name}: hash mismatch")
    for item in drift:
        print(f"DRIFT {item}")
    if drift:
        raise EnumerationError("frozen inputs drifted; the frozen denominator was not rewritten")

    expected_links = {
        "corpus-enumeration": (document["artifact"]["path"], document["artifact"]["sha256"]),
        "package-pins": (_relative(pins_path, base), _sha256_bytes(stable_inputs["package-pins"])),
        "enumerator": (_relative(TOOL_PATH, base), document["generated_by"]["tool_sha256"]),
        "schema": (_relative(SCHEMA_PATH, base), _sha256_bytes(stable_inputs["schema"])),
    }
    for name, (path, digest) in expected_links.items():
        if frozen[name] != {"path": path, "sha256": digest}:
            raise EnumerationError(f"freeze manifest has inconsistent {name} linkage")

    expected_versions = document["generated_by"]["parser_versions"]
    if expected_versions != _parser_versions():
        raise EnumerationError(
            f"parser version drift: expected {expected_versions}, got {_parser_versions()}"
        )

    artifact_bytes = stable_inputs["corpus-enumeration"]
    pins_bytes = stable_inputs["package-pins"]
    artifact_rows = _read_artifact(artifact_path, artifact_bytes)
    pins = read_pins(pins_path, pins_bytes)
    try:
        tarball_tree = read_safe_offline_tree(tarballs_path)
    except (OSError, ValueError) as error:
        raise EnumerationError("cannot snapshot tarball directory") from error
    archives = discover_archives(pins, tarballs_path, tarball_tree)
    frozen_tarballs = sorted(
        spec["path"] for name, spec in frozen.items() if name.startswith("tarball:")
    )
    actual_tarballs = sorted(_relative(archive.path, base) for archive in archives)
    if frozen_tarballs != actual_tarballs:
        raise EnumerationError("freeze manifest tarball set does not match the pinned corpus")
    regenerated = enumerate_rows(archives)
    if artifact_rows != regenerated:
        raise EnumerationError("syntactic re-enumeration differs from the frozen artifact")
    if document["artifact"]["row_count"] != len(artifact_rows):
        raise EnumerationError("frozen row_count does not match artifact")
    package_count = len({(row.package, row.version) for row in artifact_rows})
    if document["artifact"]["package_count"] != package_count:
        raise EnumerationError("frozen package_count does not match artifact")
    try:
        inputs_unchanged = (
            read_safe_offline_file(freeze) == freeze_bytes
            and read_safe_offline_file(artifact_path) == artifact_bytes
            and read_safe_offline_file(pins_path) == pins_bytes
            and read_safe_offline_tree(tarballs_path) == tarball_tree
        )
    except (OSError, ValueError):
        inputs_unchanged = False
    if not inputs_unchanged:
        raise EnumerationError("frozen source evidence became quarantined during verification")
    print(f"frozen corpus enumeration: intact ({len(artifact_rows)} entrypoints, {package_count} packages)")
    print("coverage semantics: visitation, not understanding")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="enumerate pinned local npm tarballs and freeze the result")
    build_parser.add_argument("--pins", required=True, help="TSV: status, package, version, dist.shasum")
    build_parser.add_argument("--tarballs", required=True, help="directory containing exactly the pinned npm tarballs")
    build_parser.add_argument("--output", required=True, help="new external offline corpus-enumeration.tsv; register it separately")
    build_parser.add_argument("--freeze", required=True, help="new external offline JSON freeze sidecar; register it separately")
    verify_parser = commands.add_parser("verify", help="verify hashes and syntactically reproduce a frozen artifact")
    verify_parser.add_argument("--freeze", required=True, help="corpus-enumeration freeze sidecar")
    return root


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv[1:])
    try:
        return build(args) if args.command == "build" else verify(args)
    except (EnumerationError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
