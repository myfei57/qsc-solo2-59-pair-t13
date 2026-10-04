"""PCS 状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PcsSnapshot:
    """PCS 某一时刻的状态。"""

    state: str
    generation: int
    derate_ratio: float
    output_kw: float
    delivered_kw: float
    reactive_kvar: float
    efficient_at: float
    switch: dict
    ramp_kw: float
    ramp_steps: int
    ramp_traveled_kw: float
    power_commands: int
    ladder: dict
    tripped: bool
    trip_reasons: list

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "generation": self.generation,
            "derate_ratio": round(self.derate_ratio, 4),
            "output_kw": round(self.output_kw, 3),
            "delivered_kw": round(self.delivered_kw, 3),
            "reactive_kvar": round(self.reactive_kvar, 3),
            "efficient_at": round(self.efficient_at, 4),
            "switch": dict(self.switch),
            "ramp_kw": round(self.ramp_kw, 3),
            "ramp_steps": self.ramp_steps,
            "ramp_traveled_kw": round(self.ramp_traveled_kw, 3),
            "power_commands": self.power_commands,
            "ladder": dict(self.ladder),
            "tripped": self.tripped,
            "trip_reasons": list(self.trip_reasons),
        }
