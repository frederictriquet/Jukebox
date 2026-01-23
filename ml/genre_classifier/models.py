"""Machine learning models for multi-label genre classification.

Provides Random Forest, XGBoost, and SVM classifiers wrapped for
multi-label classification with consistent interface.
"""

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.svm import SVC


class BaseGenreClassifier(ABC):
    """Abstract base class for multi-label genre classifiers."""

    name: str = "base"

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> "BaseGenreClassifier":
        """Fit the model on training data.

        Args:
            X: Features array (n_samples, n_features)
            y: Labels array (n_samples, n_classes) - binary multi-label
        """
        pass

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict genre labels (binary).

        Returns:
            Binary predictions (n_samples, n_classes)
        """
        pass

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities.

        Returns:
            Probabilities (n_samples, n_classes)
        """
        pass

    @abstractmethod
    def get_params(self) -> dict[str, Any]:
        """Get model hyperparameters."""
        pass

    def get_feature_importance(self) -> np.ndarray | None:
        """Get feature importances if available.

        Returns:
            Average importance across all labels, or None if not available
        """
        return None


class RandomForestGenreClassifier(BaseGenreClassifier):
    """Random Forest classifier for multi-label genre classification.

    Uses MultiOutputClassifier to train one Random Forest per genre.
    """

    name = "random_forest"

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: int | None = 20,
        min_samples_split: int = 5,
        min_samples_leaf: int = 2,
        max_features: str = "sqrt",
        class_weight: str = "balanced",
        random_state: int = 42,
        n_jobs: int = -1,
    ):
        """Initialize Random Forest classifier.

        Args:
            n_estimators: Number of trees in the forest
            max_depth: Maximum depth of trees (None = unlimited)
            min_samples_split: Minimum samples to split a node
            min_samples_leaf: Minimum samples in leaf node
            max_features: Features to consider for best split
            class_weight: Weight classes to handle imbalance
            random_state: Random seed for reproducibility
            n_jobs: Number of parallel jobs (-1 = all cores)
        """
        base_clf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            class_weight=class_weight,
            random_state=random_state,
            n_jobs=n_jobs,
        )
        self.model = MultiOutputClassifier(base_clf, n_jobs=n_jobs)
        self._base_clf = base_clf
        self._params = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "min_samples_split": min_samples_split,
            "min_samples_leaf": min_samples_leaf,
            "max_features": max_features,
            "class_weight": class_weight,
        }

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RandomForestGenreClassifier":
        """Fit the Random Forest model."""
        self.model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict genre labels (binary)."""
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities for each genre."""
        # predict_proba returns list of arrays, one per output
        # Each array is (n_samples, 2) for binary classification
        # We want probability of positive class (index 1)
        probas = self.model.predict_proba(X)
        # Stack probabilities of positive class
        return np.column_stack([p[:, 1] if p.shape[1] > 1 else p[:, 0] for p in probas])

    def get_params(self) -> dict[str, Any]:
        """Get model hyperparameters."""
        return self._params.copy()

    def get_feature_importance(self) -> np.ndarray:
        """Get average feature importances across all genre classifiers."""
        importances = np.array([
            est.feature_importances_ for est in self.model.estimators_
        ])
        return importances.mean(axis=0)


class XGBoostGenreClassifier(BaseGenreClassifier):
    """XGBoost classifier for multi-label genre classification.

    Uses MultiOutputClassifier wrapper for multi-label support.
    """

    name = "xgboost"

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: int = 6,
        learning_rate: float = 0.1,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_alpha: float = 0.1,
        reg_lambda: float = 1.0,
        random_state: int = 42,
        n_jobs: int = -1,
    ):
        """Initialize XGBoost classifier."""
        try:
            from xgboost import XGBClassifier
        except ImportError:
            raise ImportError(
                "XGBoost not installed. Install with: pip install xgboost"
            )

        base_clf = XGBClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            reg_alpha=reg_alpha,
            reg_lambda=reg_lambda,
            random_state=random_state,
            n_jobs=n_jobs,
            eval_metric="logloss",
        )
        self.model = MultiOutputClassifier(base_clf, n_jobs=n_jobs)
        self._base_clf = base_clf
        self._params = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
        }

    def fit(self, X: np.ndarray, y: np.ndarray) -> "XGBoostGenreClassifier":
        """Fit the XGBoost model."""
        self.model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict genre labels (binary)."""
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities for each genre."""
        probas = self.model.predict_proba(X)
        return np.column_stack([p[:, 1] if p.shape[1] > 1 else p[:, 0] for p in probas])

    def get_params(self) -> dict[str, Any]:
        """Get model hyperparameters."""
        return self._params.copy()

    def get_feature_importance(self) -> np.ndarray:
        """Get average feature importances across all genre classifiers."""
        importances = np.array([
            est.feature_importances_ for est in self.model.estimators_
        ])
        return importances.mean(axis=0)


class SVMGenreClassifier(BaseGenreClassifier):
    """Support Vector Machine classifier for multi-label genre classification.

    Uses MultiOutputClassifier wrapper for multi-label support.
    """

    name = "svm"

    def __init__(
        self,
        C: float = 1.0,
        kernel: str = "rbf",
        gamma: str = "scale",
        class_weight: str = "balanced",
        probability: bool = True,
        random_state: int = 42,
    ):
        """Initialize SVM classifier."""
        base_clf = SVC(
            C=C,
            kernel=kernel,
            gamma=gamma,
            class_weight=class_weight,
            probability=probability,
            random_state=random_state,
        )
        self.model = MultiOutputClassifier(base_clf, n_jobs=-1)
        self._base_clf = base_clf
        self._params = {
            "C": C,
            "kernel": kernel,
            "gamma": gamma,
            "class_weight": class_weight,
        }

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SVMGenreClassifier":
        """Fit the SVM model."""
        self.model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict genre labels (binary)."""
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities for each genre."""
        probas = self.model.predict_proba(X)
        return np.column_stack([p[:, 1] if p.shape[1] > 1 else p[:, 0] for p in probas])

    def get_params(self) -> dict[str, Any]:
        """Get model hyperparameters."""
        return self._params.copy()


# Model registry for easy access
MODEL_REGISTRY: dict[str, type[BaseGenreClassifier]] = {
    "random_forest": RandomForestGenreClassifier,
    "xgboost": XGBoostGenreClassifier,
    "svm": SVMGenreClassifier,
}


def get_model(name: str, **kwargs) -> BaseGenreClassifier:
    """Get a model instance by name.

    Args:
        name: Model name ('random_forest', 'xgboost', 'svm')
        **kwargs: Model hyperparameters

    Returns:
        Model instance

    Raises:
        ValueError: If model name is unknown
    """
    if name not in MODEL_REGISTRY:
        available = ", ".join(MODEL_REGISTRY.keys())
        raise ValueError(f"Unknown model: {name}. Available: {available}")

    return MODEL_REGISTRY[name](**kwargs)


def get_all_models(**common_kwargs) -> list[BaseGenreClassifier]:
    """Get instances of all available models.

    Args:
        **common_kwargs: Kwargs passed to all models (e.g., random_state)

    Returns:
        List of model instances
    """
    models = []
    for name, cls in MODEL_REGISTRY.items():
        try:
            # Filter kwargs to only those accepted by this model
            model = cls(**{k: v for k, v in common_kwargs.items()
                          if k in cls.__init__.__code__.co_varnames})
            models.append(model)
        except ImportError:
            # Skip models with missing dependencies (e.g., xgboost)
            continue
    return models
