#!/usr/bin/env bash
# Regenerate uv.lock with public PyPI index.
# Use this before pushing when local env uses an internal mirror.
set -euo pipefail
cd "$(dirname "$0")/.."
UV_INDEX_URL=https://pypi.org/simple/ uv lock "$@"
echo "uv.lock regenerated with public PyPI ($(grep -c 'pypi.org' uv.lock) public URLs, $(grep -c 'bytedpypi' uv.lock) internal URLs)"
