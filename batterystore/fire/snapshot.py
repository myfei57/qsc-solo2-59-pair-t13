"""消防状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FireSnapshot:
    """消防联动某一时刻的状态。"""

    detectors: dict
    valve: dict
    stages: list
    sequence: list
    release_ready: bool
    pcs_tripped: bool
    holds: int
    aborts: int

    def as_dict(self) -> dict:
        return {
            "detectors": dict(self.detectors),
            "valve": dict(self.valve),
            "stages": list(self.stages),
            "sequence": list(self.sequence),
            "release_ready": self.release_ready,
            "pcs_tripped": self.pcs_tripped,
            "holds": self.holds,
            "aborts": self.aborts,
        }
