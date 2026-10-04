"""SOC 历史。

历史按固定长度保留，用于计算窗口内的漂移量与展示趋势。漂移量是"报告值
与估算值之差"的绝对值，超过容差就说明需要重新校准。
"""

from __future__ import annotations


class SocHistory:
    """SOC 采样历史。"""

    def __init__(self, limit: int = 512) -> None:
        self._entries: list[dict] = []
        self._limit = max(1, limit)

    def record(self, soc_pct: float, reported_pct: float, ts: float, epoch: int) -> dict:
        """记一条 SOC 采样，返回记录。"""

        entry = {
            "ts": round(float(ts), 3),
            "soc_pct": round(float(soc_pct), 3),
            "reported_pct": round(float(reported_pct), 3),
            "epoch": int(epoch),
        }
        self._entries.append(entry)
        if len(self._entries) > self._limit:
            del self._entries[: len(self._entries) - self._limit]
        return dict(entry)

    def series(self, limit: int = 60) -> list[dict]:
        """返回最近的若干条采样。"""

        return [dict(entry) for entry in self._entries[-limit:]]

    def latest(self) -> dict | None:
        """返回最近一条采样。"""

        return dict(self._entries[-1]) if self._entries else None

    def drift_pct(self) -> float:
        """返回最近一条采样的漂移绝对值。"""

        latest = self._entries[-1] if self._entries else None
        if latest is None:
            return 0.0
        return abs(latest["soc_pct"] - latest["reported_pct"])

    def count(self) -> int:
        """返回累计采样条数（受窗口上限约束）。"""

        return len(self._entries)
