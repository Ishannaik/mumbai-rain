"""The student. Reads data/log.csv, trains a tiny calibrated rain classifier, and
promotes it to web/model.json ONLY if it beats both the current champion AND the raw
forecast on a time-split holdout. Runs daily in CI; no-ops until enough data exists.

Model = logistic regression (5 features -> probability of rain). Tiny, interpretable,
serves as plain arithmetic (sigmoid(w·x + b)) in the browser. Label is binary
(observed_raining from METAR), so this is calibration/classification, not regression —
the goal is cutting false alarms.
"""
import csv, json, math
from datetime import datetime, timezone
from sklearn.linear_model import LogisticRegression

MODEL_PATH = "public/model.json"  # Astro serves this at /model.json (was web/model.json pre-Astro)
LOG_PATH = "data/log.csv"
MIN_ROWS = 200  # ~8-9 days of labelled data before a model is trustworthy
# Must match nowcast.js RAIN_THRESHOLD_MM and scoreboard RAIN_TH — one product definition
# of "raw rain call" (~noticeable drizzle). Labels remain METAR RA/DZ, not mm.
RAIN_MM = 0.3
FEATURE_NAMES = ["fc_bestmatch_mm", "fc_ecmwf_mm", "hour_sin", "hour_cos", "recent_rain_mm"]


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def row_to_features(row):
    bm = _f(row["fc_bestmatch_mm"])
    ec = _f(row.get("fc_ecmwf_mm"), bm)        # blank benchmark -> fall back to best_match
    hour = _f(row["hour"])
    return [bm, ec, math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24),
            _f(row["recent_rain_mm"])]


def matured(rows):
    return [r for r in rows if str(r.get("observed_raining", "")).strip() != ""]


def build_xy(rows):
    return [row_to_features(r) for r in rows], [int(float(r["observed_raining"])) for r in rows]


def brier(probs, actual):
    """Mean squared error of probabilistic forecasts. Lower = better-calibrated."""
    return sum((p - a) ** 2 for p, a in zip(probs, actual)) / len(probs)


def sigmoid(z):
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))


def predict_proba(model, feats):
    z = model["intercept"] + sum(w * x for w, x in zip(model["weights"], feats))
    return sigmoid(z)


def passes_gate(cand_brier, champ_brier, raw_brier, clim_brier=None):
    """Promote only if the candidate beats raw, climatology (when provided), AND champion.
    Monotonic improvement — the live model can only be replaced by a better one.
    clim_brier is optional for back-compat with older tests; train always passes it."""
    if cand_brier > raw_brier:
        return False
    if clim_brier is not None and cand_brier > clim_brier:
        return False
    if champ_brier is not None and cand_brier > champ_brier:
        return False
    return True


def should_demote(champ_b, raw_b, clim_b=None):
    """True when a STANDING logistic champion no longer beats the raw forecast (or clim)
    on the fresh holdout — it must re-earn its place under the same bar a candidate faces.
    champ_b is None when there's no logistic champion → nothing to demote.
    Strict '>' so a tie keeps the champion."""
    if champ_b is None:
        return False
    if champ_b > raw_b:
        return True
    if clim_b is not None and champ_b > clim_b:
        return True
    return False


def raw_passthrough_model(raw_b, clim_b, champ_b, n_train, n_test, trained_at):
    """A model.json that serves the raw Open-Meteo forecast: linear, weights [1,0,0,0,0],
    intercept 0 -> predict = max(0, fc_bestmatch_mm). type='raw' (not 'logistic') so the
    browser's linear path serves it as raw AND the next retrain's _load_champion ignores it.
    Keeps the stable model.json schema (same keys as a promoted model)."""
    return {
        "type": "raw",
        "features": FEATURE_NAMES,
        "weights": [1.0, 0.0, 0.0, 0.0, 0.0],
        "intercept": 0.0,
        "trained_at": trained_at,
        "n_train": n_train, "n_test": n_test,
        "brier": round(raw_b, 4),          # it now IS raw, so its Brier == raw's
        "raw_brier": round(raw_b, 4),
        "clim_brier": round(clim_b, 4),
        "champion_brier": round(champ_b, 4) if champ_b is not None else None,
    }


def train_classifier(X, y):
    clf = LogisticRegression(max_iter=1000).fit(X, y)
    return {
        "type": "logistic",
        "features": FEATURE_NAMES,
        "weights": [round(float(w), 6) for w in clf.coef_[0]],
        "intercept": round(float(clf.intercept_[0]), 6),
    }


def _load_champion():
    try:
        with open(MODEL_PATH) as f:
            m = json.load(f)
        return m if m.get("type") == "logistic" else None  # ignore the seeded regression stub
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def main():
    with open(LOG_PATH, newline="") as f:
        rows = matured(list(csv.DictReader(f)))

    if len(rows) < MIN_ROWS:
        print(f"{len(rows)}/{MIN_ROWS} matured rows — not enough to train yet. Skipping (no-op).")
        return

    rows.sort(key=lambda r: r["valid_at"])               # time order — no leakage
    split = int(len(rows) * 0.8)
    train_rows, test_rows = rows[:split], rows[split:]
    Xtr, ytr = build_xy(train_rows)
    Xte, yte = build_xy(test_rows)

    if len(set(ytr)) < 2 or len(set(yte)) < 2:
        print("Train/holdout lacks both rain and dry examples — skipping until more variety.")
        return

    candidate = train_classifier(Xtr, ytr)
    cand_b = brier([predict_proba(candidate, x) for x in Xte], yte)

    base_rate = sum(ytr) / len(ytr)
    raw_b = brier([1.0 if x[0] >= RAIN_MM else 0.0 for x in Xte], yte)   # raw forecast's rain call
    clim_b = brier([base_rate] * len(yte), yte)                          # always predict base rate
    champ = _load_champion()
    champ_b = brier([predict_proba(champ, x) for x in Xte], yte) if champ else None

    candidate.update({
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_train": len(train_rows), "n_test": len(test_rows),
        "brier": round(cand_b, 4), "raw_brier": round(raw_b, 4),
        "clim_brier": round(clim_b, 4),
        "champion_brier": round(champ_b, 4) if champ_b is not None else None,
    })
    print(f"candidate Brier={cand_b:.4f}  raw-forecast={raw_b:.4f}  "
          f"climatology={clim_b:.4f}  champion={champ_b}  "
          f"(raw rain ≥ {RAIN_MM} mm/h)")

    if passes_gate(cand_b, champ_b, raw_b, clim_b):
        with open(MODEL_PATH, "w") as f:
            json.dump(candidate, f, indent=2)
        print("PROMOTED — beats raw forecast, climatology, AND champion.")
    elif should_demote(champ_b, raw_b, clim_b):
        demoted = raw_passthrough_model(
            raw_b, clim_b, champ_b, len(train_rows), len(test_rows),
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        with open(MODEL_PATH, "w") as f:
            json.dump(demoted, f, indent=2)
        print(f"DEMOTED to raw — champion (Brier {champ_b:.4f}) no longer beats raw "
              f"({raw_b:.4f}) and/or clim ({clim_b:.4f}). Serving the forecast until a model beats it.")
    else:
        print("Rejected — did not beat raw + clim + champion. Champion kept.")


if __name__ == "__main__":
    main()
