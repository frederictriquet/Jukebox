"""Search and filter plugin - unified management of search bar and genre filters.

This plugin manages genre filter buttons in a centralized way and installs a
proxy model on the track list for real-time filtering. It operates in two modes:

- **jukebox/curating modes**: genre buttons live in `genre_buttons_area` (below
  the search bar in the main layout), managed as `genre_buttons`.
- **cue_maker mode**: genre buttons live in the BottomDrawer, created on demand
  via `get_drawer_genre_buttons_container()` and tracked as `_drawer_buttons`.

In cue_maker mode, search and genre filtering are handled entirely by the
GenreFilterProxyModel — the database FTS5 is bypassed. This avoids the DB
returning 0 tracks when queried with mode="cue_maker".

Button state (ON/OFF/INDIFFERENT) is persisted across mode switches via the
`_genre_states` dict, which is updated by `_on_filter_changed()` and restored
when a new button set is created (toolbar or drawer).

Advanced filter mode allows arbitrary boolean expressions like
``(D or H) and not P``. When active, the expression overrides button-based
filtering. Both modes are saveable as presets (button presets store genre states;
expression presets store the ``_expr`` key).

Events:
- Subscribes to: TRACKS_ADDED
- Emits: GENRE_FILTER_CHANGED
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


# ============================================================================
# Genre expression parser
# ============================================================================

# A compiled genre filter: takes the set of genre codes for a track, returns bool.
GenreEval = Callable[[set[str]], bool]


class _TokenStream:
    """Minimal token stream for the recursive-descent expression parser."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def consume(self, expected: str | None = None) -> str:
        if self._pos >= len(self._tokens):
            raise ValueError("Unexpected end of expression")
        token = self._tokens[self._pos]
        if expected is not None and token != expected:
            raise ValueError(f"Expected '{expected}', got '{token}'")
        self._pos += 1
        return token

    def is_empty(self) -> bool:
        return self._pos >= len(self._tokens)


