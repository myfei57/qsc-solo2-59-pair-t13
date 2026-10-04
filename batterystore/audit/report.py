"""审计报告。

报告在汇总之外补上时间跨度与最活跃组件：运维先看汇总判断性质，再看跨度判断
是不是同一次操作留下的连续记录。
"""

from __future__ import annotations

from .record import AuditRecord
from .summary import summarize


def build_report(records: list[AuditRecord], recent: int = 20) -> dict:
    """生成审计报告。"""

    summary = summarize(records)
    if not records:
        return {**summary, "first_ts": None, "last_ts": None, "span_s": 0.0, "busiest": "", "tail": []}
    stamps = [record.ts for record in records]
    by_component = summary["by_component"]
    busiest = max(by_component, key=lambda name: by_component[name]) if by_component else ""
    return {
        **summary,
        "first_ts": round(min(stamps), 3),
        "last_ts": round(max(stamps), 3),
        "span_s": round(max(stamps) - min(stamps), 3),
        "busiest": busiest,
        "tail": [record.as_dict() for record in records[-recent:]],
    }
