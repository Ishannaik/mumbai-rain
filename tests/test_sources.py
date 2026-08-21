from pipeline.sources import build_forecast_url, _ecmwf_url, parse_forecast


def test_url_builders_target_the_two_models():
    # best_match drives the app feed (now incl. RH); ECMWF-IFS is the benchmark.
    assert "best_match" in build_forecast_url(19.12, 72.85)
    assert "hourly=precipitation" in build_forecast_url(19.12, 72.85)
    assert "relative_humidity_2m" in build_forecast_url(19.12, 72.85)
    assert "ecmwf_ifs025" in _ecmwf_url(19.12, 72.85)


def test_parse_forecast_aligns_models_by_time():
    raw_best = {"hourly": {"time": ["2026-06-23T00:00", "2026-06-23T01:00"],
                           "precipitation": [0.0, 2.5],
                           "relative_humidity_2m": [81, 88]}}
    raw_ecmwf = {"hourly": {"time": ["2026-06-23T00:00", "2026-06-23T01:00"],
                            "precipitation": [0.1, 3.0]}}
    out = parse_forecast(raw_best, raw_ecmwf)
    assert out["valid_at"] == ["2026-06-23T00:00", "2026-06-23T01:00"]
    assert out["fc_bestmatch_mm"] == [0.0, 2.5]
    assert out["fc_ecmwf_mm"] == [0.1, 3.0]
    assert out["fc_rh_bestmatch"] == [81, 88]


def test_parse_forecast_missing_ecmwf_time_is_none_not_zero():
    # A missing benchmark hour must be None, never 0.0 — scoring a missing
    # forecast as "predicted no rain" would silently fake the benchmark.
    raw_best = {"hourly": {"time": ["2026-06-23T00:00", "2026-06-23T01:00"],
                           "precipitation": [1.0, 2.0]}}
    raw_ecmwf = {"hourly": {"time": ["2026-06-23T00:00"], "precipitation": [1.1]}}
    out = parse_forecast(raw_best, raw_ecmwf)
    assert out["fc_ecmwf_mm"] == [1.1, None]
    assert out["fc_rh_bestmatch"] == [None, None]  # no RH key in payload -> neutral None


def test_get_session_has_retry_and_backoff():
    # A transient 5xx/timeout must not drop a whole hourly snapshot: the shared
    # session retries with backoff. (No network — inspect the mounted adapter.)
    from pipeline.sources import _session, TIMEOUT
    retries = _session.get_adapter("https://api.open-meteo.com/v1/forecast").max_retries
    assert retries.total == 3
    assert retries.backoff_factor >= 1.0
    assert 429 in retries.status_forcelist and 503 in retries.status_forcelist
    assert TIMEOUT >= 30


def test_recent_rain_sums_three_hours_before_now():
    from pipeline.sources import recent_rain_from_series
    times = ["2026-07-02T20:00", "2026-07-02T21:00", "2026-07-02T22:00",
             "2026-07-02T23:00", "2026-07-03T00:00"]
    precip = [1.0, 2.0, 3.0, 4.0, 9.9]
    # now = 23:00 → the 3 hours before it (20,21,22) = 6.0; the current hour is excluded.
    assert recent_rain_from_series(times, precip, "2026-07-02T23:00") == 6.0


def test_recent_rain_excludes_current_hour_mirrors_client():
    from pipeline.sources import recent_rain_from_series
    times = ["2026-07-02T21:00", "2026-07-02T22:00", "2026-07-02T23:00"]
    precip = [5.0, 5.0, 5.0]
    # now = 23:00 → i=2, window [max(0,-1):2] = hours 21,22 → 10.0 (mirrors precip.slice(i-3,i)).
    assert recent_rain_from_series(times, precip, "2026-07-02T23:00") == 10.0


def test_recent_rain_treats_none_as_zero():
    from pipeline.sources import recent_rain_from_series
    times = ["2026-07-02T20:00", "2026-07-02T21:00", "2026-07-02T22:00", "2026-07-02T23:00"]
    precip = [None, 2.0, None, 0.0]
    # now = 23:00 → window [20,21,22] = [None,2.0,None] → 2.0 (None counts as 0, like `v || 0`).
    assert recent_rain_from_series(times, precip, "2026-07-02T23:00") == 2.0


def test_recent_rain_near_series_start_clamps():
    from pipeline.sources import recent_rain_from_series
    times = ["2026-07-02T00:00", "2026-07-02T01:00"]
    precip = [3.0, 4.0]
    # now = 01:00 → i=1, window [max(0,-2):1] = [3.0] → 3.0 (fewer than 3 hours available).
    assert recent_rain_from_series(times, precip, "2026-07-02T01:00") == 3.0
