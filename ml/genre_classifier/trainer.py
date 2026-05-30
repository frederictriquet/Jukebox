"""Training and evaluation module for multi-label genre classifiers."""

import hashlib
import logging
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    hamming_loss,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

from .data_loader import ML_FEATURE_COLUMNS, load_training_data  # type: ignore[import]
from .feature_engineering import FeaturePreprocessor, MultiLabelGenreEncoder  # type: ignore[import]
from .models import BaseGenreClassifier, get_all_models, get_model  # type: ignore[import]

logger = logging.getLogger(__name__)


@dataclass
class MultiLabelMetrics:
    """Container for multi-label evaluation metrics."""

    # Overall metrics
    hamming_loss: float  # Fraction of wrong labels
    subset_accuracy: float  # Exact match ratio (all labels correct)
    f1_micro: float  # Micro-averaged F1
    f1_macro: float  # Macro-averaged F1
    f1_weighted: float  # Weighted F1
    f1_samples: float  # Sample-averaged F1
    precision_micro: float
    recall_micro: float

    # Per-genre metrics
    per_genre_metrics: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "hamming_loss": self.hamming_loss,
            "subset_accuracy": self.subset_accuracy,
            "f1_micro": self.f1_micro,
            "f1_macro": self.f1_macro,
            "f1_weighted": self.f1_weighted,
            "f1_samples": self.f1_samples,
            "precision_micro": self.precision_micro,
            "recall_micro": self.recall_micro,
            "per_genre_metrics": self.per_genre_metrics,
        }


@dataclass
class TrainingResult:
    """Result of model training."""

    model_name: str
    metrics: MultiLabelMetrics
    feature_importance: pd.DataFrame | None
    training_time: float
    n_samples: int
    n_features: int
    n_genres: int
    genres: list[str]

    def summary(self) -> str:
        """Generate a text summary of the training result."""
        lines = [
            f"=== {self.model_name} ===",
            f"Samples: {self.n_samples}, Features: {self.n_features}, Genres: {self.n_genres}",
            f"Hamming Loss: {self.metrics.hamming_loss:.4f} (lower is better)",
            f"Subset Accuracy: {self.metrics.subset_accuracy:.4f} (exact match)",
            f"F1 Micro: {self.metrics.f1_micro:.4f}",
            f"F1 Macro: {self.metrics.f1_macro:.4f}",
            f"F1 Samples: {self.metrics.f1_samples:.4f}",
        ]
        return "\n".join(lines)


