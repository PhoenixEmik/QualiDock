#!/usr/bin/env bash
# Test provisioning only; the application never installs optional QC tools.
set -euo pipefail
qc_bin="${RUNNER_TEMP:-/tmp}/qualidock-optional-qc-tools"
mkdir -p "$qc_bin"
curl -fsSL https://github.com/esteinig/nanoq/releases/download/0.10.0/nanoq-0.10.0-x86_64-unknown-linux-musl.tar.gz -o "$qc_bin/nanoq.tar.gz"
echo "9bad0be294e1d9a2395037d47ff9c1e931420ab02b7371296dbcef8782a81d00  $qc_bin/nanoq.tar.gz" | sha256sum --check --status
tar -xzf "$qc_bin/nanoq.tar.gz" -C "$qc_bin" --strip-components=1 nanoq-0.10.0-x86_64-unknown-linux-musl/nanoq
chmod 700 "$qc_bin/nanoq"
"$qc_bin/nanoq" --version
if [ -n "${GITHUB_PATH:-}" ]; then echo "$qc_bin" >> "$GITHUB_PATH"; fi
