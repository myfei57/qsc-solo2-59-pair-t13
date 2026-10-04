"""温控状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TempSnapshot:
    """温控某一时刻的状态。"""

    temperature_c: float
    ratio: float
    charge_limit_ratio: float
    band: str
    cooling: bool
    cooler_ticks: int
    removed_c: float
    baseline: dict

    def as_dict(self) -> dict:
        return {
            "temperature_c": round(self.temperature_c, 2),
            "ratio": round(self.ratio, 4),
            "charge_limit_ratio": round(self.charge_limit_ratio, 4),
            "band": self.band,
            "cooling": self.cooling,
            "cooler_ticks": self.cooler_ticks,
            "removed_c": round(self.removed_c, 3),
            "baseline": dict(self.baseline),
        }