class GenreClassifierTrainer:
    """Trainer for multi-label genre classification models."""

    def __init__(
        self,
        test_size: float = 0.2,
        random_state: int = 42,
    ):
        """Initialize the trainer.

        Args:
            test_size: Proportion of data for testing
            random_state: Random seed for reproducibility
        """
        self.test_size = test_size
        self.random_state = random_state

        self.preprocessor = FeaturePreprocessor()
        self.label_encoder = MultiLabelGenreEncoder()

        self.X_train: np.ndarray | None = None  # noqa: N803
        self.X_test: np.ndarray | None = None  # noqa: N803
        self.y_train: np.ndarray | None = None
        self.y_test: np.ndarray | None = None
        self.genres: list[str] = []

    def load_data(
        self,
        db_path: Path | str | None = None,
        min_samples_per_genre: int = 5,
    ) -> tuple[int, int, int]:
        """Load and prepare data for training.

        Args:
            db_path: Path to database (uses default if None)
            min_samples_per_genre: Minimum samples per genre

        Returns:
            Tuple of (n_samples, n_features, n_genres)
        """
        kwargs: dict[str, Any] = {"min_samples_per_genre": min_samples_per_genre}
        if db_path:
            kwargs["db_path"] = db_path

        x_raw, y, genres = load_training_data(**kwargs)  # type: ignore[call-arg]

        self.genres = genres
        self.label_encoder.fit(genres)

        # Convert labels DataFrame to numpy array
        y_array = y.values

        # Split data (stratified split not available for multi-label, use random)
        split_result = train_test_split(
            x_raw,
            y_array,
            test_size=self.test_size,
            random_state=self.random_state,
        )
        x_train_raw: pd.DataFrame = split_result[0]  # type: ignore[assignment]
        x_test_raw: pd.DataFrame = split_result[1]  # type: ignore[assignment]
        self.y_train = np.asarray(split_result[2])
        self.y_test = np.asarray(split_result[3])

        # Preprocess features
        x_train = self.preprocessor.fit_transform(x_train_raw)
        self.X_train = x_train  # noqa: N803
        self.X_test = self.preprocessor.transform(x_test_raw)  # noqa: N803

        # Le nombre réel de features est la dimension de la matrice prétraitée,
        # pas len(ML_FEATURE_COLUMNS) : ces deux valeurs divergent si les colonnes
        # DB ne correspondent pas aux colonnes attendues.
        return len(y), x_train.shape[1], len(genres)

    def evaluate_model(
        self,
        model: BaseGenreClassifier,
        features: np.ndarray,
        labels: np.ndarray,
    ) -> MultiLabelMetrics:
        """Evaluate a model on given data.

        Args:
            model: Trained model
            features: Feature matrix
            labels: True labels (binary matrix)

        Returns:
            Multi-label evaluation metrics
        """
        y_pred = model.predict(features)

        # Overall metrics
        h_loss = hamming_loss(labels, y_pred)
        subset_acc = accuracy_score(labels, y_pred)  # Exact match

        f1_micro = f1_score(labels, y_pred, average="micro", zero_division=0)  # type: ignore[arg-type]
        f1_macro = f1_score(labels, y_pred, average="macro", zero_division=0)  # type: ignore[arg-type]
        f1_weighted = f1_score(labels, y_pred, average="weighted", zero_division=0)  # type: ignore[arg-type]
        f1_samples = f1_score(labels, y_pred, average="samples", zero_division=0)  # type: ignore[arg-type]

        precision_micro = precision_score(labels, y_pred, average="micro", zero_division=0)  # type: ignore[arg-type]
        recall_micro = recall_score(labels, y_pred, average="micro", zero_division=0)  # type: ignore[arg-type]

        # Per-genre metrics
        per_genre = {}
        for i, genre in enumerate(self.genres):
            y_true_genre = labels[:, i]
            y_pred_genre = y_pred[:, i]
            support = int(y_true_genre.sum())

            if support > 0:
                per_genre[genre] = {
                    "precision": precision_score(
                        y_true_genre, y_pred_genre, zero_division=0  # type: ignore[arg-type]
                    ),
                    "recall": recall_score(
                        y_true_genre, y_pred_genre, zero_division=0  # type: ignore[arg-type]
                    ),
                    "f1": f1_score(y_true_genre, y_pred_genre, zero_division=0),  # type: ignore[arg-type]
                    "support": support,
                }

        return MultiLabelMetrics(
            hamming_loss=h_loss,
            subset_accuracy=subset_acc,
            f1_micro=f1_micro,
            f1_macro=f1_macro,
            f1_weighted=f1_weighted,
            f1_samples=f1_samples,
            precision_micro=precision_micro,
            recall_micro=recall_micro,
            per_genre_metrics=per_genre,
        )

    def train_model(
        self,
        model: BaseGenreClassifier,
    ) -> TrainingResult:
        """Train and evaluate a model.

        Args:
            model: Model instance to train

        Returns:
            Training result with metrics
        """
        if self.X_train is None or self.X_test is None:  # noqa: N803
            raise RuntimeError("Data not loaded. Call load_data() first.")
        if self.y_train is None or self.y_test is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        start_time = time.time()

        # Train model
        model.fit(self.X_train, self.y_train)  # noqa: N803

        training_time = time.time() - start_time

        # Evaluate on test set
        metrics = self.evaluate_model(model, self.X_test, self.y_test)  # noqa: N803

        # Feature importance
        feature_importance = None
        importances = model.get_feature_importance()
        if importances is not None:
            feature_importance = pd.DataFrame(
                {
                    "feature": ML_FEATURE_COLUMNS,
                    "importance": importances,
                }
            ).sort_values("importance", ascending=False)

        return TrainingResult(
            model_name=model.name,
            metrics=metrics,
            feature_importance=feature_importance,
            training_time=training_time,
            n_samples=len(self.y_train) + len(self.y_test),
            n_features=self.X_train.shape[1],  # noqa: N803
            n_genres=len(self.genres),
            genres=self.genres,
        )

    def compare_models(
        self,
        models: list[BaseGenreClassifier] | None = None,
    ) -> pd.DataFrame:
        """Compare multiple models.

        Args:
            models: List of models to compare (uses all if None)

        Returns:
            DataFrame with comparison results
        """
        all_models: list[BaseGenreClassifier] = (
            models if models is not None else get_all_models(random_state=self.random_state)
        )

        results = []
        for model in all_models:
            logger.info("Training %s...", model.name)
            result = self.train_model(model)
            results.append(
                {
                    "model": model.name,
                    "hamming_loss": result.metrics.hamming_loss,
                    "subset_accuracy": result.metrics.subset_accuracy,
                    "f1_micro": result.metrics.f1_micro,
                    "f1_macro": result.metrics.f1_macro,
                    "f1_samples": result.metrics.f1_samples,
                    "training_time": result.training_time,
                }
            )
            logger.info(result.summary())

        return pd.DataFrame(results).sort_values("f1_micro", ascending=False)


