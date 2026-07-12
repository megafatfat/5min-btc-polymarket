# Dry-Run Log Analysis

- **Log**: `/Users/stephen/Projects/pbt-5m-enhanced/reports/dry_run_monitor_session.log`
- **Profile**: `conservative`
- **Entry window**: 90-150s
- **Hedge trigger**: dominant ask ≥ 0.95 and left ≤ 45s

## Totals

| Metric | Count |
|--------|------:|
| Parsed rows | 89 |
| Raw signals | 28 |
| Allowed after entry-window filter | 6 |
| Filtered out | 22 |
| Hedge-ready events | 0 |

## Entry class breakdown

- `in_entry_window`: 6
- `skip_outside_entry_window`: 9
- `skip_too_early_to_enter`: 13

## Per-cycle summary

### `btc-updown-5m-1783771200`
- Raw signals: 3
- Allowed in window: 0
- Hedge hits: 0

### `btc-updown-5m-1783771500`
- Raw signals: 25
- Allowed in window: 6
- Hedge hits: 0
- First allowed entry: UP @ 0.7 (133s left, 2026-07-11T12:07:47.650970Z)
- Best allowed trigger: DOWN @ 0.89 (105s left)
- Reversal: UP → DOWN (271s → 61s left)

## Best allowed entries (closest to 120s target)

- btc-updown-5m-1783771500: UP trigger=0.71 left=116s (2026-07-11T12:08:04.239579Z)
- btc-updown-5m-1783771500: DOWN trigger=0.84 left=111s (2026-07-11T12:08:09.722712Z)
- btc-updown-5m-1783771500: UP trigger=0.7 left=133s (2026-07-11T12:07:47.650970Z)
- btc-updown-5m-1783771500: DOWN trigger=0.89 left=105s (2026-07-11T12:08:15.240523Z)
- btc-updown-5m-1783771500: DOWN trigger=0.78 left=100s (2026-07-11T12:08:20.770758Z)
- btc-updown-5m-1783771500: DOWN trigger=0.8 left=94s (2026-07-11T12:08:26.257086Z)

## Top hedge-ready events

- None under current hedge thresholds.
