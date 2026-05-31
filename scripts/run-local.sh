#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
exec .venv/bin/telegram-laptop-files --config config.local.yaml --require-token
