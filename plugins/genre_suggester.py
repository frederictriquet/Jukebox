"""Genre Suggester Plugin - ML-based genre predictions for current track."""

import logging
from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from jukebox.core.event_bus import Events
from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol

logger = logging.getLogger(__name__)

MODEL_PATH = Path.home() / ".jukebox" / "genre_model.pkl"
THRESHOLD = 0.5
TOP_N = 5


class GenreSuggestionWidget(QWidget):
    """Compact bottom widget displaying ML genre suggestions."""

    def __init__(self) -> None:
        """Initialize widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI."""
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        self.title_label = QLabel("<b>ML Genres:</b>")
        layout.addWidget(self.title_label)

        self.info_label = QLabel("--")
        layout.addWidget(self.info_label)

        self.genre_labels: list[QLabel] = []
        for _ in range(TOP_N):
            label = QLabel()
            label.setVisible(False)
            self.genre_labels.append(label)
            layout.addWidget(label)

        layout.addStretch()
        self.setLayout(layout)
        self.setMaximumHeight(30)

    def display_suggestions(self, predictions: list[tuple[str, float]]) -> None:
        """Display genre predictions with color coding."""
        self.info_label.setVisible(False)
        for i, label in enumerate(self.genre_labels):
            if i < len(predictions):
                code, prob = predictions[i]
                pct = int(prob * 100)
                color = "#00CC00" if prob >= THRESHOLD else "#888888"
                label.setText(f'<span style="color:{color}">{code} {pct}%</span>')
                label.setVisible(True)
            else:
                label.setVisible(False)

    def show_loading(self) -> None:
        """Show loading state."""
        self.info_label.setText("Analyzing...")
        self.info_label.setVisible(True)
        for label in self.genre_labels:
            label.setVisible(False)

    def show_unavailable(self, message: str) -> None:
        """Show unavailable state with message."""
        self.info_label.setText(f'<span style="color:#888888">{message}</span>')
        self.info_label.setVisible(True)
        for label in self.genre_labels:
            label.setVisible(False)


class GenreSuggesterPlugin:
    """Plugin that displays ML genre predictions for the current track."""

    name = "genre_suggester"
    version = "1.0.0"
    description = "ML-based genre suggestions for current track"
    modes = ["jukebox", "curating"]

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin and load ML model."""
        self.context = context
        self.widget: GenreSuggestionWidget | None = None

        # Load model
        try:
            from ml.genre_classifier.trainer import TrainedModel

            self.model: TrainedModel | None = TrainedModel.load(MODEL_PATH)
            logger.info("[genre_suggester] Model loaded from %s", MODEL_PATH)
        except FileNotFoundError:
            self.model = None
            logger.warning("[genre_suggester] Model not found at %s", MODEL_PATH)
        except Exception:
            self.model = None
            logger.exception("[genre_suggester] Failed to load model")

        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register bottom widget."""
        self.widget = GenreSuggestionWidget()
        ui_builder.add_bottom_widget(self.widget)

    def _on_track_loaded(self, track_id: int) -> None:
        """Handle track loaded event."""
        if self.widget is None:
            return

        if self.model is None:
            self.widget.show_unavailable("Model not found")
            return

        try:
            from ml.genre_classifier.data_loader import load_track_features

            features = load_track_features(track_id)
        except Exception:
            logger.exception("[genre_suggester] Failed to load features for track %d", track_id)
            self.widget.show_unavailable("Feature loading error")
            return

        if features is None:
            self.widget.show_unavailable("No ML analysis")
            return

        try:
            predictions = self.model.predict_top_n(features, n=TOP_N)
            self.widget.display_suggestions(predictions)
        except Exception:
            logger.exception("[genre_suggester] Prediction failed for track %d", track_id)
            self.widget.show_unavailable("Prediction error")

    def shutdown(self) -> None:
        """Cleanup references."""
        self.widget = None
        self.model = None
