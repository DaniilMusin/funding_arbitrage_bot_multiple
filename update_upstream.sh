#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d "hummingbot" ]]; then
  echo "[ERROR] 'hummingbot' submodule directory not found. Did you clone with --recurse-submodules?" >&2
  exit 1
fi

echo "[INFO] Updating upstream submodule 'hummingbot'..."
git submodule update --init --remote hummingbot

upstream_ref=$(git -C hummingbot rev-parse --short HEAD)
echo "[INFO] Upstream at ${upstream_ref}"

echo "[INFO] Recording upstream ref in .upstream-version"
echo "${upstream_ref}" > .upstream-version

echo "[OK] Upstream updated. Run your test suite to verify compatibility."
