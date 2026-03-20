.PHONY: help install test lint format type-check clean run sync \
        analyze ml-stats ml-compare ml-train \
        shazamix-index shazamix-stats

# Model type for ml-train (override with: make ml-train ML_MODEL=xgboost)
ML_MODEL ?= random_forest

help:
	@echo "Available commands:"
	@echo "  make install         Install dependencies (with dev)"
	@echo "  make sync            Sync dependencies from pyproject.toml"
	@echo "  make test            Run tests with coverage"
	@echo "  make lint            Run linting checks"
	@echo "  make format          Format code"
	@echo "  make type-check      Run type checking"
	@echo "  make clean           Clean build artifacts"
	@echo "  make run             Run application"
	@echo "  make ci              Run all CI checks"
	@echo ""
	@echo "ML (genre classifier):"
	@echo "  make ml-analyze      Extract ML features from tracks"
	@echo "  make ml-stats        Show dataset statistics"
	@echo "  make ml-compare      Compare all models (rf, xgboost, svm)"
	@echo "  make ml-train        Train best model and deploy to ~/.jukebox/genre_model.pkl"
	@echo "                       Override model: make ml-train ML_MODEL=xgboost"
	@echo ""
	@echo "Shazamix (fingerprinting):"
	@echo "  make shazamix-index  Index tracks (extract audio fingerprints)"
	@echo "  make shazamix-stats  Show fingerprint database statistics"

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
ml-analyze:
	uv run python -m ml.genre_classifier.cli analyze -w 8

# ML: dataset statistics
ml-stats:
	uv run genre-classifier stats

# ML: compare all models
ml-compare:
	uv run genre-classifier compare

# ML: train and deploy model to ~/.jukebox/genre_model.pkl
ml-train:
	uv run genre-classifier train -m $(ML_MODEL) -o ~/.jukebox/genre_model.pkl
	@echo "Model deployed: ~/.jukebox/genre_model.pkl"

# Shazamix: index tracks (extract audio fingerprints)
shazamix-index:
	uv run shazamix index

# Shazamix: show fingerprint database statistics
shazamix-stats:
	uv run shazamix stats
