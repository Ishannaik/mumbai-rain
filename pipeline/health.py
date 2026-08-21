"""Diary + model health report.

Run anytime (local or CI). Prints a human summary and writes public/metrics.json
so the scoreboard / API / SEO crawlers can show freshness + skill without
re-deriving train math.

  uv run python -m pipeline.health
  uv run python -m pipeline.health --fail-stale 12   # exit 1 if last issue >12h
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.train import (
    FEATURE_NAMES,
    LOG_PATH,
    MIN_ROWS,
    MODEL_PATH,
    RAIN_MM,
    brier,
    build_xy,
    matured,
    predict_proba,
    row_to_features,
)

METRICS_PATH = "public/metrics.json"
STALE_WARN_H = 6.0
STALE_FAIL_H = 24.0


def _parse_issued(s: str) -> datetime:
    # issued_at is "YYYY-MM-DDTHH:00" UTC from log_snapshot
    return datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)


def _load_rows(path: str | None = None) -> list[dict]:
    with open(path or LOG_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_model(path: str | None = None) -> dict | None:
    try:
        with open(path or MODEL_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _bss(score: float | None, ref: float | None) -> float | None:
    if score is None or ref is None or ref <= 0:
        return None
    return round(1.0 - (score / ref), 4)


def _contingency(rows: list[dict], call_rain) -> dict:
    tp = fp = fn = tn = 0
    for r in rows:
        called = bool(call_rain(r))
        did = int(float(r["observed_raining"])) == 1
        if called and did:
            tp += 1
        elif called and not did:
            fp += 1
        elif not called and did:
            fn += 1
        else:
            tn += 1
    rain_obs = tp + fn
    rain_calls = tp + fp
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "pod": round(tp / rain_obs, 4) if rain_obs else None,
        "far": round(fp / rain_calls, 4) if rain_calls else None,
        "csi": round(tp / (tp + fp + fn), 4) if (tp + fp + fn) else None,
        "bias": round(rain_calls / rain_obs, 4) if rain_obs else None,
        "accuracy": round((tp + tn) / len(rows), 4) if rows else None,
    }


def _holdout_metrics(rows: list[dict], model: dict | None) -> dict:
    """Mirror train.py: time-ordered 80/20 holdout, Brier vs raw/clim, model POD@0.5."""
    lab = matured(rows)
    lab.sort(key=lambda r: r["valid_at"])
    out = {
        "n_labelled": len(lab),
        "min_rows": MIN_ROWS,
        "ready": len(lab) >= MIN_ROWS,
        "holdout": None,
    }
    if len(lab) < MIN_ROWS:
        return out

    split = int(len(lab) * 0.8)
    train_rows, test_rows = lab[:split], lab[split:]
    Xte, yte = build_xy(test_rows)
    if len(set(yte)) < 2:
        out["holdout"] = {"error": "holdout lacks both rain and dry classes"}
        return out

    base_rate = sum(int(float(r["observed_raining"])) for r in train_rows) / len(train_rows)
    raw_probs = [1.0 if x[0] >= RAIN_MM else 0.0 for x in Xte]
    clim_probs = [base_rate] * len(yte)
    raw_b = brier(raw_probs, yte)
    clim_b = brier(clim_probs, yte)

    model_b = None
    model_type = None
    model_probs = None
    if model and model.get("type") == "logistic" and model.get("weights"):
        model_type = "logistic"
        # Use live weights (same arithmetic as browser). Score with the model's
        # OWN declared features so an old 5-feature champion still evaluates
        # (row_to_features maps by feature name, not position).
        m_feats = model.get("features") or FEATURE_NAMES
        m = {
            "type": "logistic",
            "weights": model["weights"],
            "intercept": model["intercept"],
            "features": m_feats,
        }
        model_Xte = [row_to_features(r, m_feats) for r in test_rows]
        model_probs = [predict_proba(m, x) for x in model_Xte]
        model_b = brier(model_probs, yte)
    elif model:
        model_type = model.get("type", "unknown")

    def raw_call(r):
        try:
            return float(r["fc_bestmatch_mm"]) >= RAIN_MM
        except (TypeError, ValueError):
            return False

    raw_ct = _contingency(test_rows, raw_call)
    model_ct = None
    if model_probs is not None:
        # Pair each test row with its probability for p>=0.5 contingency
        def model_call_factory(probs):
            idx = {"i": 0}

            def call(_r):
                p = probs[idx["i"]]
                idx["i"] += 1
                return p >= 0.5
            return call

        model_ct = _contingency(test_rows, model_call_factory(model_probs))

    out["holdout"] = {
        "n_train": len(train_rows),
        "n_test": len(test_rows),
        "base_rate_train": round(base_rate, 4),
        "rain_mm_threshold": RAIN_MM,
        "brier": {
            "model": round(model_b, 4) if model_b is not None else None,
            "raw": round(raw_b, 4),
            "clim": round(clim_b, 4),
            "stored_model": model.get("brier") if model else None,
        },
        "bss": {
            "model_vs_raw": _bss(model_b, raw_b) if model_b is not None else None,
            "model_vs_clim": _bss(model_b, clim_b) if model_b is not None else None,
        },
        "raw_contingency": raw_ct,
        "model_contingency_p05": model_ct,
        "model_type": model_type,
        "beats_raw": (model_b is not None and model_b <= raw_b),
        "beats_clim": (model_b is not None and model_b <= clim_b),
        "status": (
            "ok" if model_b is not None and model_b <= raw_b and model_b <= clim_b
            else "degraded" if model_b is not None
            else "no_logistic"
        ),
    }
    return out


def build_report(rows: list[dict] | None = None, model: dict | None = None) -> dict:
    rows = rows if rows is not None else _load_rows()
    model = model if model is not None else _load_model()
    lab = matured(rows)
    rain = sum(1 for r in lab if int(float(r["observed_raining"])) == 1)
    issued = sorted({r["issued_at"] for r in rows if r.get("issued_at")})
    last_issued = issued[-1] if issued else None
    hours_stale = None
    if last_issued:
        hours_stale = round(
            (datetime.now(timezone.utc) - _parse_issued(last_issued)).total_seconds() / 3600,
            2,
        )

    # Gap count between consecutive issues
    gaps = 0
    max_gap_h = 0.0
    for a, b in zip(issued, issued[1:]):
        h = (_parse_issued(b) - _parse_issued(a)).total_seconds() / 3600
        if h > 1.5:
            gaps += 1
            max_gap_h = max(max_gap_h, h)

    holdout = _holdout_metrics(rows, model)

    # All-labelled raw contingency (scoreboard parity)
    def raw_all(r):
        try:
            return float(r["fc_bestmatch_mm"]) >= RAIN_MM
        except (TypeError, ValueError):
            return False

    all_raw = _contingency(lab, raw_all) if lab else None

    stale_level = "ok"
    if hours_stale is None:
        stale_level = "unknown"
    elif hours_stale > STALE_FAIL_H:
        stale_level = "critical"
    elif hours_stale > STALE_WARN_H:
        stale_level = "warn"

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": "https://rain.ishannaik.com",
        "paths": {"log": LOG_PATH, "model": MODEL_PATH},
        "collection": {
            "n_rows": len(rows),
            "n_labelled": len(lab),
            "n_pending": len(rows) - len(lab),
            "n_rain": rain,
            "base_rate": round(rain / len(lab), 4) if lab else None,
            "n_runs": len(issued),
            "first_issued": issued[0] if issued else None,
            "last_issued": last_issued,
            "hours_since_last_issue": hours_stale,
            "stale_level": stale_level,
            "gap_count_gt_1h": gaps,
            "max_gap_h": round(max_gap_h, 1),
            "unique_valid": len({r["valid_at"] for r in lab}),
        },
        "model": {
            "type": model.get("type") if model else None,
            "trained_at": model.get("trained_at") if model else None,
            "stored_brier": model.get("brier") if model else None,
            "stored_raw_brier": model.get("raw_brier") if model else None,
            "stored_clim_brier": model.get("clim_brier") if model else None,
            "n_train": model.get("n_train") if model else None,
            "n_test": model.get("n_test") if model else None,
            "features": model.get("features") if model else None,
        },
        "eval": holdout,
        "all_labelled_raw": all_raw,
        "thresholds": {
            "rain_mm": RAIN_MM,
            "logistic_prob": 0.5,
            "min_rows": MIN_ROWS,
            "stale_warn_h": STALE_WARN_H,
            "stale_fail_h": STALE_FAIL_H,
        },
        "go_live": {
            "enough_data": len(lab) >= MIN_ROWS,
            "model_logistic": bool(model and model.get("type") == "logistic"),
            "beats_raw_holdout": (holdout.get("holdout") or {}).get("beats_raw"),
            "beats_clim_holdout": (holdout.get("holdout") or {}).get("beats_clim"),
            "collect_fresh": stale_level in ("ok", "warn"),
        },
    }


def print_summary(report: dict) -> None:
    c = report["collection"]
    e = report.get("eval", {}).get("holdout") or {}
    m = report["model"]
    print("=== mumbai-rain health ===")
    print(f"generated   {report['generated_at']}")
    print(f"rows        {c['n_rows']}  labelled={c['n_labelled']}  pending={c['n_pending']}")
    print(f"rain        {c['n_rain']}  base_rate={c['base_rate']}")
    print(f"collect     last={c['last_issued']}  stale_h={c['hours_since_last_issue']}  "
          f"level={c['stale_level']}  gaps>{1}h={c['gap_count_gt_1h']} max={c['max_gap_h']}h")
    print(f"model       type={m.get('type')}  trained_at={m.get('trained_at')}  "
          f"stored_brier={m.get('stored_brier')}")
    if e and "brier" in e:
        b = e["brier"]
        print(f"holdout     n_test={e.get('n_test')}  model={b.get('model')}  "
              f"raw={b.get('raw')}  clim={b.get('clim')}  status={e.get('status')}")
        print(f"bss         vs_raw={e.get('bss', {}).get('model_vs_raw')}  "
              f"vs_clim={e.get('bss', {}).get('model_vs_clim')}")
    g = report["go_live"]
    print(f"go_live     data={g['enough_data']} logistic={g['model_logistic']} "
          f"beats_raw={g['beats_raw_holdout']} beats_clim={g['beats_clim_holdout']} "
          f"fresh={g['collect_fresh']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mumbai rain diary + model health")
    p.add_argument("--out", default=METRICS_PATH, help="Write JSON report here")
    p.add_argument("--fail-stale", type=float, default=None,
                   help="Exit 1 if hours since last issue exceeds this")
    p.add_argument("--quiet", action="store_true", help="JSON only to stdout, no summary")
    args = p.parse_args(argv)

    report = build_report()
    if not args.quiet:
        print_summary(report)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"wrote       {out}")

    stale_h = report["collection"]["hours_since_last_issue"]
    if args.fail_stale is not None and (stale_h is None or stale_h > args.fail_stale):
        print(f"FAIL stale: hours_since_last_issue={stale_h} > {args.fail_stale}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
