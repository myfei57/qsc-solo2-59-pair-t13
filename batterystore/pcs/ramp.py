"""功率爬坡限制。

PCS 输出不能阶跃：每个控制周期最多按 ``ramp_kw_per_s`` 靠近目标值一步。
爬坡器记录步数与累计爬坡量，审计据此核对"先钳位后爬坡"的顺序是否成立。
"""

from __future__ import annotations


class RampLimiter:
    """按速率限制逼近目标功率。"""

    def __init__(self, ramp_kw_per_s: float) -> None:
        if ramp_kw_per_s <= 0:
            raise ValueError("爬坡速率必须为正")
        self._rate = float(ramp_kw_per_s)
        self._current_kw = 0.0
        self._steps = 0
        self._traveled_kw = 0.0

    @property
    def rate(self) -> float:
        return self._rate

    def step(self, target_kw: float, dt: float) -> float:
        """推进一个步长，返回爬坡后的功率。"""

        if dt <= 0:
            raise ValueError("步长必须为正")
        target = float(target_kw)
        budget = self._rate * float(dt)
        delta = target - self._current_kw
        if abs(delta) <= budget:
            self._current_kw = target
            self._traveled_kw += abs(delta)
        else:
            self._current_kw += budget if delta > 0 else -budget
            self._traveled_kw += budget
        self._steps += 1
        return self._current_kw

    def current(self) -> float:
        """返回当前功率。"""

        return self._current_kw

    def steps_taken(self) -> int:
        """返回累计爬坡步数。"""

        return self._steps

    def traveled_kw(self) -> float:
        """返回累计爬坡量。"""

        return self._traveled_kw

    def reset(self) -> float:
        """把功率归零，返回归零前的值。"""

        previous = self._current_kw
        self._current_kw = 0.0
        return previous
