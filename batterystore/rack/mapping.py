"""簇编号映射。

现场重编号后，历史告警里的旧编号必须能解析到当前簇：映射按代际保存，
每重编号一次代际加一。告警路由取"最新代际"的标签；只有需要复现历史现场时
才按代际回查，这样运维按当前编号就能找到真正过温的那一簇。
"""

from __future__ import annotations

from ..errors import NamespaceError


class RackMapping:
    """簇标识 → 现场编号的代际映射。"""

    def __init__(self) -> None:
        self._labels: dict[str, str] = {}
        self._zones: dict[str, str] = {}
        self._history: list[dict] = []
        self._epoch = 0

    @property
    def epoch(self) -> int:
        """返回当前代际。"""

        return self._epoch

    def assign(self, rack_id: str, label: str, zone: str) -> dict:
        """登记或重编一簇，返回本次变更记录。"""

        if not rack_id or not label or not zone:
            raise NamespaceError("簇标识、编号与消防分区都不能为空", component="rack")
        previous = self._labels.get(rack_id)
        self._labels[rack_id] = label
        self._zones[rack_id] = zone
        self._epoch += 1
        change = {
            "epoch": self._epoch,
            "rack_id": rack_id,
            "previous_label": previous,
            "label": label,
            "zone": zone,
        }
        self._history.append(change)
        return change

    def label_of(self, rack_id: str) -> str:
        """返回某簇的最新编号。"""

        label = self._labels.get(rack_id)
        if label is None:
            raise NamespaceError(f"未登记的簇: {rack_id}", component="rack")
        return label

    def zone_of(self, rack_id: str) -> str:
        """返回某簇的消防分区。"""

        zone = self._zones.get(rack_id)
        if zone is None:
            raise NamespaceError(f"未登记的簇: {rack_id}", component="rack")
        return zone

    def racks_of_zone(self, zone: str) -> list[str]:
        """返回某消防分区下的簇标识。"""

        return sorted(rack for rack, current in self._zones.items() if current == zone)

    def resolve(self, label: str) -> str:
        """按现场编号反查簇标识。"""

        for rack_id, current in self._labels.items():
            if current == label:
                return rack_id
        raise NamespaceError(f"未知的簇编号: {label}", component="rack")

    def history(self) -> list[dict]:
        """返回全部编号变更记录。"""

        return [dict(change) for change in self._history]

    def snapshot(self) -> dict:
        """返回当前映射表。"""

        return {
            "epoch": self._epoch,
            "labels": {rack_id: self._labels[rack_id] for rack_id in sorted(self._labels)},
            "zones": {rack_id: self._zones[rack_id] for rack_id in sorted(self._zones)},
        }
