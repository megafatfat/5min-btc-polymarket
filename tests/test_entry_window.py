from src.signal.entry_window import EntryWindowConfig, evaluate_entry_window


def test_too_late_below_hard_min():
    cfg = EntryWindowConfig()
    allowed, status, _ = evaluate_entry_window(45.0, cfg)
    assert allowed is False
    assert status == "skip_too_late_to_enter"


def test_too_early_above_window_max():
    cfg = EntryWindowConfig()
    allowed, status, meta = evaluate_entry_window(271.0, cfg)
    assert allowed is False
    assert status == "skip_too_early_to_enter"
    assert meta["reason"] == "above_window_max"


def test_outside_window_below_target_band():
    cfg = EntryWindowConfig()
    allowed, status, meta = evaluate_entry_window(77.0, cfg)
    assert allowed is False
    assert status == "skip_outside_entry_window"
    assert meta["reason"] == "below_window_min"


def test_in_entry_window():
    cfg = EntryWindowConfig()
    for sec_left in (90.0, 120.0, 150.0, 116.0):
        allowed, status, _ = evaluate_entry_window(sec_left, cfg)
        assert allowed is True
        assert status == "in_entry_window"