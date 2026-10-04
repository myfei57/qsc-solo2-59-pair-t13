"""均衡目标选择、节拍与状态机。"""

from __future__ import annotations

import pytest

from batterystore.balance.select import cell_delta_mv, select_cells


def test_balance_restores_delta_to_target(platform):
    platform.disturb_cell(cell_index=0, delta_v=0.06)
    assert platform.racks["rk-01"].metrics().delta_mv > platform.config.balance.target_delta_mv
    report = platform.balance(max_steps=600)
    assert report["ok"], report["violations"]
    assert platform.balancer.is_complete()
    assert platform.balancer.delta_mv() <= platform.config.balance.target_delta_mv
    snapshot = platform.balance_snapshot()
    assert snapshot["state"] == "complete"
    assert snapshot["counts"]["completions"] >= 1
    assert snapshot["run"]["cycle_s"] > 0


def test_select_returns_empty_when_delta_within_target(platform):
    cells = platform.racks["rk-01"].cells()
    assert cell_delta_mv(cells) == pytest.approx(0.0)
    assert select_cells(cells, platform.config.balance.target_delta_mv, 2) == []


def test_select_tops_up_to_minimum_cells(platform):
    cells = platform.racks["rk-01"].cells()
    cells[5].update(voltage_v=cells[5].voltage_v + 0.1)
    chosen = select_cells(cells, platform.config.balance.target_delta_mv, 3)
    assert len(chosen) == 3
    assert cells[5].cell_id in chosen


def test_balance_aborts_on_overrun(platform):
    rack = platform.racks["rk-01"]
    rack.cells()[0].update(voltage_v=rack.cells()[0].voltage_v + 0.5)
    platform.balancer.start(rack.cells())
    for _ in range(5):
        platform.balancer.advance(platform.config.balance.max_duration_s, rack.cells())
    assert platform.balancer.state.state == "aborted"
    assert platform.balancer.snapshot().run["overrun"] is True
    assert platform.balancer.reset()["previous"] == "aborted"


def test_charging_blocked_until_balance_complete(platform):
    platform.disturb_cell(cell_index=0, delta_v=0.08)
    platform.sample_temperature(temperature_c=30.0, dt=1.0)
    blocked = platform.charge(steps=2, dt=60.0)
    assert not blocked["ok"]
    assert "balance_incomplete" in blocked["violations"]
