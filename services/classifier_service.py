from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "results" / "model" / "seriousness_classifier.joblib"
MODEL_FEATURES = (
    "onset_age_years",
    "weight_kg",
    "sex_code",
    "report_type",
    "country_code",
    "reporter_qualification",
    "report_year",
    "report_month",
    "drug_count",
    "suspect_drug_count",
    "reaction_count",
)
@lru_cache(maxsize=1)
def load_classifier(model_path: Path = MODEL_PATH) -> Any:
    if not model_path.is_file():
        raise FileNotFoundError(f"Classifier model artifact was not found: {model_path}")
    model = joblib.load(model_path)
    actual_features = getattr(model, "feature_names_in_", None)
    if actual_features is None or tuple(actual_features) != MODEL_FEATURES:
        raise RuntimeError("Persisted classifier feature contract does not match the application")
    if not callable(getattr(model, "predict", None)):
        raise TypeError("Persisted classifier does not support prediction")
    return model


def categorical_values(model: Any) -> dict[str, tuple[str, ...]]:
    try:
        encoder = model.named_steps["preprocess"].named_transformers_["categorical"].named_steps[
            "one_hot"
        ]
        columns = model.named_steps["preprocess"].transformers_[1][2]
        return {
            column: tuple(str(value) for value in categories)
            for column, categories in zip(columns, encoder.categories_)
        }
    except (AttributeError, KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Persisted classifier categorical contract is unavailable") from error


def _validate_numeric(value: Any, name: str, *, minimum: float, maximum: float | None = None) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise TypeError(f"{name} must be numeric or None")
    if value is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum:g}")
    if maximum is not None and value is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum:g}")


def prepare_new_report(features: dict[str, Any], model: Any) -> pd.DataFrame:
    missing = [column for column in MODEL_FEATURES if column not in features]
    extra = [column for column in features if column not in MODEL_FEATURES]
    if missing:
        raise ValueError(f"Missing classifier features: {', '.join(missing)}")
    if extra:
        raise ValueError(f"Unexpected classifier features: {', '.join(extra)}")

    _validate_numeric(features["onset_age_years"], "onset_age_years", minimum=0, maximum=150)
    _validate_numeric(features["weight_kg"], "weight_kg", minimum=0, maximum=1000)
    _validate_numeric(features["report_year"], "report_year", minimum=1900, maximum=2100)
    _validate_numeric(features["report_month"], "report_month", minimum=1, maximum=12)
    for name in ("drug_count", "suspect_drug_count", "reaction_count"):
        value = features[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if features["suspect_drug_count"] > features["drug_count"]:
        raise ValueError("suspect_drug_count cannot exceed drug_count")

    categories = categorical_values(model)
    for name in ("sex_code", "report_type", "country_code", "reporter_qualification"):
        value = features[name]
        if not isinstance(value, str) or value not in categories[name]:
            allowed = ", ".join(categories[name])
            raise ValueError(f"{name} must be one of: {allowed}")
    return pd.DataFrame([{column: features[column] for column in MODEL_FEATURES}])


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in MODEL_FEATURES if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing classifier features: {', '.join(missing)}")
    return frame.loc[:, MODEL_FEATURES].copy()


def predict_seriousness(
    model: Any,
    frame: pd.DataFrame,
) -> dict[str, Any]:
    features = prepare_features(frame)
    predicted = model.predict(features)
    if len(predicted) != 1:
        raise ValueError("Classifier prediction must contain exactly one result")
    result: dict[str, Any] = {"predicted_class": int(predicted[0])}
    predict_proba = getattr(model, "predict_proba", None)
    if callable(predict_proba):
        probabilities = np.asarray(predict_proba(features))
        classes = getattr(model, "classes_", None)
        if classes is None and hasattr(model, "named_steps"):
            classes = getattr(model.named_steps.get("model"), "classes_", None)
        if (
            classes is None
            or probabilities.ndim != 2
            or probabilities.shape[0] != 1
            or probabilities.shape[1] != len(classes)
        ):
            raise RuntimeError("Classifier probabilities are unavailable or malformed")
        class_indexes = {int(value): index for index, value in enumerate(classes)}
        if 1 in class_indexes:
            result["serious_probability"] = float(probabilities[0, class_indexes[1]])
    return result


def classify_new_report(features: dict[str, Any], *, model: Any | None = None) -> dict[str, Any]:
    classifier = model if model is not None else load_classifier()
    frame = prepare_new_report(features, classifier)
    return predict_seriousness(classifier, frame)
