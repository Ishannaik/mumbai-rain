"""The student. Reads data/log.csv, trains a tiny calibrated rain classifier, and
promotes it to web/model.json ONLY if it beats both the current champion AND the raw
forecast on a time-split holdout. Runs daily in CI; no-ops until enough data exists.

Model = logistic regression (5 features -> probability of rain). Tiny, interpretable,
serves as plain arithmetic (sigmoid(w·x + b)) in the browser. Label is binary
(observed_raining from METAR), so this is calibration/classification, not regression —
the goal is cutting false alarms.
"""
import csv, json, math
from datetime import datetime, timedelta, timezone
from sklearn.linear_model import LogisticRegression

MODEL_PATH = "public/model.json"  # Astro serves this at /model.json (was web/model.json pre-Astro)
LOG_PATH = "data/log.csv"
MIN_ROWS = 200  # ~8-9 days of labelled data before a model is trustworthy
# Must match nowcast.js RAIN_THRESHOLD_MM and scoreboard RAIN_TH — one product definition
# of "raw rain call" (~noticeable drizzle). Labels remain METAR RA/DZ, not mm.
RAIN_MM = 0.3
# Ablation-tuned feature set (Aug 2026): adding relative_humidity_2m (the dominant
# monsoon rain predictor) cut holdout Brier 0.0761->0.0657 on all rows, and
# 0.0714->0.0603 on forward-only (serve-matching) rows. Dewpoint and lead-hours
# were tested and REJECTED — they added noise, not signal.
FEATURE_NAMES = ["fc_bestmatch_mm", "fc_ecmwf_mm", "fc_rh_bestmatch",
                 "hour_sin", "hour_cos", "recent_rain_mm"]

# Walk-forward validation. A single 80/20 split overstates skill: weather is autocorrelated
# and one valid_at appears once per lead time (~7 rows), so a neighbouring hour on the other
# side of the boundary is nearly the same observation.
FOLDS = 4
# Purge measured in HOURS, not rows. sklearn's TimeSeriesSplit(gap=n) gaps by row count,
# which here is ~7 rows per hour and drifts whenever a lead time is added or a snapshot is
# missed — so the gap is applied over valid_at instead.
PURGE_HOURS = 6
MIN_FOLD_ROWS = 25  # a fold smaller than this says nothing; skip it rather than score noise


def _parse_valid_at(row):
    """valid_at as a datetime. Logged as naive IST-local ISO, compared only against itself."""
    return datetime.fromisoformat(row["valid_at"])


def walk_forward_folds(rows, folds=FOLDS, purge_hours=PURGE_HOURS, min_fold_rows=MIN_FOLD_ROWS):
    """Expanding-window folds over time, purged. Yields (train_rows, test_rows) oldest first.

    Fold boundaries fall between DISTINCT valid_at values, never inside one, so the ~7 rows
    sharing a timestamp cannot be split across train and test. Training is then truncated to
    valid_at <= test_start - purge_hours, which is the leakage the purge exists to stop:
    without it the last training hour sits minutes away from the first test hour.

    Expanding rather than sliding: each fold trains on everything before it, which is how the
    model will actually be fitted in production.
    """
    stamps = sorted({_parse_valid_at(r) for r in rows})
    if len(stamps) < folds + 1:
        return

    # Equal-sized blocks of timestamps; the tail block absorbs any remainder.
    block = len(stamps) // (folds + 1)
    if block == 0:
        return

    for fold in range(1, folds + 1):
        boundary = stamps[block * fold]
        test_end = stamps[block * (fold + 1)] if fold < folds else None

        train_cutoff = boundary - timedelta(hours=purge_hours)
        train_rows = [r for r in rows if _parse_valid_at(r) <= train_cutoff]
        test_rows = [
            r
            for r in rows
            if _parse_valid_at(r) >= boundary and (test_end is None or _parse_valid_at(r) < test_end)
        ]

        if len(train_rows) < min_fold_rows or len(test_rows) < min_fold_rows:
            continue
        if len(set(int(float(r["observed_raining"])) for r in train_rows)) < 2:
            continue
        if len(set(int(float(r["observed_raining"])) for r in test_rows)) < 2:
            continue
        yield train_rows, test_rows


def brier_skill_score(cand_brier, ref_brier):
    """1 - cand/ref. Positive means better than the reference; 0 means no better.

    A reference Brier of 0 means the baseline was perfect on that fold, so there is no skill
    left to add: report 0.0 rather than dividing by zero.
    """
    if ref_brier == 0:
        return 0.0
    return 1.0 - (cand_brier / ref_brier)


