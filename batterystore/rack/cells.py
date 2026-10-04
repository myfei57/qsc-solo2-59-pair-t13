"""单体电芯。

电芯同时带"出厂额定值"和"当前额定值"：更换电芯后当前额定值会被改写，温控
降额基线必须跟着刷新，否则正常工况会被旧额定值判成高温。额定值参与压差
计算，任何压差判据都以当前额定值为基准。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Cell:
    """一颗单体电芯。"""

    cell_id: str
    nominal_v: float
    rating_v: float
    voltage_v: float
    temperature_c: float = 25.0
    soc_pct: float = 50.0
    cycles: int = 0

    def __post_init__(self) -> None:
        if self.rating_v <= 0:
            raise ValueError("额定电压必须为正")

    def delta_mv(self) -> float:
        """相对当前额定值的偏置（毫伏）。"""

        return (self.voltage_v - self.rating_v) * 1000.0

    def headroom_mv(self, v_max: float) -> float:
        """距单体电压上限还剩多少毫伏。"""

        return (float(v_max) - self.voltage_v) * 1000.0

    def apply_rating(self, rating_v: float) -> float:
        """更新额定值，返回被替换掉的旧额定值。"""

        if rating_v <= 0:
            raise ValueError("额定电压必须为正")
        previous = self.rating_v
        self.rating_v = float(rating_v)
        return previous

    def update(self, voltage_v: float | None = None, temperature_c: float | None = None) -> None:
        """按采集值更新电压与温度。"""

        if voltage_v is not None:
            self.voltage_v = float(voltage_v)
        if temperature_c is not None:
            self.temperature_c = float(temperature_c)

    def as_dict(self) -> dict:
        return {
            "cell_id": self.cell_id,
            "rating_v": round(self.rating_v, 4),
            "voltage_v": round(self.voltage_v, 4),
            "temperature_c": round(self.temperature_c, 2),
            "soc_pct": round(self.soc_pct, 2),
            "delta_mv": round(self.delta_mv(), 2),
            "cycles": self.cycles,
        }
