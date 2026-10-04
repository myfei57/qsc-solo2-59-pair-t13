"""电压裕度。

充电电流大小受最高单体距电压上限的裕度约束：裕度越小，允许的充电电流越小。
把裕度单独算出来，可以让"先降流还是先核压"的顺序问题有一个明确依据——电压
没有稳定到裕度窗口内时不允许把电流顶上去。
"""

from __future__ import annotations

from ..config import PcsLimits, RackLimits
from ..rack.rack import Rack


def charge_headroom_mv(rack: Rack, limits: RackLimits) -> float:
    """返回簇内最高单体距电压上限的裕度（毫伏）。"""

    cells = rack.cells()
    highest = max(cells, key=lambda cell: cell.voltage_v)
    return highest.headroom_mv(limits.cell_v_max)


def current_for_headroom(headroom_mv: float, limits: PcsLimits) -> float:
    """按电压裕度折算允许的充电电流。"""

    if headroom_mv <= 0:
        return 0.0
    ratio = min(1.0, headroom_mv / (limits.current_step_a * 10.0))
    return round(limits.current_max_a * ratio, 3)
