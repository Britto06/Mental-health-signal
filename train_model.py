"""
Trains the Mental Health Signal model.

IMPORTANT: there's no real student survey dataset here yet, so this generates
SYNTHETIC training data using the same rule-based logic as the site's local
demo model, plus random noise. That means right now the Random Forest will
mostly learn to reproduce those rules (with some smoothing from the noise) —
it is NOT yet learning from real human data.

To make this a genuine predictive model for your report, replace `synth_row`
and `label_score` below with a real dataset (e.g. a survey you run with your
club, or a public dataset such as one of the "Social Media & Mental Health"
sets on Kaggle) with real `mental_health_score` labels. Everything else
(the Pipeline, ColumnTransformer, evaluation, joblib export) stays the same.
"""

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder, OrdinalEncoder, FunctionTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import joblib

RNG = np.random.default_rng(42)
N_SAMPLES = 4000

STRESS_LEVELS = ["Low", "Medium", "High", "Very High"]
STRESS_WEIGHT = {"Low": 0, "Medium": 1, "High": 2.5, "Very High": 4.2}


def synth_row():
    return dict(
        age=int(RNG.integers(16, 60)),
        gender=RNG.choice(["Male", "Female", "Other"]),
        academic_level=RNG.choice(["High school", "Undergraduate", "Postgraduate"]),
        platform=RNG.choice(["Instagram", "YouTube", "WhatsApp", "X"]),
        purpose=RNG.choice(["Entertainment", "Education", "Social connection", "Work"]),
        screen_time=round(float(np.clip(RNG.normal(5, 2.5), 0, 16)), 1),
        phone_unlocks=int(np.clip(RNG.normal(80, 40), 0, 300)),
        study_hours=round(float(np.clip(RNG.normal(3.5, 2), 0, 16)), 1),
        activity=round(float(np.clip(RNG.normal(1, 0.8), 0, 8)), 1),
        sleep=round(float(np.clip(RNG.normal(6.8, 1.5), 0, 14)), 1),
        stress=RNG.choice(STRESS_LEVELS, p=[0.25, 0.35, 0.25, 0.15]),
    )


def age_modifier(age):
    return float(np.clip(1.3 - (age - 15) * 0.015, 0.8, 1.3))


def label_score(row):
    score = 0.0
    mod = age_modifier(row["age"])
    score += max(0, 7 - row["sleep"]) * 0.5 + max(0, row["sleep"] - 9) * 0.3
    score += max(0, row["screen_time"] - 4) * 0.35 * mod
    score += max(0, row["phone_unlocks"] - 60) * 0.015 * mod
    if row["study_hours"] < 1.5:
        score += (1.5 - row["study_hours"]) * 0.4
    if row["study_hours"] > 7:
        score += (row["study_hours"] - 7) * 0.3
    score += max(0, 0.5 - row["activity"]) * 1.0
    if row["purpose"] == "Entertainment" and row["screen_time"] > 5:
        score += 0.4 * mod
    score += STRESS_WEIGHT[row["stress"]]
    score += RNG.normal(0, 0.4)  # noise, so it isn't a perfect lookup table
    return float(np.clip(score, 0, 10))


def build_dataset(n=N_SAMPLES):
    rows = [synth_row() for _ in range(n)]
    df = pd.DataFrame(rows)
    df["mental_health_score"] = [label_score(r) for r in rows]
    return df


def build_pipeline():
    numeric_features = ["screen_time", "study_hours", "activity", "sleep"]
    skewed_features = ["phone_unlocks"]
    ordinal_features = ["stress"]
    categorical_features = ["gender", "academic_level", "platform", "purpose"]
    passthrough_numeric = ["age"]

    preprocessor = ColumnTransformer(transformers=[
        ("num", StandardScaler(), numeric_features),
        ("skewed", Pipeline([
            ("log", FunctionTransformer(np.log1p, validate=True, feature_names_out="one-to-one")),
            ("scale", StandardScaler()),
        ]), skewed_features),
        ("ord", OrdinalEncoder(categories=[STRESS_LEVELS]), ordinal_features),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
        ("age", StandardScaler(), passthrough_numeric),
    ])

    return Pipeline([
        ("preprocess", preprocessor),
        ("rf", RandomForestRegressor(n_estimators=300, max_depth=12, random_state=42, n_jobs=-1)),
    ])


def main():
    df = build_dataset()
    X = df.drop(columns=["mental_health_score"])
    y = df["mental_health_score"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = build_pipeline()
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    print(f"R2:   {r2_score(y_test, pred):.4f}")
    print(f"MAE:  {mean_absolute_error(y_test, pred):.4f}")
    try:
        rmse = mean_squared_error(y_test, pred, squared=False)
    except TypeError:
        rmse = np.sqrt(mean_squared_error(y_test, pred))
    print(f"RMSE: {rmse:.4f}")

    joblib.dump(model, "pipeline.pkl")
    print("Saved pipeline.pkl")


if __name__ == "__main__":
    main()