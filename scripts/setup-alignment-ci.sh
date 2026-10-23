#!/usr/bin/env bash
# Isolated test provisioning only. The application never installs native tools.
set -euo pipefail
alignment_tools="${RUNNER_TEMP:-/tmp}/qualidock-alignment-tools"
mkdir -p "$alignment_tools" validation/htslib-security
alignment_tools="$(cd "$alignment_tools" && pwd)"
repo_root="$PWD"
apt_run=()
if [ "$(id -u)" -ne 0 ]; then apt_run=(sudo); fi
"${apt_run[@]}" apt-get update -qq
"${apt_run[@]}" apt-get install -y build-essential libcurl4-openssl-dev libssl-dev libbz2-dev liblzma-dev zlib1g-dev libdeflate-dev
# Official GitHub release-asset SHA-256, retrieved independently on 2026-10-23.
curl -fsSL https://github.com/samtools/samtools/releases/download/1.24/samtools-1.24.tar.bz2 -o "$alignment_tools/samtools.tar.bz2"
echo "89b2a440123eeaa400392ce1736e7d60ce9041843027d76819753c5a8246bfdd  $alignment_tools/samtools.tar.bz2" | sha256sum --check
tar -xjf "$alignment_tools/samtools.tar.bz2" -C "$alignment_tools"
(
  cd "$alignment_tools/samtools-1.24"
  ./configure --without-curses --with-htslib=htslib-1.24
  make -j2 samtools
)
samtools_bin="$alignment_tools/samtools-1.24/samtools"
"$samtools_bin" --version | tee validation/alignment-tooling.txt
grep -qx 'samtools 1.24' validation/alignment-tooling.txt
grep -qx 'Using htslib 1.24' validation/alignment-tooling.txt
ldd "$samtools_bin" > validation/htslib-security/samtools-linkage.txt
if grep -q 'libhts' validation/htslib-security/samtools-linkage.txt; then
  echo 'Expected release-bundled static HTSlib; unexpected dynamic HTSlib' >&2
  exit 1
fi
sha256sum "$alignment_tools/samtools.tar.bz2" "$samtools_bin" "$alignment_tools/samtools-1.24/htslib-1.24/libhts.a" > validation/htslib-security/toolchain-sha256.txt
cp validation/alignment-tooling.txt validation/htslib-security/
if [ -n "${GITHUB_PATH:-}" ]; then echo "$alignment_tools/samtools-1.24" >> "$GITHUB_PATH"; fi

if [[ " $* " == *" --mosdepth "* ]]; then
  # Upstream's static 0.3.14 binary embeds vulnerable HTSlib 1.22.1. Rebuild
  # the same scientific source/bindings with exact patched library loading.
  # Instrument only --version to report hts_version() from the actual reader.
  "${apt_run[@]}" apt-get install -y nim
  for source in \
    'mosdepth|https://github.com/brentp/mosdepth/archive/refs/tags/v0.3.14.tar.gz|abac67de4547dc5642efd46846044d6b3536d2ca3443b4ca172446edf82eeb42' \
    'hts-nim|https://github.com/brentp/hts-nim/archive/refs/tags/v0.3.31.tar.gz|e2e8572156cced4557fcb75ecf5a7ee072bcc7abf81066d4b54d5bf674dab3e0' \
    'docopt|https://github.com/docopt/docopt.nim/archive/refs/tags/v0.7.1.tar.gz|a172f7e8be5c10735727ca00f69294e8615c4ad055dd9b58dcdb0f7c6bd7d025' \
    'regex|https://github.com/nitely/nim-regex/archive/refs/tags/v0.11.1.tar.gz|c9890246cada2eedee9c4a880073727f4f7025367d9c63bf89e4c50a64eaad67' \
    'unicodedb|https://github.com/nitely/nim-unicodedb/archive/refs/tags/v0.7.0.tar.gz|ccf0fe9ec986420e368d2c1fcbe420d0157a49f5d8cb1fe9489518bbffda374a' \
    'unicodeplus|https://github.com/nitely/nim-unicodeplus/archive/refs/tags/v0.5.0.tar.gz|1649472ef3bcb5f9e8bab2cae402a9394e1aab089ab9a6a7abe05c6d9e9e74d7'; do
    IFS='|' read -r name url digest <<< "$source"
    curl -fsSL "$url" -o "$alignment_tools/$name.tar.gz"
    echo "$digest  $alignment_tools/$name.tar.gz" | sha256sum --check
    tar -xzf "$alignment_tools/$name.tar.gz" -C "$alignment_tools"
  done
  make -C "$alignment_tools/samtools-1.24/htslib-1.24" -j2 lib-shared
  python "$repo_root/scripts/prepare-mosdepth-security-build.py" "$alignment_tools"
  nim --version > validation/htslib-security/nim-version.txt
  nim c --gc:refc -d:release \
    --path:"$alignment_tools/hts-nim-0.3.31/src" \
    --path:"$alignment_tools/docopt.nim-0.7.1/src" \
    --path:"$alignment_tools/nim-regex-0.11.1/src" \
    --path:"$alignment_tools/nim-unicodedb-0.7.0/src" \
    --path:"$alignment_tools/nim-unicodeplus-0.5.0/src" \
    --out:"$alignment_tools/mosdepth" "$alignment_tools/mosdepth-0.3.14/mosdepth.nim"
  "$alignment_tools/mosdepth" --version | tee validation/mosdepth-tooling.txt
  grep -qx 'mosdepth 0.3.14' validation/mosdepth-tooling.txt
  grep -qx 'Using htslib 1.24' validation/mosdepth-tooling.txt
  "$alignment_tools/mosdepth" --help >> validation/mosdepth-tooling.txt
  sha256sum "$alignment_tools/mosdepth" "$alignment_tools/samtools-1.24/htslib-1.24/libhts.so" "$alignment_tools/"*.tar.gz >> validation/htslib-security/toolchain-sha256.txt
  # hts-nim uses dlopen: ldd alone cannot establish its loaded HTSlib.
  LD_DEBUG=libs "$alignment_tools/mosdepth" --version > validation/htslib-security/mosdepth-version.txt 2> validation/htslib-security/mosdepth-loader.txt
  grep -F "$alignment_tools/samtools-1.24/htslib-1.24/libhts.so" validation/htslib-security/mosdepth-loader.txt
  if [ -n "${GITHUB_PATH:-}" ]; then echo "$alignment_tools" >> "$GITHUB_PATH"; fi
fi
