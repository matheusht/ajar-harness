FROM node:24.13.0-bookworm-slim@sha256:4660b1ca8b28d6d1906fd644abe34b2ed81d15434d26d845ef0aced307cf4b6f

ARG TARGETARCH
ARG CLAUDE_VERSION=2.1.278
ARG CLAUDE_PACKAGE_INTEGRITY=sha512-mfNRqC0GaEXqmP97NiwJBeYBmRuqe2VzgLUreUUaEhyJxJWx2Z6ClW1tBOncGNNXdhj6EY4LPvUIWP+oq311CA==
ARG CLAUDE_LINUX_ARM64_INTEGRITY=sha512-QAsHwRVX03nXgAA7pTdvZSLguegbAAPuLG1vY09YHhkukqD6FlkSDwYqK9XFh4up8rFjK7qrzXtokuNULP0nEg==

RUN apt-get update \
 && apt-get install --yes --no-install-recommends ca-certificates python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/claude-install
RUN test "$TARGETARCH" = arm64 \
 && npm pack --json "@anthropic-ai/claude-code@${CLAUDE_VERSION}" > main.json \
 && npm pack --json "@anthropic-ai/claude-code-linux-arm64@${CLAUDE_VERSION}" > platform.json \
 && python3 - "$CLAUDE_PACKAGE_INTEGRITY" "$CLAUDE_LINUX_ARM64_INTEGRITY" <<'PY'
import json
import pathlib
import sys

for filename, expected in zip(("main.json", "platform.json"), sys.argv[1:], strict=True):
    rows = json.loads(pathlib.Path(filename).read_text(encoding="utf-8"))
    if len(rows) != 1 or rows[0].get("integrity") != expected:
        raise SystemExit(f"registry integrity mismatch: {filename}")
PY
RUN npm install --global --omit=optional \
      ./anthropic-ai-claude-code-${CLAUDE_VERSION}.tgz \
      ./anthropic-ai-claude-code-linux-arm64-${CLAUDE_VERSION}.tgz \
 && test "$(claude --version)" = "${CLAUDE_VERSION} (Claude Code)" \
 && claude --help >/dev/null \
 && python3 --version \
 && rm -rf /opt/claude-install /root/.npm

WORKDIR /workspace
USER node

