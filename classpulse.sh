#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo "Missing local .venv; install requirements before launching." >&2
    exit 1
fi
exec "$ROOT/.venv/bin/python" "$ROOT/deploy/local_service_manager.py" "$@"
