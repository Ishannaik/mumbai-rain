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
    """best_match: Open-Meteo's tuned blend. Our app's primary forecast feed.
    relative_humidity_2m is a first-class rain feature for the monsoon (the
    ablation that won: adding RH to the model cut holdout Brier 0.0761->0.0657)."""
    return (f"{BASE}?latitude={lat}&longitude={lon}"
            f"&hourly=precipitation,relative_humidity_2m&models=best_match&forecast_days=1"
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
    be silently scored as 'predicted no rain'; downstream training drops None rows.
    RH (relative_humidity_2m) rides along as the accuracy-winning feature."""
    times = raw_best["hourly"]["time"]
    ecmwf_by_time = dict(zip(raw_ecmwf["hourly"]["time"],
                             raw_ecmwf["hourly"]["precipitation"]))
    rh = raw_best["hourly"].get("relative_humidity_2m")
    return {
        "valid_at": times,
        "fc_bestmatch_mm": raw_best["hourly"]["precipitation"],
        "fc_ecmwf_mm": [ecmwf_by_time.get(t) for t in times],
        "fc_rh_bestmatch": rh if rh is not None else [None] * len(times),
    }


def fetch_forecast(lat: float, lon: float) -> dict:
    raw_best = _get(build_forecast_url(lat, lon)).json()
    raw_ecmwf = _get(_ecmwf_url(lat, lon)).json()
    return parse_forecast(raw_best, raw_ecmwf)


def recent_rain_from_series(times, precip, now_stamp):
    """Pure. Sum precipitation over the 3 hours STRICTLY BEFORE `now_stamp`, mirroring
    the browser's shapeForecast() in src/layouts/Almanac.astro:
        i = first index whose hour >= now;  window = precip[i-3 : i];  None -> 0.
    `times` and `now_stamp` are IST 'YYYY-MM-DDTHH:MM' strings (Asia/Kolkata), compared
    on the 'YYYY-MM-DDTHH' hour prefix. Returns mm rounded to 2 dp (stored-column parity).
    This is a FEATURE, not a label — circularity only matters for the METAR label."""
    key = now_stamp[:13]
    i = next((k for k, t in enumerate(times) if t[:13] >= key), len(times) - 1)
    window = precip[max(0, i - 3):i]
    total = sum(v for v in window if isinstance(v, (int, float)))
    return round(total, 2)


def fetch_recent_rain_mm(lat: float, lon: float) -> float:
    """Rolling sum of the last 3 hours of precipitation, ending at (excluding) the current
    hour — the SAME window the browser computes in shapeForecast(), so the model is trained
    and served on the same feature. (Was: yesterday 21:00-23:00, constant across a day.)
    `current.time` is Open-Meteo's current IST instant, exactly what the client reads."""
    url = (f"{BASE}?latitude={lat}&longitude={lon}"
           f"&hourly=precipitation&current=precipitation"
           f"&past_days=1&forecast_days=1&timezone=Asia%2FKolkata")
    raw = _get(url).json()
    return recent_rain_from_series(
        raw["hourly"]["time"], raw["hourly"]["precipitation"], raw["current"]["time"])
