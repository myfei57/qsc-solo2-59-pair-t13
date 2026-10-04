"""均衡目标选择。

只对高于簇内最低电压一定幅度的单体放电，且数量不得少于 ``min_cells``：
选择太少说明压差本来就在目标带内，不必启动均衡。返回的是单体标识清单，
调用方据此决定给谁放电。
"""

from __future__ import annotations

from ..rack.cells import Cell


def cell_delta_mv(cells: list[Cell]) -> float:
    """返回簇内压差（毫伏）。"""

    if not cells:
        raise ValueError("没有单体可以计算压差")
    voltages = [cell.voltage_v for cell in cells]
    return (max(voltages) - min(voltages)) * 1000.0


def select_cells(cells: list[Cell], target_delta_mv: float, min_cells: int) -> list[str]:
    """选出需要放电的单体标识。"""

    if not cells:
        return []
    floor = min(cell.voltage_v for cell in cells)
    margin = float(target_delta_mv) / 1000.0
    candidates = [cell.cell_id for cell in cells if cell.voltage_v - floor > margin]
    if not candidates:
        return []
    need = max(1, int(min_cells))
    if len(candidates) < need:
        # 越限但只有少量单体偏高：按电压从高到低补足最小放电数量，
        # 否则会把"压差确实越限"误判成"已经在目标带内"。
        ordered = sorted(cells, key=lambda cell: cell.voltage_v, reverse=True)
        return sorted(cell.cell_id for cell in ordered[:need])
    return sorted(candidates)
