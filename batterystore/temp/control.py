"""冷却单元。

冷却只在温度越过降额起点时启动，按固定速率把温度拉回；冷却本身也按控制
周期推进，这样"降额了但没开冷却"能在审计里一眼看出来。
"""

from __future__ import annotations


class Cooler:
    """液冷机组。"""

    def __init__(self, cool_rate_c_per_s: float) -> None:
        if cool_rate_c_per_s < 0:
            raise ValueError("冷却速率不能为负")
        self._rate = float(cool_rate_c_per_s)
        self._running = False
        self._ticks = 0
        self._removed_c = 0.0

    @property
    def rate(self) -> float:
        return self._rate

    def start(self) -> bool:
        """启动冷却，返回运行状态。"""

        self._running = True
        return self._running

    def stop(self) -> bool:
        """停止冷却，返回运行状态。"""

        self._running = False
        return self._running

    def is_running(self) -> bool:
        """冷却是否在运行。"""

        return self._running

    def tick(self, dt: float, temperature_c: float) -> float:
        """推进一个冷却步长，返回冷却后的温度。"""

        if dt <= 0:
            raise ValueError("步长必须为正")
        self._ticks += 1
        if not self._running:
            return float(temperature_c)
        drop = self._rate * float(dt)
        cooled = float(temperature_c) - drop
        self._removed_c += drop
        return cooled

    def ticks(self) -> int:
        """返回累计冷却步数。"""

        return self._ticks

    def removed_c(self) -> float:
        """返回累计移除的热量（摄氏度）。"""

        return self._removed_c
