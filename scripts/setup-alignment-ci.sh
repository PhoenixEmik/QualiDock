#!/usr/bin/env bash
# Test-only upstream installation; the running application never installs tools.
set -euo pipefail
alignment_tools="${RUNNER_TEMP:-/tmp}/qualidock-alignment-tools"
mkdir -p "$alignment_tools" validation
sudo apt-get update -qq
sudo apt-get install -y libcurl4-openssl-dev libssl-dev libbz2-dev liblzma-dev zlib1g-dev libdeflate-dev
curl -fsSL https://github.com/samtools/samtools/releases/download/1.22.1/samtools-1.22.1.tar.bz2 -o "$alignment_tools/samtools.tar.bz2"
echo "02aa5cd0ba52e06c2080054e059d7d77a885dfe9717c31cd89dfe7a4047eda0e  $alignment_tools/samtools.tar.bz2" | sha256sum --check --status
tar -xjf "$alignment_tools/samtools.tar.bz2" -C "$alignment_tools"
(
  cd "$alignment_tools/samtools-1.22.1"
  ./configure --without-curses
  make -j2 samtools
)
"$alignment_tools/samtools-1.22.1/samtools" --version | tee validation/alignment-tooling.txt
if [ -n "${GITHUB_PATH:-}" ]; then echo "$alignment_tools/samtools-1.22.1" >> "$GITHUB_PATH"; fi

if [[ " $* " == *" --mosdepth "* ]]; then
  curl -fsSL https://github.com/brentp/mosdepth/releases/download/v0.3.14/mosdepth -o "$alignment_tools/mosdepth"
  echo "c5182b74a8f1b66710efa16e122cbc8a197834874b103e7c5c0bd9a6265ae7b6  $alignment_tools/mosdepth" | sha256sum --check --status
  chmod 700 "$alignment_tools/mosdepth"
  "$alignment_tools/mosdepth" --version | tee validation/mosdepth-tooling.txt
  "$alignment_tools/mosdepth" --help >> validation/mosdepth-tooling.txt
  if [ -n "${GITHUB_PATH:-}" ]; then echo "$alignment_tools" >> "$GITHUB_PATH"; fi
fi
