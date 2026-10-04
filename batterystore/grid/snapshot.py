"""并网点状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GridSnapshot:
    """并网点某一时刻的状态。"""

    limit: dict
    flow: dict
    frequency: dict
    checks: int
    rejections: int

    def as_dict(self) -> dict:
        return {
            "limit": dict(self.limit),
            "flow": dict(self.flow),
            "frequency": dict(self.frequency),
            "checks": self.checks,
            "rejections": self.rejections,
        }
