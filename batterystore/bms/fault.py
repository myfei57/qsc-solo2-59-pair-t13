"""并发故障上报。

多簇同时上报故障时必须走同一把锁：每簇各自累计确认轮次，达到 ``confirm_rounds``
才咬合闩锁。没有这把锁时，两个协程各自读改写同一份计数会互相覆盖，表现就是
"其中一簇被确认后另一簇还挂着"——漏掉的那一簇不会降功率。
"""

from __future__ import annotations

import threading

from .latch import FaultLatch


class FaultRegistry:
    """带确认轮次的并发故障登记表。"""

    def __init__(self, latch: FaultLatch, confirm_rounds: int = 2) -> None:
        if confirm_rounds < 1:
            raise ValueError("确认轮次必须为正")
        self._latch = latch
        self._confirm_rounds = confirm_rounds
        self._counts: dict[str, int] = {}
        self._last_code: dict[str, str] = {}
        self._reports = 0
        self._lock = threading.RLock()

    @property
    def confirm_rounds(self) -> int:
        return self._confirm_rounds

    def report(self, rack_id: str, code: str, now: float) -> dict:
        """登记一次故障上报，返回该簇当前的确认进度与闩锁状态。"""

        with self._lock:
            self._reports += 1
            count = self._counts.get(rack_id, 0) + 1
            self._counts[rack_id] = count
            self._last_code[rack_id] = code
            latched = count >= self._confirm_rounds
            if latched:
                self._latch.engage(rack_id, code, now)
            else:
                self._latch.refresh(rack_id, now)
            return {
                "rack_id": rack_id,
                "code": code,
                "count": count,
                "required": self._confirm_rounds,
                "latched": latched,
            }

    def clear(self, rack_id: str) -> bool:
        """清掉某簇的确认计数并释放闩锁。"""

        with self._lock:
            self._counts.pop(rack_id, None)
            self._last_code.pop(rack_id, None)
            return self._latch.release(rack_id)

    def pending(self) -> list[dict]:
        """返回尚未达到确认轮次的簇。"""

        with self._lock:
            return [
                {"rack_id": rack_id, "count": count, "required": self._confirm_rounds, "code": self._last_code.get(rack_id, "")}
                for rack_id, count in sorted(self._counts.items())
                if count < self._confirm_rounds
            ]

    def counter(self, rack_id: str) -> int:
        """返回某簇累计确认轮次。"""

        with self._lock:
            return self._counts.get(rack_id, 0)

    def total_reports(self) -> int:
        """返回累计上报条数。"""

        with self._lock:
            return self._reports
