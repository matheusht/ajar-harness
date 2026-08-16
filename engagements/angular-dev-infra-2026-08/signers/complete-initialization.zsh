#!/bin/zsh
# Operator-run activation for angular-dev-infra-2026-08.
# An agent prepared this file. Only the operator may execute it — the private key
# must never enter an agent context (engine/gates.md: agents never become the signed operator).
set -euo pipefail

engagement_dir="/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/angular-dev-infra-2026-08"
harness_dir="/Users/matheusvsky/Documents/trab/llm-redteam-harness"
operator_key="/Users/matheusvsky/.ssh/harness-signing/gemini-cli-operator-ed25519"
challenge_file="${engagement_dir}/signers/init-challenge.json"
allowed_signers="${engagement_dir}/signers/operator.allowed_signers"
recorded_at="2026-08-12T12:00:00Z"
expected_scope="9feb17a37cf15bcfa170b3117e253dd5c7243e459225b038dea8b3917b75bf3c"
expected_allowed="ccd13b84d23e9f64b1cb96458b49cb0219ee6115453652e2fbc5e7bf0944b9cc"

actual_scope="$(shasum -a 256 "${engagement_dir}/scope.md" | awk '{print $1}')"
actual_allowed="$(shasum -a 256 "${allowed_signers}" | awk '{print $1}')"

if [[ "${actual_scope}" != "${expected_scope}" ]]; then
  print -u2 "Refusing: scope.md changed after the challenge was frozen."
  print -u2 "  expected ${expected_scope}"
  print -u2 "  actual   ${actual_scope}"
  exit 1
fi

if [[ "${actual_allowed}" != "${expected_allowed}" ]]; then
  print -u2 "Refusing: operator allowed-signers file changed."
  exit 1
fi

if [[ ! -f "${operator_key}" ]]; then
  print -u2 "Refusing: operator private key not found at ${operator_key}."
  exit 1
fi

if [[ -e "${challenge_file}.sig" ]]; then
  print -u2 "Refusing: ${challenge_file}.sig already exists; preserve it for review or move it explicitly."
  exit 1
fi

/usr/bin/ssh-keygen -Y sign \
  -f "${operator_key}" \
  -n llm-redteam-harness-operator-v1 \
  "${challenge_file}"

cd "${harness_dir}"
HARNESS_OPERATOR_SIGNATURE_FILE="${challenge_file}.sig" \
HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE="${allowed_signers}" \
  ./.venv/bin/python tools/run-engagement.py init \
    --engagement "${engagement_dir}" \
    --recorded-at "${recorded_at}"

print "Initialization recorded. Scope attested at ${expected_scope}."
