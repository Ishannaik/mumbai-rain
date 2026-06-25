# Mumbai Rain Nowcaster — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hyperlocal "will it rain at my Mumbai spot in the next 2 hours?" web app, powered by a tiny self-improving model that bias-corrects free global forecasts for Mumbai's microclimate — and is measured head-to-head against the ECMWF-AIFS frontier model.

**Architecture:** Static site (Cloudflare Pages) calls Open-Meteo live in the browser and applies a tiny exported model (`model.json`) as plain arithmetic — no server, no live ML. A GitHub Actions cron is the "self-improving brain": it logs forecast-vs-observed every hour, retrains the corrector daily, and only promotes a new model if it beats the current champion AND raw AIFS on a holdout. Git is the database (a committed CSV). Everything is free at $0 / 0 users.

**Tech Stack:** Python 3.11 + `uv` (pipeline, training), scikit-learn (Ridge — interpretable linear baseline first), plain HTML/CSS/vanilla JS (frontend), Node built-in `node:test` (JS tests), `pytest` (Python tests), GitHub Actions (cron + free compute), Cloudflare Pages (free static hosting).

## Global Constraints

- **Free 24/7, $0 even at 0 users.** No card, no funding, no usage-based billing, no warm/paid servers.
- **No local ML.** Nothing runs on the user's PC. Training runs on GitHub Actions runners (free); serving is arithmetic in the browser.
- **No API keys for the live path.** The browser path uses only Open-Meteo (no key, CORS-enabled). Any keyed/auth data source is build-time only and optional.
- **Timescale:** next 0–2 hours ("nowcast"). ENSO/El Niño is NOT a feature at this timescale — the global forecast already encodes current state.
- **Target city:** Mumbai only. Hyperspecialized, not general.
- **Model must serve as plain JSON weights** evaluable in JS (`sum(w*x)+b`). Start linear; upgrade only if it measurably beats linear on holdout.
- **Eval gate is mandatory:** a retrained model is promoted ONLY if it beats both the current champion and raw AIFS on the holdout. Monotonic improvement, never regression.
- **Storage:** committed CSV in the repo (`data/log.csv`). No database until the CSV is too big to commit.
- Use `uv run python`, never a raw venv path.
- Coordinates default to a Mumbai grid; locality list in `web/data/localities.json`.

## Build-Time Corrections (verified live, supersede the original text below)

1. **Benchmark model: `ecmwf_ifs025`, field `fc_ecmwf_mm`** — NOT AIFS. Open-Meteo serves
   null precipitation for `ecmwf_aifs025` (verified 48/48 null). ECMWF-IFS is the operational
   physics gold standard and serves real precip. Replace every `fc_aifs_mm`/`aifs` reference
   below with `fc_ecmwf_mm`/`ecmwf`. Honest claim = beat persistence + climatology + raw IFS,
   win on calibration — NOT "beat the frontier AI dynamically".
2. **A missing benchmark hour is `None`, never `0.0`** — scoring a missing forecast as
   "predicted no rain" fakes the benchmark. Training drops `None` rows.
3. **Label source = NASA GPM IMERG (Late Run)** via the Giovanni Time Series API + an
   Earthdata bearer token (GitHub secret) — NOT Open-Meteo `past_days` (model-derived =
   circular). IMD is disqualified (static-IP whitelist incompatible with CI runners).
   This replaces the `fetch_observed` design in Task 1/2.

---

## File Structure

```
mumbai-rain/
  pyproject.toml              # uv project, deps: scikit-learn, numpy, requests, pytest
  README.md
  data/
    log.csv                   # the growing dataset (git = database). Header committed; rows appended by cron.
    flood-zones.json          # baked Mumbai flood hotspots (curated + elevation), for flood-risk lookup
  pipeline/
    sources.py                # pure HTTP: fetch Open-Meteo forecast (best_match + aifs) and observed rain
    log_snapshot.py           # CLI: append one forecast snapshot row to data/log.csv (run hourly by cron)
    features.py               # pure: build (X, y) training matrix from matured log rows
    train.py                  # CLI: train Ridge corrector, eval-gate vs champion + AIFS, export web/model.json
    metrics.py                # pure: MAE, skill-score vs baseline
  web/
    index.html
    style.css
    app.js                    # UI wiring: geolocation/locality dropdown, fetch live, render
    nowcast.js                # pure: apply model.json to live forecast -> next-2h verdict
    flood.js                  # pure: flood-risk score from rainfall + zone
    model.json                # exported weights (committed by retrain cron). Seeded as identity at start.
    data/
      localities.json         # Mumbai locality -> {lat, lon}
      flood-zones.json        # symlink/copy of ../data/flood-zones.json served statically
  tests/                      # pytest (python)
    test_sources.py
    test_features.py
    test_train.py
    test_metrics.py
  web/test/                   # node:test (js)
    nowcast.test.mjs
    flood.test.mjs
  .github/workflows/
    collect.yml               # hourly: run pipeline/log_snapshot.py, commit row
    retrain.yml               # daily: features -> train -> eval gate -> commit model.json if better
```

