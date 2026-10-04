"""分区探测。

每个消防分区独立布置烟感与温感，任一越线即判该分区火情。探测结果按分区
汇总，联动编排只需要知道"哪些分区起火了"，不必逐个读传感器。
"""

from __future__ import annotations

from ..config import FireLimits


class ZoneDetectors:
    """分区烟温探测器组。"""

    def __init__(self, zones: list[str]) -> None:
        if not zones:
            raise ValueError("至少需要一个消防分区")
        self._readings: dict[str, dict] = {
            zone: {"smoke_ppm": 0.0, "temperature_c": 25.0} for zone in zones
        }

    def zones(self) -> list[str]:
        """返回全部分区名。"""

        return sorted(self._readings)

    def update(self, zone: str, smoke_ppm: float, temperature_c: float) -> dict:
        """写入某分区的烟感与温感读数。"""

        if zone not in self._readings:
            raise KeyError(f"未登记的分区: {zone}")
        self._readings[zone] = {"smoke_ppm": float(smoke_ppm), "temperature_c": float(temperature_c)}
        return dict(self._readings[zone])

    def detections(self, limits: FireLimits) -> list[str]:
        """返回越线的分区清单。"""

        return [
            zone
            for zone in self.zones()
            if limits.detected(self._readings[zone]["smoke_ppm"], self._readings[zone]["temperature_c"])
        ]

    def snapshot(self) -> dict:
        """返回各分区当前读数。"""

        return {zone: dict(reading) for zone, reading in sorted(self._readings.items())}
