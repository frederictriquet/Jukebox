.PHONY: help install test lint format type-check clean run sync analyze

help:
	@echo "Available commands:"
	@echo "  make install      Install dependencies (with dev)"
	@echo "  make sync         Sync dependencies from pyproject.toml"
	@echo "  make test         Run tests with coverage"
	@echo "  make lint         Run linting checks"
	@echo "  make format       Format code"
	@echo "  make type-check   Run type checking"
	@echo "  make clean        Clean build artifacts"
	@echo "  make run          Run application"
	@echo "  make ci           Run all CI checks"
	@echo "  make analyze      Analyze tracks (extract ML features)"

install:
	uv sync --all-extras

sync:
	uv sync

test:
	uv run pytest --cov=jukebox --cov-report=html --cov-report=term-missing -v

lint:
	uv run ruff check jukebox tests

format:
	uv run black jukebox tests
	uv run ruff check --fix jukebox tests

type-check:
	uv run mypy jukebox

clean:
	rm -rf dist build *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -f jukebox.log
	rm -f uv.lock

run:
	uv run python -m jukebox.main

# Run all CI checks locally
ci: format lint type-check test
	@echo "All CI checks passed!"

# Analyze tracks (extract ML features for genre classification)
analyze:
	uv run python -m ml.genre_classifier.cli analyze -w 8
