"""Cue Maker plugin - main plugin class."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol
    from plugins.cue_maker.analyzer import AnalyzeWorker
    from plugins.cue_maker.widgets.cue_maker_widget import CueMakerWidget

logger = logging.getLogger(__name__)


class CueMakerPlugin:
    """Plugin for creating cue sheets from DJ mixes.

    This plugin provides a dedicated mode for:
    - Loading and analyzing DJ mixes with shazamix
    - Validating and correcting identified tracks
    - Adjusting timestamps manually or via waveform
    - Adding tracks manually via search/directory navigator
    - Exporting to standard CUE format

    Active only in cue_maker mode.
    """

    name = "cue_maker"
    version = "1.0.0"
    description = "Create cue sheets for DJ mixes"
    modes = ["cue_maker"]  # Active only in cue_maker mode

    def __init__(self) -> None:
        """Initialize plugin state."""
        self.context: PluginContextProtocol | None = None
        self.main_widget: CueMakerWidget | None = None
        self._analyzer: AnalyzeWorker | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin with application context.

        Args:
            context: Application context providing access to services
        """
        self.context = context
        logger.info("[Cue Maker] Plugin initialized")

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI elements.

        Creates the main cue maker widget and adds it to the bottom of the main window.
        The widget is hidden by default and shown when entering cue_maker mode.

        Args:
            ui_builder: UI builder for adding UI elements
        """
        from plugins.cue_maker.widgets.cue_maker_widget import CueMakerWidget

        assert self.context is not None
        self.main_widget = CueMakerWidget(self.context)
        ui_builder.add_bottom_widget(self.main_widget)

        # Hide initially - activate() will show it when entering cue_maker mode
        self.main_widget.setVisible(False)

        # Connect signals
        self.main_widget.analyze_requested.connect(self._on_analyze)

        logger.info("[Cue Maker] UI registered")

    def activate(self, mode: str) -> None:
        """Activate plugin when entering cue_maker mode.

        Args:
            mode: Mode being activated (should be "cue_maker")
        """
        if self.main_widget:
            self.main_widget.setVisible(True)
        logger.debug("[Cue Maker] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin when leaving cue_maker mode.

        Args:
            mode: Mode being deactivated
        """
        if self.main_widget:
            self.main_widget.setVisible(False)
        logger.debug("[Cue Maker] Deactivated for %s mode", mode)

    def shutdown(self) -> None:
        """Cleanup resources when plugin is unloaded."""
        if self._analyzer and self._analyzer.isRunning():
            self._analyzer.quit()
            self._analyzer.wait(3000)
        self._analyzer = None
        self.main_widget = None
        self.context = None
        logger.info("[Cue Maker] Plugin shut down")

    # --- Analysis ---

    def _on_analyze(self) -> None:
        """Start shazamix analysis of the loaded mix."""
        if not self.main_widget or not self.context:
            return

        mix_path = self.main_widget.model.sheet.mix_filepath
        if not mix_path:
            return

        # Get database path from config
        db_path = getattr(self.context.config, "shazamix_db_path", "")
        if not db_path:
            logger.warning("[Cue Maker] No shazamix database path configured")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self.main_widget,
                "Configuration",
                "No shazamix database path configured.\n" "Set shazamix_db_path in config.yaml.",
            )
            return

        from plugins.cue_maker.analyzer import AnalyzeWorker

        self._analyzer = AnalyzeWorker(mix_path, db_path)
        self._analyzer.progress.connect(self.main_widget.set_analysis_progress)
        self._analyzer.finished.connect(self.main_widget.on_analysis_complete)
        self._analyzer.error.connect(self.main_widget.on_analysis_error)

        self.main_widget.analyze_btn.setEnabled(False)
        self._analyzer.start()
        logger.info("[Cue Maker] Analysis started for %s", mix_path)
