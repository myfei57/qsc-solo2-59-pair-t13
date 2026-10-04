"""PCS 保护判据。

过流与过功率是两条独立的保护线。判据只返回越限项名称，动作由编排决定，
这样同一份判据既可用于周期巡检，也可用于切换前的最后一道核对。
"""

from __future__ import annotations

from ..config import PcsLimits


class PcsProtection:
    """PCS 保护判据。"""

    def __init__(self, limits: PcsLimits) -> None:
        self._limits = limits
        self._trips = 0

    @property
    def limits(self) -> PcsLimits:
        return self._limits

    def check(self, current_a: float, power_kw: float) -> list[str]:
        """返回当前工况下的越限项。"""

        violations: list[str] = []
        if abs(float(current_a)) >= self._limits.protection_current_a:
            violations.append("over_current")
        if abs(float(power_kw)) > self._limits.max_power_kw:
            violations.append("over_power")
        return violations

    def note_trip(self) -> int:
        """记录一次保护动作，返回累计次数。"""

        self._trips += 1
        return self._trips

    def trips(self) -> int:
        """返回累计保护动作次数。"""

        return self._trips
