"""The only module that talks to Open-Meteo.

Open-Meteo is a free, keyless delivery pipe for global weather models (GFS, ICON,
ECMWF incl. the AIFS AI model) — NOT a source of ground truth. Every value here is
model output. Truth/labels come from METAR (NOAA Aviation Weather, station VABB) on
the CI path (see pipeline/labels).
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 30  # seconds; Open-Meteo can be slow under load (was 20 → ReadTimeout in CI)

# One shared session with retry/backoff so a transient 5xx or read-timeout doesn't drop
# a whole hourly snapshot. backoff_factor=1 → sleeps 0s, 2s, 4s between the 3 attempts.
_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=1.0,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
)))


def _get(url: str):
    """Single choke point for every Open-Meteo GET: shared session, retry/backoff, timeout."""
    return _session.get(url, timeout=TIMEOUT)


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
    raw_best = _get(build_forecast_url(lat, lon)).json()
    raw_ecmwf = _get(_ecmwf_url(lat, lon)).json()
    return parse_forecast(raw_best, raw_ecmwf)


def fetch_recent_rain_mm(lat: float, lon: float) -> float:
    """Sum of the last 3 hours of Open-Meteo precipitation — a FEATURE, not a label.
    (Circularity only matters for the label, which comes from METAR. The forecast's own
    recent value is a fine input — it's the strongest 0-2h predictor.)"""
    url = (f"{BASE}?latitude={lat}&longitude={lon}&hourly=precipitation"
           f"&past_days=1&forecast_days=0&timezone=Asia%2FKolkata")
    vals = _get(url).json()["hourly"]["precipitation"]
    recent = [v for v in vals[-3:] if isinstance(v, (int, float))]
    return round(sum(recent), 2)
