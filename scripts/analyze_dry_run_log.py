#!/usr/bin/env python3
"""Analyze dry-run monitor logs and summarize entry/hedge timing."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.risk.skew_hedge import HedgeConfig, dominant_side_from_asks, evaluate_skew_hedge, load_hedge_config
from src.signal.entry_window import EntryWindowConfig, evaluate_entry_window, load_entry_window_config

LINE_RE = re.compile(
    r"^(?P<ts>\S+)\s+(?P<status>\S+)\s+slug=(?P<slug>\S+)\s+left=(?P<left>[\d.]+|-)s"
    r"(?:\s+up_ask=(?P<up>[\d.]+|None))?(?:\s+dn_ask=(?P<dn>[\d.]+|None))?"
    r"(?:\s+side=(?P<side>UP|DOWN)\s+trigger=(?P<trigger>[\d.]+))?"
    r"(?:\s+hedge=(?P<hedge_side>UP|DOWN)\s+\$(?P<hedge_usd>[\d.]+)@(?P<hedge_px>[\d.]+))?"
)


@dataclass
class LogRow:
    ts: str
    status: str
    slug: str
    seconds_left: Optional[float]
    up_ask: Optional[float]
    down_ask: Optional[float]
    side: Optional[str]
    trigger_price: Optional[float]
    hedge_side: Optional[str] = None
    hedge_notional_usd: Optional[float] = None
    hedge_price: Optional[float] = None


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None or value in {"-", "None"}:
        return None
    return float(value)


def parse_log(path: Path) -> tuple[list[LogRow], dict[str, str]]:
    rows: list[LogRow] = []
    meta: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[dry-run] profile="):
            meta["header"] = line
            continue
        if line.startswith("[dry-run] finished"):
            meta["footer"] = line
            continue

        match = LINE_RE.match(line)
        if not match:
            continue

        rows.append(
            LogRow(
                ts=match.group("ts"),
                status=match.group("status"),
                slug=match.group("slug"),
                seconds_left=_parse_float(match.group("left")),
                up_ask=_parse_float(match.group("up")),
                down_ask=_parse_float(match.group("dn")),
                side=match.group("side"),
                trigger_price=_parse_float(match.group("trigger")),
                hedge_side=match.group("hedge_side"),
                hedge_notional_usd=_parse_float(match.group("hedge_usd")),
                hedge_price=_parse_float(match.group("hedge_px")),
            )
        )
    return rows, meta


def classify_signal(
    row: LogRow,
    entry_cfg: EntryWindowConfig,
    hedge_cfg: HedgeConfig,
) -> dict[str, Any]:
    if row.seconds_left is None:
        return {"entry_class": "unknown", "hedge": {"hedge_triggered": False, "reason": "missing_seconds_left"}}

    allowed, entry_status, _ = evaluate_entry_window(row.seconds_left, entry_cfg)
    hedge = evaluate_skew_hedge(
        seconds_left=row.seconds_left,
        up_ask=row.up_ask,
        down_ask=row.down_ask,
        cfg=hedge_cfg,
        main_side=row.side,
    )
    return {
        "entry_allowed": allowed,
        "entry_class": entry_status,
        "hedge": hedge,
    }


def first_per_slug(rows: list[LogRow], predicate) -> dict[str, LogRow]:
    out: dict[str, LogRow] = {}
    for row in rows:
        if row.slug in {"-", ""}:
            continue
        if predicate(row) and row.slug not in out:
            out[row.slug] = row
    return out


def build_report(
    rows: list[LogRow],
    meta: dict[str, str],
    profile: str,
) -> dict[str, Any]:
    entry_cfg = load_entry_window_config(profile=profile)
    hedge_cfg = load_hedge_config(profile=profile)
    status_counts = Counter(row.status for row in rows)

    signal_rows = [r for r in rows if r.status == "signal_ready" or r.side is not None]
    classified: list[dict[str, Any]] = []

    entry_classes = Counter()
    hedge_hits = 0
    for row in signal_rows:
        if row.side is None and row.status != "signal_ready":
            continue
        cls = classify_signal(row, entry_cfg, hedge_cfg)
        entry_classes[cls["entry_class"]] += 1
        if cls["hedge"].get("hedge_triggered"):
            hedge_hits += 1
        classified.append(
            {
                "ts": row.ts,
                "slug": row.slug,
                "seconds_left": row.seconds_left,
                "side": row.side,
                "trigger_price": row.trigger_price,
                "up_ask": row.up_ask,
                "down_ask": row.down_ask,
                **cls,
            }
        )

    allowed_signals = [c for c in classified if c.get("entry_allowed")]
    in_window = [c for c in classified if c.get("entry_class") == "in_entry_window"]
    hedge_ready = [c for c in classified if c["hedge"].get("hedge_triggered")]

    by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in classified:
        by_slug[item["slug"]].append(item)

    cycle_summaries = []
    for slug, items in sorted(by_slug.items()):
        allowed = [i for i in items if i.get("entry_allowed")]
        hedges = [i for i in items if i["hedge"].get("hedge_triggered")]
        best_allowed = max(allowed, key=lambda i: i.get("trigger_price") or 0, default=None)
        strongest = max(items, key=lambda i: i.get("trigger_price") or 0, default=None)
        cycle_summaries.append(
            {
                "slug": slug,
                "raw_signals": len(items),
                "allowed_signals": len(allowed),
                "hedge_hits": len(hedges),
                "first_allowed": allowed[0] if allowed else None,
                "best_allowed_trigger": best_allowed,
                "strongest_raw_trigger": strongest,
                "reversal": _detect_reversal(items),
            }
        )

    return {
        "source_log": str(rows[0].slug if rows else ""),
        "meta": meta,
        "profile": profile,
        "entry_window": entry_cfg.as_dict(),
        "hedge_config": hedge_cfg.as_dict(),
        "totals": {
            "rows_parsed": len(rows),
            "status_counts": dict(status_counts),
            "raw_signals": len(classified),
            "allowed_after_entry_window": len(allowed_signals),
            "in_entry_window": len(in_window),
            "hedge_ready": len(hedge_ready),
            "filtered_out": len(classified) - len(allowed_signals),
        },
        "entry_class_counts": dict(entry_classes),
        "top_allowed_entries": sorted(
            allowed_signals,
            key=lambda i: abs((i.get("seconds_left") or 0) - entry_cfg.target_sec),
        )[:10],
        "top_hedge_events": sorted(
            hedge_ready,
            key=lambda i: i["hedge"].get("dominant_price") or 0,
            reverse=True,
        )[:10],
        "cycles": cycle_summaries,
    }


def _detect_reversal(items: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    sides = [i.get("side") for i in items if i.get("side")]
    if len(sides) < 2:
        return None
    first = sides[0]
    last = sides[-1]
    if first == last:
        return None
    return {
        "from": first,
        "to": last,
        "first_ts": items[0].get("ts"),
        "last_ts": items[-1].get("ts"),
        "first_left_sec": items[0].get("seconds_left"),
        "last_left_sec": items[-1].get("seconds_left"),
    }


def render_markdown(report: dict[str, Any], log_path: Path) -> str:
    totals = report["totals"]
    lines = [
        "# Dry-Run Log Analysis",
        "",
        f"- **Log**: `{log_path}`",
        f"- **Profile**: `{report['profile']}`",
        f"- **Entry window**: {report['entry_window']['window_min_sec']:.0f}-{report['entry_window']['window_max_sec']:.0f}s",
        f"- **Hedge trigger**: dominant ask ≥ {report['hedge_config']['trigger_side_price_gte']} and left ≤ {report['hedge_config']['trigger_seconds_left_lte']}s",
        "",
        "## Totals",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Parsed rows | {totals['rows_parsed']} |",
        f"| Raw signals | {totals['raw_signals']} |",
        f"| Allowed after entry-window filter | {totals['allowed_after_entry_window']} |",
        f"| Filtered out | {totals['filtered_out']} |",
        f"| Hedge-ready events | {totals['hedge_ready']} |",
        "",
        "## Entry class breakdown",
        "",
    ]
    for key, count in sorted(report["entry_class_counts"].items()):
        lines.append(f"- `{key}`: {count}")

    lines.extend(["", "## Per-cycle summary", ""])
    for cycle in report["cycles"]:
        lines.append(f"### `{cycle['slug']}`")
        lines.append(f"- Raw signals: {cycle['raw_signals']}")
        lines.append(f"- Allowed in window: {cycle['allowed_signals']}")
        lines.append(f"- Hedge hits: {cycle['hedge_hits']}")
        if cycle["first_allowed"]:
            fa = cycle["first_allowed"]
            lines.append(
                f"- First allowed entry: {fa['side']} @ {fa['trigger_price']} "
                f"({fa['seconds_left']:.0f}s left, {fa['ts']})"
            )
        if cycle["best_allowed_trigger"]:
            ba = cycle["best_allowed_trigger"]
            lines.append(
                f"- Best allowed trigger: {ba['side']} @ {ba['trigger_price']} "
                f"({ba['seconds_left']:.0f}s left)"
            )
        if cycle["reversal"]:
            rev = cycle["reversal"]
            lines.append(
                f"- Reversal: {rev['from']} → {rev['to']} "
                f"({rev['first_left_sec']:.0f}s → {rev['last_left_sec']:.0f}s left)"
            )
        lines.append("")

    lines.extend(["## Best allowed entries (closest to 120s target)", ""])
    for item in report["top_allowed_entries"]:
        lines.append(
            f"- {item['slug']}: {item['side']} trigger={item['trigger_price']} "
            f"left={item['seconds_left']:.0f}s ({item['ts']})"
        )

    lines.extend(["", "## Top hedge-ready events", ""])
    if not report["top_hedge_events"]:
        lines.append("- None under current hedge thresholds.")
    else:
        for item in report["top_hedge_events"]:
            hedge = item["hedge"]
            lines.append(
                f"- {item['slug']}: hedge {hedge['hedge_side']} ${hedge['hedge_notional_usd']} "
                f"dominant={hedge['dominant_side']}@{hedge['dominant_price']} "
                f"left={item['seconds_left']:.0f}s ({item['ts']})"
            )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze dry_run_monitor log files")
    ap.add_argument(
        "--log",
        default=str(ROOT / "reports" / "dry_run_monitor_session.log"),
        help="Path to dry-run monitor log",
    )
    ap.add_argument("--profile", choices=["conservative", "aggressive"], default="conservative")
    ap.add_argument(
        "--out-json",
        default=str(ROOT / "reports" / "dry_run_analysis.json"),
    )
    ap.add_argument(
        "--out-md",
        default=str(ROOT / "reports" / "dry_run_analysis.md"),
    )
    args = ap.parse_args()

    log_path = Path(args.log)
    rows, meta = parse_log(log_path)
    report = build_report(rows, meta, args.profile)
    report["source_log"] = str(log_path)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report, log_path), encoding="utf-8")

    totals = report["totals"]
    print(f"Analyzed: {log_path}")
    print(f"Raw signals: {totals['raw_signals']}")
    print(f"Allowed in entry window: {totals['allowed_after_entry_window']}")
    print(f"Filtered out: {totals['filtered_out']}")
    print(f"Hedge-ready: {totals['hedge_ready']}")
    print(f"JSON: {out_json}")
    print(f"Markdown: {out_md}")


if __name__ == "__main__":
    main()