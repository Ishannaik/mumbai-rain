"""Ground-truth rain labels from METAR (NOAA Aviation Weather) — independent of any
forecast model, free, no auth. Airport observers/sensors report present weather every
~30 min. We turn that into a binary 'did it rain this hour' label.

This is the LABEL source on purpose: it's a real observation, not model output, so
training a corrector against it is non-circular. Default station VABB = Mumbai
(Chhatrapati Shivaji Intl).
"""
import requests
from datetime import datetime, timedelta, timezone

METAR_URL = "https://aviationweather.gov/api/data/metar?ids={ids}&format=json&hours={hours}"

# METAR present-weather precipitation descriptors. RA covers -RA/+RA/SHRA/TSRA; DZ = drizzle.
# Mist (BR), haze (HZ), fog (FG) are NOT rain.
RAIN_TOKENS = ("RA", "DZ")

IST = timezone(timedelta(hours=5, minutes=30))


def metar_is_raining(wx) -> bool:
    if not wx:
        return False
    return any(tok in wx for tok in RAIN_TOKENS)


def _utc_report_to_ist_hour(report_time: str) -> str:
    """"2026-06-25T15:00:00.000Z" -> "2026-06-25T20:00" — convert METAR UTC to the
    IST hour key so it matches Open-Meteo's Asia/Kolkata hourly grid.
    ponytail: floors to the hour; a :30 obs lands on the hour it falls in. Sub-hour
    alignment can be refined at training time if it ever matters."""
    dt = datetime.strptime(report_time[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:00")


def parse_metar(data: list) -> dict:
    """Pure: list of NOAA METAR dicts -> {ist_hour: raining_bool}. If several obs fall in
    the same hour, OR them (any rain in the hour counts as rain)."""
    out = {}
    for o in data:
        rt = o.get("reportTime")
        if not rt:
            continue
        key = _utc_report_to_ist_hour(rt)
        out[key] = out.get(key, False) or metar_is_raining(o.get("wxString", ""))
    return out


def fetch_metar(station: str = "VABB", hours: int = 3) -> dict:
    data = requests.get(METAR_URL.format(ids=station, hours=hours), timeout=20).json()
    return parse_metar(data)
