"""SOC 估算。

估算口径固定为"最近一次校准值 + 校准之后的库仑净增量"，校准代际原样带出。
按校准之前的偏移继续折算，就会出现实际剩 30% 却显示 45% 的偏差；把代际
写进结果，调用方能直接核对这次估算用的是哪一代校准。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import SocLimits


@dataclass(frozen=True)
class SocEstimate:
    """一次 SOC 估算结果。"""

    soc_pct: float
    calibration_epoch: int
    base_soc_pct: float
    delta_pct: float
    stale: bool
    drift_pct: float

    def as_dict(self) -> dict:
        return {
            "soc_pct": round(self.soc_pct, 3),
            "calibration_epoch": self.calibration_epoch,
            "base_soc_pct": round(self.base_soc_pct, 3),
            "delta_pct": round(self.delta_pct, 3),
            "stale": self.stale,
            "drift_pct": round(self.drift_pct, 3),
        }


def estimate_soc(
    calibration: dict,
    net_ah: float,
    limits: SocLimits,
    reported_pct: float,
) -> SocEstimate:
    """按最近一代校准与库仑净增量估算 SOC。"""

    base = float(calibration.get("soc_pct", limits.initial_soc_pct))
    delta = limits.amp_hours_to_percent(float(net_ah))
    raw = base + delta
    bounded = max(0.0, min(100.0, raw))
    return SocEstimate(
        soc_pct=bounded,
        calibration_epoch=int(calibration.get("epoch", 0)),
        base_soc_pct=base,
        delta_pct=delta,
        stale=bool(calibration.get("expired", False)),
        drift_pct=bounded - float(reported_pct),
    )
