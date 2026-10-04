"""控制台页面服务。

四个页面（簇状态、PCS、功率、告警）由独立 HTML 文件提供，页面只读取 JSON
接口，不在服务端拼字符串。:meth:`PageLibrary.exists` 供启动自检核对页面是否
齐全，缺页面时启动报告里能直接看出来。
"""

from __future__ import annotations

import os

PAGES = {
    "racks": "racks.html",
    "pcs": "pcs.html",
    "power": "power.html",
    "alarms": "alarms.html",
}


class PageLibrary:
    """静态页面目录。"""

    def __init__(self, root: str) -> None:
        self._root = os.path.abspath(root)

    @property
    def root(self) -> str:
        return self._root

    def resolve(self, path: str) -> str | None:
        """把请求路径解析成页面名，非页面路径返回 ``None``。"""

        name = path.strip("/")
        if name in PAGES:
            return name
        trimmed = name[:-5] if name.endswith(".html") else ""
        return trimmed if trimmed in PAGES else None

    def path_of(self, name: str) -> str:
        """返回页面文件路径。"""

        if name not in PAGES:
            raise KeyError(f"未知页面: {name}")
        return os.path.join(self._root, PAGES[name])

    def render(self, name: str) -> str:
        """读取页面内容。"""

        with open(self.path_of(name), "r", encoding="utf-8") as handle:
            return handle.read()

    def index(self) -> list[dict]:
        """返回页面清单与是否就位。"""

        return [
            {"name": name, "path": f"/{name}", "file": PAGES[name], "present": os.path.isfile(self.path_of(name))}
            for name in sorted(PAGES)
        ]

    def exists(self) -> bool:
        """四个页面是否全部就位。"""

        return all(item["present"] for item in self.index())
