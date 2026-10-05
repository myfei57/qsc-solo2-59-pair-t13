"""并离网切换的原子落定、并发拒绝分类与复位确定态。"""

from __future__ import annotations

import threading

import pytest

from batterystore.errors import InterlockError


def test_transfer_record_carries_order_and_rationale(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "test")
    record = pcs.transfer("grid_tie", "test", sync={"ok": True, "frequency_hz": 50.0, "violations": []}, actor="op-1")
    assert record["order"] == "off_grid_first"
    assert "冲击电流" in record["rationale"]
    assert "保护" in record["rationale"]
    assert record["sync"]["ok"] is True
    assert record["actor"] == "op-1"
    assert pcs.is_consistent()


def test_sync_gate_rejects_before_closing(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "test")
    with pytest.raises(InterlockError) as excinfo:
        pcs.transfer("grid_tie", "test", sync={"ok": False, "frequency_hz": 52.0, "violations": ["frequency_out_of_band"]})
    assert excinfo.value.detail["rejected"] == "condition"
    assert excinfo.value.detail["condition"] == "sync_not_met"
    assert pcs.state_machine.state == "off_grid"
    assert pcs.switch.is_closed() is False
    assert pcs.is_consistent()


def test_preemption_names_the_holder(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "setup")
    pcs._transfer_lock.acquire()
    pcs._transfer_holder = {"actor": "op-7", "target": "grid_tie", "reason": "race"}
    try:
        with pytest.raises(InterlockError) as excinfo:
            pcs.transfer("off_grid", "test", actor="op-9")
    finally:
        pcs._transfer_holder = None
        pcs._transfer_lock.release()
    detail = excinfo.value.detail
    assert detail["rejected"] == "preempted"
    assert detail["holder"]["actor"] == "op-7"
    assert "op-7" in excinfo.value.message
    assert pcs.state_machine.state == "off_grid"


def test_condition_rejection_names_the_condition(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "test")
    pcs.trip("over_current")
    with pytest.raises(InterlockError) as excinfo:
        pcs.transfer("off_grid", "test")
    assert excinfo.value.detail["rejected"] == "condition"
    assert excinfo.value.detail["condition"] == "tripped"
    pcs.reset_trip()
    with pytest.raises(InterlockError) as excinfo:
        pcs.transfer("grid_tie", "test")
    assert excinfo.value.detail["condition"] == "illegal_transition"


def test_concurrent_hammer_never_lands_between_states(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "setup")
    outcomes = {"won": 0, "preempted": 0, "condition": 0}
    lock = threading.Lock()

    def worker(target: str, actor: str) -> None:
        for _ in range(60):
            try:
                pcs.transfer(target, "hammer", actor=actor)
            except InterlockError as error:
                kind = error.detail.get("rejected", "condition")
            else:
                kind = "won"
            with lock:
                outcomes[kind] += 1
            assert pcs.is_consistent()

    threads = [
        threading.Thread(target=worker, args=("grid_tie", "hammer-tie")),
        threading.Thread(target=worker, args=("off_grid", "hammer-off")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert outcomes["won"] > 0
    assert pcs.state_machine.state in ("off_grid", "grid_tie")
    assert pcs.is_consistent()


def test_reset_trip_returns_to_determinate_stopped(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "test")
    pcs.transfer("grid_tie", "test")
    pcs.trip("over_current")
    # 模拟切换中途失败留下的残渣：状态已停、接触器仍合。
    pcs.switch.close()
    reset = pcs.reset_trip()
    assert reset["was_tripped"] is True
    assert pcs.state_machine.state == "stopped"
    assert pcs.switch.is_closed() is False
    assert pcs.snapshot().ramp_kw == 0.0
    assert pcs.is_consistent()


def test_grid_tie_commit_happens_after_sync_check(platform):
    platform.start()
    report = platform.transfer_grid_tie()
    assert report["ok"], report["violations"]
    actions = [step["action"] for step in report["steps"]]
    assert actions == ["ready_confirmed", "transfer", "tie_check", "transfer", "clamp", "power_output"]
    build, commit = (step["detail"] for step in report["steps"] if step["action"] == "transfer")
    assert build["to"] == "off_grid"
    assert commit["to"] == "grid_tie"
    assert commit["order"] == "off_grid_first"
    assert commit["sync"]["ok"] is True
    assert commit["actor"] == report["op_id"]


def test_frequency_failure_stops_before_commit(platform):
    platform.start()
    report = platform.transfer_grid_tie(frequency_hz=52.0)
    assert not report["ok"]
    assert report["violations"] == ["frequency_out_of_band"]
    transfers = [step["detail"]["to"] for step in report["steps"] if step["action"] == "transfer"]
    assert transfers == ["off_grid"]
    assert platform.pcs.state_machine.state == "off_grid"
    assert platform.pcs.is_consistent()


def test_off_grid_report_and_rejection_classification(platform):
    platform.start()
    platform.transfer_grid_tie()
    report = platform.transfer_off_grid()
    assert report["ok"]
    assert platform.pcs.state_machine.state == "off_grid"
    again = platform.transfer_off_grid()
    assert not again["ok"]
    assert again["violations"] == ["pcs_transfer_rejected"]
    platform.pcs.trip("test_trip")
    tripped = platform.transfer_off_grid()
    assert tripped["violations"] == ["pcs_tripped"]


def test_off_grid_preempted_while_transfer_in_flight(platform):
    platform.start()
    pcs = platform.pcs
    pcs._transfer_lock.acquire()
    pcs._transfer_holder = {"actor": "op-x", "target": "grid_tie", "reason": "race"}
    try:
        report = platform.transfer_off_grid()
    finally:
        pcs._transfer_holder = None
        pcs._transfer_lock.release()
    assert not report["ok"]
    assert report["violations"] == ["pcs_transfer_preempted"]
    assert report["steps"][0]["action"] == "transfer_preempted"
    assert report["steps"][0]["detail"]["detail"]["holder"]["actor"] == "op-x"


def test_concurrency_probe_classifies_rejections(platform):
    platform.start()
    probe = platform.concurrency_probe(rounds=12)
    assert probe["ok"], probe
    assert probe["illegal_states"] == []
    assert probe["inconsistent"] == 0
    assert probe["rejections"] == probe["preempted"] + probe["condition_rejections"]
