"""设备命名空间登记表。

现场按 ``<区域>:<设备>`` 寻址，控制台、审计与告警路由共用同一套地址，避免
出现"控制台能看到的设备在审计里查不到"的情况。同一地址重复登记直接报错，
因为重复登记意味着两处代码对同一台物理设备各有一套理解。
"""

from __future__ import annotations

from ..errors import NamespaceError


class NamespaceRegistry:
    """区域／设备／类型的地址登记表。"""

    def __init__(self, station: str) -> None:
        if not station:
            raise NamespaceError("电站名不能为空", component="ns")
        self._station = station
        self._entries: dict[str, dict] = {}

    @property
    def station(self) -> str:
        return self._station

    def register(self, area: str, device: str, kind: str) -> str:
        """登记一台设备，返回其地址。"""

        if not area or not device or not kind:
            raise NamespaceError("区域、设备与类型都不能为空", component="ns")
        address = f"{area}:{device}"
        if address in self._entries:
            raise NamespaceError(f"地址重复登记: {address}", component="ns")
        self._entries[address] = {"address": address, "area": area, "device": device, "kind": kind}
        return address

    def resolve(self, address: str) -> dict:
        """按地址取设备描述，未知地址报错。"""

        entry = self._entries.get(address)
        if entry is None:
            raise NamespaceError(f"未知设备地址: {address}", component="ns")
        return dict(entry)

    def addresses(self) -> list[dict]:
        """返回全部设备描述（按地址排序）。"""

        return [dict(self._entries[key]) for key in sorted(self._entries)]

    def of_kind(self, kind: str) -> list[str]:
        """返回某类型设备的全部地址。"""

        return sorted(entry["address"] for entry in self._entries.values() if entry["kind"] == kind)

    def count(self) -> int:
        """已登记设备数量。"""

        return len(self._entries)
