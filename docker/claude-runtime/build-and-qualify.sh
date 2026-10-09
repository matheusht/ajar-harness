#!/bin/sh
set -eu

docker_bin=${DOCKER:-docker}
version=2.1.278
local_image="llm-redteam-harness/claude-runtime:${version}"

"$docker_bin" buildx build \
    --platform linux/arm64 \
    --file "$(dirname "$0")/Dockerfile" \
    --tag "$local_image" \
    --load \
    "$(dirname "$0")"

test "$("$docker_bin" run --rm --pull never "$local_image" claude --version)" = "${version} (Claude Code)"
"$docker_bin" run --rm --pull never "$local_image" claude --help >/dev/null
"$docker_bin" run --rm --pull never "$local_image" python3 --version >/dev/null

if [ "${QUALIFY_LOCAL_ONLY:-0}" = 1 ]; then
    printf '%s\n' "$local_image"
    exit 0
fi

: "${CLAUDE_RUNTIME_REPOSITORY:?set CLAUDE_RUNTIME_REPOSITORY to an operator-owned registry repository}"
case "$CLAUDE_RUNTIME_REPOSITORY" in
    http://*|https://*|*@*|*:*) echo "repository must be a registry path without scheme, tag, or digest" >&2; exit 2 ;;
esac
tagged_image="${CLAUDE_RUNTIME_REPOSITORY}:${version}"
"$docker_bin" tag "$local_image" "$tagged_image"
"$docker_bin" push "$tagged_image" >/dev/null
digest=$("$docker_bin" buildx imagetools inspect "$tagged_image" --format '{{.Manifest.Digest}}')
case "$digest" in
    sha256:????????????????????????????????????????????????????????????????) ;;
    *) echo "qualification failed: invalid manifest digest" >&2; exit 1 ;;
esac
image_ref="${CLAUDE_RUNTIME_REPOSITORY}@${digest}"
"$docker_bin" pull "$image_ref" >/dev/null
test "$("$docker_bin" run --rm --pull never "$image_ref" claude --version)" = "${version} (Claude Code)"
"$docker_bin" run --rm --pull never "$image_ref" claude --help >/dev/null
"$docker_bin" run --rm --pull never "$image_ref" python3 --version >/dev/null
printf '%s\n' "$image_ref"
