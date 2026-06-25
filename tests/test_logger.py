from pipeline.labels import metar_is_raining, parse_metar, _utc_report_to_ist_hour
from pipeline.log_snapshot import append_snapshot, backfill_observed, LOG_HEADER


def test_metar_is_raining_detects_precip_only():
    assert metar_is_raining("RA") is True
    assert metar_is_raining("-RA") is True
    assert metar_is_raining("TSRA") is True
    assert metar_is_raining("DZ") is True
    assert metar_is_raining("BR") is False    # mist
    assert metar_is_raining("HZ") is False    # haze
    assert metar_is_raining("") is False
    assert metar_is_raining(None) is False


def test_utc_report_to_ist_hour():
    # 15:00 UTC + 5:30 = 20:30 IST -> floor 20:00 ; 14:30 UTC -> 20:00 IST
    assert _utc_report_to_ist_hour("2026-06-25T15:00:00.000Z") == "2026-06-25T20:00"
    assert _utc_report_to_ist_hour("2026-06-25T14:30:00.000Z") == "2026-06-25T20:00"


def test_parse_metar_or_combines_within_hour():
    data = [{"reportTime": "2026-06-25T15:00:00.000Z", "wxString": "BR"},
            {"reportTime": "2026-06-25T14:30:00.000Z", "wxString": "RA"}]
    out = parse_metar(data)
    assert out["2026-06-25T20:00"] is True   # one dry + one rain in same IST hour -> rain


def test_append_snapshot_blank_label_and_none_ecmwf():
    fc = {"valid_at": ["2026-06-25T20:00"], "fc_bestmatch_mm": [1.0], "fc_ecmwf_mm": [None]}
    rows = append_snapshot([], fc, 19.12, 72.85, "2026-06-25T14:00", recent_rain_mm=0.5)
    r = rows[0]
    assert r["observed_raining"] == ""
    assert r["fc_ecmwf_mm"] == ""      # None benchmark -> blank, never 0
    assert r["hour"] == 20
    assert set(r.keys()) == set(LOG_HEADER)


def test_backfill_sets_binary_label():
    rows = [{"valid_at": "2026-06-25T20:00", "observed_raining": ""}]
    backfill_observed(rows, {"2026-06-25T20:00": True})
    assert rows[0]["observed_raining"] == 1

    dry = [{"valid_at": "2026-06-25T21:00", "observed_raining": ""}]
    backfill_observed(dry, {"2026-06-25T21:00": False})
    assert dry[0]["observed_raining"] == 0


def test_backfill_skips_already_labelled():
    rows = [{"valid_at": "2026-06-25T20:00", "observed_raining": 0}]
    backfill_observed(rows, {"2026-06-25T20:00": True})
    assert rows[0]["observed_raining"] == 0   # not overwritten
