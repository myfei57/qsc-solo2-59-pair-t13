"""效率曲线。

效率随负载率变化，轻载效率明显偏低。曲线用折线插值，控制台展示的"发出多少
电"与配额记账都用它折算，避免两处各写一个常数。
"""

from __future__ import annotations

from ..config import PcsLimits


class EfficiencyCurve:
    """按负载率插值的效率曲线。"""

    def __init__(self, points: list[tuple[float, float]]) -> None:
        if len(points) < 2:
            raise ValueError("效率曲线至少需要两个点")
        self._points = sorted((float(load), float(value)) for load, value in points)

    @classmethod
    def from_limits(cls, limits: PcsLimits) -> "EfficiencyCurve":
        """按 PCS 限额构造默认曲线。"""

        peak = limits.efficiency
        return cls([(0.0, peak * 0.72), (0.2, peak * 0.93), (0.5, peak), (1.0, peak * 0.98)])

    def at(self, load_ratio: float) -> float:
        """按负载率插值取效率。"""

        ratio = max(0.0, min(1.0, float(load_ratio)))
        previous_load, previous_value = self._points[0]
        if ratio <= previous_load:
            return previous_value
        for load, value in self._points[1:]:
            if ratio <= load:
                span = load - previous_load
                if span <= 0:
                    return value
                weight = (ratio - previous_load) / span
                return previous_value + (value - previous_value) * weight
            previous_load, previous_value = load, value
        return self._points[-1][1]

    def points(self) -> list[dict]:
        """返回曲线控制点。"""

        return [{"load": load, "efficiency": value} for load, value in self._points]
