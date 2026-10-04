"""审计汇总。

汇总按严重度、组件与动作三个维度计数，供控制台与交付自检核对"这一轮到底
发生过什么"。计数只统计内存窗口内的记录，跨重启的完整口径以落盘流水为准。
"""

from __future__ import annotations

from .record import AuditRecord


def summarize(records: list[AuditRecord]) -> dict:
    """把一批记录汇总成计数表。"""

    by_severity: dict[str, int] = {}
    by_component: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for record in records:
        by_severity[record.severity] = by_severity.get(record.severity, 0) + 1
        by_component[record.component] = by_component.get(record.component, 0) + 1
        by_action[record.action] = by_action.get(record.action, 0) + 1
    return {
        "total": len(records),
        "by_severity": dict(sorted(by_severity.items())),
        "by_component": dict(sorted(by_component.items())),
        "by_action": dict(sorted(by_action.items())),
        "alarms": sum(1 for record in records if record.is_alarm()),
    }
