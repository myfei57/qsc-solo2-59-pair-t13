"""SOC 校准记录。

每次 BMS 校准都生成一代记录：校准值、时刻与代际。SOC 估算必须按最新一代算，
拿旧一代的偏移继续折算会出现"实际剩 30% 却显示 45%"这类偏差；代际与有效期
一起记录，估算侧才能判断当前值是否还可用。
"""

from __future__ import annotations

import threading


class Calibration:
    """带代际与有效期的 SOC 校准记录。"""

    def __init__(self, ttl_s: float, initial_soc_pct: float) -> None:
        self._ttl_s = float(ttl_s)
        self._soc_pct = float(initial_soc_pct)
        self._epoch = 0
        self._stamped_at = 0.0
        self._history: list[dict] = []
        self._lock = threading.RLock()

    @property
    def epoch(self) -> int:
        """返回当前校准代际。"""

        with self._lock:
            return self._epoch

    def record(self, soc_pct: float, now: float, source: str) -> dict:
        """登记一次校准，返回校准记录。"""

        with self._lock:
            previous = self._soc_pct
            self._soc_pct = float(soc_pct)
            self._stamped_at = float(now)
            self._epoch += 1
            entry = {
                "epoch": self._epoch,
                "soc_pct": round(self._soc_pct, 3),
                "previous_soc_pct": round(previous, 3),
                "stamped_at": round(self._stamped_at, 3),
                "source": source,
            }
            self._history.append(entry)
            return dict(entry)

    def latest(self, now: float) -> dict:
        """返回最新一代校准及其是否仍在有效期。"""

        with self._lock:
            return {
                "epoch": self._epoch,
                "soc_pct": round(self._soc_pct, 3),
                "stamped_at": round(self._stamped_at, 3),
                "age_s": round(max(0.0, float(now) - self._stamped_at), 2),
                "expired": self._expired(now),
            }

    def _expired(self, now: float) -> bool:
        return max(0.0, float(now) - self._stamped_at) > self._ttl_s

    def history(self, limit: int = 20) -> list[dict]:
        """返回最近若干次校准。"""

        with self._lock:
            return [dict(item) for item in self._history[-limit:]]
