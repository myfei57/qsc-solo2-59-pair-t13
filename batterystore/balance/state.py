"""均衡状态机。

均衡只有四档：``idle``、``running``、``complete``、``aborted``。充电放行只看
``complete``，因此均衡被中止或还没跑完时，充电请求会被联锁拒绝，不会出现
"低电压电芯没补平就开充"。
"""

from __future__ import annotations

import threading

STATES = ("idle", "running", "complete", "aborted")


class BalanceState:
    """带计数的均衡状态机。"""

    def __init__(self) -> None:
        self._state = "idle"
        self._runs = 0
        self._completions = 0
        self._aborts = 0
        self._history: list[dict] = []
        self._lock = threading.RLock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def transition(self, target: str, reason: str) -> str:
        """切换状态并记录迁移。"""

        if target not in STATES:
            raise ValueError(f"未知的均衡状态: {target}")
        with self._lock:
            previous = self._state
            self._state = target
            if target == "running":
                self._runs += 1
            elif target == "complete":
                self._completions += 1
            elif target == "aborted":
                self._aborts += 1
            self._history.append({"from": previous, "to": target, "reason": reason})
            return self._state

    def is_complete(self) -> bool:
        """均衡是否已完成。"""

        return self.state == "complete"

    def counts(self) -> dict:
        """返回运行、完成与中止计数。"""

        with self._lock:
            return {"runs": self._runs, "completions": self._completions, "aborts": self._aborts}

    def history(self, limit: int = 20) -> list[dict]:
        """返回最近的迁移记录。"""

        with self._lock:
            return [dict(item) for item in self._history[-limit:]]
