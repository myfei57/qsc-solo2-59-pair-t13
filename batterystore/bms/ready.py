"""就绪判据。

PCS 并离网切换前必须拿到 BMS 的就绪确认。就绪是四条同时成立的合取：压差在
窗口内、温度低于就绪上限、SOC 落在就绪区间、且没有保持中的闩锁故障。任何一条
不成立都要给出原因名，让拒绝理由直接进审计。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import BmsLimits
from ..rack.rack import Rack


@dataclass(frozen=True)
class ReadyReport:
    """一次就绪核对的结果。"""

    rack_id: str
    ready: bool
    reasons: list[str] = field(default_factory=list)
    delta_mv: float = 0.0
    temperature_c: float = 0.0
    soc_pct: float = 0.0

    def as_dict(self) -> dict:
        return {
            "rack_id": self.rack_id,
            "ready": self.ready,
            "reasons": list(self.reasons),
            "delta_mv": round(self.delta_mv, 2),
            "temperature_c": round(self.temperature_c, 2),
            "soc_pct": round(self.soc_pct, 2),
        }


class ReadyGate:
    """就绪判据核对器。"""

    def __init__(self, limits: BmsLimits) -> None:
        self._limits = limits

    @property
    def limits(self) -> BmsLimits:
        return self._limits

    def evaluate(self, rack: Rack, latched: bool) -> ReadyReport:
        """核对一簇是否满足就绪判据。"""

        metrics = rack.metrics()
        soc = rack.soc_pct()
        reasons: list[str] = []
        if metrics.delta_mv > self._limits.ready_delta_mv:
            reasons.append("cell_delta_high")
        if metrics.max_temperature_c >= self._limits.ready_temp_c:
            reasons.append("temperature_high")
        if not self._limits.soc_window_ok(soc):
            reasons.append("soc_out_of_window")
        if latched:
            reasons.append("fault_latched")
        return ReadyReport(
            rack_id=rack.rack_id,
            ready=not reasons,
            reasons=reasons,
            delta_mv=metrics.delta_mv,
            temperature_c=metrics.max_temperature_c,
            soc_pct=soc,
        )
