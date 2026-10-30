
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer, make_column_selector
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from sklearn.utils.multiclass import type_of_target


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "datasets" / "diabetes.csv"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "diabetes_model.joblib"


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATA_PATH}"
        )

    df = pd.read_csv(DATA_PATH)

    df.columns = (
        df.columns.str.strip().str.lower()
    )

    df = df.drop_duplicates()

    if "class" not in df.columns:
        raise ValueError(
            "Target column 'class' was not found. "
            f"Columns found: {list(df.columns)}"
        )

    for col in df.select_dtypes(
        include=["object", "string"]
    ).columns:
        df[col] = df[col].str.strip()

    df = df.dropna(subset=["class"])

    X = df.drop(columns=["class"])
    y = df["class"].astype(str).str.strip()

    if X.empty or y.nunique() < 2:
        raise ValueError(
            "The dataset must contain features "
            "and at least two target classes."
        )

    if type_of_target(y) not in ("binary", "multiclass"):
        raise ValueError(
            "The target column is not a valid "
            "classification target."
        )

    if "age" in X.columns:
        X["age"] = pd.to_numeric(
            X["age"], errors="coerce"
        )

    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)

    numeric_selector = make_column_selector(
        dtype_include=np.number
    )
    categorical_selector = make_column_selector(
        dtype_exclude=np.number
    )

    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median"))
    ])

    categorical_pipeline = Pipeline([
        (
            "imputer",
            SimpleImputer(strategy="most_frequent")
        ),
        (
            "encoder",
            OneHotEncoder(handle_unknown="ignore")
        )
    ])

    preprocessing = ColumnTransformer([
        ("numeric", numeric_pipeline, numeric_selector),
        (
            "categorical",
            categorical_pipeline,
            categorical_selector
        )
    ])

    pipeline = Pipeline([
        ("preprocessing", preprocessing),
        (
            "classifier",
            RandomForestClassifier(
                n_estimators=200,
                random_state=42,
                class_weight="balanced"
            )
        )
    ])

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y_encoded,
        test_size=0.20,
        random_state=42,
        stratify=y_encoded
    )

    print("Dataset loaded successfully")
    print("Rows:", len(df))
    print("Features:", X.shape[1])
    print("Target classes:", list(label_encoder.classes_))
    print("Training records:", len(X_train))
    print("Testing records:", len(X_test))

    pipeline.fit(X_train, y_train)

    predictions = pipeline.predict(X_test)

    print("\nModel evaluation")
    print("Accuracy:", round(
        accuracy_score(y_test, predictions), 4
    ))

    print("\nClassification report:")
    print(classification_report(
        y_test,
        predictions,
        labels=np.arange(len(label_encoder.classes_)),
        target_names=[
            str(c) for c in label_encoder.classes_
        ],
        zero_division=0
    ))

    print("Confusion matrix:")
    print(confusion_matrix(
        y_test,
        predictions,
        labels=np.arange(len(label_encoder.classes_))
    ))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump({
        "pipeline": pipeline,
        "label_encoder": label_encoder,
        "feature_columns": list(X.columns),
        "target_name": "class"
    }, MODEL_PATH)

    print("\nSaved model to:", MODEL_PATH)


if __name__ == "__main__":
    main()
