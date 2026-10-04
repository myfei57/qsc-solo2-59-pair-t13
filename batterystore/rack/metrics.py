"""簇级度量。

压差、温差与 SOC 是三条独立的巡检轴：压差看落后单体，温差看散热与风道，
SOC 看可用电量。三者合成一份不可变快照，控制台与审计用同一份口径。
"""

from __future__ import annotations

from dataclasses import dataclass

from .cells import Cell


@dataclass(frozen=True)
class RackMetrics:
    """一簇电池的聚合度量。"""

    cells: int
    voltage_v: float
    min_voltage_v: float
    max_voltage_v: float
    delta_mv: float
    min_temperature_c: float
    max_temperature_c: float
    spread_c: float
    average_soc_pct: float

    def as_dict(self) -> dict:
        return {
            "cells": self.cells,
            "voltage_v": round(self.voltage_v, 3),
            "min_voltage_v": round(self.min_voltage_v, 4),
            "max_voltage_v": round(self.max_voltage_v, 4),
            "delta_mv": round(self.delta_mv, 2),
            "min_temperature_c": round(self.min_temperature_c, 2),
            "max_temperature_c": round(self.max_temperature_c, 2),
            "spread_c": round(self.spread_c, 2),
            "average_soc_pct": round(self.average_soc_pct, 2),
        }


def compute_metrics(cells: list[Cell]) -> RackMetrics:
    """把一批单体聚合成簇级度量。"""

    if not cells:
        raise ValueError("没有单体可以聚合")
    voltages = [cell.voltage_v for cell in cells]
    temperatures = [cell.temperature_c for cell in cells]
    socs = [cell.soc_pct for cell in cells]
    return RackMetrics(
        cells=len(cells),
        voltage_v=sum(voltages),
        min_voltage_v=min(voltages),
        max_voltage_v=max(voltages),
        delta_mv=(max(voltages) - min(voltages)) * 1000.0,
        min_temperature_c=min(temperatures),
        max_temperature_c=max(temperatures),
        spread_c=max(temperatures) - min(temperatures),
        average_soc_pct=sum(socs) / len(socs),
    )
