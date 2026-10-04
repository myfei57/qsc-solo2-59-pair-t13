"""审计查询。

控制台按组件、严重度与动作过滤流水。过滤集中在一次实现里，避免每个页面
各写一套筛选条件导致同一份数据在不同页面显示不一致。
"""

from __future__ import annotations

from .record import AuditRecord


def query_entries(
    records: list[AuditRecord],
    *,
    component: str | None = None,
    severity: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """按条件过滤审计记录，返回最近的若干条（最新在前）。"""

    selected = [
        record
        for record in records
        if (component is None or record.component == component)
        and (severity is None or record.severity == severity)
        and (action is None or record.action == action)
    ]
    selected.sort(key=lambda record: record.ts)
    return [record.as_dict() for record in reversed(selected[-limit:])]
