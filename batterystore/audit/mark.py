"""操作边界索引。

一次并离网切换、一次消防联动会留下十几条流水，巡检关心的是"这次操作从哪到
哪、花了多久"。这里按 ``op_id`` 把记录归并成操作区间，缺 ``op_id`` 的记录
归入一次独立的循环动作。
"""

from __future__ import annotations

from .record import AuditRecord

LOOSE = "cycle"


def index_operations(records: list[AuditRecord], limit: int = 20) -> list[dict]:
    """按操作标识归并记录，返回最近若干次操作区间。"""

    buckets: dict[str, dict] = {}
    for record in records:
        key = record.op_id() or LOOSE
        bucket = buckets.setdefault(key, {"op_id": key, "first_ts": record.ts, "last_ts": record.ts, "count": 0, "components": set(), "actions": []})
        bucket["first_ts"] = min(bucket["first_ts"], record.ts)
        bucket["last_ts"] = max(bucket["last_ts"], record.ts)
        bucket["count"] += 1
        bucket["components"].add(record.component)
        bucket["actions"].append(record.action)
    ordered = sorted(buckets.values(), key=lambda item: item["last_ts"], reverse=True)[:limit]
    return [
        {
            "op_id": item["op_id"],
            "first_ts": round(item["first_ts"], 3),
            "last_ts": round(item["last_ts"], 3),
            "span_s": round(item["last_ts"] - item["first_ts"], 3),
            "count": item["count"],
            "components": sorted(item["components"]),
            "actions": item["actions"],
        }
        for item in ordered
    ]
