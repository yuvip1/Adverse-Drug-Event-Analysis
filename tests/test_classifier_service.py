from typing import ClassVar

import pandas as pd
import pytest

from services import classifier_service


def _features() -> dict[str, object]:
    return {
        "onset_age_years": None,
        "weight_kg": 70.0,
        "sex_code": "unknown",
        "report_type": "1",
        "country_code": "US",
        "reporter_qualification": "1",
        "report_year": 2024,
        "report_month": 1,
        "drug_count": 2,
        "suspect_drug_count": 1,
        "reaction_count": 1,
    }


class FakeModel:
    feature_names_in_ = classifier_service.MODEL_FEATURES
    classes_ = (0, 1)

    def __init__(self) -> None:
        self.named_steps = {
            "preprocess": FakePreprocessor(),
        }

    def predict(self, frame: pd.DataFrame) -> list[int]:
        assert list(frame.columns) == list(classifier_service.MODEL_FEATURES)
        assert frame.iloc[0]["onset_age_years"] is None
        return [1]

    def predict_proba(self, frame: pd.DataFrame) -> list[list[float]]:
        return [[0.2, 0.8]]


class FakePreprocessor:
    transformers_: ClassVar[list[tuple[object, object, object]]] = [
        (
            "numeric",
            object(),
            (
                "onset_age_years",
                "weight_kg",
                "report_year",
                "report_month",
                "drug_count",
                "suspect_drug_count",
                "reaction_count",
            ),
        ),
        (
            "categorical",
            object(),
            ("sex_code", "report_type", "country_code", "reporter_qualification"),
        ),
    ]

    def __init__(self) -> None:
        self.named_transformers_ = {
            "categorical": FakeCategoricalTransformer(),
        }


class FakeCategoricalTransformer:
    named_steps: ClassVar[dict[str, object]] = {
        "one_hot": type(
            "Encoder",
            (),
            {
                "categories_": [
                    ("1", "2", "unknown"),
                    ("1", "2", "3"),
                    ("US", "XX"),
                    ("", "1"),
                ]
            },
        )()
    }


def test_load_classifier_validates_artifact_contract(tmp_path, monkeypatch):
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"placeholder")
    classifier_service.load_classifier.cache_clear()
    monkeypatch.setattr(classifier_service.joblib, "load", lambda path: FakeModel())

    assert isinstance(classifier_service.load_classifier(model_path), FakeModel)
    classifier_service.load_classifier.cache_clear()


def test_load_classifier_rejects_missing_artifact(tmp_path):
    classifier_service.load_classifier.cache_clear()
    with pytest.raises(FileNotFoundError, match="not found"):
        classifier_service.load_classifier(tmp_path / "missing.joblib")


def test_categorical_values_are_read_from_fitted_model():
    values = classifier_service.categorical_values(FakeModel())

    assert values["sex_code"] == ("1", "2", "unknown")
    assert values["report_type"] == ("1", "2", "3")
    assert values["country_code"] == ("US", "XX")
    assert values["reporter_qualification"] == ("", "1")


def test_prepare_new_report_preserves_exact_feature_order_and_missing_values():
    frame = classifier_service.prepare_new_report(_features(), FakeModel())

    assert list(frame.columns) == list(classifier_service.MODEL_FEATURES)
    assert frame.iloc[0]["onset_age_years"] is None
    assert frame.iloc[0]["country_code"] == "US"


def test_prediction_returns_class_and_probability_for_new_report():
    result = classifier_service.classify_new_report(_features(), model=FakeModel())

    assert result == {
        "predicted_class": 1,
        "serious_probability": 0.8,
    }


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"country_code": "USA"}, "country_code"),
        ({"report_month": 13}, "report_month"),
        ({"drug_count": -1}, "drug_count"),
        ({"suspect_drug_count": 3}, "suspect_drug_count"),
        ({"report_type": "EXP"}, "report_type"),
    ],
)
def test_new_report_validation_rejects_invalid_values(changes, message):
    features = _features()
    features.update(changes)

    with pytest.raises((ValueError, TypeError), match=message):
        classifier_service.classify_new_report(features, model=FakeModel())


def test_new_report_validation_rejects_missing_feature():
    features = _features()
    del features["reaction_count"]

    with pytest.raises(ValueError, match="Missing classifier features"):
        classifier_service.classify_new_report(features, model=FakeModel())


def test_prediction_supports_missing_probability_interface():
    class ClassOnlyModel(FakeModel):
        predict_proba = None

    result = classifier_service.classify_new_report(
        _features(),
        model=ClassOnlyModel(),
    )

    assert result == {"predicted_class": 1}