def _tokenize_expr(expr: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    s = expr.upper()
    while i < len(s):
        if s[i].isspace():
            i += 1
        elif s[i] in ("(", ")"):
            tokens.append(s[i])
            i += 1
        elif s[i].isalpha():
            j = i
            while j < len(s) and s[j].isalpha():
                j += 1
            tokens.append(s[i:j])
            i = j
        else:
            raise ValueError(f"Unexpected character: '{s[i]}'")
    return tokens


def _parse_or(stream: _TokenStream, valid: set[str]) -> GenreEval:
    left = _parse_and(stream, valid)
    while stream.peek() == "OR":
        stream.consume()
        right = _parse_and(stream, valid)
        left = (lambda lhs, rhs: lambda g: lhs(g) or rhs(g))(left, right)
    return left


def _parse_and(stream: _TokenStream, valid: set[str]) -> GenreEval:
    left = _parse_not(stream, valid)
    while stream.peek() == "AND":
        stream.consume()
        right = _parse_not(stream, valid)
        left = (lambda lhs, rhs: lambda g: lhs(g) and rhs(g))(left, right)
    return left


def _parse_not(stream: _TokenStream, valid: set[str]) -> GenreEval:
    if stream.peek() == "NOT":
        stream.consume()
        operand = _parse_not(stream, valid)
        return (lambda o: lambda g: not o(g))(operand)
    return _parse_atom(stream, valid)


def _parse_atom(stream: _TokenStream, valid: set[str]) -> GenreEval:
    token = stream.peek()
    if token == "(":
        stream.consume()
        result = _parse_or(stream, valid)
        stream.consume(")")
        return result
    if token is not None and token not in ("AND", "OR", "NOT", "(", ")", None):
        stream.consume()
        if token not in valid:
            raise ValueError(f"Unknown genre code: '{token}'")
        return (lambda t: lambda g: t in g)(token)
    raise ValueError(f"Unexpected token: '{token}'")


def compile_genre_expr(expr: str, valid_codes: set[str]) -> GenreEval:
    """Compile a boolean genre expression string into a callable.

    Syntax: ``CODE``, ``not EXPR``, ``EXPR and EXPR``, ``EXPR or EXPR``,
    ``( EXPR )``. Codes are case-insensitive. Raises ``ValueError`` on error.
    """
    tokens = _tokenize_expr(expr)
    if not tokens:
        raise ValueError("Empty expression")
    stream = _TokenStream(tokens)
    result = _parse_or(stream, {c.upper() for c in valid_codes})
    if not stream.is_empty():
        raise ValueError(f"Unexpected token after expression: '{stream.peek()}'")
    return result


# ============================================================================
# Proxy model
# ============================================================================


class GenreFilterState(IntEnum):
    """State of a genre filter button."""

    INDIFFERENT = 0
    ON = 1
    OFF = 2


class GenreFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that filters tracks by genre and search."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._on_genres: set[str] = set()
        self._off_genres: set[str] = set()
        self._search_text: str = ""
        self._expr_fn: GenreEval | None = None

    def set_search_text(self, text: str) -> None:
        self._search_text = text.lower()
        self.invalidateFilter()

    def set_genre_filter(self, on_genres: set[str], off_genres: set[str]) -> None:
        self._on_genres = on_genres
        self._off_genres = off_genres
        self.invalidateFilter()

    def set_genre_expr(self, expr_fn: GenreEval | None) -> None:
        """Set a compiled expression filter (overrides ON/OFF buttons when not None)."""
        self._expr_fn = expr_fn
        self.invalidateFilter()

    def filterAcceptsRow(  # noqa: N802
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        source_model = self.sourceModel()
        if source_model is None:
            return True

        tracks: list[dict[str, Any]] = getattr(source_model, "tracks", [])
        if source_row >= len(tracks):
            return True

        track = tracks[source_row]

        # Search filter: every word must appear in at least one field
        if self._search_text:
            artist = (track.get("artist") or "").lower()
            title = (track.get("title") or "").lower()
            filename = (track.get("filename") or "").lower()
            haystack = f"{artist} {title} {filename}"
            for word in self._search_text.split():
                if word not in haystack:
                    return False

        # Parse track genre codes
        genre_str = track.get("genre", "") or ""
        track_genres: set[str] = set()
        for part in genre_str.split("-"):
            code = part.strip()
            if code and not code.startswith("*"):
                track_genres.add(code)

        # Advanced expression filter (overrides ON/OFF when active)
        if self._expr_fn is not None:
            return self._expr_fn(track_genres)

        # Button-based ON/OFF filter
        if not self._on_genres and not self._off_genres:
            return True
        for g in self._on_genres:
            if g not in track_genres:
                return False
        return all(g not in track_genres for g in self._off_genres)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:  # noqa: N802
        """Delegate sorting to the source model to use numeric keys (not DisplayRole strings)."""
        source = self.sourceModel()
        if source is not None:
            source.sort(column, order)
            self.invalidate()


# ============================================================================
# Genre filter button
# ============================================================================


class GenreFilterButton(QPushButton):
    """Button that cycles through indifferent/on/off states."""

    _STYLES = {
        GenreFilterState.INDIFFERENT: (
            "background-color: #555; color: #aaa; font-weight: bold; font-size: 13px;"
        ),
        GenreFilterState.ON: (
            "background-color: #2d7a2d; color: white; font-weight: bold; font-size: 13px;"
        ),
        GenreFilterState.OFF: (
            "background-color: #7a2d2d; color: white; font-weight: bold; font-size: 13px;"
        ),
    }

    def __init__(self, code: str, name: str, parent: Any = None) -> None:
        super().__init__(code, parent)
        self.code = code
        self.genre_name = name
        self.state = GenreFilterState.INDIFFERENT
        self.setFixedSize(32, 26)
        self.setToolTip(name)
        self._apply_style()
        self.clicked.connect(self._cycle)

    def _cycle(self) -> None:
        self.state = GenreFilterState((self.state + 1) % 3)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(self._STYLES[self.state])


# ============================================================================
# Plugin
# ============================================================================

_COMBO_STYLE = (
    "QComboBox { background-color: #444; color: #ccc; border: 1px solid #666;"
    " border-radius: 3px; padding: 1px 4px; font-size: 12px; }"
    "QComboBox::drop-down { border: none; }"
    "QComboBox QAbstractItemView { background-color: #333; color: #ccc;"
    " selection-background-color: #555; }"
)
_BTN_NEUTRAL = (
    "QPushButton { background-color: #444; color: #ccc; border: 1px solid #666;"
    " border-radius: 3px; font-size: 14px; font-weight: bold; }"
)
_INPUT_BASE = (
    "QLineEdit {{ background-color: #333; color: #ccc; border: 1px solid {border};"
    " border-radius: 3px; padding: 1px 4px; font-family: monospace; font-size: 12px; }}"
)


class SearchAndFilterPlugin:
    """Centralized search and genre filter plugin.

    Maintains two independent sets of genre filter buttons:

    - ``genre_buttons`` / ``toolbar_container``: created once in ``register_ui``
      and placed in ``main_window.genre_buttons_area``. Used in jukebox and
      curating modes.
    - ``_drawer_buttons``: created on each call to
      ``get_drawer_genre_buttons_container()``, placed inside the cue_maker
      BottomDrawer. Automatically cleared when the drawer container is destroyed.

    Both sets share ``_genre_states`` and the advanced expression ``_advanced_expr``
    across mode switches. When ``_advanced_active`` is True the proxy uses a
    compiled ``GenreEval`` instead of the ON/OFF sets.

    Active in: jukebox, cue_maker modes
    """

    name = "search_and_filter"
    version = "1.0.0"
    description = "Centralized search and genre filter management"
    modes = ["jukebox", "cue_maker"]

    _NO_PRESET = "— none —"
    _EXPR_KEY = "_expr"  # key used in preset dicts for expression presets

    def __init__(self) -> None:
        self.context: PluginContextProtocol | None = None
        self.proxy: GenreFilterProxyModel | None = None

        # Toolbar button set
        self.genre_buttons: list[GenreFilterButton] = []
        self.toolbar_container: QWidget | None = None

        # Drawer button set (created on demand)
        self._drawer_buttons: list[GenreFilterButton] = []

        # Persisted button states across mode switches
        self._genre_states: dict[str, GenreFilterState] = {}
        self._valid_codes: set[str] = set()
        self._track_list: Any = None

        # Presets: {name: {code: int}} or {name: {"_expr": str}}
        self._presets: dict[str, dict[str, Any]] = {}
        self._preset_combo: QComboBox | None = None
        self._drawer_preset_combo: QComboBox | None = None

        # Advanced expression filter
        self._advanced_active: bool = False
        self._advanced_expr: str = ""
        self._genre_area: QWidget | None = None  # toolbar area for height resizing
        self._advanced_row: QWidget | None = None  # toolbar advanced row
        self._drawer_advanced_row: QWidget | None = None
        self._advanced_input: QLineEdit | None = None
        self._drawer_advanced_input: QLineEdit | None = None
        self._advanced_status: QLabel | None = None
        self._drawer_advanced_status: QLabel | None = None
        self._advanced_toggle_buttons: list[QPushButton] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, context: PluginContextProtocol) -> None:
        self.context = context
        context.subscribe(Events.TRACKS_ADDED, self._on_tracks_added)
        self._valid_codes = {c.code.upper() for c in context.config.genre_editor.codes}
        self._load_presets()
        logging.info("[Search & Filter] Plugin initialized")

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        if not self.context:
            return

        self.proxy = GenreFilterProxyModel()
        main_window = ui_builder.main_window
        self._track_list = main_window.track_list
        self._track_list.set_proxy_model(self.proxy)

        if hasattr(main_window, "search_bar"):
            main_window.search_bar.search_triggered.connect(self._on_search)

        self._create_toolbar_buttons()

        if hasattr(main_window, "genre_buttons_area") and self.toolbar_container:
            area = main_window.genre_buttons_area
            self._genre_area = area
            area_layout = QVBoxLayout(area)
            area_layout.setContentsMargins(0, 0, 0, 0)
            area_layout.setSpacing(0)
            area_layout.addWidget(self.toolbar_container)
            area.setFixedHeight(30)
            logging.info("[Search & Filter] Added genre buttons to genre_buttons_area")

        logging.info("[Search & Filter] Registered with %d genre buttons", len(self.genre_buttons))

    def activate(self, mode: str) -> None:
        if not self.toolbar_container and self.context:
            self._create_toolbar_buttons()

        for btn in self.genre_buttons:
            if btn.code in self._genre_states:
                btn.state = self._genre_states[btn.code]
                btn._apply_style()

        if self._advanced_active and self._advanced_expr:
            self._apply_advanced_expr(self._advanced_expr)
        else:
            self._on_filter_changed()
        logging.info("[Search & Filter] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        if self.proxy:
            self.proxy.set_genre_filter(set(), set())
            self.proxy.set_genre_expr(None)
            self.proxy.set_search_text("")
        logging.info("[Search & Filter] Deactivated from %s mode", mode)

    def shutdown(self) -> None:
        if self._track_list:
            self._track_list.remove_proxy_model()
        self._track_list = None
        self.proxy = None
        self.genre_buttons.clear()

    # ------------------------------------------------------------------
    # Button container builders
    # ------------------------------------------------------------------

    def _create_toolbar_buttons(self) -> None:
        """Create the two-row toolbar container (row1: buttons; row2: advanced input)."""
        if not self.context or self.toolbar_container:
            return

        sorted_codes = sorted(self.context.config.genre_editor.codes, key=lambda c: c.code)

        self.toolbar_container = QWidget()
        vbox = QVBoxLayout(self.toolbar_container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Row 1 — genre buttons + preset controls + advanced toggle
        row1 = QWidget()
        row1.setFixedHeight(30)
        hbox = QHBoxLayout(row1)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(6)

        label = QLabel("Genres")
        label.setStyleSheet("font-weight: bold; font-size: 12px; color: #aaa;")
        hbox.addWidget(label)

        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            btn.clicked.connect(self._on_filter_changed)
            self.genre_buttons.append(btn)
            hbox.addWidget(btn)

        self._preset_combo = self._build_preset_controls(hbox)
        self._build_advanced_toggle(hbox)
        hbox.addStretch()
        vbox.addWidget(row1)

        # Row 2 — advanced expression input (hidden by default)
        row2 = self._build_advanced_row(is_toolbar=True)
        self._advanced_row = row2
        if not self._advanced_active:
            row2.hide()
        vbox.addWidget(row2)

    def get_drawer_genre_buttons_container(self) -> QWidget:
        """Get a SEPARATE container with genre buttons + advanced filter for the drawer."""
        if not self.context:
            return QWidget()

        sorted_codes = sorted(self.context.config.genre_editor.codes, key=lambda c: c.code)

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Row 1
        row1 = QWidget()
        row1.setFixedHeight(30)
        hbox = QHBoxLayout(row1)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(6)

        label = QLabel("Genres")
        label.setStyleSheet("font-weight: bold; font-size: 12px; color: #aaa;")
        hbox.addWidget(label)

        self._drawer_buttons = []
        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            if code_config.code in self._genre_states:
                btn.state = self._genre_states[code_config.code]
                btn._apply_style()
            btn.clicked.connect(self._on_filter_changed)
            self._drawer_buttons.append(btn)
            hbox.addWidget(btn)

        self._drawer_preset_combo = self._build_preset_controls(hbox)
        self._build_advanced_toggle(hbox)
        hbox.addStretch()
        vbox.addWidget(row1)

        # Row 2
        row2 = self._build_advanced_row(is_toolbar=False)
        self._drawer_advanced_row = row2
        if not self._advanced_active:
            row2.hide()
        vbox.addWidget(row2)

        container.destroyed.connect(self._clear_drawer_buttons)
        return container

    # ------------------------------------------------------------------
    # Preset controls builder
    # ------------------------------------------------------------------

    def _build_preset_controls(self, layout: QHBoxLayout) -> QComboBox:
        """Add separator + preset combobox + save/delete buttons to *layout*."""
        _add_vsep(layout)

        combo = QComboBox()
        combo.setFixedWidth(130)
        combo.setStyleSheet(_COMBO_STYLE)
        self._populate_preset_combo(combo)
        combo.activated.connect(lambda _idx: self._on_preset_activated(combo))
        layout.addWidget(combo)

        save_btn = QPushButton("+")
        save_btn.setFixedSize(22, 26)
        save_btn.setToolTip("Save current preset")
        save_btn.setStyleSheet(
            _BTN_NEUTRAL + "QPushButton:hover { background-color: #2d7a2d; color: white; }"
        )
        save_btn.clicked.connect(lambda: self._on_save_preset(combo))
        layout.addWidget(save_btn)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(22, 26)
        del_btn.setToolTip("Delete selected preset")
        del_btn.setStyleSheet(
            _BTN_NEUTRAL + "QPushButton:hover { background-color: #7a2d2d; color: white; }"
        )
        del_btn.clicked.connect(lambda: self._on_delete_preset(combo))
        layout.addWidget(del_btn)

        return combo

    # ------------------------------------------------------------------
    # Advanced filter UI builders
    # ------------------------------------------------------------------

    def _build_advanced_toggle(self, layout: QHBoxLayout) -> None:
        """Add separator + checkable 'Advanced' button to *layout*."""
        _add_vsep(layout)

        btn = QPushButton("Advanced")
        btn.setCheckable(True)
        btn.setChecked(self._advanced_active)
        btn.setFixedHeight(22)
        btn.setStyleSheet(
            "QPushButton { background-color: #444; color: #888; border: 1px solid #666;"
            " border-radius: 3px; font-size: 11px; padding: 0 6px; }"
            "QPushButton:checked { background-color: #3a4a6a; color: #aac4ff;"
            " border-color: #5577aa; }"
            "QPushButton:hover { background-color: #555; }"
        )
        btn.toggled.connect(self._on_advanced_toggled)
        self._advanced_toggle_buttons.append(btn)
        layout.addWidget(btn)

    def _build_advanced_row(self, *, is_toolbar: bool) -> QWidget:
        """Create the advanced expression input row widget."""
        row = QWidget()
        row.setFixedHeight(28)
        hbox = QHBoxLayout(row)
        hbox.setContentsMargins(2, 1, 2, 1)
        hbox.setSpacing(6)

        lbl = QLabel("Filter:")
        lbl.setStyleSheet("font-size: 12px; color: #888;")
        hbox.addWidget(lbl)

        inp = QLineEdit()
        inp.setPlaceholderText("e.g.  (D or H) and not P")
        inp.setText(self._advanced_expr)
        inp.setStyleSheet(_INPUT_BASE.format(border="#666"))
        inp.textChanged.connect(self._on_advanced_text_changed)
        hbox.addWidget(inp)

        status = QLabel("")
        status.setFixedWidth(16)
        status.setStyleSheet("font-size: 13px;")
        hbox.addWidget(status)

        if is_toolbar:
            self._advanced_input = inp
            self._advanced_status = status
        else:
            self._drawer_advanced_input = inp
            self._drawer_advanced_status = status

        return row

    # ------------------------------------------------------------------
    # Advanced filter state management
    # ------------------------------------------------------------------

    def _on_advanced_toggled(self, checked: bool) -> None:
        """Slot for the Advanced toggle button."""
        self._set_advanced_mode(checked)

    def _set_advanced_mode(self, active: bool, *, apply: bool = True) -> None:
        """Master switch for advanced mode — updates all UI and the proxy."""
        if self._advanced_active == active:
            return
        self._advanced_active = active

        self._set_advanced_rows_visible(active)
        if not active and self.proxy:
            self.proxy.set_genre_expr(None)

        # Sync all toggle buttons without triggering this slot again
        for btn in self._advanced_toggle_buttons:
            try:
                btn.blockSignals(True)
                btn.setChecked(active)
                btn.blockSignals(False)
            except RuntimeError:
                pass

        if apply:
            if active:
                self._apply_advanced_expr(self._advanced_expr)
            else:
                self._on_filter_changed()

    def _activate_advanced_with_expr(self, expr: str) -> None:
        """Switch to advanced mode, populate the input, and apply *expr*."""
        self._advanced_expr = expr
        # Populate inputs before _set_advanced_mode triggers _apply_advanced_expr
        for inp in (self._advanced_input, self._drawer_advanced_input):
            if inp is not None:
                try:
                    inp.blockSignals(True)
                    inp.setText(expr)
                    inp.blockSignals(False)
                except RuntimeError:
                    pass
        self._set_advanced_mode(True)

    def _set_advanced_rows_visible(self, visible: bool) -> None:
        for row in (self._advanced_row, self._drawer_advanced_row):
            if row is not None:
                try:
                    row.setVisible(visible)
                except RuntimeError:
                    pass
        if self._genre_area is not None:
            try:
                self._genre_area.setFixedHeight(60 if visible else 30)
            except RuntimeError:
                pass

    def _on_advanced_text_changed(self, text: str) -> None:
        """Apply expression and sync the other input (toolbar ↔ drawer)."""
        self._apply_advanced_expr(text)
        for inp in (self._advanced_input, self._drawer_advanced_input):
            if inp is None:
                continue
            try:
                if inp.text() != text:
                    inp.blockSignals(True)
                    inp.setText(text)
                    inp.blockSignals(False)
            except RuntimeError:
                pass

    def _apply_advanced_expr(self, expr: str) -> None:
        """Compile *expr* and push it to the proxy; update status indicators."""
        if not self.context:
            return
        text = expr.strip()
        if not text:
            self._advanced_expr = ""
            if self.proxy:
                self.proxy.set_genre_expr(None)
                # Fall back to button-based filter
                self._push_button_filter()
            self._set_expr_status(None, "")
            return

        try:
            fn = compile_genre_expr(text, self._valid_codes)
            self._advanced_expr = text
            if self.proxy:
                self.proxy.set_genre_expr(fn)
            self._set_expr_status(True, "")
        except ValueError as exc:
            self._set_expr_status(False, str(exc))

    def _set_expr_status(self, valid: bool | None, tooltip: str) -> None:
        """Update the border colour and status icon on all advanced inputs."""
        if valid is None:
            border, icon = "#666", ""
        elif valid:
            border, icon = "#2d7a2d", "✓"
        else:
            border, icon = "#7a2d2d", "✗"

        style = _INPUT_BASE.format(border=border)
        for inp, lbl in (
            (self._advanced_input, self._advanced_status),
            (self._drawer_advanced_input, self._drawer_advanced_status),
        ):
            if inp is not None:
                try:
                    inp.setStyleSheet(style)
                except RuntimeError:
                    pass
            if lbl is not None:
                try:
                    lbl.setText(icon)
                    lbl.setToolTip(tooltip)
                except RuntimeError:
                    pass

    @staticmethod
    def _build_genre_sets(buttons: list[GenreFilterButton]) -> tuple[set[str], set[str]]:
        """Return (on_genres, off_genres) from button states."""
        on_genres: set[str] = set()
        off_genres: set[str] = set()
        for btn in buttons:
            if btn.state == GenreFilterState.ON:
                on_genres.add(btn.code)
            elif btn.state == GenreFilterState.OFF:
                off_genres.add(btn.code)
        return on_genres, off_genres

    def _push_button_filter(self) -> None:
        """Push current button ON/OFF sets to the proxy (without emitting events)."""
        active = self._drawer_buttons if self._drawer_buttons else self.genre_buttons
        on_genres, off_genres = self._build_genre_sets(active)
        if self.proxy:
            self.proxy.set_genre_filter(on_genres, off_genres)

    # ------------------------------------------------------------------
    # Preset management
    # ------------------------------------------------------------------

    def _load_presets(self) -> None:
        if not self.context:
            return
        try:
            raw = self.context.database.settings.get("search_and_filter", "genre_presets")
            if raw:
                self._presets = json.loads(raw)
        except Exception:
            self._presets = {}

    def _save_presets_to_db(self) -> None:
        if not self.context:
            return
        try:
            self.context.database.settings.save(
                "search_and_filter", "genre_presets", json.dumps(self._presets)
            )
        except Exception as exc:
            logging.warning("[Search & Filter] Failed to save presets: %s", exc)

    def _populate_preset_combo(self, combo: QComboBox) -> None:
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem(self._NO_PRESET)
            for pname in sorted(self._presets.keys()):
                combo.addItem(pname)
            combo.setCurrentIndex(0)
        finally:
            combo.blockSignals(False)

    def _sync_preset_combos(self) -> None:
        for combo in (self._preset_combo, self._drawer_preset_combo):
            if combo is None:
                continue
            try:
                self._populate_preset_combo(combo)
            except RuntimeError:
                pass

    def _on_preset_activated(self, combo: QComboBox) -> None:
        name = combo.currentText()
        active_buttons = self._drawer_buttons if self._drawer_buttons else self.genre_buttons

        if name == self._NO_PRESET:
            self._set_advanced_mode(False, apply=False)
            self._clear_advanced_inputs()
            for btn in active_buttons:
                btn.state = GenreFilterState.INDIFFERENT
                btn._apply_style()
            self._on_filter_changed()
            return

        if not name or name not in self._presets:
            return

        preset = self._presets[name]
        if self._EXPR_KEY in preset:
            for btn in active_buttons:
                btn.state = GenreFilterState.INDIFFERENT
                btn._apply_style()
            self._activate_advanced_with_expr(preset[self._EXPR_KEY])
        else:
            self._set_advanced_mode(False, apply=False)
            self._clear_advanced_inputs()
            for btn in active_buttons:
                btn.state = GenreFilterState(
                    preset.get(btn.code, int(GenreFilterState.INDIFFERENT))
                )
                btn._apply_style()
            self._on_filter_changed()

    def _clear_advanced_inputs(self) -> None:
        """Reset advanced expression text and status without triggering the filter."""
        self._advanced_expr = ""
        for inp in (self._advanced_input, self._drawer_advanced_input):
            if inp is not None:
                try:
                    inp.blockSignals(True)
                    inp.setText("")
                    inp.blockSignals(False)
                except RuntimeError:
                    pass
        self._set_expr_status(None, "")

    def _on_save_preset(self, combo: QComboBox) -> None:
        name, ok = QInputDialog.getText(combo, "New preset", "Preset name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if self._advanced_active and self._advanced_expr:
            self._presets[name] = {self._EXPR_KEY: self._advanced_expr}
        else:
            active_buttons = self._drawer_buttons if self._drawer_buttons else self.genre_buttons
            self._presets[name] = {btn.code: int(btn.state) for btn in active_buttons}
        self._save_presets_to_db()
        self._sync_preset_combos()
        idx = combo.findText(name)
        if idx >= 0:
            try:
                combo.setCurrentIndex(idx)
            except RuntimeError:
                pass
        logging.info("[Search & Filter] Preset '%s' saved", name)

    def _on_delete_preset(self, combo: QComboBox) -> None:
        name = combo.currentText()
        if not name or name == self._NO_PRESET or name not in self._presets:
            return
        self._presets.pop(name)
        self._save_presets_to_db()
        self._sync_preset_combos()
        logging.info("[Search & Filter] Preset '%s' deleted", name)

    # ------------------------------------------------------------------
    # Search / filter handlers
    # ------------------------------------------------------------------

    def _on_search(self, text: str) -> None:
        if self.proxy:
            self.proxy.set_search_text(text)

    def _on_filter_changed(self) -> None:
        """Handle genre button state change: persist state, update proxy, emit event."""
        active_buttons = self._drawer_buttons if self._drawer_buttons else self.genre_buttons
        on_genres, off_genres = self._build_genre_sets(active_buttons)
        self._genre_states = {btn.code: btn.state for btn in active_buttons}

        # When advanced mode is active the expression handles proxy filtering
        if not self._advanced_active and self.proxy:
            self.proxy.set_genre_filter(on_genres, off_genres)

        if self.context:
            self.context.emit(
                Events.GENRE_FILTER_CHANGED,
                on_genres=on_genres,
                off_genres=off_genres,
            )

    def _on_tracks_added(self) -> None:
        if self.proxy:
            self.proxy.invalidateFilter()

    # ------------------------------------------------------------------
    # Drawer cleanup
    # ------------------------------------------------------------------

    def _clear_drawer_buttons(self) -> None:
        """Called when the drawer container is destroyed."""
        self._drawer_buttons = []
        self._drawer_preset_combo = None
        self._drawer_advanced_input = None
        self._drawer_advanced_status = None
        self._drawer_advanced_row = None
        # Purge dead toggle button refs
        self._advanced_toggle_buttons = [b for b in self._advanced_toggle_buttons if _is_alive(b)]


# ============================================================================
# Helpers
# ============================================================================


def _add_vsep(layout: QHBoxLayout) -> None:
    """Add a small vertical separator line to *layout*."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFixedHeight(20)
    sep.setStyleSheet("color: #666;")
    layout.addWidget(sep)


def _is_alive(widget: QWidget) -> bool:
    """Return True if *widget* has not been destroyed."""
    try:
        widget.isVisible()
        return True
    except RuntimeError:
        return False
