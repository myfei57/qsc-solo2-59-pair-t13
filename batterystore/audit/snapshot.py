"""审计状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditSnapshot:
    """审计某一时刻的状态。"""

    summary: dict
    report: dict
    operations: list
    journal_count: int
    active_segment: int
    segments: int

    def as_dict(self) -> dict:
        return {
            "summary": dict(self.summary),
            "report": dict(self.report),
            "operations": list(self.operations),
            "journal_count": self.journal_count,
            "active_segment": self.active_segment,
            "segments": self.segments,
        }
