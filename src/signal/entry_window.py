"""Entry timing filter: prefer entries around ~120s before market close."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "btc_5m_profiles.yaml"


@dataclass(frozen=True)
class EntryWindowConfig:
    target_sec: int = 120
    tolerance_sec: int = 30
    min_entry_seconds_left: int = 60

    @property
    def window_min_sec(self) -> float:
        return max(
            float(self.min_entry_seconds_left),
            float(self.target_sec - self.tolerance_sec),
        )

    @property
    def window_max_sec(self) -> float:
        return float(self.target_sec + self.tolerance_sec)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "target_sec": self.target_sec,
            "tolerance_sec": self.tolerance_sec,
            "min_entry_seconds_left": self.min_entry_seconds_left,
            "window_min_sec": self.window_min_sec,
            "window_max_sec": self.window_max_sec,
        }


def load_entry_window_config(
    config_path: Optional[Path] = None,
    profile: str = "conservative",
) -> EntryWindowConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    strategy = raw.get("strategy_reference") or {}
    session = raw.get("shared_rules", {}).get("session_timing") or {}

    return EntryWindowConfig(
        target_sec=int(strategy.get("entry_window_seconds_left_target", 120)),
        tolerance_sec=int(strategy.get("entry_window_seconds_left_tolerance", 30)),
        min_entry_seconds_left=int(session.get("min_entry_seconds_left", 60)),
    )


def evaluate_entry_window(
    seconds_left: float,
    cfg: EntryWindowConfig,
) -> tuple[bool, str, dict[str, Any]]:
    """Return (allowed, status, metadata)."""
    meta = {
        "seconds_left": seconds_left,
        "entry_window": cfg.as_dict(),
    }

    if seconds_left < cfg.min_entry_seconds_left:
        return False, "skip_too_late_to_enter", meta

    if seconds_left > cfg.window_max_sec:
        meta["reason"] = "above_window_max"
        return False, "skip_too_early_to_enter", meta

    if seconds_left < cfg.window_min_sec:
        meta["reason"] = "below_window_min"
        return False, "skip_outside_entry_window", meta

    return True, "in_entry_window", meta