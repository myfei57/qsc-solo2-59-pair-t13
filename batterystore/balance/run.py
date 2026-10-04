"""均衡脉冲节拍。

均衡按"放电脉冲 + 静置"交替推进：脉冲段给被选中的单体放电，静置段让电压
回落。持续时长超过上限即判中止，避免一个压差始终不收敛的簇把均衡跑到失控。
"""

from __future__ import annotations

from ..config import BalanceLimits


class BalanceRun:
    """一次均衡运行的节拍器。"""

    def __init__(self, limits: BalanceLimits) -> None:
        self._limits = limits
        self._targets: list[str] = []
        self._elapsed_s = 0.0
        self._pulses = 0
        self._phase = "idle"

    @property
    def limits(self) -> BalanceLimits:
        return self._limits

    def begin(self, targets: list[str]) -> list[str]:
        """开始一次运行，返回本次的目标清单。"""

        self._targets = sorted(targets)
        self._elapsed_s = 0.0
        self._pulses = 0
        self._phase = "pulse" if self._targets else "idle"
        return list(self._targets)

    def targets(self) -> list[str]:
        """返回本次运行的目标单体。"""

        return list(self._targets)

    def advance(self, dt: float) -> str:
        """推进一个节拍，返回当前相位。"""

        if dt <= 0:
            raise ValueError("步长必须为正")
        self._elapsed_s += float(dt)
        if self._phase == "pulse":
            self._pulses += 1
            self._phase = "rest"
        elif self._phase == "rest":
            self._phase = "pulse"
        return self._phase

    def phase(self) -> str:
        """返回当前相位。"""

        return self._phase

    def elapsed_s(self) -> float:
        """返回已运行时长。"""

        return self._elapsed_s

    def pulses(self) -> int:
        """返回已执行脉冲数。"""

        return self._pulses

    def overrun(self) -> bool:
        """是否超过时长上限。"""

        return self._elapsed_s > self._limits.max_duration_s

    def summary(self) -> dict:
        """返回本次运行摘要。"""

        return {
            "targets": len(self._targets),
            "pulses": self._pulses,
            "cycle_s": self._limits.cycle_s,
            "elapsed_s": round(self._elapsed_s, 2),
            "phase": self._phase,
            "overrun": self.overrun(),
        }
