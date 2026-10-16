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
sudo apt-get update -qq
sudo apt-get install -y bowtie2 libgd-graph-perl
curl -fsSL https://github.com/StevenWingett/FastQ-Screen/archive/refs/tags/v0.16.0.tar.gz -o "$qc_bin/fastq-screen.tar.gz"
echo "4c193cd4755506a1ecb2ae0e325a4d2e47a26ae093786255be46c38a8d8c16ed  $qc_bin/fastq-screen.tar.gz" | sha256sum --check --status
tar -xzf "$qc_bin/fastq-screen.tar.gz" -C "$qc_bin"
chmod 700 "$qc_bin/FastQ-Screen-0.16.0/fastq_screen"
"$qc_bin/FastQ-Screen-0.16.0/fastq_screen" --version
bowtie2 --version
if [ -n "${GITHUB_PATH:-}" ]; then echo "$qc_bin" >> "$GITHUB_PATH"; fi
if [ -n "${GITHUB_PATH:-}" ]; then echo "$qc_bin/FastQ-Screen-0.16.0" >> "$GITHUB_PATH"; fi
