"""温度降额曲线。

曲线分三段：起点以下不降额，起点到满额点之间线性下降，满额点以上压到下限
系数。系数直接乘以 PCS 功率指令，控制台展示的是同一份系数。
"""

from __future__ import annotations

from ..config import TempLimits


class DerateCurve:
    """两段折线的降额曲线。"""

    def __init__(self, limits: TempLimits) -> None:
        self._limits = limits

    @property
    def limits(self) -> TempLimits:
        return self._limits

    def ratio(self, temperature_c: float) -> float:
        """返回给定温度下的降额系数。"""

        value = float(temperature_c)
        if value <= self._limits.derate_start_c:
            return 1.0
        if value >= self._limits.derate_full_c:
            return self._limits.derate_floor_ratio
        span = self._limits.derate_full_c - self._limits.derate_start_c
        weight = (value - self._limits.derate_start_c) / span
        return 1.0 - (1.0 - self._limits.derate_floor_ratio) * weight

    def band(self, temperature_c: float) -> str:
        """返回温度所处的档位名。"""

        value = float(temperature_c)
        if value >= self._limits.derate_full_c:
            return "full_derate"
        if value >= self._limits.derate_start_c:
            return "derated"
        if value >= self._limits.warn_c:
            return "warm"
        return "normal"

    def points(self) -> list[dict]:
        """返回曲线控制点，供控制台画图。"""

        return [
            {"temperature_c": self._limits.derate_start_c, "ratio": 1.0},
            {"temperature_c": self._limits.derate_full_c, "ratio": self._limits.derate_floor_ratio},
        ]
