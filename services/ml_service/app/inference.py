"""Prediction with a versioned model: validates inputs, returns reproducibility metadata."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from services.ml_service.app.dataset import CATEGORICAL_FEATURES
from services.ml_service.app.training import TrainedModel


class FeatureValidationError(ValueError):
    pass


def validate_features(model: TrainedModel, features: Mapping[str, Any]) -> dict[str, Any]:
    missing = [c for c in model.feature_columns if c not in features]
    if missing:
        raise FeatureValidationError(f"missing features: {missing}")
    clean: dict[str, Any] = {}
    for column in model.feature_columns:
        value = features[column]
        if column in CATEGORICAL_FEATURES:
            if not isinstance(value, str) or not value:
                raise FeatureValidationError(f"{column} must be a non-empty string")
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise FeatureValidationError(f"{column} must be numeric")
            if math.isinf(value):
                raise FeatureValidationError(f"{column} must be finite or NaN (missing)")
        clean[column] = value
    return clean


def predict(model: TrainedModel, features: Mapping[str, Any]) -> dict[str, Any]:
    row = validate_features(model, features)
    probability = float(model.predict_proba(pd.DataFrame([row]))[0])
    return {
        "probability_profitable": probability,
        "selected": probability >= model.threshold,
        "threshold": model.threshold,
        "model": model.name,
        "model_version": model.version,
        "data_fingerprint": model.metadata.get("data_fingerprint"),
        "predicted_at": datetime.now(timezone.utc).isoformat(),
    }
