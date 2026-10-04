"""PCS 停机与跳闸。

跳闸是一次性动作：一旦跳闸，必须先复位才能重新并网。跳闸原因按发生顺序保留，
消防联动与保护动作都会走这里，避免两处各写一套停机逻辑。
"""

from __future__ import annotations


class CutOff:
    """停机／跳闸记录器。"""

    def __init__(self) -> None:
        self._tripped = False
        self._reasons: list[str] = []
        self._resets = 0

    def trip(self, reason: str) -> bool:
        """执行跳闸，返回跳闸后的状态。"""

        if not reason:
            raise ValueError("跳闸原因不能为空")
        self._tripped = True
        self._reasons.append(reason)
        return self._tripped

    def clear(self) -> bool:
        """复位跳闸，返回复位前的状态。"""

        previous = self._tripped
        self._tripped = False
        if previous:
            self._resets += 1
        return previous

    def is_tripped(self) -> bool:
        """是否处于跳闸态。"""

        return self._tripped

    def reasons(self) -> list[str]:
        """返回全部跳闸原因。"""

        return list(self._reasons)

    def resets(self) -> int:
        """返回累计复位次数。"""

        return self._resets
