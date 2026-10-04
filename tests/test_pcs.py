"""PCS 状态机、爬坡、电流阶梯与保护。"""

from __future__ import annotations

import pytest

from batterystore.errors import InterlockError
from batterystore.pcs.mode import ModeTable


def test_mode_table_rejects_unknown_transfer():
    table = ModeTable()
    assert table.allows("stopped", "off_grid")
    assert not table.allows("stopped", "grid_tie")
    with pytest.raises(InterlockError):
        table.require("stopped", "grid_tie")
    with pytest.raises(InterlockError):
        table.require("idle", "off_grid")
    assert {"from": "off_grid", "to": "grid_tie"} in table.matrix()


def test_transfer_sequence_and_switch(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "test")
    pcs.transfer("grid_tie", "test")
    assert pcs.is_tied()
    assert pcs.switch.is_closed()
    assert pcs.switch.last_action() == "close"
    assert pcs.switch.cycles() == 1
    record = pcs.transfer("off_grid", "test")
    assert record["from"] == "grid_tie"
    assert pcs.switch.is_closed() is False
    with pytest.raises(ValueError):
        pcs.switch.open()


def test_ramp_limits_step(platform):
    ramp = platform.pcs
    ramp.transfer("off_grid", "test")
    ramp.transfer("grid_tie", "test")
    first = ramp.set_point(400.0, 1.0)
    assert first["ramped_kw"] == pytest.approx(platform.config.pcs.ramp_kw_per_s)
    second = ramp.set_point(400.0, 1.0)
    assert second["ramped_kw"] > first["ramped_kw"]
    snapshot = ramp.snapshot()
    assert snapshot.ramp_steps == 2
    # 离网切换本身会下发一次 0kW 指令，因此指令数比爬坡步数多一。
    assert snapshot.power_commands == 3
    assert snapshot.ramp_traveled_kw > 0


def test_derate_is_strictest_factor(platform):
    factor = platform.pcs.apply_derate(temperature=0.5, grid=0.8)
    assert factor.ratio == 0.5
    assert factor.as_dict()["sources"]["grid"] == 0.8
    point = platform.pcs.set_point(300.0, 1.0)
    assert point["derate"]["ratio"] == 0.5


def test_current_ladder_requires_voltage_check(platform):
    ladder = platform.pcs.ladder
    ladder.begin(120.0)
    ladder.lower_to(40.0)
    with pytest.raises(InterlockError):
        ladder.raise_to(80.0)
    assert ladder.verify_voltage(3.2, 3.2, 0.05) is True
    assert ladder.raise_to(80.0) == 80.0
    with pytest.raises(InterlockError):
        ladder.raise_to(200.0)
    assert ladder.counts()["checks"] == 1
    with pytest.raises(InterlockError):
        ladder.raise_to(120.0)
    assert ladder.verify_voltage(3.0, 3.2, 0.05) is False
    assert len(ladder.sequence()) >= 4


def test_trip_and_reset(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "test")
    pcs.transfer("grid_tie", "test")
    report = pcs.trip("over_current")
    assert report["state"] == "tripped"
    assert pcs.cut.is_tripped()
    assert pcs.switch.is_closed() is False
    with pytest.raises(InterlockError):
        pcs.transfer("off_grid", "test")
    reset = pcs.reset_trip()
    assert reset["was_tripped"] is True
    assert reset["resets"] == 1
    assert pcs.cut.is_tripped() is False
    assert pcs.protection.trips() == 1
    assert pcs.protection.check(0.0, 10.0) == []
    assert pcs.protection.check(platform.config.pcs.protection_current_a, 0.0) == ["over_current"]


def test_snapshot_includes_mode_matrix(platform):
    snapshot = platform.pcs_snapshot()
    assert snapshot["state"] == "stopped"
    assert snapshot["mode_matrix"]
    assert snapshot["ladder"]["raises"] == 0
    assert snapshot["efficient_at"] > 0
