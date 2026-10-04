"""并网点频率监视。

频率超出窗口即判并网条件不成立，控制台按最近样本展示偏差。监视窗口只保留
有限个样本，长期运行不会无限占用内存。
"""

from __future__ import annotations

from ..config import GridLimits


class FrequencyMonitor:
    """频率采样与窗口判定。"""

    def __init__(self, limits: GridLimits, limit: int = 240) -> None:
        self._limits = limits
        self._limit = max(1, limit)
        self._samples: list[dict] = []
        self._out_of_band = 0

    @property
    def limits(self) -> GridLimits:
        return self._limits

    def sample(self, frequency_hz: float, now: float) -> dict:
        """记一次频率采样，返回本次判定结果。"""

        value = float(frequency_hz)
        ok = self._limits.frequency_ok(value)
        if not ok:
            self._out_of_band += 1
        entry = {
            "ts": round(float(now), 3),
            "frequency_hz": round(value, 4),
            "deviation_hz": round(value - self._limits.rated_frequency_hz, 4),
            "ok": ok,
        }
        self._samples.append(entry)
        if len(self._samples) > self._limit:
            del self._samples[: len(self._samples) - self._limit]
        return dict(entry)

    def last(self) -> dict | None:
        """返回最近一次采样。"""

        return dict(self._samples[-1]) if self._samples else None

    def samples(self, limit: int = 60) -> list[dict]:
        """返回最近的若干采样。"""

        return [dict(item) for item in self._samples[-limit:]]

    def out_of_band(self) -> int:
        """返回超窗次数。"""

        return self._out_of_band

    def snapshot(self) -> dict:
        """返回频率监视摘要。"""

        return {
            "rated_frequency_hz": self._limits.rated_frequency_hz,
            "band_hz": self._limits.frequency_band_hz,
            "samples": len(self._samples),
            "out_of_band": self._out_of_band,
            "last": self.last(),
        }