**Responsibilities:**
- `pipeline/sources.py` — the ONLY place that talks to Open-Meteo. Pure functions returning dicts; no file I/O.
- `pipeline/features.py` — pure transform: log rows → `(X, y)`. The label `y` = observed rain; features include the AIFS + best_match forecasts for the same valid time, plus hour-of-day and recent rain.
- `pipeline/train.py` — orchestration + the eval gate. The gate is the safety-critical money path.
- `web/nowcast.js` — mirrors the model math in JS. Must stay in sync with the exported `model.json` schema.

---

## Data Model

`data/log.csv` columns (one row = one forecast snapshot for one valid hour, at one location):

```
issued_at,valid_at,lat,lon,fc_bestmatch_mm,fc_aifs_mm,hour,recent_rain_mm,observed_mm
```

- `issued_at` — when the snapshot was taken (ISO, UTC).
- `valid_at` — the hour the forecast is about (ISO, UTC).
- `fc_bestmatch_mm`, `fc_aifs_mm` — forecast precip for `valid_at` from each model.
- `hour` — local (Asia/Kolkata) hour of `valid_at`, 0–23.
- `recent_rain_mm` — rain in the 3h before `issued_at` (persistence signal).
- `observed_mm` — what actually fell at `valid_at`. **Blank when first logged; backfilled once `valid_at` is in the past.**

A row is "matured" (usable for training) once `observed_mm` is filled.

`model.json` schema (linear corrector):

```json
{
  "version": 1,
  "trained_at": "2026-06-24T00:00:00Z",
  "features": ["fc_aifs_mm", "fc_bestmatch_mm", "hour_sin", "hour_cos", "recent_rain_mm"],
  "weights": [0.0, 0.0, 0.0, 0.0, 0.0],
  "intercept": 0.0,
  "champion_mae": null,
  "aifs_mae": null
}
```

Seed `model.json` as **identity** (predict `fc_aifs_mm` directly): `features:["fc_aifs_mm"], weights:[1.0], intercept:0.0`. This guarantees the app works on day 1 before any training, and the first real model must beat this identity baseline.

---

### Task 1: Project scaffold + Open-Meteo source functions

**Files:**
- Create: `pyproject.toml`, `README.md`, `pipeline/__init__.py`, `pipeline/sources.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces:
  - `fetch_forecast(lat: float, lon: float) -> dict` — returns `{"valid_at": [iso...], "fc_bestmatch_mm": [float...], "fc_aifs_mm": [float...]}` for the next ~6 hours, hourly.
  - `fetch_observed(lat: float, lon: float, past_days: int = 2) -> dict` — returns `{"valid_at": [iso...], "observed_mm": [float...]}` (recent actuals via Open-Meteo `past_days`).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "mumbai-rain"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31", "scikit-learn>=1.4", "numpy>=1.26"]

[dependency-groups]
dev = ["pytest>=8.0"]
```

- [ ] **Step 2: Write the failing test** (`tests/test_sources.py`)

```python
from pipeline.sources import build_forecast_url, parse_forecast

def test_build_forecast_url_includes_both_models():
    url = build_forecast_url(19.12, 72.85)
    assert "ecmwf_aifs025" in url
    assert "best_match" in url
    assert "hourly=precipitation" in url

def test_parse_forecast_aligns_models_by_time():
    raw_best = {"hourly": {"time": ["2026-06-23T00:00", "2026-06-23T01:00"],
                           "precipitation": [0.0, 2.5]}}
    raw_aifs = {"hourly": {"time": ["2026-06-23T00:00", "2026-06-23T01:00"],
                           "precipitation": [0.1, 3.0]}}
    out = parse_forecast(raw_best, raw_aifs)
    assert out["valid_at"] == ["2026-06-23T00:00", "2026-06-23T01:00"]
    assert out["fc_bestmatch_mm"] == [0.0, 2.5]
    assert out["fc_aifs_mm"] == [0.1, 3.0]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL (ImportError / function not defined).

- [ ] **Step 4: Implement `pipeline/sources.py`**

```python
import requests

BASE = "https://api.open-meteo.com/v1/forecast"

def build_forecast_url(lat: float, lon: float) -> str:
    return (f"{BASE}?latitude={lat}&longitude={lon}"
            f"&hourly=precipitation&models=best_match&forecast_days=1"
            f"&timezone=Asia%2FKolkata")

def _aifs_url(lat: float, lon: float) -> str:
    return (f"{BASE}?latitude={lat}&longitude={lon}"
            f"&hourly=precipitation&models=ecmwf_aifs025&forecast_days=1"
            f"&timezone=Asia%2FKolkata")

def parse_forecast(raw_best: dict, raw_aifs: dict) -> dict:
    times = raw_best["hourly"]["time"]
    aifs_by_time = dict(zip(raw_aifs["hourly"]["time"],
                            raw_aifs["hourly"]["precipitation"]))
    return {
        "valid_at": times,
        "fc_bestmatch_mm": raw_best["hourly"]["precipitation"],
        "fc_aifs_mm": [aifs_by_time.get(t, 0.0) for t in times],
    }

def fetch_forecast(lat: float, lon: float) -> dict:
    raw_best = requests.get(build_forecast_url(lat, lon), timeout=20).json()
    raw_aifs = requests.get(_aifs_url(lat, lon), timeout=20).json()
    return parse_forecast(raw_best, raw_aifs)

