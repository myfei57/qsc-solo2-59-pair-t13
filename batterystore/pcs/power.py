"""功率输出。

功率控制器只做三件事：接受功率指令、按降额系数折算实际输出、按效率折算
上网电量。无功固定按容量比例给出，供并网点展示。
"""

from __future__ import annotations

from .curve import EfficiencyCurve


class PowerController:
    """有功／无功功率控制。"""

    def __init__(self, max_power_kw: float, curve: EfficiencyCurve) -> None:
        self._max_power_kw = float(max_power_kw)
        self._curve = curve
        self._power_kw = 0.0
        self._ratio = 1.0
        self._commands = 0

    @property
    def max_power_kw(self) -> float:
        return self._max_power_kw

    def command(self, power_kw: float) -> float:
        """接受一次功率指令，返回生效前的值。"""

        previous = self._power_kw
        self._power_kw = float(power_kw)
        self._commands += 1
        return previous

    def with_derate(self, ratio: float) -> float:
        """更新降额系数，返回生效后的系数。"""

        self._ratio = max(0.0, min(1.0, float(ratio)))
        return self._ratio

    def output_kw(self) -> float:
        """返回降额后的输出功率。"""

        return self._power_kw * self._ratio

    def load_ratio(self) -> float:
        """返回负载率。"""

        if self._max_power_kw <= 0:
            return 0.0
        return min(1.0, abs(self.output_kw()) / self._max_power_kw)

    def efficiency(self) -> float:
        """返回当前负载率下的效率。"""

        return self._curve.at(self.load_ratio())

    def delivered_kw(self) -> float:
        """返回折算效率后的实际输出功率。"""

        return self.output_kw() * self.efficiency()

    def reactive_kvar(self) -> float:
        """按容量比例返回无功功率。"""

        return self.output_kw() * 0.1

    def commands(self) -> int:
        """返回累计指令条数。"""

        return self._commands
