#!/bin/bash
git pull
python -m venv .venv
source .venv/bin/activate
uv sync

