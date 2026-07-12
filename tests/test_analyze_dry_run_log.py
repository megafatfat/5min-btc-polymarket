from pathlib import Path

from scripts.analyze_dry_run_log import build_report, parse_log

SAMPLE = """\
[dry-run] profile=conservative threshold=0.7 min_entry_sec=60 duration_min=8
2026-07-11T12:03:43.750520Z signal_ready slug=btc-updown-5m-1783771200 left=76.669s up_ask=0.38 dn_ask=0.71 side=DOWN trigger=0.71
2026-07-11T12:05:29.194319Z signal_ready slug=btc-updown-5m-1783771500 left=271.218s up_ask=0.73 dn_ask=0.28 side=UP trigger=0.73
2026-07-11T12:08:04.239579Z signal_ready slug=btc-updown-5m-1783771500 left=116.187s up_ask=0.71 dn_ask=0.3 side=UP trigger=0.71
[dry-run] finished signals=3
"""


def test_parse_and_classify(tmp_path: Path):
    log = tmp_path / "sample.log"
    log.write_text(SAMPLE, encoding="utf-8")
    rows, meta = parse_log(log)
    report = build_report(rows, meta, profile="conservative")

    assert report["totals"]["raw_signals"] == 3
    assert report["totals"]["allowed_after_entry_window"] == 1
    assert report["entry_class_counts"]["skip_too_early_to_enter"] == 1
    assert report["entry_class_counts"]["skip_outside_entry_window"] == 1
    assert report["entry_class_counts"]["in_entry_window"] == 1