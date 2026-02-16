"""Cue Maker plugin - main plugin class."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol

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
        self.main_widget: QWidget | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin with application context.

        Args:
            context: Application context providing access to services
        """
        self.context = context
        logger.info("[Cue Maker] Plugin initialized")

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI elements.

        Creates the main cue maker widget and adds it to the main window.
        The widget is hidden by default and shown when entering cue_maker mode.

        Args:
            ui_builder: UI builder for adding UI elements
        """
        # TODO: Create CueMakerWidget
        # self.main_widget = CueMakerWidget(self.context)
        # ui_builder.add_bottom_widget(self.main_widget)

        # Hide initially (activate() will show it)
        # if self.main_widget:
        #     self.main_widget.setVisible(False)

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
        self.main_widget = None
        self.context = None
        logger.info("[Cue Maker] Plugin shut down")
