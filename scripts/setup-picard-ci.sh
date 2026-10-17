#!/usr/bin/env bash
# Test-only upstream dependencies. The application never installs Java/R/tools.
set -euo pipefail
picard_tools="${RUNNER_TEMP:-/tmp}/qualidock-picard-tools"
mkdir -p "$picard_tools"
curl -fsSL https://github.com/broadinstitute/picard/releases/download/3.5.0/picard.jar -o "$picard_tools/picard.jar"
echo "b7d97861c3a54ba5a421f5a317f38382f955803862d30ef4aca2bcdc54943631  $picard_tools/picard.jar" | sha256sum --check --status
chmod 644 "$picard_tools/picard.jar"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends r-base-core
if [ -n "${GITHUB_PATH:-}" ]; then echo "$picard_tools" >> "$GITHUB_PATH"; fi
if [[ " $* " == *" --study "* ]]; then
  evidence="$PWD/validation/picard-tool-study"
  mkdir -p "$evidence" "$picard_tools/tmp"
  java --version > "$evidence/java.version.txt" 2>&1
  Rscript --version > "$evidence/R.version.txt" 2>&1
  # Picard's version/help parser exits 1 without running an analysis. Require
  # its exact version response; never extend this exception to scientific runs.
  cp "$picard_tools/picard.jar" "$evidence/picard.jar"
  if java -Xmx128m -jar "$picard_tools/picard.jar" CollectInsertSizeMetrics --version > "$evidence/picard.version.txt" 2>&1; then
    version_status=0
  else
    version_status=$?
  fi
  test "$version_status" -eq 1
  grep -qx 'Version:3.5.0' "$evidence/picard.version.txt"
  if java -Xmx128m -jar "$picard_tools/picard.jar" CollectInsertSizeMetrics --help > "$evidence/picard.help.txt" 2>&1; then
    help_status=0
  else
    help_status=$?
  fi
  test "$help_status" -le 1
  grep -q 'CollectInsertSizeMetrics' "$evidence/picard.help.txt"
  grep -q 'INPUT' "$evidence/picard.help.txt"
  echo "version=$version_status help=$help_status" > "$evidence/probe-exit-codes.txt"
  for population in paired single; do
    extra=()
    if [ "$population" = single ]; then extra=(--single); fi
    python scripts/prepare-insert-test.py --output "$picard_tools/$population" "${extra[@]}"
    java -Xms64m -Xmx512m -XX:ActiveProcessorCount=1 -Djava.io.tmpdir="$picard_tools/tmp" -jar "$picard_tools/picard.jar" CollectInsertSizeMetrics \
      "INPUT=$picard_tools/$population/input.bam" "OUTPUT=$evidence/$population.insert_size_metrics.txt" \
      "H=$evidence/$population.histogram.pdf" "TMP_DIR=$picard_tools/tmp" \
      MINIMUM_PCT=0.05 DEVIATIONS=10 INCLUDE_DUPLICATES=false METRIC_ACCUMULATION_LEVEL=ALL_READS \
      ASSUME_SORTED=false VALIDATION_STRINGENCY=STRICT CREATE_INDEX=false CREATE_MD5_FILE=false \
      > "$evidence/$population.stdout.log" 2> "$evidence/$population.stderr.log"
    cp "$picard_tools/$population/input.sam" "$evidence/$population.sam"
  done
fi
