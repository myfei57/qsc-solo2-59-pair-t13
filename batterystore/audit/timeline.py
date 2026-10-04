"""时间线构造。

时间线把记录按时间升序铺开，并按电站过滤。消防联动与并离网切换这类多步
动作在时间线上是连续的一段，运维据此核对步骤先后是否符合联控链。
"""

from __future__ import annotations

from .record import AuditRecord


def build_timeline(records: list[AuditRecord], station: str | None = None) -> list[dict]:
    """把记录整理成时间线。"""

    selected = [record for record in records if station is None or record.station == station]
    selected.sort(key=lambda record: record.ts)
    return [
        {
            "ts": round(record.ts, 3),
            "component": record.component,
            "action": record.action,
            "severity": record.severity,
            "message": record.message,
            "op_id": record.op_id(),
        }
        for record in selected
    ]
