"""故障闩锁。

闩锁按簇独立保持：某簇确认过故障之后，即使采集值短暂回到正常，也必须在保持
时长内继续判故障；只有显式释放并再次通过就绪判据才允许恢复。代际在每次咬合
时加一，审计据此区分"同一故障的持续"与"又一次新故障"。
"""

from __future__ import annotations

import threading


class FaultLatch:
    """按簇保持的故障闩锁。"""

    def __init__(self, hold_s: float) -> None:
        if hold_s <= 0:
            raise ValueError("闩锁保持时长必须为正")
        self._hold_s = float(hold_s)
        self._entries: dict[str, dict] = {}
        self._lock = threading.RLock()

    @property
    def hold_s(self) -> float:
        return self._hold_s

    def engage(self, rack_id: str, code: str, now: float) -> dict:
        """咬合某簇的闩锁，返回闩锁记录。"""

        with self._lock:
            entry = self._entries.get(rack_id)
            if entry is None:
                entry = {"rack_id": rack_id, "code": code, "generation": 0, "stamped_at": float(now)}
                self._entries[rack_id] = entry
            entry["code"] = code
            entry["stamped_at"] = float(now)
            entry["generation"] += 1
            return dict(entry)

    def refresh(self, rack_id: str, now: float) -> dict | None:
        """在保持时长内继续刷新闩锁时间，返回刷新后的记录。"""

        with self._lock:
            entry = self._entries.get(rack_id)
            if entry is None:
                return None
            entry["stamped_at"] = float(now)
            return dict(entry)

    def held(self, rack_id: str, now: float) -> bool:
        """闩锁是否仍在保持。"""

        with self._lock:
            entry = self._entries.get(rack_id)
            if entry is None:
                return False
            return float(now) - entry["stamped_at"] <= self._hold_s

    def release(self, rack_id: str) -> bool:
        """释放某簇闩锁，返回是否确实释放过。"""

        with self._lock:
            return self._entries.pop(rack_id, None) is not None

    def generation(self, rack_id: str) -> int:
        """返回某簇闩锁代际，未咬合时为 0。"""

        with self._lock:
            entry = self._entries.get(rack_id)
            return int(entry["generation"]) if entry else 0

    def active(self, now: float) -> list[dict]:
        """返回仍在保持的闩锁记录。"""

        with self._lock:
            entries = [dict(item) for item in self._entries.values()]
        return [entry for entry in entries if float(now) - entry["stamped_at"] <= self._hold_s]

    def snapshot(self) -> dict:
        """返回全部闩锁记录，供状态页与审计读取。"""

        with self._lock:
            return {rack_id: dict(entry) for rack_id, entry in sorted(self._entries.items())}
