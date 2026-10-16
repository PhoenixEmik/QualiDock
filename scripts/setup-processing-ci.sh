#!/usr/bin/env bash
# Explicit CI provisioning only. The application never installs tools.
set -euo pipefail
sudo apt-get update -qq
sudo apt-get install -y fastp
processing_bin="${RUNNER_TEMP:-/tmp}/qualidock-processing-tools"
mkdir -p "$processing_bin"
curl -fsSL https://github.com/shenwei356/seqkit/releases/download/v2.14.0/seqkit_linux_amd64.tar.gz -o "$processing_bin/seqkit.tar.gz"
echo "3d664ffb48438d1fbd3f3cfc060c71d00368a26435f1c876944aea7fcdff86b5  $processing_bin/seqkit.tar.gz" | sha256sum --check --status
tar -xzf "$processing_bin/seqkit.tar.gz" -C "$processing_bin" seqkit
chmod 700 "$processing_bin/seqkit"
"$processing_bin/seqkit" version
fastp --version
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$processing_bin" >> "$GITHUB_PATH"
fi
