#!/bin/zsh
# CLOSE angular-cli-2026-08 — OPERATOR-EXECUTED (three ssh signatures required)
# The agent prepared this file. Only the operator may execute it: each authority step
# requires the operator's private key. Run:  zsh close-engagement.zsh
# v2: fixed set -e abort on the signature-required exit (capture with || true),
#     challenge extraction now reads the JSON line AFTER the marker, and every step
#     prints its full output.
HARNESS_DIR="/Users/matheusvsky/Documents/trab/llm-redteam-harness"
ENG="engagements/angular-cli-2026-08"
OP_KEY="/Users/matheusvsky/.ssh/harness-signing/gemini-cli-operator-ed25519"
ALLOWED="${HARNESS_DIR}/engagements/angular-cli-2026-08/signers/operator.allowed_signers"
PY="${HARNESS_DIR}/.venv/bin/python"
cd "${HARNESS_DIR}"

if [[ ! -f "${OP_KEY}" ]]; then
  print -u2 "Refusing: operator private key not found at ${OP_KEY}."
  exit 1
fi

# run one kernel command; if it returns operator_signature_required, extract the
# challenge (the JSON line after the marker), sign it, and retry with the env vars.
run_signed() {
  local out=""
  out=$("$@" 2>&1 || true)                       # do NOT let set -e abort here
  if [[ "$out" == *"operator_signature_required"* ]]; then
    local challenge
    challenge=$(print -r -- "$out" | awk '/^Operator signature challenge:/{getline; print; exit}')
    if [[ -z "$challenge" ]]; then
      print -u2 "No challenge captured. Full output:"
      print -r -- "$out"
      return 1
    fi
    local cfile="/tmp/close-challenge-$$.json"
    print -r -- "$challenge" > "$cfile"
    print ">> Signing kernel challenge..."
    /usr/bin/ssh-keygen -Y sign -f "${OP_KEY}" -n llm-redteam-harness-operator-v1 "${cfile}" > /dev/null 2>&1 || {
      print -u2 "ssh-keygen signing failed for ${cfile}"; return 1
    }
    print ">> Signature: ${cfile}.sig"
    out=$(HARNESS_OPERATOR_SIGNATURE_FILE="${cfile}.sig" HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE="${ALLOWED}" "$@" 2>&1 || true)
  fi
  print -r -- "$out"
}

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SID=$(${PY} tools/run-engagement.py runtime-identity --role broker 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['session_id'])")

echo "=== 1/4 supersede the stale cascading-phase close request ==="
run_signed ${PY} tools/run-engagement.py resolve-authority --engagement ${ENG} \
  --request-id auth-close-cli-2026-08-15 --resolution superseded --operator-id matheusht \
  --session-id "$SID" --recorded-at "$NOW" \
  --reason "Superseded: predates the deep/chainstorm/next phases (7 findings, 5 chains, VRP filing prep)."

echo "=== 2/4 request the fresh close authority ==="
${PY} tools/run-engagement.py request-authority --engagement ${ENG} \
  --request-id auth-close-cli-2026-08-15-final --action-kind close \
  --action-file ${ENG}/authority/requests/auth-close-cli-2026-08-15-final.action.json \
  --lane-id close-lane --actor-role broker --actor-id local-uid-501:broker \
  --session-id "$SID" --recorded-at "$NOW" --expires-at "2026-08-17T00:00:00Z" \
  --reason "Close angular-cli-2026-08 after 7 promoted findings, 5 chain verdicts, VRP filing prep complete, cleanup ledger final." || true

echo "=== 3/4 approve the fresh close request ==="
run_signed ${PY} tools/run-engagement.py resolve-authority --engagement ${ENG} \
  --request-id auth-close-cli-2026-08-15-final --resolution approved --operator-id matheusht \
  --session-id "$SID" --recorded-at "$NOW" \
  --reason "Operator approves closing angular-cli-2026-08."

echo "=== 4/4 close ==="
run_signed ${PY} tools/run-engagement.py close --engagement ${ENG} \
  --operator-id matheusht --reason "Engagement closed after 7 findings promoted, chains adjudicated, VRP filing prep delivered, winners/losers recorded, cleanup ledger final." \
  --recorded-at "$NOW" --authority-request-id auth-close-cli-2026-08-15-final \
  --lane-id close-lane --executor-id local-uid-501:broker --session-id "$SID"

echo "=== DONE — verify with: run-engagement.py check-resume --engagement ${ENG} ==="
