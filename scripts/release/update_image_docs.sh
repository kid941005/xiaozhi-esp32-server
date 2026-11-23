#!/usr/bin/env bash
# 同步 README（以及可选 Release 说明）中的镜像表与 digest。
# 用法：bash scripts/release/update_image_docs.sh v0.9.10 [--notes <file>] [--dh-digest ...] [--ghcr-digest ...]
set -euo pipefail
cd "$(dirname "$0")/../.."
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then PY=python; fi
exec "$PY" scripts/release/update_image_docs.py "$@"
