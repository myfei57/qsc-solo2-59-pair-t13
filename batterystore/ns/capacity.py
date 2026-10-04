"""站容量核算。

电站容量按"簇数 × 单体数 × 额定电压 × 额定安时"折算成可用电量，并给出
功率配比。运维用它核对新建电站的铭牌与现场实际配置是否一致，控制台把它
展示在概览页顶部。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import StationConfig


@dataclass(frozen=True)
class CapacityPlan:
    """一次容量核算的结果。"""

    rack_count: int
    cells_per_rack: int
    nominal_voltage_v: float
    rated_energy_kwh: float
    usable_energy_kwh: float
    power_ratio: float

    def as_dict(self) -> dict:
        return {
            "rack_count": self.rack_count,
            "cells_per_rack": self.cells_per_rack,
            "nominal_voltage_v": round(self.nominal_voltage_v, 2),
            "rated_energy_kwh": round(self.rated_energy_kwh, 3),
            "usable_energy_kwh": round(self.usable_energy_kwh, 3),
            "power_ratio": round(self.power_ratio, 4),
        }


def plan_capacity(config: StationConfig, rack_count: int) -> CapacityPlan:
    """按配置与簇数核算额定／可用容量与功率配比。"""

    if rack_count <= 0:
        raise ValueError("簇数必须为正")
    cells = config.rack.cell_count
    pack_voltage = cells * config.rack.cell_nominal_v
    rated_energy = pack_voltage * config.soc.capacity_ah * rack_count / 1000.0
    soc_span = (config.rack.soc_max_pct - config.rack.soc_min_pct) / 100.0
    usable = rated_energy * soc_span
    power_ratio = config.pcs.max_power_kw * rack_count / rated_energy if rated_energy else 0.0
    return CapacityPlan(
        rack_count=rack_count,
        cells_per_rack=cells,
        nominal_voltage_v=pack_voltage,
        rated_energy_kwh=rated_energy,
        usable_energy_kwh=usable,
        power_ratio=power_ratio,
    )
