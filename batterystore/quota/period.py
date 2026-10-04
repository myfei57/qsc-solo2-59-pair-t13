"""记账周期。

配额按固定小时数滚动。周期键变化时清零本周期累计量并保留一段历史，跨周期
的充放电不会互相污染，控制台也能回看前几个周期的用量。
"""

from __future__ import annotations


class PeriodTracker:
    """周期键跟踪器。"""

    def __init__(self, period_hours: float) -> None:
        if period_hours <= 0:
            raise ValueError("周期长度必须为正")
        self._period_hours = float(period_hours)
        self._key = ""
        self._rolls = 0
        self._history: list[dict] = []

    @property
    def period_hours(self) -> float:
        return self._period_hours

    def key_for(self, now: float) -> str:
        """按时间戳算出所属周期键。"""

        index = int(float(now) // (self._period_hours * 3600.0))
        return f"p{index:06d}"

    def current(self) -> str:
        """返回当前周期键。"""

        return self._key

    def switch(self, now: float, totals: dict) -> dict:
        """在周期变化时滚动一次，返回滚动结果。"""

        candidate = self.key_for(now)
        if candidate == self._key:
            return {"rolled": False, "key": self._key, "previous": None}
        previous = self._key or None
        if previous is not None:
            self._history.append({"key": previous, **{key: totals.get(key, 0.0) for key in ("charge_kwh", "discharge_kwh")}})
            self._rolls += 1
        self._key = candidate
        return {"rolled": previous is not None, "key": self._key, "previous": previous}

    def rolls(self) -> int:
        """返回滚动次数。"""

        return self._rolls

    def history(self) -> list[dict]:
        """返回历史周期用量。"""

        return [dict(item) for item in self._history]
