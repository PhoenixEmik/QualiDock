#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077
exec "${QUALIDOCK_INSTALL}/.venv/bin/qualidock" --host 0.0.0.0 --port "$port"
