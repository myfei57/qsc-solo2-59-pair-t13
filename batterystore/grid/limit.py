"""并网点功率限额。

放电按上网限额、充电按用电限额分别钳位。钳位必须在爬坡之前完成：先爬坡再
钳位会让并网点在一瞬间越限，这正是"限功率参数带了但没用上"的表现。
"""

from __future__ import annotations

from ..config import GridLimits


class PowerLimit:
    """并网点功率限额。"""

    def __init__(self, limits: GridLimits) -> None:
        self._limits = limits

    @property
    def limits(self) -> GridLimits:
        return self._limits

    def clamp(self, power_kw: float) -> float:
        """按上网／用电限额钳位，返回钳位后的功率。"""

        value = float(power_kw)
        if value >= 0:
            return min(value, self._limits.export_limit_kw)
        return max(value, -self._limits.import_limit_kw)

    def headroom_kw(self, power_kw: float) -> float:
        """返回距对应方向限额还剩多少千瓦。"""

        value = float(power_kw)
        if value >= 0:
            return self._limits.export_limit_kw - value
        return self._limits.import_limit_kw + value

    def ratio(self, power_kw: float) -> float:
        """返回功率占对应方向限额的比例，用于降额合成。"""

        value = float(power_kw)
        if value == 0:
            return 1.0
        limit = self._limits.export_limit_kw if value > 0 else self._limits.import_limit_kw
        return max(0.0, min(1.0, abs(value) / limit))

    def as_dict(self) -> dict:
        return {
            "export_limit_kw": self._limits.export_limit_kw,
            "import_limit_kw": self._limits.import_limit_kw,
        }
