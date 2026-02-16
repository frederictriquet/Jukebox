#!/bin/bash
# Analyze tracks - can be run from any directory
# Usage: ./scripts/analyze.sh [--limit N] [other options...]

set -e

# Resolve project root (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"
source "$PROJECT_DIR"/.envrc
# exec uv run python -m ml.genre_classifier.cli analyze -w 8 -l 1
exec uv run shazamix index --mode jukebox -w 8 -l 10