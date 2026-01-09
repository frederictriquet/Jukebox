"""Tests for search bar."""

from jukebox.ui.components.search_bar import SearchBar


class TestSearchBar:
    """Test SearchBar widget."""

    def test_initialization(self, qapp):  # type: ignore
        """Test search bar initializes correctly."""
        search_bar = SearchBar()
        assert search_bar is not None
        assert search_bar.placeholderText() == "Search tracks..."

    def test_debounce_timer(self, qapp):  # type: ignore
        """Test debounce timer exists."""
        search_bar = SearchBar()
        assert search_bar.debounce_timer is not None
        assert search_bar.debounce_timer.isSingleShot()

    def test_short_text_no_search(self, qapp):  # type: ignore
        """Test short text doesn't trigger search."""
        search_bar = SearchBar()
        search_bar.setText("a")
        # Timer should not be active for single char
        assert not search_bar.debounce_timer.isActive()

    def test_long_text_starts_timer(self, qapp):  # type: ignore
        """Test long text starts debounce timer."""
        search_bar = SearchBar()
        search_bar.setText("abc")
        # Timer should be active for 2+ chars
        assert search_bar.debounce_timer.isActive()
