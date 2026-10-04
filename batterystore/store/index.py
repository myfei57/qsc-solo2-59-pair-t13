"""文档索引摘要。

控制台与自检都要回答同一个问题："这一轮到底往盘上写了什么"。这里把文档
标识、字节数与最后修改时间汇成一张表，避免调用方各自去数文件。
"""

from __future__ import annotations

import os

from .jsonfile import JsonStore


def summarize_documents(store: JsonStore) -> list[dict]:
    """返回存储目录全部文档的名称、大小与修改时间。"""

    report: list[dict] = []
    for doc_id in store.list_ids():
        path = store.path_of(doc_id)
        stat = os.stat(path)
        report.append(
            {
                "doc_id": doc_id,
                "bytes": stat.st_size,
                "modified_at": round(stat.st_mtime, 3),
            }
        )
    return report
