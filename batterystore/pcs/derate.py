"""降额系数合成。

温控与并网限额各自给出一个系数，PCS 取其中更严的一个。合成结果连同来源一起
记录，审计才能回答"这一轮功率为什么被压住"。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DerateFactor:
    """一次降额合成结果。"""

    ratio: float
    sources: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ratio": round(self.ratio, 4),
            "sources": {key: round(value, 4) for key, value in self.sources.items()},
        }


def combine_ratios(**ratios: float) -> DerateFactor:
    """取所有系数中最严的一个，并记录每个来源的取值。"""

    if not ratios:
        return DerateFactor(1.0, {})
    normalized = {name: max(0.0, min(1.0, float(value))) for name, value in ratios.items()}
    return DerateFactor(min(normalized.values()), normalized)
