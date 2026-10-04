"""灭火介质阀。

开阀不是瞬时动作：发出指令后要经过确认时长，行程到位才算开阀成功。联动
顺序要求"先开阀确认成功，再断 PCS"——开阀失败就停下，不继续落停，避免
电池还在放电而灭火介质没到位。
"""

from __future__ import annotations

from ..errors import FireError


class SuppressionValve:
    """灭火介质控制阀。"""

    def __init__(self, travel_mm: float, confirm_s: float) -> None:
        if travel_mm <= 0:
            raise ValueError("阀行程必须为正")
        self._travel_mm = float(travel_mm)
        self._confirm_s = float(confirm_s)
        self._commanded = False
        self._opened_at = 0.0
        self._confirmed = False
        self._cycles = 0

    @property
    def confirm_s(self) -> float:
        return self._confirm_s

    def open(self, now: float) -> dict:
        """发出开阀指令，返回指令记录。"""

        if self._commanded:
            raise FireError("灭火阀已处于开阀流程", component="fire")
        self._commanded = True
        self._opened_at = float(now)
        self._confirmed = False
        self._cycles += 1
        return {"commanded": True, "opened_at": round(self._opened_at, 3), "cycles": self._cycles}

    def confirm(self, now: float) -> bool:
        """核对开阀是否到位，返回是否确认成功。"""

        if not self.is_commanded():
            return False
        self._confirmed = (float(now) - self._opened_at) >= self._confirm_s
        return self._confirmed

    def is_commanded(self) -> bool:
        """是否已发出开阀指令。"""

        return self._commanded

    def is_confirmed(self) -> bool:
        """开阀是否已确认成功。"""

        return self._confirmed

    def travel_mm(self) -> float:
        """返回当前阀行程。"""

        return self._travel_mm if self._confirmed else 0.0

    def cycles(self) -> int:
        """返回累计开阀次数。"""

        return self._cycles

    def close(self) -> bool:
        """关阀并复位确认状态，返回是否曾经开过阀。"""

        was_open = self._commanded
        self._commanded = False
        self._confirmed = False
        return was_open

    def as_dict(self) -> dict:
        return {
            "commanded": self._commanded,
            "confirmed": self._confirmed,
            "travel_mm": round(self.travel_mm(), 2),
            "cycles": self._cycles,
        }
