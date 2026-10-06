#!/usr/bin/env bash
set -euo pipefail
artifact="$RUNNER_TEMP/gitleaks_8.30.1_linux_x64.tar.gz"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz \
  --output "$artifact"
printf '%s  %s\n' 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb "$artifact" | sha256sum --check --strict
tar -xzf "$artifact" -C "$RUNNER_TEMP" gitleaks
printf '%s\n' "$RUNNER_TEMP" >> "$GITHUB_PATH"
