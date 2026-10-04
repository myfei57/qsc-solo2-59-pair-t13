"""并离网开关本体。

接触器只有闭合与分断两态，切换次数用于保养提示。切换本体不关心顺序，
顺序由编排决定：必须先拿到 BMS 就绪确认才允许闭合。
"""

from __future__ import annotations


class TransferSwitch:
    """并网点接触器。"""

    def __init__(self) -> None:
        self._closed = False
        self._cycles = 0
        self._last_action = "init"

    def close(self) -> bool:
        """闭合接触器。"""

        if self._closed:
            raise ValueError("接触器已经闭合")
        self._closed = True
        self._cycles += 1
        self._last_action = "close"
        return self._closed

    def open(self) -> bool:
        """分断接触器。"""

        if not self._closed:
            raise ValueError("接触器已经分断")
        self._closed = False
        self._last_action = "open"
        return self._closed

    def is_closed(self) -> bool:
        """接触器是否闭合。"""

        return self._closed

    def cycles(self) -> int:
        """返回累计切换次数。"""

        return self._cycles

    def last_action(self) -> str:
        """返回最近一次动作名。"""

        return self._last_action

    def as_dict(self) -> dict:
        return {"closed": self._closed, "cycles": self._cycles, "last_action": self._last_action}
