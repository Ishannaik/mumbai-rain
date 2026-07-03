import math
from pipeline.train import (row_to_features, brier, sigmoid, predict_proba,
                            passes_gate, train_classifier, build_xy, matured, FEATURE_NAMES,
                            should_demote, raw_passthrough_model)


def test_row_to_features_shape_and_cyclic_hour():
    f = row_to_features({"fc_bestmatch_mm": "2.0", "fc_ecmwf_mm": "1.5",
                         "hour": "6", "recent_rain_mm": "0.5"})
    assert len(f) == len(FEATURE_NAMES)
    assert f[0] == 2.0 and f[1] == 1.5
    assert math.isclose(f[2], math.sin(2 * math.pi * 6 / 24), abs_tol=1e-9)


def test_row_to_features_blank_ecmwf_falls_back_to_bestmatch():
    f = row_to_features({"fc_bestmatch_mm": "3.0", "fc_ecmwf_mm": "",
                         "hour": "0", "recent_rain_mm": "0"})
    assert f[1] == 3.0   # blank ECMWF -> best_match value, never 0


def test_matured_filters_unlabelled():
    rows = [{"observed_raining": "1"}, {"observed_raining": ""}, {"observed_raining": "0"}]
    assert len(matured(rows)) == 2


def test_brier_and_sigmoid():
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert brier([0.5, 0.5], [1, 0]) == 0.25
    assert math.isclose(sigmoid(0), 0.5, abs_tol=1e-9)


def test_gate_requires_beating_raw_and_champion():
    assert passes_gate(0.10, champ_brier=0.20, raw_brier=0.25) is True
    assert passes_gate(0.22, champ_brier=0.20, raw_brier=0.25) is False   # worse than champion
    assert passes_gate(0.30, champ_brier=0.20, raw_brier=0.25) is False   # worse than raw
    assert passes_gate(0.10, champ_brier=None, raw_brier=0.25) is True    # no champion yet


def test_train_classifier_learns_separable_signal():
    # rain when recent_rain high; model should give higher prob for the rainy row
    rows = []
    for v in (0.0, 0.0, 0.0, 5.0, 5.0, 5.0):
        rows.append({"fc_bestmatch_mm": str(v), "fc_ecmwf_mm": str(v),
                     "hour": "12", "recent_rain_mm": str(v),
                     "observed_raining": "1" if v > 0 else "0"})
    X, y = build_xy(rows)
    m = train_classifier(X, y)
    assert m["type"] == "logistic" and len(m["weights"]) == len(FEATURE_NAMES)
    dry = predict_proba(m, row_to_features(rows[0]))
    wet = predict_proba(m, row_to_features(rows[-1]))
    assert wet > dry


def test_demote_when_champion_worse_than_raw():
    # today's real situation: champion 0.1783 lost to raw 0.1724 -> demote
    assert should_demote(0.1783, 0.1724) is True


def test_no_demote_when_champion_beats_raw():
    assert should_demote(0.15, 0.1724) is False


def test_no_demote_when_no_logistic_champion():
    # champ_b is None (serving raw already) -> nothing to demote
    assert should_demote(None, 0.1724) is False


def test_no_demote_on_tie():
    # tie keeps the champion, mirroring passes_gate's strict '>'
    assert should_demote(0.1724, 0.1724) is False


def test_passthrough_serves_raw_and_is_ignored_as_champion():
    m = raw_passthrough_model(0.1724, 0.3384, 0.1783, 100, 25, "2026-07-03T16:00:00Z")
    assert m["type"] != "logistic"            # so nowcast.js serves it as raw...
    assert m["weights"] == [1.0, 0.0, 0.0, 0.0, 0.0]  # predict = max(0, fc_bestmatch_mm)
    assert m["intercept"] == 0.0
    assert m["features"] == FEATURE_NAMES
    assert m["brier"] == 0.1724 and m["raw_brier"] == 0.1724
    assert m["champion_brier"] == 0.1783
    assert set(m) == {"type", "features", "weights", "intercept", "trained_at",
                      "n_train", "n_test", "brier", "raw_brier", "clim_brier", "champion_brier"}


def test_promotion_gate_unchanged():
    # regression guard: the existing gate still behaves
    assert passes_gate(0.10, 0.20, 0.15) is True     # beats champ & raw
    assert passes_gate(0.16, 0.20, 0.15) is False    # loses to raw
