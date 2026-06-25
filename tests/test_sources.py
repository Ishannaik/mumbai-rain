from pipeline.sources import build_forecast_url, _ecmwf_url, parse_forecast


def test_url_builders_target_the_two_models():
    # best_match drives the app feed; ECMWF-IFS is fetched separately as the benchmark.
    assert "best_match" in build_forecast_url(19.12, 72.85)
    assert "hourly=precipitation" in build_forecast_url(19.12, 72.85)
    assert "ecmwf_ifs025" in _ecmwf_url(19.12, 72.85)


def test_parse_forecast_aligns_models_by_time():
    raw_best = {"hourly": {"time": ["2026-06-23T00:00", "2026-06-23T01:00"],
                           "precipitation": [0.0, 2.5]}}
    raw_ecmwf = {"hourly": {"time": ["2026-06-23T00:00", "2026-06-23T01:00"],
                            "precipitation": [0.1, 3.0]}}
    out = parse_forecast(raw_best, raw_ecmwf)
    assert out["valid_at"] == ["2026-06-23T00:00", "2026-06-23T01:00"]
    assert out["fc_bestmatch_mm"] == [0.0, 2.5]
    assert out["fc_ecmwf_mm"] == [0.1, 3.0]


def test_parse_forecast_missing_ecmwf_time_is_none_not_zero():
    # A missing benchmark hour must be None, never 0.0 — scoring a missing
    # forecast as "predicted no rain" would silently fake the benchmark.
    raw_best = {"hourly": {"time": ["2026-06-23T00:00", "2026-06-23T01:00"],
                           "precipitation": [1.0, 2.0]}}
    raw_ecmwf = {"hourly": {"time": ["2026-06-23T00:00"], "precipitation": [1.1]}}
    out = parse_forecast(raw_best, raw_ecmwf)
    assert out["fc_ecmwf_mm"] == [1.1, None]
