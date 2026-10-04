"""审计记录、汇总、时间线与操作边界。"""

from __future__ import annotations

from batterystore.audit.record import AuditRecord
from batterystore.audit.timeline import build_timeline


def test_audit_record_roundtrip():
    record = AuditRecord.create(1.0, "station1", "pcs", "transfer", severity="bad", message="m", op_id="op-1")
    assert record.severity == "notice"
    assert record.is_alarm() is False
    assert record.op_id() == "op-1"
    restored = AuditRecord.from_dict(record.as_dict())
    assert restored == record
    assert AuditRecord.create(1.0, "s", "c", "a", severity="alarm").is_alarm() is True
    assert AuditRecord.create(1.0, "s", "c", "a").op_id() == ""


def test_audit_log_records_and_queries(platform):
    platform.start()
    platform.transfer_grid_tie()
    summary = platform.audit.summary()
    assert summary["total"] > 0
    assert summary["journal_count"] >= summary["total"]
    entries = platform.audit.query(component="pcs", limit=50)
    assert entries
    assert all(entry["component"] == "pcs" for entry in entries)
    assert platform.audit.tail(limit=1)
    assert platform.audit.entries(limit=1)
    assert platform.audit.report()["span_s"] >= 0.0
    assert platform.audit.operations(limit=5)
    assert platform.audit.replay_segment(0)
    assert platform.audit.replay_from_journal(limit=5)


def test_audit_snapshot_and_timeline(platform):
    platform.start()
    platform.report_fault("rk-01", "cell_over_temp")
    platform.report_fault("rk-01", "cell_over_temp")
    snapshot = platform.audit_snapshot()
    assert snapshot["journal_count"] > 0
    assert snapshot["summary"]["alarms"] >= 1
    assert snapshot["segments"] >= 1
    assert snapshot["operations"]
    timeline = build_timeline(platform.audit.records(limit=50), station="station1")
    assert timeline
    assert timeline[0]["ts"] <= timeline[-1]["ts"]
    assert build_timeline(platform.audit.records(limit=50), station="other") == []


def test_alarms_only_contain_warning_and_alarm(platform):
    platform.start()
    platform.report_fault("rk-01", "cell_over_temp")
    platform.report_fault("rk-01", "cell_over_temp")
    alarms = platform.audit.alarms()
    assert alarms
    assert {entry["severity"] for entry in alarms} <= {"warning", "alarm"}
