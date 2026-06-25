"""The only module that talks to Open-Meteo.

Open-Meteo is a free, keyless delivery pipe for global weather models (GFS, ICON,
ECMWF incl. the AIFS AI model) — NOT a source of ground truth. Every value here is
model output. Truth/labels come from NASA GPM IMERG on the CI path (see pipeline/labels).
"""
import requests

BASE = "https://api.open-meteo.com/v1/forecast"


def build_forecast_url(lat: float, lon: float) -> str:
    """best_match: Open-Meteo's tuned blend. Our app's primary forecast feed."""
    return (f"{BASE}?latitude={lat}&longitude={lon}"
            f"&hourly=precipitation&models=best_match&forecast_days=1"
            f"&timezone=Asia%2FKolkata")


def _ecmwf_url(lat: float, lon: float) -> str:
    """ECMWF-IFS: ECMWF's flagship operational physics model — our 'frontier' benchmark.
    (We tried the AIFS AI model first, but Open-Meteo serves null precipitation for it.)"""
    return (f"{BASE}?latitude={lat}&longitude={lon}"
            f"&hourly=precipitation&models=ecmwf_ifs025&forecast_days=1"
            f"&timezone=Asia%2FKolkata")


def parse_forecast(raw_best: dict, raw_ecmwf: dict) -> dict:
    """Align two model responses by valid time. best_match drives the time axis.
    A missing/null ECMWF hour becomes None (NOT 0.0) — a missing benchmark must never
    be silently scored as 'predicted no rain'; downstream training drops None rows."""
    times = raw_best["hourly"]["time"]
    ecmwf_by_time = dict(zip(raw_ecmwf["hourly"]["time"],
                             raw_ecmwf["hourly"]["precipitation"]))
    return {
        "valid_at": times,
        "fc_bestmatch_mm": raw_best["hourly"]["precipitation"],
        "fc_ecmwf_mm": [ecmwf_by_time.get(t) for t in times],
    }


def fetch_forecast(lat: float, lon: float) -> dict:
    raw_best = requests.get(build_forecast_url(lat, lon), timeout=20).json()
    raw_ecmwf = requests.get(_ecmwf_url(lat, lon), timeout=20).json()
    return parse_forecast(raw_best, raw_ecmwf)


def fetch_recent_rain_mm(lat: float, lon: float) -> float:
    """Sum of the last 3 hours of Open-Meteo precipitation — a FEATURE, not a label.
    (Circularity only matters for the label, which comes from METAR. The forecast's own
    recent value is a fine input — it's the strongest 0-2h predictor.)"""
    url = (f"{BASE}?latitude={lat}&longitude={lon}&hourly=precipitation"
           f"&past_days=1&forecast_days=0&timezone=Asia%2FKolkata")
    vals = requests.get(url, timeout=20).json()["hourly"]["precipitation"]
    recent = [v for v in vals[-3:] if isinstance(v, (int, float))]
    return round(sum(recent), 2)
