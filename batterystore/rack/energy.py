"""簇电量折算。

电量按"簇电压 × 额定安时 × SOC 窗口"折算。充放电记账与服务配额都以这里
的结果为准，避免配电与结算各算一套。
"""

from __future__ import annotations

from ..config import RackLimits
from .cells import Cell


def pack_voltage_v(cells: list[Cell]) -> float:
    """返回串联单体的总电压。"""

    return sum(cell.voltage_v for cell in cells)


def rack_energy_kwh(cells: list[Cell], soc_pct: float, capacity_ah: float) -> float:
    """按当前电压、SOC 与额定安时折算簇内可用电量。"""

    if capacity_ah <= 0:
        raise ValueError("额定安时必须为正")
    return pack_voltage_v(cells) * capacity_ah * (float(soc_pct) / 100.0) / 1000.0


def usable_energy_kwh(cells: list[Cell], limits: RackLimits, capacity_ah: float) -> float:
    """按允许 SOC 窗口折算可用电量。"""

    span = (limits.soc_max_pct - limits.soc_min_pct) / 100.0
    return pack_voltage_v(cells) * capacity_ah * span / 1000.0
