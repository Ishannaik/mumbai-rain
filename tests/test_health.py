"""Health report: pure checks on synthetic diary + model."""
import json
from pathlib import Path

from pipeline.health import build_report, main
from pipeline.train import RAIN_MM, passes_gate, should_demote


def _row(valid, issued, bm, rain, recent=0.0, hour=12):
    return {
        "issued_at": issued,
        "valid_at": valid,
        "lat": "19.12",
        "lon": "72.85",
        "fc_bestmatch_mm": str(bm),
        "fc_ecmwf_mm": str(bm),
        "hour": str(hour),
        "recent_rain_mm": str(recent),
        "observed_raining": str(rain),
    }


def test_rain_mm_matches_product_threshold():
    # Single source of truth for "raw rain call" with the UI / scoreboard.
    assert RAIN_MM == 0.3


def test_gate_requires_clim_when_provided():
    # Beats raw + champ but loses to clim → reject
    assert passes_gate(0.22, champ_brier=0.25, raw_brier=0.30, clim_brier=0.20) is False
    # Beats all three → promote
    assert passes_gate(0.15, champ_brier=0.25, raw_brier=0.30, clim_brier=0.20) is True
    # clim omitted → legacy behaviour (raw + champ only)
    assert passes_gate(0.22, champ_brier=0.25, raw_brier=0.30) is True


def test_demote_when_worse_than_clim():
    assert should_demote(0.25, raw_b=0.30, clim_b=0.20) is True
    assert should_demote(0.15, raw_b=0.30, clim_b=0.20) is False


def test_build_report_counts_and_holdout(tmp_path, monkeypatch):
    # 220 labelled rows with a noisy mm signal (raw not perfect → BSS defined)
    rows = []
    for i in range(220):
        rain = 1 if i % 2 == 0 else 0
        # Sometimes dry hours still get 0.5 mm (false alarm), wet hours sometimes 0.05 (miss)
        if rain:
            bm = 1.0 if i % 5 else 0.05
        else:
            bm = 0.0 if i % 5 else 0.5
        day = 1 + (i // 24)
        hour = i % 24
        valid = f"2026-07-{day:02d}T{hour:02d}:00"
        issued = f"2026-07-{day:02d}T00:00"
        rows.append(_row(valid, issued, bm, rain, recent=float(rain), hour=hour))

    model = {
        "type": "logistic",
        "features": ["fc_bestmatch_mm", "fc_ecmwf_mm", "hour_sin", "hour_cos", "recent_rain_mm"],
        "weights": [2.0, 0.0, 0.0, 0.0, 0.0],
        "intercept": -1.0,
        "brier": 0.1,
        "raw_brier": 0.2,
        "clim_brier": 0.25,
        "trained_at": "2026-07-01T00:00:00Z",
        "n_train": 176,
        "n_test": 44,
    }

    report = build_report(rows=rows, model=model)
    assert report["collection"]["n_labelled"] == 220
    assert report["collection"]["n_rain"] == 110
    assert report["eval"]["ready"] is True
    h = report["eval"]["holdout"]
    assert h["n_test"] > 0
    assert h["brier"]["model"] is not None
    assert h["brier"]["raw"] is not None
    assert h["brier"]["raw"] > 0
    assert h["bss"]["model_vs_raw"] is not None
    assert report["thresholds"]["rain_mm"] == 0.3


def test_main_writes_metrics(tmp_path, monkeypatch):
    # Point health at a tiny csv + model under tmp
    log = tmp_path / "log.csv"
    model_path = tmp_path / "model.json"
    out = tmp_path / "metrics.json"

    header = "issued_at,valid_at,lat,lon,fc_bestmatch_mm,fc_ecmwf_mm,hour,recent_rain_mm,observed_raining\n"
    # 5 labelled rows (not enough for holdout ready) — still writes report
    lines = [
        "2026-08-01T00:00,2026-08-01T01:00,19.12,72.85,0.0,0.0,1,0,0\n",
        "2026-08-01T00:00,2026-08-01T02:00,19.12,72.85,1.0,1.0,2,0,1\n",
    ]
    log.write_text(header + "".join(lines), encoding="utf-8")
    model_path.write_text(json.dumps({"type": "raw", "weights": [1, 0, 0, 0, 0], "intercept": 0}),
                          encoding="utf-8")

    monkeypatch.setattr("pipeline.health.LOG_PATH", str(log))
    monkeypatch.setattr("pipeline.health.MODEL_PATH", str(model_path))

    rc = main(["--out", str(out), "--quiet"])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["collection"]["n_rows"] == 2
    assert data["eval"]["ready"] is False
