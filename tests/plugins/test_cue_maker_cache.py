"""Tests for cue maker cache module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from plugins.cue_maker.cache import load_cached_entries


class TestCueMakerCache:
    """Test cache error handling and logging."""

    def test_load_cached_entries_oserror_logs_debug(self, caplog) -> None:  # type: ignore
        """Test load_cached_entries logs debug message when OSError occurs."""
        # OSError can happen if mix file is deleted after being loaded
        # _cache_key() calls Path.stat() which raises OSError if file doesn't exist
        fake_path = "/nonexistent/deleted_mix.mp3"

        with caplog.at_level("DEBUG"):
            result = load_cached_entries(fake_path)

        assert result is None
        assert any(
            "Cannot stat mix file for cache key" in record.message and fake_path in record.message
            for record in caplog.records
        )

    def test_load_cached_entries_handles_missing_file_gracefully(self) -> None:  # type: ignore
        """Test load_cached_entries returns None when cache file doesn't exist."""
        # This tests the normal case where cache simply doesn't exist yet
        fake_path = "/some/valid/path/mix.mp3"

        with patch("plugins.cue_maker.cache._cache_key") as mock_cache_key:
            mock_cache_key.return_value = "fake_hash"
            result = load_cached_entries(fake_path)

        assert result is None
