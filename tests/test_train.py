import math
from datetime import datetime, timedelta, timezone

from pipeline.train import (row_to_features, brier, sigmoid, predict_proba,
                            passes_gate, train_classifier, build_xy, matured, FEATURE_NAMES,
                            should_demote, raw_passthrough_model,
                            walk_forward_folds, brier_skill_score, median, passes_walk_forward)

IST = timezone(timedelta(hours=5, minutes=30))


def test_row_to_features_shape_and_cyclic_hour():
    f = row_to_features({"fc_bestmatch_mm": "2.0", "fc_ecmwf_mm": "1.5",
                         "fc_rh_bestmatch": "80", "hour": "6", "recent_rain_mm": "0.5"})
    assert len(f) == len(FEATURE_NAMES)
    assert f[0] == 2.0 and f[1] == 1.5 and f[2] == 80.0
    assert math.isclose(f[3], math.sin(2 * math.pi * 6 / 24), abs_tol=1e-9)


def test_row_to_features_blank_ecmwf_falls_back_to_bestmatch():
    f = row_to_features({"fc_bestmatch_mm": "3.0", "fc_ecmwf_mm": "",
                         "fc_rh_bestmatch": "", "hour": "0", "recent_rain_mm": "0"})
    assert f[1] == 3.0   # blank ECMWF -> best_match value, never 0
    assert f[2] == 50.0  # blank RH -> neutral 50 (monsoon mean), never 0


def test_row_to_features_old_champion_feature_names():
    # an old 5-feature model declares its own features; row_to_features maps by NAME
    old = ["fc_bestmatch_mm", "fc_ecmwf_mm", "hour_sin", "hour_cos", "recent_rain_mm"]
    f = row_to_features({"fc_bestmatch_mm": "2.0", "fc_ecmwf_mm": "1.0",
                         "fc_rh_bestmatch": "99", "hour": "12", "recent_rain_mm": "0.1"},
                        feature_names=old)
    assert len(f) == 5 and f[0] == 2.0 and f[1] == 1.0


def test_matured_filters_unlabelled_and_past_hours():
    # issued 15:00 UTC = 20:30 IST; forward = valid hour >= 20:30 IST (i.e. >= 21:00)
    rows = [
        {"observed_raining": "1", "issued_at": "2026-06-25T15:00", "valid_at": "2026-06-25T21:00"},  # forward
        {"observed_raining": "", "issued_at": "2026-06-25T15:00", "valid_at": "2026-06-25T22:00"},   # unlabelled
        {"observed_raining": "0", "issued_at": "2026-06-25T15:00", "valid_at": "2026-06-25T23:00"},  # forward
        {"observed_raining": "1", "issued_at": "2026-06-25T15:00", "valid_at": "2026-06-25T20:00"},  # past IST
        {"observed_raining": "0", "issued_at": "2026-06-25T15:00", "valid_at": "2026-06-26T00:00"},  # forward (next day)
    ]
    out = matured(rows)
    assert len(out) == 3   # drops unlabelled + the same-day-past hour
    assert out[0]["valid_at"] == "2026-06-25T21:00"


def test_brier_and_sigmoid():
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert brier([0.5, 0.5], [1, 0]) == 0.25
    assert math.isclose(sigmoid(0), 0.5, abs_tol=1e-9)


def test_gate_requires_beating_raw_and_champion():
    assert passes_gate(0.10, champ_brier=0.20, raw_brier=0.25) is True
    assert passes_gate(0.22, champ_brier=0.20, raw_brier=0.25) is False   # worse than champion
    assert passes_gate(0.30, champ_brier=0.20, raw_brier=0.25) is False   # worse than raw
    assert passes_gate(0.10, champ_brier=None, raw_brier=0.25) is True    # no champion yet
    # clim is a third bar when provided
    assert passes_gate(0.18, champ_brier=0.20, raw_brier=0.25, clim_brier=0.15) is False
    assert passes_gate(0.10, champ_brier=0.20, raw_brier=0.25, clim_brier=0.15) is True


