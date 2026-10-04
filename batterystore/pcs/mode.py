"""PCS 运行模式与合法迁移。

并网、离网与停机之间的迁移有明确方向：从停机只能先到离网，从离网建压完成后
才能并网，跳闸态必须先复位。表里没有的迁移一律拒绝，避免出现"既并网又离网"
的中间态。
"""

from __future__ import annotations

from ..errors import InterlockError

MODES = ("stopped", "off_grid", "grid_tie", "tripped")

_ALLOWED: dict[str, tuple[str, ...]] = {
    "stopped": ("off_grid", "tripped"),
    "off_grid": ("grid_tie", "stopped", "tripped"),
    "grid_tie": ("off_grid", "stopped", "tripped"),
    "tripped": ("stopped",),
}


class ModeTable:
    """合法迁移表。"""

    def __init__(self, allowed: dict[str, tuple[str, ...]] | None = None) -> None:
        self._allowed = dict(allowed or _ALLOWED)

    def allows(self, source: str, target: str) -> bool:
        """判断一次迁移是否合法。"""

        return target in self._allowed.get(source, ())

    def require(self, source: str, target: str) -> None:
        """迁移不合法时抛联锁错误。"""

        if source not in MODES or target not in MODES:
            raise InterlockError(f"未知的 PCS 模式: {source} → {target}", component="pcs")
        if not self.allows(source, target):
            raise InterlockError(f"不允许从 {source} 迁移到 {target}", component="pcs")

    def matrix(self) -> list[dict]:
        """返回完整迁移矩阵，供控制台展示。"""

        return [
            {"from": source, "to": target}
            for source in MODES
            for target in MODES
            if self.allows(source, target)
        ]
