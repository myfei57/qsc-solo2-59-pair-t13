"""BMS 运行状态。

状态只有五档：``offline``（未上电）、``standby``（上电但未满足就绪）、
``ready``（满足全部并网前置）、``derated``（就绪但被温控或配额限制）、
``fault``（有闩锁故障）。控制台按这一档位选择颜色，联锁按这一档位放行动作。
"""

from __future__ import annotations

STATES = ("offline", "standby", "ready", "derated", "fault")


class BmsStatus:
    """带计数的 BMS 状态机。"""

    def __init__(self) -> None:
        self._state = "offline"
        self._checks = 0
        self._passes = 0
        self._derates = 0
        self._faults = 0
        self._transitions: list[dict] = []

    @property
    def state(self) -> str:
        return self._state

    def counts(self) -> dict:
        """返回各类计数。"""

        return {
            "checks": self._checks,
            "passes": self._passes,
            "derates": self._derates,
            "faults": self._faults,
            "transitions": len(self._transitions),
        }

    def transition(self, state: str, reason: str) -> str:
        """切换状态并记录一次迁移。"""

        if state not in STATES:
            raise ValueError(f"未知的 BMS 状态: {state}")
        previous = self._state
        self._state = state
        if state == "fault":
            self._faults += 1
        elif state == "derated":
            self._derates += 1
        self._transitions.append({"from": previous, "to": state, "reason": reason})
        return state

    def note_check(self, passed: bool) -> None:
        """记录一次就绪核对结果。"""

        self._checks += 1
        if passed:
            self._passes += 1

    def history(self, limit: int = 20) -> list[dict]:
        """返回最近的状态迁移。"""

        return [dict(item) for item in self._transitions[-limit:]]
