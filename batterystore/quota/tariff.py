"""峰谷电价。

按当天小时数区分峰谷段：白天按峰价、夜间按谷价。结算与配额展示用同一份
电价表，避免两处各写一套时段。
"""

from __future__ import annotations

from ..config import QuotaLimits

PEAK_START_HOUR = 8
PEAK_END_HOUR = 22


class Tariff:
    """峰谷电价表。"""

    def __init__(self, limits: QuotaLimits) -> None:
        self._limits = limits

    @property
    def limits(self) -> QuotaLimits:
        return self._limits

    def kind(self, now: float) -> str:
        """返回当前时段名。"""

        hour = int((float(now) % 86400.0) // 3600)
        return "peak" if PEAK_START_HOUR <= hour < PEAK_END_HOUR else "valley"

    def rate(self, now: float) -> float:
        """返回当前时段电价。"""

        if self.kind(now) == "peak":
            return self._limits.tariff_peak
        return self._limits.tariff_valley

    def as_dict(self) -> dict:
        return {
            "peak": self._limits.tariff_peak,
            "valley": self._limits.tariff_valley,
            "peak_window": [PEAK_START_HOUR, PEAK_END_HOUR],
        }
