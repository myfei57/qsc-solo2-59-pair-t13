"""联动阶段记录。

消防联动按固定阶段推进：探测 → 开阀 → 开阀确认 → 断 PCS → 审计。阶段记录
保留真实顺序，任何一步没走到就中断，审计里能直接看出卡在哪一步。
"""

from __future__ import annotations

ORDER = ("detect", "valve_open", "valve_confirmed", "pcs_trip", "audit")


class SuppressionStage:
    """联动阶段流水。"""

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def enter(self, stage: str, detail: dict | None = None) -> dict:
        """记录进入某阶段。"""

        if stage not in ORDER:
            raise ValueError(f"未知的联动阶段: {stage}")
        entry = {"stage": stage, "index": ORDER.index(stage), "detail": dict(detail or {})}
        self._entries.append(entry)
        return entry

    def sequence(self) -> list[str]:
        """返回已进入的阶段名序列。"""

        return [entry["stage"] for entry in self._entries]

    def has(self, stage: str) -> bool:
        """某阶段是否已进入。"""

        return any(entry["stage"] == stage for entry in self._entries)

    def completed(self) -> bool:
        """是否走完全部阶段。"""

        return all(self.has(stage) for stage in ORDER)

    def violations(self) -> list[str]:
        """返回顺序错误：后进入的阶段必须排在先进入阶段之后。"""

        indices = [entry["index"] for entry in self._entries]
        return ["stage_out_of_order"] if indices != sorted(indices) else []

    def entries(self) -> list[dict]:
        """返回阶段流水。"""

        return [dict(entry) for entry in self._entries]
