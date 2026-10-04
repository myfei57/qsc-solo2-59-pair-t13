"""SOC 状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SocSnapshot:
    """SOC 某一时刻的状态。"""

    estimate: dict
    calibration: dict
    coulomb: dict
    margin_pct: float
    samples: int

    def as_dict(self) -> dict:
        return {
            "estimate": dict(self.estimate),
            "calibration": dict(self.calibration),
            "coulomb": dict(self.coulomb),
            "margin_pct": round(self.margin_pct, 3),
            "samples": self.samples,
        }
