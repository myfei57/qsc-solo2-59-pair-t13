"""BMS 保护判据。

保护与就绪是两条不同的线：就绪只是"可以并网"，保护是"必须停机"。这里只做
判据计算，动作交给上层编排，保证同一份判据既用于周期巡检也用于并网前核对。
"""

from __future__ import annotations

from ..config import BmsLimits
from ..rack.rack import Rack


def evaluate_protection(rack: Rack, limits: BmsLimits) -> list[str]:
    """返回越限项名称清单。"""

    metrics = rack.metrics()
    violations: list[str] = []
    if metrics.max_temperature_c >= limits.protection_temp_c:
        violations.append("temperature_protection")
    if metrics.delta_mv >= limits.protection_delta_mv:
        violations.append("cell_delta_protection")
    return violations
