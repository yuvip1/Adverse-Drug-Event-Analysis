"""Stage 8 seriousness classifier with local MLflow tracking.

The target is fact_report.is_serious. Features are report-level fields and
aggregated drug/reaction counts; no post-outcome field is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import pyodbc
import statsmodels.api as sm
from dotenv import load_dotenv
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
MODEL_DIR = RESULTS / "model"
OUT = RESULTS / "ml_metrics.json"
MLFLOW_DB = RESULTS / "mlflow.db"

FEATURE_COLUMNS = [
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
]
NUMERIC_FEATURES = [
    "onset_age_years",
    "weight_kg",
    "report_year",
    "report_month",
    "drug_count",
    "suspect_drug_count",
    "reaction_count",
]
CATEGORICAL_FEATURES = [
    "sex_code",
    "report_type",
    "country_code",
    "reporter_qualification",
]


def load_features() -> pd.DataFrame:
    load_dotenv()
    with pyodbc.connect(os.environ["SQLSERVER_CONNECTION"]) as connection:
        query = """
        SELECT
            fr.report_key,
            fr.is_serious,
            fr.onset_age_years,
            fr.weight_kg,
            COALESCE(fr.sex_code, 'unknown') AS sex_code,
            COALESCE(fr.report_type, 'unknown') AS report_type,
            COALESCE(country.iso2_code, 'XX') AS country_code,
            COALESCE(reporter.qualification, 'unknown') AS reporter_qualification,
            date_dim.year AS report_year,
            date_dim.month AS report_month,
            COUNT(DISTINCT fd.drug_key) AS drug_count,
            COUNT(DISTINCT CASE WHEN fd.is_suspect = 1 THEN fd.drug_key END)
                AS suspect_drug_count,
            COUNT(DISTINCT rx.reaction_key) AS reaction_count
        FROM dbo.fact_report fr
        JOIN dbo.dim_date date_dim ON date_dim.date_key = fr.date_key
        LEFT JOIN dbo.dim_country country ON country.country_key = fr.country_key
        LEFT JOIN dbo.dim_reporter reporter ON reporter.reporter_key = fr.reporter_key
        LEFT JOIN dbo.fact_drug fd ON fd.report_key = fr.report_key
        LEFT JOIN dbo.fact_reaction rx ON rx.report_key = fr.report_key
        WHERE date_dim.date_key <> -1
        GROUP BY fr.report_key, fr.is_serious, fr.onset_age_years, fr.weight_kg,
                 fr.sex_code, fr.report_type, country.iso2_code,
                 reporter.qualification, date_dim.year, date_dim.month
        ORDER BY date_dim.year, date_dim.month, fr.report_key
        """
        frame = pd.read_sql_query(query, connection)
    if frame.empty:
        raise RuntimeError("No report features were returned from SQL Server")
    frame["is_serious"] = frame["is_serious"].astype(int)
    return frame


def _preprocessor() -> ColumnTransformer:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([
        ("numeric", numeric, NUMERIC_FEATURES),
        ("categorical", categorical, CATEGORICAL_FEATURES),
    ])


def _split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    periods = frame[["report_year", "report_month"]].drop_duplicates().sort_values(
        ["report_year", "report_month"]
    )
    cutoff_index = max(1, int(len(periods) * 0.8) - 1)
    cutoff = periods.iloc[cutoff_index]
    train_mask = (
        (frame["report_year"] < cutoff["report_year"])
        | (
            (frame["report_year"] == cutoff["report_year"])
            & (frame["report_month"] <= cutoff["report_month"])
        )
    )
    train = frame.loc[train_mask].copy()
    test = frame.loc[~train_mask].copy()
    if train.empty or test.empty or train["is_serious"].nunique() < 2:
        raise ValueError("Time split must produce non-empty train/test sets and two training classes")
    return train, test


def _evaluate(y_true: pd.Series, probabilities: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    probabilities = np.asarray(probabilities)
    predictions = (probabilities >= threshold).astype(int)
    observed, predicted = calibration_curve(y_true, probabilities, n_bins=5, strategy="quantile")
    calibration_error = float(np.mean(np.abs(observed - predicted))) if len(observed) else float("nan")
    return {
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "calibration_mean_absolute_error": calibration_error,
    }


def _statsmodels_logistic(
    train: pd.DataFrame, test: pd.DataFrame, preprocessor: ColumnTransformer
) -> dict[str, Any]:
    train_matrix = preprocessor.fit_transform(train[FEATURE_COLUMNS])
    test_matrix = preprocessor.transform(test[FEATURE_COLUMNS])
    names = preprocessor.get_feature_names_out().tolist()
    train_matrix = sm.add_constant(train_matrix, has_constant="add")
    test_matrix = sm.add_constant(test_matrix, has_constant="add")
    model = sm.Logit(train["is_serious"], train_matrix).fit(disp=False, maxiter=200)
    confidence = model.conf_int()

    def safe_exp(value: float) -> float | None:
        if not np.isfinite(value):
            return None
        clipped = np.clip(value, np.log(np.finfo(float).tiny), np.log(np.finfo(float).max))
        return float(np.exp(clipped))

    odds_ratios = {
        name: {
            "odds_ratio": safe_exp(float(model.params.iloc[index])),
            "ci_lower_95": safe_exp(float(confidence.iloc[index, 0])),
            "ci_upper_95": safe_exp(float(confidence.iloc[index, 1])),
        }
        for index, name in enumerate(["const", *names])
    }
    return {
        "aic": float(model.aic),
        "converged": bool(model.mle_retvals.get("converged", False)),
        "odds_ratios": odds_ratios,
        "probabilities": model.predict(test_matrix),
    }


def run() -> dict[str, Any]:
    frame = load_features()
    train, test = _split(frame)
    x_train, y_train = train[FEATURE_COLUMNS], train["is_serious"]
    x_test, y_test = test[FEATURE_COLUMNS], test["is_serious"]
    baseline_probability = float(y_train.mean())
    baseline = np.full(len(test), baseline_probability)

    logistic = Pipeline([
        ("preprocess", _preprocessor()),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    gradient_boosting = Pipeline([
        ("preprocess", _preprocessor()),
        ("model", GradientBoostingClassifier(random_state=42, n_estimators=150, max_depth=2)),
    ])
    models = {"logistic_regression": logistic, "gradient_boosting": gradient_boosting}
    evaluations: dict[str, Any] = {"baseline": _evaluate(y_test, baseline)}
    mlflow_uri = f"sqlite:///{MLFLOW_DB.resolve().as_posix()}"
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment("faers-seriousness-classifier")

    for name, model in models.items():
        with mlflow.start_run(run_name=name):
            model.fit(x_train, y_train)
            probabilities = model.predict_proba(x_test)[:, 1]
            metrics = _evaluate(y_test, probabilities)
            mlflow.log_params({"model": name, "train_rows": len(train), "test_rows": len(test)})
            mlflow.log_metrics(metrics)
            mlflow.sklearn.log_model(model, name="model", serialization_format="pickle")
            evaluations[name] = metrics

    stats_preprocessor = _preprocessor()
    statsmodels_result = _statsmodels_logistic(train, test, stats_preprocessor)
    evaluations["logistic_regression_statsmodels"] = {
        "aic": statsmodels_result["aic"],
        **_evaluate(y_test, np.asarray(statsmodels_result["probabilities"])),
        "odds_ratios": statsmodels_result["odds_ratios"],
    }
    selected_name = max(
        ("logistic_regression", "gradient_boosting"),
        key=lambda name: evaluations[name]["roc_auc"],
    )
    selected_model = models[selected_name]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "seriousness_classifier.joblib"
    joblib.dump(selected_model, model_path)
    output = {
        "target": "fact_report.is_serious",
        "feature_columns": FEATURE_COLUMNS,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_period": (
            f"{int(train.iloc[0].report_year)}-{int(train.iloc[0].report_month):02d} to "
            f"{int(train.iloc[-1].report_year)}-{int(train.iloc[-1].report_month):02d}"
        ),
        "test_period": (
            f"{int(test.iloc[0].report_year)}-{int(test.iloc[0].report_month):02d} to "
            f"{int(test.iloc[-1].report_year)}-{int(test.iloc[-1].report_month):02d}"
        ),
        "evaluation": evaluations,
        "selected_model": selected_name,
        "model_path": str(model_path.relative_to(ROOT)),
        "mlflow_tracking_uri": mlflow_uri,
        "limitation": "Spontaneous-reporting labels are not causal outcomes; temporal drift and class imbalance can affect performance.",
    }
    OUT.write_text(json.dumps(output, indent=2, default=float) + "\n", encoding="utf-8")
    print(f"ml_classifier.py: selected={selected_name}, ROC-AUC={evaluations[selected_name]['roc_auc']:.3f}")
    return output


if __name__ == "__main__":
    run()
