"""簇级告警采集。

告警由簇本身产生，携带的是内部簇标识与触发时的度量。告警不在这里决定
展示编号——那是 :mod:`batterystore.bms.route` 的职责，采集与路由分开才能
保证重编号之后展示的是最新编号。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import RackLimits
from .metrics import RackMetrics


@dataclass(frozen=True)
class RackAlarm:
    """一条簇级告警。"""

    code: str
    rack_id: str
    severity: str
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "rack_id": self.rack_id,
            "severity": self.severity,
            "detail": self.detail,
        }


def collect_alarms(
    rack_id: str,
    metrics: RackMetrics,
    limits: RackLimits,
    soc_pct: float,
    delta_mv_limit: float,
) -> list[RackAlarm]:
    """按度量、SOC 与压差门限生成告警清单。"""

    alarms: list[RackAlarm] = []
    if metrics.max_temperature_c >= limits.temp_trip_c:
        alarms.append(
            RackAlarm("over_temp_trip", rack_id, "alarm", {"temperature_c": round(metrics.max_temperature_c, 2)})
        )
    elif metrics.max_temperature_c >= limits.temp_warn_c:
        alarms.append(
            RackAlarm("over_temp_warn", rack_id, "warning", {"temperature_c": round(metrics.max_temperature_c, 2)})
        )
    if metrics.delta_mv >= delta_mv_limit:
        alarms.append(RackAlarm("cell_delta_high", rack_id, "warning", {"delta_mv": round(metrics.delta_mv, 2)}))
    if soc_pct <= limits.soc_min_pct:
        alarms.append(RackAlarm("soc_low", rack_id, "warning", {"soc_pct": round(soc_pct, 2)}))
    elif soc_pct >= limits.soc_max_pct:
        alarms.append(RackAlarm("soc_high", rack_id, "warning", {"soc_pct": round(soc_pct, 2)}))
    return alarms
