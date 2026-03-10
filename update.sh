#!/bin/bash
set -e
git checkout -- uv.lock 2>/dev/null || true
git pull
rm -rf .venv
uv venv --python 3.13
uv sync --frozen
