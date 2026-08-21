"""The data collector. Run hourly (GitHub Actions cron). Each run:
  1. fetches the current forecast (best_match + ECMWF-IFS) for the Mumbai point,
  2. appends one snapshot row per future hour (label blank),
  3. backfills observed_raining from METAR for rows whose hour is now in the past.

Git is the database: rows accumulate in data/log.csv. After ~weeks of monsoon this is
the training set for the calibration model (Task 5).
"""
import csv
from datetime import datetime, timezone

from pipeline.sources import fetch_forecast, fetch_recent_rain_mm
from pipeline.labels import fetch_metar

LOG_HEADER = ["issued_at", "valid_at", "lat", "lon",
              "fc_bestmatch_mm", "fc_ecmwf_mm", "fc_rh_bestmatch",
              "hour", "recent_rain_mm", "observed_raining"]
LOG_PATH = "data/log.csv"
MUMBAI = (19.12, 72.85)
STATION = "VABB"  # Mumbai airport METAR


def append_snapshot(rows, forecast, lat, lon, issued_at, recent_rain_mm):
    """Pure: add one row per forecast hour, observed_raining blank (filled later)."""
    new = []
    for i, vt in enumerate(forecast["valid_at"]):
        ec = forecast["fc_ecmwf_mm"][i]
        rh = forecast["fc_rh_bestmatch"][i]
        new.append({
            "issued_at": issued_at, "valid_at": vt, "lat": lat, "lon": lon,
            "fc_bestmatch_mm": forecast["fc_bestmatch_mm"][i],
            "fc_ecmwf_mm": "" if ec is None else ec,   # missing benchmark stays blank, never 0
            "fc_rh_bestmatch": "" if rh is None else rh,
            "hour": int(vt[11:13]),
            "recent_rain_mm": recent_rain_mm,
            "observed_raining": "",
        })
    return rows + new


def backfill_observed(rows, metar_by_hour):
    """Pure: fill observed_raining (1/0) for blank rows whose valid_at now has a METAR obs."""
    for r in rows:
        if r.get("observed_raining", "") == "" and r["valid_at"] in metar_by_hour:
            r["observed_raining"] = 1 if metar_by_hour[r["valid_at"]] else 0
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
        w.writeheader()
        w.writerows(rows)


def main(lat=MUMBAI[0], lon=MUMBAI[1], station=STATION):
    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    rows = _read(LOG_PATH)

    # append this hour's snapshot first (skip if we already logged this issued_at)
    if not any(r["issued_at"] == issued_at for r in rows):
        recent = fetch_recent_rain_mm(lat, lon)
        rows = append_snapshot(rows, fetch_forecast(lat, lon), lat, lon, issued_at, recent)

    # then backfill labels — so already-observable hours in this snapshot get labelled now
    rows = backfill_observed(rows, fetch_metar(station, hours=24))

    _write(LOG_PATH, rows)
    labelled = sum(1 for r in rows if r.get("observed_raining", "") != "")
    print(f"snapshot {issued_at}: {len(rows)} rows total, {labelled} labelled")


if __name__ == "__main__":
    main()
