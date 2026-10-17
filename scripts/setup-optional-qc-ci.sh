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
if [[ " $* " == *" --falco-benchmark "* ]]; then
  # Qualification only. There is deliberately no Falco execution mode in the app.
  curl -fsSL https://github.com/smithlabcode/falco/releases/download/v2.0.3/falco-2.0.3-Linux.tar.gz -o "$qc_bin/falco.tar.gz"
  echo "a6e62934a84ee5210f1d7945ee2a806edf01083a52c3afad9abf31a054218d14  $qc_bin/falco.tar.gz" | sha256sum --check --status
  tar -xzf "$qc_bin/falco.tar.gz" -C "$qc_bin"
  "$qc_bin/falco-2.0.3-Linux/bin/falco" --version
  if [ -n "${GITHUB_PATH:-}" ]; then echo "$qc_bin/falco-2.0.3-Linux/bin" >> "$GITHUB_PATH"; fi
  curl -fsSL https://raw.githubusercontent.com/nf-core/test-datasets/d5a0422243620ef4e32c19812ab12edb5dfc882e/testdata/sample_1.fastq.gz -o /tmp/qualidock-million-reads.fastq.gz
  echo "ee1fc6f0213515c1b5d0253ff37e1ad84207c43c059f73011baefd1c97ea9208  /tmp/qualidock-million-reads.fastq.gz" | sha256sum --check --status
  chmod 400 /tmp/qualidock-million-reads.fastq.gz
fi
if [[ " $* " == *" --nanoplot "* ]]; then
  # Isolated external-tool installation, never an application dependency/install.
  python -m venv "$qc_bin/nanoplot-env"
  "$qc_bin/nanoplot-env/bin/pip" install 'NanoPlot==1.48.0' 'nanoget==1.19.6' \
    'numpy==2.2.6' 'pandas==2.2.3' 'scipy==1.15.3' 'plotly==6.1.2'
  "$qc_bin/nanoplot-env/bin/NanoPlot" --version
  mkdir -p validation
  "$qc_bin/nanoplot-env/bin/pip" freeze > validation/nanoplot-tooling.txt
  # Expose only the tool; do not shadow the application's python/pip interpreter.
  ln -s "$qc_bin/nanoplot-env/bin/NanoPlot" "$qc_bin/NanoPlot"
fi