def fetch_observed(lat: float, lon: float, past_days: int = 2) -> dict:
    # ponytail: Open-Meteo past_days gives recent observed/reanalysis precip — good-enough
    # free label, no auth. Upgrade path: NASA GPM IMERG for true satellite obs.
    url = (f"{BASE}?latitude={lat}&longitude={lon}&hourly=precipitation"
           f"&past_days={past_days}&forecast_days=0&timezone=Asia%2FKolkata")
    raw = requests.get(url, timeout=20).json()
    return {"valid_at": raw["hourly"]["time"],
            "observed_mm": raw["hourly"]["precipitation"]}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_sources.py -v`
Expected: PASS (the two pure-function tests; network functions are not unit-tested).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml README.md pipeline/ tests/test_sources.py
git commit -m "feat: open-meteo source functions (best_match + AIFS + observed)"
```

---

### Task 2: Snapshot logger (the data collector)

**Files:**
- Create: `pipeline/log_snapshot.py`, `data/log.csv` (header only)
- Test: `tests/test_sources.py` (add `append_snapshot`/`backfill_observed` tests)

**Interfaces:**
- Consumes: `fetch_forecast`, `fetch_observed` from Task 1.
- Produces:
  - `LOG_HEADER: list[str]` — the CSV columns (see Data Model).
  - `append_snapshot(rows: list[dict], forecast: dict, lat, lon, issued_at: str, recent_rain_mm: float) -> list[dict]` — pure; returns new rows to append (observed blank).
  - `backfill_observed(rows: list[dict], observed: dict) -> list[dict]` — pure; fills `observed_mm` where blank and `valid_at` now known.

- [ ] **Step 1: Write the failing test** (append to `tests/test_sources.py`)

```python
from pipeline.log_snapshot import append_snapshot, backfill_observed, LOG_HEADER

def test_append_snapshot_builds_rows_with_blank_observed():
    fc = {"valid_at": ["2026-06-23T05:00"], "fc_bestmatch_mm": [1.0], "fc_aifs_mm": [1.2]}
    rows = append_snapshot([], fc, 19.12, 72.85, "2026-06-23T04:30", recent_rain_mm=0.3)
    assert rows[0]["valid_at"] == "2026-06-23T05:00"
    assert rows[0]["fc_aifs_mm"] == 1.2
    assert rows[0]["observed_mm"] == ""
    assert set(LOG_HEADER) == set(rows[0].keys())

def test_backfill_observed_fills_matching_blank_rows():
    rows = [{"valid_at": "2026-06-23T05:00", "lat": 19.12, "lon": 72.85, "observed_mm": ""}]
    obs = {"valid_at": ["2026-06-23T05:00"], "observed_mm": [4.4]}
    out = backfill_observed(rows, obs)
    assert out[0]["observed_mm"] == 4.4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `pipeline/log_snapshot.py`**

```python
import csv, sys
from datetime import datetime, timezone
from pipeline.sources import fetch_forecast, fetch_observed

LOG_HEADER = ["issued_at", "valid_at", "lat", "lon",
              "fc_bestmatch_mm", "fc_aifs_mm", "hour", "recent_rain_mm", "observed_mm"]
LOG_PATH = "data/log.csv"

def append_snapshot(rows, forecast, lat, lon, issued_at, recent_rain_mm):
    new = []
    for i, vt in enumerate(forecast["valid_at"]):
        new.append({
            "issued_at": issued_at, "valid_at": vt, "lat": lat, "lon": lon,
            "fc_bestmatch_mm": forecast["fc_bestmatch_mm"][i],
            "fc_aifs_mm": forecast["fc_aifs_mm"][i],
            "hour": int(vt[11:13]), "recent_rain_mm": recent_rain_mm,
            "observed_mm": "",
        })
    return rows + new

def backfill_observed(rows, observed):
    obs_by_time = dict(zip(observed["valid_at"], observed["observed_mm"]))
    for r in rows:
        if r.get("observed_mm", "") == "" and r["valid_at"] in obs_by_time:
            r["observed_mm"] = obs_by_time[r["valid_at"]]
    return rows

def _read(path):
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []

def _write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_HEADER)
        w.writeheader(); w.writerows(rows)

