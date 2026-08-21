"""One-shot: fill the fc_rh_bestmatch column in data/log.csv for rows collected
before RH was a feature (the first ~47 days). Same Open-Meteo pipe the collector
uses (past_days), NOT ERA5, so history stays consistent with serving.

Run once from a branch, then commit. Idempotent: re-running converges (already-
filled rows keep their value). After this, train.py sees RH for every row.
"""
from datetime import date

from pipeline.log_snapshot import _read, _write, LOG_PATH, MUMBAI
from pipeline.labels import _utc_report_to_ist_hour
from pipeline.sources import BASE, _get


def _span_past_days(rows) -> int:
    """Past days needed to cover the oldest snapshot (+2 margin, clamp 92)."""
    earliest_ist = min(_utc_report_to_ist_hour(r["issued_at"] + ":00") for r in rows)[:10]
    y, m, d = (int(x) for x in earliest_ist.split("-"))
    return max(1, min(92, (date.today() - date(y, m, d)).days + 2))


def _fetch_rh_series(lat, lon, past_days):
    """One Open-Meteo call: best_match relative_humidity_2m over the whole log."""
    url = (f"{BASE}?latitude={lat}&longitude={lon}"
           f"&hourly=relative_humidity_2m&models=best_match"
           f"&past_days={past_days}&forecast_days=1&timezone=Asia%2FKolkata")
    h = _get(url).json()["hourly"]
    return dict(zip(h["time"], h["relative_humidity_2m"]))


def backfilled_rows(rows, rh_by_hour):
    """Pure: fill fc_rh_bestmatch for rows missing it (blank/absent). Keyed by
    valid_at (IST hour grid). Missing hours stay blank — train falls back to 50."""
    out = []
    for r in rows:
        r2 = dict(r)
        cur = str(r2.get("fc_rh_bestmatch", "")).strip()
        if cur == "" and r2["valid_at"] in rh_by_hour:
            r2["fc_rh_bestmatch"] = rh_by_hour[r2["valid_at"]]
        out.append(r2)
    return out


def main():
    rows = _read(LOG_PATH)
    if not rows:
        print("log.csv empty — nothing to backfill.")
        return
    rh_by = _fetch_rh_series(MUMBAI[0], MUMBAI[1], _span_past_days(rows))
    new_rows = backfilled_rows(rows, rh_by)
    _write(LOG_PATH, new_rows)
    filled = sum(1 for r in new_rows if str(r.get("fc_rh_bestmatch", "")).strip() != "")
    print(f"fc_rh_bestmatch filled: {filled}/{len(new_rows)} rows.")


if __name__ == "__main__":
    main()