class TrainedModel:
    """Wrapper for a trained model with all necessary components for inference."""

    def __init__(
        self,
        model: BaseGenreClassifier,
        preprocessor: FeaturePreprocessor,
        label_encoder: MultiLabelGenreEncoder,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize trained model wrapper.

        Args:
            model: Trained classifier
            preprocessor: Fitted feature preprocessor
            label_encoder: Fitted label encoder
            metadata: Optional training metadata
        """
        self.model = model
        self.preprocessor = preprocessor
        self.label_encoder = label_encoder
        self.metadata = metadata or {}

    def predict(self, features: pd.DataFrame, threshold: float = 0.5) -> set[str]:
        """Predict genres for a single track.

        Args:
            features: DataFrame with feature columns
            threshold: Probability threshold for prediction

        Returns:
            Set of predicted genre strings
        """
        x = self.preprocessor.transform(features)
        y_proba = self.model.predict_proba(x)
        return self.label_encoder.decode_single(y_proba[0], threshold)

    def predict_proba(self, features: pd.DataFrame) -> dict[str, float]:
        """Get prediction probabilities for all genres.

        Args:
            features: DataFrame with feature columns

        Returns:
            Dictionary mapping genre to probability
        """
        x = self.preprocessor.transform(features)
        proba = self.model.predict_proba(x)[0]
        return {
            genre: float(prob)
            for genre, prob in zip(self.label_encoder.classes_, proba, strict=False)
        }

    def predict_top_n(
        self,
        features: pd.DataFrame,
        n: int = 3,
    ) -> list[tuple[str, float]]:
        """Get top N genre predictions with probabilities.

        Args:
            features: DataFrame with feature columns
            n: Number of top predictions

        Returns:
            List of (genre, probability) tuples
        """
        proba_dict = self.predict_proba(features)
        sorted_proba = sorted(proba_dict.items(), key=lambda x: -x[1])
        return sorted_proba[:n]

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def save(self, path: Path | str) -> None:
        """Save the trained model to disk.

        Args:
            path: Path to save the model
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "model": self.model,
            "preprocessor": self.preprocessor,
            "label_encoder": self.label_encoder,
            "metadata": {
                **self.metadata,
                "saved_at": datetime.now().isoformat(),
                "model_name": self.model.name,
                "genres": self.label_encoder.classes_,
            },
        }

        with open(path, "wb") as f:
            pickle.dump(data, f)  # noqa: S301

        path.with_suffix(".sha256").write_text(self._sha256(path))

    @classmethod
    def load(cls, path: Path | str, require_hash: bool = True) -> "TrainedModel":
        """Load a trained model from disk.

        Args:
            path: Path to the saved model
            require_hash: Si True (défaut), exige un fichier .sha256 valide avant
                de désérialiser. pickle.load exécute du code arbitraire : sans
                cette garde, un fichier modèle altéré permettrait une RCE.

        Returns:
            TrainedModel instance

        Raises:
            FileNotFoundError: Si le modèle ou son .sha256 (quand require_hash) est absent.
            ValueError: Si l'empreinte SHA256 ne correspond pas.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        hash_path = path.with_suffix(".sha256")
        if hash_path.exists():
            expected = hash_path.read_text().strip()
            actual = cls._sha256(path)
            if actual != expected:
                raise ValueError(f"SHA256 mismatch pour {path} — fichier corrompu ou altéré")
        elif require_hash:
            raise FileNotFoundError(
                f"Fichier d'empreinte introuvable : {hash_path} — refus de "
                f"désérialiser {path} sans vérification d'intégrité (pickle = RCE). "
                f"Passer require_hash=False pour forcer (dangereux)."
            )
        else:
            logger.warning(
                "[TrainedModel] Aucun fichier .sha256 pour %s — chargement sans vérification (require_hash=False)",
                path,
            )

        with open(path, "rb") as f:
            data = pickle.load(f)  # noqa: S301

        return cls(
            model=data["model"],
            preprocessor=data["preprocessor"],
            label_encoder=data["label_encoder"],
            metadata=data.get("metadata", {}),
        )


def train_best_model(
    db_path: Path | str | None = None,
    model_name: str = "random_forest",
    save_path: Path | str | None = None,
    min_samples_per_genre: int = 5,
    **model_kwargs: Any,
) -> tuple[TrainedModel, TrainingResult]:
    """Train a model and optionally save it.

    Args:
        db_path: Path to database
        model_name: Name of model to train
        save_path: Path to save model (optional)
        min_samples_per_genre: Minimum samples per genre
        **model_kwargs: Additional model hyperparameters

    Returns:
        Tuple of (TrainedModel, TrainingResult)
    """
    trainer = GenreClassifierTrainer()

    # Load data
    n_samples, n_features, n_genres = trainer.load_data(
        db_path=db_path,
        min_samples_per_genre=min_samples_per_genre,
    )
    logger.info("Loaded %d samples, %d features, %d genres", n_samples, n_features, n_genres)
    logger.info("Genres: %s", ", ".join(trainer.genres))

    # Get and train model
    model = get_model(model_name, **model_kwargs)
    result = trainer.train_model(model)

    logger.info(result.summary())

    for genre, metrics in sorted(result.metrics.per_genre_metrics.items()):
        logger.info(
            "  %s: P=%.3f R=%.3f F1=%.3f (n=%d)",
            genre,
            metrics["precision"],
            metrics["recall"],
            metrics["f1"],
            metrics["support"],
        )

    # Create trained model wrapper
    trained_model = TrainedModel(
        model=model,
        preprocessor=trainer.preprocessor,
        label_encoder=trainer.label_encoder,
        metadata={
            "model_name": model_name,
            "model_params": model.get_params(),
            "n_samples": n_samples,
            "n_features": n_features,
            "n_genres": n_genres,
            "genres": trainer.genres,
            "metrics": result.metrics.to_dict(),
            "trained_at": datetime.now().isoformat(),
        },
    )

    if save_path:
        trained_model.save(save_path)
        logger.info("Model saved to: %s", save_path)

    return trained_model, result
