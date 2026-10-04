"""库仑累计。

充电按库仑效率折算，放电按实际安时计入。累计器只关心安时，不关心 SOC；
SOC 基准由最近一次校准给出，两者分开才能保证"校准一换、估算立刻跟着换"。
"""

from __future__ import annotations


class CoulombCounter:
    """安时累计器。"""

    def __init__(self, efficiency: float) -> None:
        if not 0.0 < efficiency <= 1.0:
            raise ValueError("库仑效率必须落在 (0, 1] 区间")
        self._efficiency = float(efficiency)
        self._charged_ah = 0.0
        self._discharged_ah = 0.0
        self._intervals = 0

    @property
    def efficiency(self) -> float:
        return self._efficiency

    def through(self, current_a: float, dt: float) -> float:
        """按电流方向累计一段安时，返回这段的净安时。"""

        if dt <= 0:
            raise ValueError("步长必须为正")
        amps = float(current_a)
        hours = float(dt) / 3600.0
        if amps >= 0:
            delta = amps * self._efficiency * hours
            self._charged_ah += delta
        else:
            delta = amps * hours
            self._discharged_ah += abs(delta)
        self._intervals += 1
        return delta

    def net_ah(self) -> float:
        """返回净安时（充为正、放为负）。"""

        return self._charged_ah - self._discharged_ah

    def charged_ah(self) -> float:
        """返回累计充入安时。"""

        return self._charged_ah

    def discharged_ah(self) -> float:
        """返回累计放出安时。"""

        return self._discharged_ah

    def intervals(self) -> int:
        """返回累计推进次数。"""

        return self._intervals

    def reset(self) -> dict:
        """清零累计量，返回清零前的值。"""

        previous = {
            "charged_ah": round(self._charged_ah, 6),
            "discharged_ah": round(self._discharged_ah, 6),
            "net_ah": round(self.net_ah(), 6),
        }
        self._charged_ah = 0.0
        self._discharged_ah = 0.0
        self._intervals = 0
        return previous
