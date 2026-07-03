"""One-shot: recompute the recent_rain_mm column in data/log.csv with the CORRECTED
rolling-3h-before-now semantics (pipeline.sources.recent_rain_from_series). The old
collector wrote yesterday-21:00..23:00 for every snapshot; this rewrites the historical
column so the training set matches what the fixed collector now stores.

Data source is the SAME Open-Meteo forecast pipe (past_days) the client and collector
use — NOT ERA5 — so history stays consistent with serving. Run ONCE, from a branch
started at origin/main, then commit the rewritten log. Idempotent: re-running converges.
"""
from datetime import date

from pipeline.log_snapshot import _read, _write, LOG_PATH, MUMBAI
from pipeline.labels import _utc_report_to_ist_hour
from pipeline.sources import BASE, _get, recent_rain_from_series


def _span_past_days(rows) -> int:
    """How many past days to fetch to cover the oldest snapshot (+2 days margin, clamp 92)."""
    earliest_ist = min(_utc_report_to_ist_hour(r["issued_at"] + ":00") for r in rows)[:10]
    y, m, d = (int(x) for x in earliest_ist.split("-"))
    return max(1, min(92, (date.today() - date(y, m, d)).days + 2))


def _fetch_series(lat, lon, past_days):
    """One Open-Meteo call spanning the whole log; returns (times, precip) in IST."""
    url = (f"{BASE}?latitude={lat}&longitude={lon}&hourly=precipitation"
           f"&past_days={past_days}&forecast_days=1&timezone=Asia%2FKolkata")
    h = _get(url).json()["hourly"]
    return h["time"], h["precipitation"]


def backfilled_rows(rows, times, precip):
    """Pure: return NEW rows with recent_rain_mm recomputed per snapshot. Each row's
    issued_at (UTC) is converted to its IST hour, then the rolling-3h sum is read off
    the (times, precip) series. Cached per issued_at so a snapshot is computed once."""
    cache = {}
    out = []
    for r in rows:
        iss = r["issued_at"]
        if iss not in cache:
            now_stamp = _utc_report_to_ist_hour(iss + ":00")  # UTC stamp -> IST hour key
            cache[iss] = recent_rain_from_series(times, precip, now_stamp)
        r2 = dict(r)
        r2["recent_rain_mm"] = cache[iss]
        out.append(r2)
    return out


def main():
    rows = _read(LOG_PATH)
    if not rows:
        print("log.csv empty — nothing to backfill.")
        return
    times, precip = _fetch_series(MUMBAI[0], MUMBAI[1], _span_past_days(rows))
    new_rows = backfilled_rows(rows, times, precip)
    _write(LOG_PATH, new_rows)
    changed = sum(1 for a, b in zip(rows, new_rows)
                  if str(a["recent_rain_mm"]) != str(b["recent_rain_mm"]))
    print(f"backfilled recent_rain_mm: {changed}/{len(rows)} rows changed.")


if __name__ == "__main__":
    main()
