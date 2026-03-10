#!/bin/bash
set -e
git pull
uv venv --python 3.13
uv sync
