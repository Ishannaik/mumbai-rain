from pipeline.backfill_recent_rain import backfilled_rows


def test_backfilled_rows_recomputes_per_snapshot_and_is_pure():
    # IST hourly series with known precipitation.
    times = ["2026-07-02T20:00", "2026-07-02T21:00", "2026-07-02T22:00", "2026-07-02T23:00"]
    precip = [1.0, 2.0, 3.0, 9.9]
    # issued_at 18:00 UTC == 23:30 IST → now-hour 23:00 → sum of 20,21,22 = 6.0.
    rows = [
        {"issued_at": "2026-07-02T18:00", "valid_at": "2026-07-02T23:00", "recent_rain_mm": "999"},
        {"issued_at": "2026-07-02T18:00", "valid_at": "2026-07-03T02:00", "recent_rain_mm": "999"},
    ]
    out = backfilled_rows(rows, times, precip)
    assert out[0]["recent_rain_mm"] == 6.0
    assert out[1]["recent_rain_mm"] == 6.0          # same snapshot → same value
    assert out[0]["valid_at"] == "2026-07-02T23:00"  # other columns preserved
    assert rows[0]["recent_rain_mm"] == "999"        # input not mutated
