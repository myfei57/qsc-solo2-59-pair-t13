"""PCS 状态机。

所有迁移都在同一把可重入锁内完成：并发指令下两个协程各自读改写状态是"既并网
又离网"的直接来源。每次迁移代际加一，历史保留最近若干条，审计据此核对
切换与 BMS 就绪位的先后。
"""

from __future__ import annotations

import threading

from .mode import ModeTable


class PcsState:
    """带锁与代际的 PCS 状态机。"""

    def __init__(self, table: ModeTable | None = None) -> None:
        self._table = table or ModeTable()
        self._state = "stopped"
        self._generation = 0
        self._history: list[dict] = []
        self._lock = threading.RLock()

    @property
    def table(self) -> ModeTable:
        return self._table

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def generation(self) -> int:
        """返回迁移代际。"""

        with self._lock:
            return self._generation

    def transition(self, target: str, reason: str) -> str:
        """在锁内完成一次迁移。"""

        with self._lock:
            source = self._state
            self._table.require(source, target)
            self._state = target
            self._generation += 1
            self._history.append({"from": source, "to": target, "reason": reason, "generation": self._generation})
            return self._state

    def force(self, target: str, reason: str) -> str:
        """保护动作强制进入某档，不校验迁移表。"""

        with self._lock:
            source = self._state
            self._state = target
            self._generation += 1
            self._history.append({"from": source, "to": target, "reason": reason, "generation": self._generation})
            return self._state

    def history(self, limit: int = 20) -> list[dict]:
        """返回最近的迁移记录。"""

        with self._lock:
            return [dict(item) for item in self._history[-limit:]]

    def is_tied(self) -> bool:
        """是否处于并网态。"""

        return self.state == "grid_tie"
