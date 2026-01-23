"""Feature engineering and preprocessing for genre classification."""

from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import LabelEncoder, StandardScaler


class FeaturePreprocessor:
    """Preprocessor for audio analysis features.

    Handles missing values, scaling, and feature selection.
    """

    def __init__(
        self,
        scale_features: bool = True,
        impute_strategy: str = "median",
    ):
        """Initialize the preprocessor.

        Args:
            scale_features: Whether to standardize features
            impute_strategy: Strategy for imputing missing values
                            ('mean', 'median', 'most_frequent')
        """
        self.scale_features = scale_features
        self.impute_strategy = impute_strategy

        self.imputer: SimpleImputer | None = None
        self.scaler: StandardScaler | None = None
        self.feature_names: list[str] = []
        self._is_fitted = False

    def fit(self, X: pd.DataFrame) -> "FeaturePreprocessor":
        """Fit the preprocessor on training data.

        Args:
            X: Feature DataFrame

        Returns:
            Self for chaining
        """
        self.feature_names = list(X.columns)

        # Fit imputer for missing values
        self.imputer = SimpleImputer(strategy=self.impute_strategy)
        X_imputed = self.imputer.fit_transform(X)

        # Fit scaler if requested
        if self.scale_features:
            self.scaler = StandardScaler()
            self.scaler.fit(X_imputed)

        self._is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        """Transform features using fitted preprocessor.

        Args:
            X: Feature DataFrame

        Returns:
            Preprocessed feature array
        """
        if not self._is_fitted:
            raise RuntimeError("Preprocessor must be fitted before transform")

        # Ensure same columns in same order
        X = X[self.feature_names]

        # Impute missing values
        X_processed = self.imputer.transform(X)

        # Scale if configured
        if self.scale_features and self.scaler is not None:
            X_processed = self.scaler.transform(X_processed)

        return X_processed

    def fit_transform(self, X: pd.DataFrame) -> np.ndarray:
        """Fit and transform in one step.

        Args:
            X: Feature DataFrame

        Returns:
            Preprocessed feature array
        """
        self.fit(X)
        return self.transform(X)

    def get_params(self) -> dict[str, Any]:
        """Get preprocessor parameters for serialization."""
        return {
            "scale_features": self.scale_features,
            "impute_strategy": self.impute_strategy,
            "feature_names": self.feature_names,
        }


class MultiLabelGenreEncoder:
    """Encoder for multi-label genre classification.

    Manages the mapping between genre names and binary label matrix.
    """

    def __init__(self):
        """Initialize the encoder."""
        self.classes_: list[str] = []
        self._is_fitted = False

    def fit(self, classes: list[str]) -> "MultiLabelGenreEncoder":
        """Fit the encoder with genre names.

        Args:
            classes: List of genre names (in order)

        Returns:
            Self for chaining
        """
        self.classes_ = list(classes)
        self._is_fitted = True
        return self

    def decode_predictions(self, y_pred: np.ndarray, threshold: float = 0.5) -> list[set[str]]:
        """Convert prediction probabilities to genre sets.

        Args:
            y_pred: Prediction array (n_samples, n_classes)
            threshold: Probability threshold for positive prediction

        Returns:
            List of genre sets for each sample
        """
        if not self._is_fitted:
            raise RuntimeError("Encoder must be fitted before decode")

        results = []
        binary = (y_pred >= threshold).astype(int)

        for row in binary:
            genres = {self.classes_[i] for i, val in enumerate(row) if val == 1}
            results.append(genres)

        return results

    def decode_single(self, y_pred: np.ndarray, threshold: float = 0.5) -> set[str]:
        """Decode a single prediction.

        Args:
            y_pred: Single prediction array (n_classes,)
            threshold: Probability threshold

        Returns:
            Set of predicted genres
        """
        return self.decode_predictions(y_pred.reshape(1, -1), threshold)[0]

    def encode_genres(self, genre_sets: list[set[str]]) -> np.ndarray:
        """Encode genre sets to binary matrix.

        Args:
            genre_sets: List of genre sets

        Returns:
            Binary label matrix (n_samples, n_classes)
        """
        if not self._is_fitted:
            raise RuntimeError("Encoder must be fitted before encode")

        result = np.zeros((len(genre_sets), len(self.classes_)), dtype=int)
        for i, genres in enumerate(genre_sets):
            for j, cls in enumerate(self.classes_):
                if cls in genres:
                    result[i, j] = 1
        return result

    @property
    def n_classes(self) -> int:
        """Number of unique genres."""
        return len(self.classes_)


# Alias for backward compatibility
GenreLabelEncoder = MultiLabelGenreEncoder


def analyze_feature_importance(
    feature_names: list[str],
    importances: np.ndarray,
    top_n: int = 20,
) -> pd.DataFrame:
    """Analyze and rank feature importances.

    Args:
        feature_names: List of feature names
        importances: Array of importance values
        top_n: Number of top features to return

    Returns:
        DataFrame with ranked features
    """
    importance_df = pd.DataFrame({
        "feature": feature_names,
        "importance": importances,
    })
    importance_df = importance_df.sort_values("importance", ascending=False)
    importance_df["rank"] = range(1, len(importance_df) + 1)

    return importance_df.head(top_n)


def get_feature_groups() -> dict[str, list[str]]:
    """Get feature names grouped by category.

    Returns:
        Dictionary mapping category names to feature lists
    """
    return {
        "energy_dynamics": [
            "energy",
            "rms_energy",
            "rms_mean",
            "rms_std",
            "rms_p10",
            "rms_p90",
            "peak_amplitude",
            "crest_factor",
            "dynamic_range",
            "loudness_variation",
        ],
        "frequency_bands": [
            "bass_energy",
            "mid_energy",
            "treble_energy",
            "sub_bass_mean",
            "sub_bass_ratio",
            "bass_mean",
            "bass_ratio",
            "low_mid_mean",
            "low_mid_ratio",
            "mid_mean",
            "mid_ratio",
            "high_mid_mean",
            "high_mid_ratio",
            "high_mean",
            "high_ratio",
        ],
        "spectral": [
            "spectral_centroid",
            "spectral_centroid_std",
            "spectral_bandwidth",
            "spectral_rolloff",
            "spectral_flatness",
            "spectral_contrast",
            "spectral_entropy",
            "zero_crossing_rate",
        ],
        "mfcc": [f"mfcc_{i}" for i in range(1, 11)],
        "percussive_harmonic": [
            "percussive_energy",
            "harmonic_energy",
            "perc_harm_ratio",
            "percussive_onset_rate",
            "onset_strength_mean",
        ],
        "rhythm": [
            "tempo",
            "tempo_confidence",
            "beat_interval_mean",
            "beat_interval_std",
            "onset_rate",
            "tempogram_periodicity",
        ],
        "harmony": [
            "chroma_entropy",
            "chroma_centroid",
            "chroma_energy_std",
            "tonnetz_mean",
        ],
        "structure": [
            "intro_energy_ratio",
            "core_energy_ratio",
            "outro_energy_ratio",
            "energy_slope",
        ],
    }