def median(values):
    """Median without importing statistics for one call; empty -> None."""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def passes_walk_forward(fold_skills):
    """Median BSS vs raw > 0 across folds, and a win in at least 2 of them.

    Both conditions, not either: a median above zero carried by one huge fold is the "lucky
    monsoon week" the issue asks to exclude, and two wins out of three with a negative median
    means the losses were worse than the wins.
    """
    if len(fold_skills) < 2:
        return False
    med = median(fold_skills)
    wins = sum(1 for s in fold_skills if s > 0)
    return med is not None and med > 0 and wins >= 2


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def row_to_features(row, feature_names=None):
    """Feature vector in FEATURE_NAMES order. `feature_names` lets an OLD champion
    model (5 features) be scored on the SAME row without breaking on the new 6th.
    Missing RH falls back to 0 (pre-RH rows / nulls) rather than poisoning the sum."""
    names = feature_names or FEATURE_NAMES
    bm = _f(row["fc_bestmatch_mm"])
    ec = _f(row.get("fc_ecmwf_mm"), bm)        # blank benchmark -> fall back to best_match
    hour = _f(row["hour"])
    feats = {
        "fc_bestmatch_mm": bm,
        "fc_ecmwf_mm": ec,
        "fc_rh_bestmatch": _f(row.get("fc_rh_bestmatch"), 50.0),  # 50% RH = neutral monsoon
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "recent_rain_mm": _f(row["recent_rain_mm"]),
    }
    return [feats[n] for n in names]


IST = timezone(timedelta(hours=5, minutes=30))  # Asia/Kolkata, matches valid_at grid


def matured(rows):
    """Labelled rows whose valid hour is NOT in the past relative to issue time.
    The app only ever SERVES forward hours (nowcast.js slices from the current
    hour), so training on same-day-past hours teaches the model a distribution
    it never sees at serve time — the forward-only filter removes that mismatch.
    Timezone care: issued_at is UTC, valid_at is IST (Open-Meteo Asia/Kolkata),
    so the issue time is converted to IST before comparing."""
    out = []
    for r in rows:
        if str(r.get("observed_raining", "")).strip() == "":
            continue
        try:
            issued_utc = datetime.strptime(r["issued_at"], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
            issued_ist = issued_utc.astimezone(IST)
            valid_ist = datetime.strptime(r["valid_at"], "%Y-%m-%dT%H:%M").replace(tzinfo=IST)
        except (KeyError, ValueError):
            continue
        if valid_ist < issued_ist:
            continue
        out.append(r)
    return out


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
    """A model.json that serves the raw Open-Meteo forecast: linear, weights [1,0,...],
    intercept 0 -> predict = max(0, fc_bestmatch_mm). type='raw' (not 'logistic') so the
    browser's linear path serves it as raw AND the next retrain's _load_champion ignores it.
    Keeps the stable model.json schema (same keys as a promoted model)."""
    return {
        "type": "raw",
        "features": FEATURE_NAMES,
        "weights": [1.0] + [0.0] * (len(FEATURE_NAMES) - 1),
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
    champ_b = None
    if champ:
        # An old champion declares its own features (5); score it on the same
        # holdout rows using ITS feature vector, not the new 6-feature one.
        champ_feats = champ.get("features") or FEATURE_NAMES
        champ_Xte = [row_to_features(r, champ_feats) for r in test_rows]
        champ_b = brier([predict_proba(champ, x) for x in champ_Xte], yte)

    # Walk-forward folds, scored against the raw forecast on each fold's own holdout.
    fold_skills = []
    for fold_train, fold_test in walk_forward_folds(rows):
        Xf_tr, yf_tr = build_xy(fold_train)
        Xf_te, yf_te = build_xy(fold_test)
        fold_model = train_classifier(Xf_tr, yf_tr)
        fold_cand = brier([predict_proba(fold_model, x) for x in Xf_te], yf_te)
        fold_raw = brier([1.0 if x[0] >= RAIN_MM else 0.0 for x in Xf_te], yf_te)
        skill = brier_skill_score(fold_cand, fold_raw)
        fold_skills.append(skill)
        print(f"  fold {len(fold_skills)}: n_train={len(fold_train)} n_test={len(fold_test)} "
              f"Brier={fold_cand:.4f} raw={fold_raw:.4f} BSS={skill:+.4f}")

    fold_median = median(fold_skills)
    walk_forward_ok = passes_walk_forward(fold_skills)

    candidate.update({
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_train": len(train_rows), "n_test": len(test_rows),
        "brier": round(cand_b, 4), "raw_brier": round(raw_b, 4),
        "clim_brier": round(clim_b, 4),
        "champion_brier": round(champ_b, 4) if champ_b is not None else None,
        "cv_folds": len(fold_skills),
        "cv_purge_hours": PURGE_HOURS,
        "cv_bss_vs_raw": [round(s, 4) for s in fold_skills],
        "cv_bss_median": round(fold_median, 4) if fold_median is not None else None,
    })
    print(f"candidate Brier={cand_b:.4f}  raw-forecast={raw_b:.4f}  "
          f"climatology={clim_b:.4f}  champion={champ_b}  "
          f"(raw rain ≥ {RAIN_MM} mm/h)")
    if fold_skills:
        print(f"walk-forward: {len(fold_skills)} fold(s), median BSS vs raw "
              f"{fold_median:+.4f}, wins {sum(1 for s in fold_skills if s > 0)}/{len(fold_skills)} "
              f"-> {'PASS' if walk_forward_ok else 'FAIL'}")
    else:
        print(f"walk-forward: no usable folds (need {PURGE_HOURS}h purge + variety in each) "
              "-> cannot promote on a single split alone.")

    if not walk_forward_ok:
        print("Rejected — walk-forward validation did not hold up across folds. Champion kept.")
    elif passes_gate(cand_b, champ_b, raw_b, clim_b):
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
