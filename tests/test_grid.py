"""并网限额、频率监视与电量流向。"""

from __future__ import annotations

import pytest


def test_power_limit_clamps_both_directions(platform):
    limit = platform.grid.limit
    assert limit.clamp(9999.0) == platform.config.grid.export_limit_kw
    assert limit.clamp(-9999.0) == -platform.config.grid.import_limit_kw
    assert limit.headroom_kw(0.0) == platform.config.grid.export_limit_kw
    assert limit.ratio(0.0) == 1.0
    assert limit.ratio(platform.config.grid.export_limit_kw) == 1.0
    assert limit.as_dict()["import_limit_kw"] == platform.config.grid.import_limit_kw


def test_frequency_monitor_flags_out_of_band(platform):
    monitor = platform.grid
    band = platform.config.grid.frequency_band_hz
    ok = monitor.monitor_frequency(platform.config.grid.rated_frequency_hz, 0.0)
    assert ok["ok"] is True
    bad = monitor.monitor_frequency(platform.config.grid.rated_frequency_hz + band + 0.5, 1.0)
    assert bad["ok"] is False
    assert bad["deviation_hz"] > band
    snapshot = monitor.snapshot()
    assert snapshot.frequency["out_of_band"] == 1
    assert snapshot.frequency["last"]["frequency_hz"] == bad["frequency_hz"]


def test_check_rejects_out_of_band_frequency(platform):
    result = platform.grid.check(51.0, 100.0, 0.0)
    assert "frequency_out_of_band" in result["violations"]
    assert result["allowed_kw"] <= platform.config.grid.export_limit_kw
    assert platform.grid.snapshot().rejections == 1


def test_clamp_happens_before_ramp(platform):
    clamped = platform.grid.clamp_for_ramp(900.0)
    assert clamped["clamped"] is True
    assert clamped["allowed_kw"] == platform.config.grid.export_limit_kw
    assert clamped["ratio"] == 1.0


def test_power_flow_directions(platform):
    flow = platform.grid
    discharge = flow.record_flow(360.0, 3600.0)
    charge = flow.record_flow(-360.0, 3600.0)
    assert discharge["direction"] == "export"
    assert charge["direction"] == "import"
    totals = flow.snapshot().flow
    assert totals["export_kwh"] == pytest.approx(360.0, abs=0.01)
    assert totals["import_kwh"] == pytest.approx(360.0, abs=0.01)
    assert totals["net_kwh"] == pytest.approx(0.0, abs=0.01)
