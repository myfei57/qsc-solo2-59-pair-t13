"""电量流向累计。

充放电按周期累计上网与用电电量，配额记账直接读这里的数，避免结算与配电
各算一套。累计量按方向分开，任何一次控制周期推进都不会把方向弄反。
"""

from __future__ import annotations


class PowerFlow:
    """上网／用电电量累计器。"""

    def __init__(self) -> None:
        self._import_kwh = 0.0
        self._export_kwh = 0.0
        self._intervals = 0

    def charge(self, power_kw: float, dt: float) -> float:
        """记录一段充电（用电）电量，返回本段电量。"""

        energy = abs(float(power_kw)) * float(dt) / 3600.0
        self._import_kwh += energy
        self._intervals += 1
        return energy

    def discharge(self, power_kw: float, dt: float) -> float:
        """记录一段放电（上网）电量，返回本段电量。"""

        energy = abs(float(power_kw)) * float(dt) / 3600.0
        self._export_kwh += energy
        self._intervals += 1
        return energy

    def totals(self) -> dict:
        """返回累计电量。"""

        return {
            "import_kwh": round(self._import_kwh, 6),
            "export_kwh": round(self._export_kwh, 6),
            "net_kwh": round(self._export_kwh - self._import_kwh, 6),
            "intervals": self._intervals,
        }

    def reset(self) -> dict:
        """清零累计量，返回清零前的值。"""

        previous = self.totals()
        self._import_kwh = 0.0
        self._export_kwh = 0.0
        self._intervals = 0
        return previous