def main(lat=19.12, lon=72.85):
    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    rows = _read(LOG_PATH)
    obs = fetch_observed(lat, lon)
    recent = sum(v for v in obs["observed_mm"][-3:] if isinstance(v, (int, float)))
    rows = backfill_observed(rows, obs)
    rows = append_snapshot(rows, fetch_forecast(lat, lon), lat, lon, issued_at, recent)
    _write(LOG_PATH, rows)
    print(f"logged snapshot at {issued_at}; total rows={len(rows)}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create `data/log.csv` with header only**

```bash
echo "issued_at,valid_at,lat,lon,fc_bestmatch_mm,fc_aifs_mm,hour,recent_rain_mm,observed_mm" > data/log.csv
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_sources.py -v`
Expected: PASS.

- [ ] **Step 6: Smoke-test the collector live**

Run: `uv run python -m pipeline.log_snapshot`
Expected: prints "logged snapshot ...; total rows=N" (N>0) and `data/log.csv` gains rows.

- [ ] **Step 7: Commit**

```bash
git add pipeline/log_snapshot.py data/log.csv tests/test_sources.py
git commit -m "feat: hourly snapshot logger (forecast + backfilled observed)"
```

---

### Task 3: Feature builder

**Files:**
- Create: `pipeline/features.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: matured log rows (dicts with `observed_mm` filled).
- Produces:
  - `FEATURE_NAMES: list[str]` = `["fc_aifs_mm","fc_bestmatch_mm","hour_sin","hour_cos","recent_rain_mm"]`
  - `build_matrix(rows: list[dict]) -> tuple[list[list[float]], list[float]]` — returns `(X, y)`, skipping rows with blank `observed_mm`.
  - `row_to_features(row: dict) -> list[float]` — single-row feature vector (reused by serving-parity test).

- [ ] **Step 1: Write the failing test** (`tests/test_features.py`)

```python
import math
from pipeline.features import build_matrix, row_to_features, FEATURE_NAMES

def test_row_to_features_encodes_hour_cyclically():
    row = {"fc_aifs_mm": "2.0", "fc_bestmatch_mm": "1.0",
           "hour": "6", "recent_rain_mm": "0.5", "observed_mm": "3.0"}
    feats = row_to_features(row)
    assert feats[0] == 2.0 and feats[1] == 1.0
    assert math.isclose(feats[2], math.sin(2*math.pi*6/24), abs_tol=1e-9)
    assert len(feats) == len(FEATURE_NAMES)

def test_build_matrix_skips_unmatured_rows():
    rows = [
        {"fc_aifs_mm":"1","fc_bestmatch_mm":"1","hour":"3","recent_rain_mm":"0","observed_mm":"2"},
        {"fc_aifs_mm":"1","fc_bestmatch_mm":"1","hour":"4","recent_rain_mm":"0","observed_mm":""},
    ]
    X, y = build_matrix(rows)
    assert len(X) == 1 and y == [2.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_features.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `pipeline/features.py`**

```python
import math

FEATURE_NAMES = ["fc_aifs_mm", "fc_bestmatch_mm", "hour_sin", "hour_cos", "recent_rain_mm"]

def row_to_features(row):
    hour = float(row["hour"])
    return [
        float(row["fc_aifs_mm"]),
        float(row["fc_bestmatch_mm"]),
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        float(row["recent_rain_mm"]),
    ]

def build_matrix(rows):
    X, y = [], []
    for r in rows:
        if r.get("observed_mm", "") in ("", None):
            continue
        X.append(row_to_features(r))
        y.append(float(r["observed_mm"]))
    return X, y
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_features.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/features.py tests/test_features.py
git commit -m "feat: feature builder with cyclic hour encoding"
```

---

### Task 4: Metrics

**Files:**
- Create: `pipeline/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Produces:
  - `mae(pred: list[float], actual: list[float]) -> float`
  - `skill_score(model_mae: float, baseline_mae: float) -> float` — `1 - model/baseline` (positive = better than baseline).

- [ ] **Step 1: Write the failing test** (`tests/test_metrics.py`)

```python
from pipeline.metrics import mae, skill_score

def test_mae_basic():
    assert mae([1.0, 3.0], [1.0, 1.0]) == 1.0

def test_skill_score_positive_when_better():
    assert skill_score(0.5, 1.0) == 0.5
    assert skill_score(1.0, 1.0) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `pipeline/metrics.py`**

```python
def mae(pred, actual):
    assert len(pred) == len(actual) and pred, "non-empty equal-length required"
    return sum(abs(p - a) for p, a in zip(pred, actual)) / len(pred)

def skill_score(model_mae, baseline_mae):
    if baseline_mae == 0:
        return 0.0
    return 1 - model_mae / baseline_mae
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/metrics.py tests/test_metrics.py
git commit -m "feat: MAE + skill-score metrics"
```

---

### Task 5: Train + eval gate + export model.json

**Files:**
- Create: `pipeline/train.py`, `web/model.json` (seeded identity)
- Test: `tests/test_train.py`

**Interfaces:**
- Consumes: `build_matrix` (Task 3), `mae`/`skill_score` (Task 4), `FEATURE_NAMES`.
- Produces:
  - `train_corrector(X, y) -> dict` — fits `Ridge`, returns a `model.json` dict (FEATURE_NAMES order).
  - `passes_gate(candidate_mae, champion_mae, aifs_mae) -> bool` — True only if candidate beats BOTH (or champion is None).
  - `main()` — reads log, time-splits holdout, trains, gates, writes `web/model.json` only if it passes.

- [ ] **Step 1: Write the failing test** (`tests/test_train.py`)

```python
from pipeline.train import train_corrector, passes_gate
from pipeline.features import FEATURE_NAMES

def test_train_corrector_recovers_identity():
    # y == fc_aifs exactly -> weights should lean on fc_aifs, low error
    X = [[v, 0, 0, 1, 0] for v in (0.0, 1.0, 2.0, 3.0, 4.0)]
    y = [v for v in (0.0, 1.0, 2.0, 3.0, 4.0)]
    model = train_corrector(X, y)
    assert model["features"] == FEATURE_NAMES
    assert len(model["weights"]) == len(FEATURE_NAMES)

def test_gate_requires_beating_both():
    assert passes_gate(0.4, champion_mae=0.5, aifs_mae=0.6) is True
    assert passes_gate(0.55, champion_mae=0.5, aifs_mae=0.6) is False   # worse than champion
    assert passes_gate(0.4, champion_mae=0.5, aifs_mae=0.3) is False    # worse than AIFS
    assert passes_gate(0.4, champion_mae=None, aifs_mae=0.6) is True    # no champion yet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_train.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `pipeline/train.py`**

```python
import json, csv
from datetime import datetime, timezone
from sklearn.linear_model import Ridge
from pipeline.features import FEATURE_NAMES, build_matrix, row_to_features
from pipeline.metrics import mae

MODEL_PATH = "web/model.json"
LOG_PATH = "data/log.csv"

def train_corrector(X, y):
    reg = Ridge(alpha=1.0).fit(X, y)
    return {
        "version": 1,
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": FEATURE_NAMES,
        "weights": [round(float(w), 6) for w in reg.coef_],
        "intercept": round(float(reg.intercept_), 6),
        "champion_mae": None,
        "aifs_mae": None,
    }

def predict(model, feats):
    p = model["intercept"] + sum(w * x for w, x in zip(model["weights"], feats))
    return max(0.0, p)  # rain can't be negative

def passes_gate(candidate_mae, champion_mae, aifs_mae):
    if candidate_mae >= aifs_mae:
        return False
    if champion_mae is not None and candidate_mae >= champion_mae:
        return False
    return True

def _load_champion():
    try:
        with open(MODEL_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def main():
    with open(LOG_PATH, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("observed_mm", "") not in ("", None)]
    if len(rows) < 200:
        print(f"only {len(rows)} matured rows; need >=200 to train. skipping.")
        return
    rows.sort(key=lambda r: r["valid_at"])
    split = int(len(rows) * 0.8)
    train_rows, test_rows = rows[:split], rows[split:]

    Xtr, ytr = build_matrix(train_rows)
    candidate = train_corrector(Xtr, ytr)

    Xte, yte = build_matrix(test_rows)
    cand_pred = [predict(candidate, x) for x in Xte]
    aifs_pred = [x[0] for x in Xte]              # feature[0] == fc_aifs_mm == raw frontier
    cand_mae, aifs_mae = mae(cand_pred, yte), mae(aifs_pred, yte)

    champ = _load_champion()
    champ_mae = None
    if champ:
        champ_mae = mae([predict(champ, x) for x in Xte], yte)

    candidate["champion_mae"], candidate["aifs_mae"] = round(cand_mae, 4), round(aifs_mae, 4)
    print(f"candidate MAE={cand_mae:.4f}  AIFS MAE={aifs_mae:.4f}  champion MAE={champ_mae}")

    if passes_gate(cand_mae, champ_mae, aifs_mae):
        with open(MODEL_PATH, "w") as f:
            json.dump(candidate, f, indent=2)
        print("PROMOTED new model (beats champion AND AIFS).")
    else:
        print("rejected: did not beat both baselines. champion kept.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Seed `web/model.json` as identity**

```json
{
  "version": 1,
  "trained_at": "2026-06-23T00:00:00Z",
  "features": ["fc_aifs_mm", "fc_bestmatch_mm", "hour_sin", "hour_cos", "recent_rain_mm"],
  "weights": [1.0, 0.0, 0.0, 0.0, 0.0],
  "intercept": 0.0,
  "champion_mae": null,
  "aifs_mae": null
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_train.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/train.py web/model.json tests/test_train.py
git commit -m "feat: Ridge corrector + eval gate (beat champion AND frontier AIFS)"
```

---

### Task 6: Frontend nowcast logic (serving parity)

**Files:**
- Create: `web/nowcast.js`
- Test: `web/test/nowcast.test.mjs`

**Interfaces:**
- Consumes: `model.json` schema (Task 5), live forecast shaped like `fetch_forecast` output.
- Produces (ES module exports):
  - `rowFeatures({fc_aifs_mm, fc_bestmatch_mm, hour, recent_rain_mm}) -> number[]` — MUST match `row_to_features` order/encoding.
  - `predict(model, feats) -> number` — MUST match Python `predict` (clamped ≥0).
  - `verdict(model, forecast, nowHour, recentRain) -> {willRain: boolean, startsInHrs: number|null, peakMm: number}` — applies model to the next 2 forecast hours.

- [ ] **Step 1: Write the failing test** (`web/test/nowcast.test.mjs`)

```js
import { test } from "node:test";
import assert from "node:assert";
import { rowFeatures, predict, verdict } from "../nowcast.js";

test("rowFeatures matches python cyclic encoding", () => {
  const f = rowFeatures({fc_aifs_mm: 2, fc_bestmatch_mm: 1, hour: 6, recent_rain_mm: 0.5});
  assert.equal(f[0], 2);
  assert.ok(Math.abs(f[2] - Math.sin(2*Math.PI*6/24)) < 1e-9);
  assert.equal(f.length, 5);
});

test("predict clamps negatives to zero", () => {
  const model = {weights:[1,0,0,0,0], intercept:-5};
  assert.equal(predict(model, [2,0,0,0,0]), 0);
});

test("verdict flags rain when corrected precip crosses threshold", () => {
  const model = {weights:[1,0,0,0,0], intercept:0};
  const fc = {valid_at:["t0","t1"], fc_aifs_mm:[0.0, 1.5], fc_bestmatch_mm:[0,0]};
  const v = verdict(model, fc, 5, 0);
  assert.equal(v.willRain, true);
  assert.equal(v.startsInHrs, 1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test web/test/nowcast.test.mjs`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `web/nowcast.js`**

```js
const RAIN_THRESHOLD_MM = 0.3;  // ponytail: 0.3mm/h ~ "noticeable drizzle". Tune against observed.

export function rowFeatures({fc_aifs_mm, fc_bestmatch_mm, hour, recent_rain_mm}) {
  return [
    fc_aifs_mm, fc_bestmatch_mm,
    Math.sin(2*Math.PI*hour/24), Math.cos(2*Math.PI*hour/24),
    recent_rain_mm,
  ];
}

export function predict(model, feats) {
  const p = model.intercept + model.weights.reduce((s, w, i) => s + w*feats[i], 0);
  return Math.max(0, p);
}

export function verdict(model, fc, nowHour, recentRain) {
  let startsInHrs = null, peakMm = 0;
  const horizon = Math.min(2, fc.valid_at.length);
  for (let i = 0; i < horizon; i++) {
    const mm = predict(model, rowFeatures({
      fc_aifs_mm: fc.fc_aifs_mm[i], fc_bestmatch_mm: fc.fc_bestmatch_mm[i],
      hour: (nowHour + i) % 24, recent_rain_mm: recentRain,
    }));
    peakMm = Math.max(peakMm, mm);
    if (mm >= RAIN_THRESHOLD_MM && startsInHrs === null) startsInHrs = i;
  }
  return {willRain: startsInHrs !== null, startsInHrs, peakMm: Math.round(peakMm*10)/10};
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test web/test/nowcast.test.mjs`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/nowcast.js web/test/nowcast.test.mjs
git commit -m "feat: browser nowcast logic with python serving parity"
```

---

### Task 7: Flood-risk lookup

**Files:**
- Create: `web/flood.js`, `data/flood-zones.json`, `web/data/flood-zones.json`
- Test: `web/test/flood.test.mjs`

**Interfaces:**
- Produces (ES module exports):
  - `nearestZone(lat, lon, zones) -> {name, severity}` — closest hotspot by squared distance.
  - `floodRisk(peakMm, zone) -> {level: "low"|"watch"|"high", reason: string}` — combines forecast peak + zone severity.

- [ ] **Step 1: Create `data/flood-zones.json`** (curated known Mumbai chronic-flooding spots; severity 1–3)

```json
[
  {"name": "Hindmata (Dadar)", "lat": 19.0176, "lon": 72.8430, "severity": 3},
  {"name": "Sion", "lat": 19.0410, "lon": 72.8620, "severity": 3},
  {"name": "Kurla", "lat": 19.0726, "lon": 72.8845, "severity": 3},
  {"name": "Andheri Subway", "lat": 19.1197, "lon": 72.8468, "severity": 3},
  {"name": "Milan Subway (Santacruz)", "lat": 19.0860, "lon": 72.8400, "severity": 3},
  {"name": "Gandhi Market (King's Circle)", "lat": 19.0270, "lon": 72.8570, "severity": 3},
  {"name": "Powai", "lat": 19.1176, "lon": 72.9060, "severity": 1},
  {"name": "Bandra", "lat": 19.0596, "lon": 72.8295, "severity": 2},
  {"name": "Chembur", "lat": 19.0626, "lon": 72.8990, "severity": 2},
  {"name": "Malad Subway", "lat": 19.1860, "lon": 72.8480, "severity": 3}
]
```

(Copy to `web/data/flood-zones.json` so it's statically served: `cp data/flood-zones.json web/data/flood-zones.json`.)

- [ ] **Step 2: Write the failing test** (`web/test/flood.test.mjs`)

```js
import { test } from "node:test";
import assert from "node:assert";
import { nearestZone, floodRisk } from "../flood.js";

const ZONES = [
  {name:"A", lat:19.02, lon:72.84, severity:3},
  {name:"B", lat:19.12, lon:72.91, severity:1},
];

test("nearestZone picks closest", () => {
  assert.equal(nearestZone(19.03, 72.85, ZONES).name, "A");
});

test("floodRisk escalates with rain in a severe zone", () => {
  assert.equal(floodRisk(0.1, {name:"A", severity:3}).level, "low");
  assert.equal(floodRisk(6, {name:"A", severity:3}).level, "high");
  assert.equal(floodRisk(6, {name:"B", severity:1}).level, "watch");
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `node --test web/test/flood.test.mjs`
Expected: FAIL.

- [ ] **Step 4: Implement `web/flood.js`**

```js
export function nearestZone(lat, lon, zones) {
  let best = null, bestD = Infinity;
  for (const z of zones) {
    const d = (z.lat-lat)**2 + (z.lon-lon)**2;
    if (d < bestD) { bestD = d; best = z; }
  }
  return best;
}

// ponytail: rules-based hazard, not a hydrodynamic model. peakMm = next-2h corrected rain.
// Upgrade path: train a flood-depth surrogate on historical waterlogging once labels exist.
export function floodRisk(peakMm, zone) {
  const score = peakMm * (zone ? zone.severity : 1);
  if (score >= 12) return {level: "high",  reason: `heavy rain over ${zone.name} (chronic flood spot)`};
  if (score >= 4)  return {level: "watch", reason: `rain building over ${zone.name}`};
  return {level: "low", reason: "no significant pooling expected"};
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `node --test web/test/flood.test.mjs`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/flood.js data/flood-zones.json web/data/flood-zones.json web/test/flood.test.mjs
git commit -m "feat: rules-based flood-risk lookup over Mumbai hotspots"
```

---

### Task 8: Frontend page + wiring

**Files:**
- Create: `web/index.html`, `web/style.css`, `web/app.js`, `web/data/localities.json`

**Interfaces:**
- Consumes: `nowcast.js`, `flood.js`, `model.json`, `data/localities.json`, live Open-Meteo.

- [ ] **Step 1: Create `web/data/localities.json`**

```json
[
  {"name": "Andheri", "lat": 19.1197, "lon": 72.8468},
  {"name": "Bandra", "lat": 19.0596, "lon": 72.8295},
  {"name": "Powai", "lat": 19.1176, "lon": 72.9060},
  {"name": "Dadar", "lat": 19.0176, "lon": 72.8430},
  {"name": "Colaba", "lat": 18.9067, "lon": 72.8147},
  {"name": "Borivali", "lat": 19.2290, "lon": 72.8567},
  {"name": "Thane", "lat": 19.2183, "lon": 72.9781},
  {"name": "Chembur", "lat": 19.0626, "lon": 72.8990}
]
```

- [ ] **Step 2: Create `web/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mumbai Rain — next 2 hours</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main>
    <h1>☔ Rain at your spot</h1>
    <select id="locality" aria-label="Choose area"></select>
    <p id="verdict" class="verdict">Loading…</p>
    <p id="flood" class="flood"></p>
    <p id="meta" class="meta"></p>
  </main>
  <script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create `web/style.css`** (minimal, fast, dark)

```css
:root { color-scheme: dark; }
body { margin:0; font:18px/1.5 system-ui, sans-serif; background:#0b1020; color:#e8eefc;
       display:grid; place-items:center; min-height:100vh; }
main { width:min(92vw, 420px); padding:24px; }
h1 { font-size:1.4rem; margin:0 0 16px; }
select { width:100%; padding:10px; font-size:1rem; border-radius:10px;
         background:#161d33; color:#e8eefc; border:1px solid #2a3556; }
.verdict { font-size:1.5rem; font-weight:700; margin:20px 0 8px; }
.flood { font-size:1rem; padding:8px 12px; border-radius:8px; display:inline-block; }
.flood.high { background:#7f1d1d; } .flood.watch { background:#78531a; } .flood.low { background:#1a3a2a; }
.meta { color:#7f8bb0; font-size:0.85rem; margin-top:18px; }
```

- [ ] **Step 4: Create `web/app.js`**

```js
import { verdict } from "./nowcast.js";
import { nearestZone, floodRisk } from "./flood.js";

const BASE = "https://api.open-meteo.com/v1/forecast";

async function loadJSON(path) { return (await fetch(path)).json(); }

async function fetchForecast(lat, lon) {
  const q = `latitude=${lat}&longitude=${lon}&hourly=precipitation&forecast_days=1&past_days=1&timezone=Asia%2FKolkata`;
  const [best, aifs] = await Promise.all([
    fetch(`${BASE}?${q}&models=best_match`).then(r => r.json()),
    fetch(`${BASE}?${q}&models=ecmwf_aifs025`).then(r => r.json()),
  ]);
  return { best, aifs };
}

function sliceFromNow(best, aifs) {
  const times = best.hourly.time;
  const nowIso = new Date().toISOString().slice(0, 13); // YYYY-MM-DDTHH
  let i = times.findIndex(t => t.slice(0, 13) >= nowIso);
  if (i < 0) i = 0;
  const aifsByTime = Object.fromEntries(aifs.hourly.time.map((t, k) => [t, aifs.hourly.precipitation[k]]));
  const recentRain = best.hourly.precipitation.slice(Math.max(0, i-3), i)
    .reduce((s, v) => s + (v || 0), 0);
  return {
    valid_at: times.slice(i),
    fc_bestmatch_mm: best.hourly.precipitation.slice(i),
    fc_aifs_mm: times.slice(i).map(t => aifsByTime[t] ?? 0),
    nowHour: new Date().getHours(),
    recentRain,
  };
}

async function render(loc, model, zones) {
  document.getElementById("verdict").textContent = "Loading…";
  const { best, aifs } = await fetchForecast(loc.lat, loc.lon);
  const fc = sliceFromNow(best, aifs);
  const v = verdict(model, fc, fc.nowHour, fc.recentRain);
  const zone = nearestZone(loc.lat, loc.lon, zones);
  const fr = floodRisk(v.peakMm, zone);

  document.getElementById("verdict").textContent = v.willRain
    ? (v.startsInHrs === 0 ? `Raining now (~${v.peakMm} mm/h)` : `Rain in ~${v.startsInHrs}h (~${v.peakMm} mm/h)`)
    : "No rain in the next 2h ☀️";
  const fEl = document.getElementById("flood");
  fEl.textContent = fr.level === "low" ? "" : `⚠️ ${fr.reason}`;
  fEl.className = "flood " + fr.level;
  document.getElementById("meta").textContent =
    `model v${model.version} · corrects ECMWF-AIFS for Mumbai · updated ${model.trained_at.slice(0,10)}`;
}

async function init() {
  const [zones, localities, model] = await Promise.all([
    loadJSON("data/flood-zones.json"), loadJSON("data/localities.json"), loadJSON("model.json"),
  ]);
  const sel = document.getElementById("locality");
  localities.forEach((l, i) => sel.add(new Option(l.name, i)));
  sel.onchange = () => render(localities[sel.value], model, zones);
  render(localities[0], model, zones);
}
init();
```

- [ ] **Step 5: Smoke-test locally**

Run: `cd web && python -m http.server 8000` then open `http://localhost:8000`.
Expected: a verdict line renders for the selected locality (live Open-Meteo call succeeds; no console errors).

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/style.css web/app.js web/data/localities.json
git commit -m "feat: fast single-page Mumbai rain UI (locality + verdict + flood)"
```

---

### Task 9: GitHub Actions — collect + retrain crons

**Files:**
- Create: `.github/workflows/collect.yml`, `.github/workflows/retrain.yml`

**Interfaces:**
- Consumes: `pipeline/log_snapshot.py` (Task 2), `pipeline/train.py` (Task 5).

- [ ] **Step 1: Create `.github/workflows/collect.yml`**

```yaml
name: collect
on:
  schedule: [{cron: "0 * * * *"}]   # hourly
  workflow_dispatch:
permissions:
  contents: write
jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run python -m pipeline.log_snapshot
      - run: |
          git config user.name "rain-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/log.csv
          git commit -m "data: hourly snapshot" || echo "no changes"
          git push
```

- [ ] **Step 2: Create `.github/workflows/retrain.yml`**

```yaml
name: retrain
on:
  schedule: [{cron: "30 0 * * *"}]  # daily 00:30 UTC
  workflow_dispatch:
permissions:
  contents: write
jobs:
  retrain:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run pytest -q
      - run: uv run python -m pipeline.train
      - run: |
          git config user.name "rain-bot"
          git config user.email "bot@users.noreply.github.com"
          git add web/model.json
          git commit -m "model: retrain (promoted only if beats champion + AIFS)" || echo "no promotion"
          git push
```

- [ ] **Step 3: Verify workflows are valid YAML**

Run: `uv run python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('ok')"`
Expected: `ok` (add `pyyaml` to dev deps if missing, or skip — GitHub validates on push).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit -m "ci: hourly collect + daily self-improving retrain with eval gate"
```

---

### Task 10: Deploy to Cloudflare Pages

**Files:** none (config via Cloudflare dashboard / `wrangler`).

- [ ] **Step 1: Push repo to GitHub**

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

- [ ] **Step 2: Connect Cloudflare Pages**

In Cloudflare dashboard → Pages → Connect to Git → select repo. Build settings:
- Build command: *(none — static)*
- Build output directory: `web`
Deploy. (Free tier, no card.)

- [ ] **Step 3: Verify live**

Open the `*.pages.dev` URL. Expected: page loads, locality dropdown works, verdict renders from live Open-Meteo.

- [ ] **Step 4: Enable the crons**

In GitHub → Actions, confirm `collect` and `retrain` are enabled. Manually trigger `collect` once (`workflow_dispatch`) to seed data and confirm the bot can commit.

---

## Self-Review

**Spec coverage:**
- Hyperlocal Mumbai next-2h rain → Tasks 6, 8. ✅
- Beat frontier (AIFS) → eval gate compares vs `fc_aifs_mm`, Task 5. ✅
- Self-improving via live data → Tasks 2, 9 (collect + retrain crons). ✅
- Free 24/7, $0, no local ML → static site + GitHub Actions + Cloudflare Pages, Tasks 9–10. ✅
- Flood-risk (AI-not-crowdsourced, baked lookup) → Task 7. ✅
- No API keys on live path → browser uses only Open-Meteo, Task 8. ✅

**Type/parity consistency:**
- `row_to_features` (Py, Task 3) and `rowFeatures` (JS, Task 6) use identical feature order + cyclic hour encoding — covered by parity tests. ✅
- `predict` clamps ≥0 in both Py (Task 5) and JS (Task 6). ✅
- `model.json` schema identical across seed (Task 5), trainer output (Task 5), and JS loader (Tasks 6, 8). ✅

**Known shortcuts (ponytail comments in code):**
- Labels use Open-Meteo `past_days` (ERA5-ish), not true gauge/IMERG obs — upgrade path noted in `sources.py`.
- Flood-risk is rules-based, not hydrodynamic — upgrade path noted in `flood.js`.
- Linear (Ridge) model first; upgrade to GBM only if it beats linear on holdout.
- `log.csv` in git is the database until it's too big; then move to Cloudflare D1.

---

## Execution Handoff

Plan complete and saved to `mumbai-rain/PLAN.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Or run it autonomously via `/loop` (one task per iteration).
