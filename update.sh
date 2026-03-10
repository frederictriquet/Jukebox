#!/bin/bash
set -e
git pull
rm -rf .venv
uv venv --python 3.13
uv sync
