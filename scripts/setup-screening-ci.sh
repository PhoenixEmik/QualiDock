#!/usr/bin/env bash
# Explicit isolated CI/development fixture bootstrap. Never called by the app.
set -euo pipefail
screening_ci_root=$(mktemp -d "${RUNNER_TEMP:-/private/tmp}/qualidock-screening.XXXXXX")
screening_ci_root=$(realpath "$screening_ci_root")
screening_source_sha=e1a819d985d1a257e20a8fc57eb27a5d51f4c39e
curl -fsSL "https://codeload.github.com/DerrickWood/kraken2/tar.gz/$screening_source_sha" -o "$screening_ci_root/source.tar.gz"
python - "$screening_ci_root" <<'PY'
import hashlib,sys,tarfile
from pathlib import Path
root=Path(sys.argv[1]);archive=root/'source.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='6c69e6d07ebcbebb8cab8448b4818d40a3c9b24097a97384a5e4f8b0cf4da23c', 'Pinned Kraken2 source archive changed'
with tarfile.open(archive) as source:source.extractall(root,filter='data')
PY
mkdir "$screening_ci_root/bin"
KRAKEN2_SKIP_FOPENMP='' "$screening_ci_root/kraken2-$screening_source_sha/install_kraken2.sh" "$screening_ci_root/bin" > "$screening_ci_root/compile.log" 2>&1
python scripts/prepare-screening-test-db.py --kraken2-dir "$screening_ci_root/bin" --output "$screening_ci_root/database" > "$screening_ci_root/databases.json"
if [[ -n "${GITHUB_ENV:-}" ]]; then
  echo "QUALIDOCK_KRAKEN2=$screening_ci_root/bin/kraken2" >> "$GITHUB_ENV"
  echo "QUALIDOCK_SCREENING_TEST_DB=$screening_ci_root/database" >> "$GITHUB_ENV"
  echo "QUALIDOCK_SCREENING_DATABASES=$(cat "$screening_ci_root/databases.json")" >> "$GITHUB_ENV"
  echo 'QUALIDOCK_REQUIRE_SCREENING_TESTS=1' >> "$GITHUB_ENV"
fi
printf 'Isolated screening fixture root: %s\n' "$screening_ci_root"
