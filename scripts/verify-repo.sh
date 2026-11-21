#!/usr/bin/env bash
# Canonical single-command verification driver for `ajar-harness`.
#
# Usage:
#   scripts/verify-repo.sh --fast           # Inner loop (~15s): AGENTS.md, ruff, arch_lint, mypy, unit+contract+DST
#   scripts/verify-repo.sh --full           # Pre-PR outer loop: adds integration tests + archived legacy checks
#   scripts/verify-repo.sh --full --strict-legacy
#
set -euo pipefail

MODE="fast"
STRICT_LEGACY=0

for arg in "$@"; do
  case "$arg" in
    --fast) MODE="fast" ;;
    --full) MODE="full" ;;
    --strict-legacy) STRICT_LEGACY=1 ;;
    -h|--help)
      sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (use --fast, --full, --strict-legacy, or --help)" >&2
      exit 2
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

resolve_tool() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    command -v "$name"
    return 0
  fi
  for cand in "/opt/pipx/bin/$name" "$HOME/.local/bin/$name"; do
    if [[ -x "$cand" ]]; then
      echo "$cand"
      return 0
    fi
  done
  echo "Missing required tool '$name'. Install with: python3 -m pip install -e '.[dev]'" >&2
  return 1
}

RUFF="$(resolve_tool ruff)"
MYPY="$(resolve_tool mypy)"
PYTEST="$(resolve_tool pytest)"

echo "==> [1/5] AGENTS.md budget (<= 50 lines) & CLAUDE.md parity"
lines="$(wc -l < AGENTS.md | tr -d ' ')"
test "$lines" -le 50
cmp -s AGENTS.md CLAUDE.md
echo "    OK (AGENTS.md == CLAUDE.md, ${lines} lines)"

echo "==> [2/5] Ruff lint (E, F, I, W, B)"
"$RUFF" check ajar tests tools/arch_lint.py

echo "==> [3/5] Mechanical architecture guardrails (tools/arch_lint.py)"
python3 tools/arch_lint.py

echo "==> [4/5] Static type-check (mypy --strict core + package)"
"$MYPY" --strict ajar/domain ajar/store ajar/services tools/arch_lint.py
"$MYPY" ajar --ignore-missing-imports

if [[ "$MODE" == "fast" ]]; then
  echo "==> [5/5] Fast inner-loop suite (unit + conformance + arch_lint + parity + DST)"
  "$PYTEST" -m "not integration" -q
  echo "verify-repo (--fast): PASS"
  exit 0
fi

echo "==> [5/6] Full pytest suite (unit + DST + compiler/debugger integration)"
"$PYTEST" -q

echo "==> [6/6] Archived historical record reader tests (tools/legacy/*-test.py)"
if python3 -c "import jsonschema" >/dev/null 2>&1; then
  for t in tools/legacy/*-test.py; do
    python3 "$t"
  done
else
  if [[ "$STRICT_LEGACY" -eq 1 ]]; then
    echo "ERROR: jsonschema==4.26.0 not installed and --strict-legacy was requested." >&2
    exit 1
  fi
  echo "    SKIPPED locally (jsonschema==4.26.0 not installed in current Python; runs in CI)."
fi

echo "verify-repo (--full): PASS"
