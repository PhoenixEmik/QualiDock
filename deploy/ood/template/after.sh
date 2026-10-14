#!/usr/bin/env bash
set +x
set -euo pipefail
if ! wait_until_port_used "${host}:${port}" 120; then
  echo "QualiDock did not start. Check the Batch Connect output log." >&2
  exit 1
fi