def test_train_classifier_learns_separable_signal():
    # rain when recent_rain high; model should give higher prob for the rainy row
    rows = []
    for v in (0.0, 0.0, 0.0, 5.0, 5.0, 5.0):
        rows.append({"fc_bestmatch_mm": str(v), "fc_ecmwf_mm": str(v),
                     "fc_rh_bestmatch": "70", "hour": "12", "recent_rain_mm": str(v),
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


def test_demote_when_champion_worse_than_clim():
    assert should_demote(0.22, raw_b=0.30, clim_b=0.18) is True
    assert should_demote(0.15, raw_b=0.30, clim_b=0.18) is False


def test_passthrough_serves_raw_and_is_ignored_as_champion():
    m = raw_passthrough_model(0.1724, 0.3384, 0.1783, 100, 25, "2026-07-03T16:00:00Z")
    assert m["type"] != "logistic"            # so nowcast.js serves it as raw...
    assert m["weights"][0] == 1.0 and m["weights"][1:] == [0.0] * (len(FEATURE_NAMES) - 1)
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


# --- Walk-forward validation (issue #1) -------------------------------------


def _rows(hours, leads=7, rain=lambda h: h % 2):
    """One row per (valid_at hour, lead time), mimicking the log's ~7x duplication."""
    base = datetime(2026, 7, 1, 0, 0)
    out = []
    for h in range(hours):
        valid_at = base + timedelta(hours=h)
        for lead in range(leads):
            out.append({
                "valid_at": valid_at.isoformat(timespec="minutes"),
                "issued_at": (valid_at - timedelta(hours=lead)).isoformat(timespec="minutes"),
                "fc_bestmatch_mm": "1.0" if rain(h) else "0.0",
                "fc_ecmwf_mm": "1.0" if rain(h) else "0.0",
                "hour": str(valid_at.hour),
                "recent_rain_mm": "0.0",
                "observed_raining": str(rain(h)),
            })
    return out


def test_walk_forward_purge_leaves_no_training_row_inside_the_gap():
    """The purge is the point: no training valid_at may sit within PURGE_HOURS of the test start."""
    rows = _rows(200)
    folds = list(walk_forward_folds(rows, folds=4, purge_hours=6))
    assert folds, "fixture should produce usable folds"

    for train_rows, test_rows in folds:
        train_end = max(datetime.fromisoformat(r["valid_at"]) for r in train_rows)
        test_start = min(datetime.fromisoformat(r["valid_at"]) for r in test_rows)
        gap_hours = (test_start - train_end).total_seconds() / 3600
        assert gap_hours >= 6, f"purge violated: only {gap_hours}h between train end and test start"


def test_walk_forward_never_splits_one_valid_at_across_train_and_test():
    """One valid_at is ~7 rows; if it straddles the boundary the holdout has seen its own hour."""
    rows = _rows(200)
    for train_rows, test_rows in walk_forward_folds(rows, folds=4, purge_hours=6):
        train_stamps = {r["valid_at"] for r in train_rows}
        test_stamps = {r["valid_at"] for r in test_rows}
        assert not (train_stamps & test_stamps)


def test_walk_forward_windows_expand_and_move_forward():
    """Expanding window: each fold trains on at least as much as the previous one, later in time."""
    rows = _rows(200)
    folds = list(walk_forward_folds(rows, folds=4, purge_hours=6))
    assert len(folds) >= 2
    sizes = [len(train_rows) for train_rows, _ in folds]
    starts = [min(datetime.fromisoformat(r["valid_at"]) for r in test_rows) for _, test_rows in folds]
    assert sizes == sorted(sizes)
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


def test_walk_forward_test_blocks_do_not_overlap():
    rows = _rows(200)
    seen = set()
    for _, test_rows in walk_forward_folds(rows, folds=4, purge_hours=6):
        stamps = {r["valid_at"] for r in test_rows}
        assert not (stamps & seen), "fold test blocks must be disjoint"
        seen |= stamps


def test_walk_forward_yields_nothing_when_there_is_too_little_history():
    assert list(walk_forward_folds(_rows(3), folds=4, purge_hours=6)) == []


def test_walk_forward_skips_folds_with_only_one_class():
    """A fold that never rains cannot score calibration, so it must be dropped, not scored."""
    rows = _rows(200, rain=lambda h: 0)          # never rains anywhere
    assert list(walk_forward_folds(rows, folds=4, purge_hours=6)) == []


def test_brier_skill_score_signs():
    assert brier_skill_score(0.10, 0.20) > 0      # better than reference
    assert brier_skill_score(0.20, 0.20) == 0     # no better
    assert brier_skill_score(0.30, 0.20) < 0      # worse
    assert brier_skill_score(0.10, 0.0) == 0.0    # perfect reference -> no skill to add, no ZeroDivisionError


def test_median_handles_even_and_odd_and_empty():
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 2, 3]) == 2.5
    assert median([]) is None


def test_promotion_needs_median_above_zero_and_two_wins():
    assert passes_walk_forward([0.1, 0.2, 0.3])          # consistent
    assert passes_walk_forward([-0.01, 0.2, 0.3])        # one loss, median still positive
    # The lucky-monsoon-week case the issue names: one huge win, everything else negative.
    assert not passes_walk_forward([5.0, -0.1, -0.2])
    # Two wins but the losses dominate, so the median is negative.
    assert not passes_walk_forward([0.01, 0.02, -1.0, -1.0])
    assert not passes_walk_forward([0.5])                # a single fold is not validation
    assert not passes_walk_forward([])
