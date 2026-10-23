#!/usr/bin/env bash
# Isolated qualification tools only; never called by a running QualiDock session.
set -euo pipefail
variant_tools="${RUNNER_TEMP:-/tmp}/qualidock-variant-tools"
mkdir -p "$variant_tools" validation/variant-tooling
apt_run=()
if [ "$(id -u)" -ne 0 ]; then apt_run=(sudo); fi
"${apt_run[@]}" apt-get update -qq
"${apt_run[@]}" apt-get install -y build-essential libcurl4-openssl-dev libbz2-dev liblzma-dev zlib1g-dev libdeflate-dev
# Official release-asset SHA-256 from repos/samtools/bcftools/releases/tags/1.24.
curl -fsSL https://github.com/samtools/bcftools/releases/download/1.24/bcftools-1.24.tar.bz2 -o "$variant_tools/bcftools.tar.bz2"
echo "8caddc22610ee2851666047c859bb91da0c1e32d0c2ec553db6f153ad130e46f  $variant_tools/bcftools.tar.bz2" | sha256sum --check
tar -xjf "$variant_tools/bcftools.tar.bz2" -C "$variant_tools"
(
  cd "$variant_tools/bcftools-1.24"
  ./configure --with-htslib=htslib-1.24
  make -j2 bcftools
) > validation/variant-tooling/build.log 2>&1
"$variant_tools/bcftools-1.24/bcftools" --version | tee validation/variant-tooling/version.txt
grep -qx 'bcftools 1.24' validation/variant-tooling/version.txt
grep -qx 'Using htslib 1.24' validation/variant-tooling/version.txt
ldd "$variant_tools/bcftools-1.24/bcftools" > validation/variant-tooling/linkage.txt
if grep -q 'libhts' validation/variant-tooling/linkage.txt; then
  echo 'Unexpected system HTSlib: qualification requires the release-bundled static reader' >&2
  exit 1
fi
sha256sum "$variant_tools/bcftools.tar.bz2" "$variant_tools/bcftools-1.24/bcftools" "$variant_tools/bcftools-1.24/htslib-1.24/libhts.a" > validation/variant-tooling/sha256.txt
if [ -n "${GITHUB_PATH:-}" ]; then echo "$variant_tools/bcftools-1.24" >> "$GITHUB_PATH"; fi
