"""电池簇、度量、电量与编号映射。"""

from __future__ import annotations

import pytest

from batterystore.errors import NamespaceError
from batterystore.rack.alarms import collect_alarms
from batterystore.rack.mapping import RackMapping
from batterystore.rack.metrics import compute_metrics


def test_rack_metrics_and_energy(platform):
    rack = platform.racks["rk-01"]
    metrics = rack.metrics()
    assert metrics.delta_mv == pytest.approx(0.0)
    assert metrics.cells == platform.config.rack.cell_count
    assert rack.voltage_v() > 0
    assert rack.energy_kwh(platform.config.soc.capacity_ah) > 0
    assert rack.usable_energy_kwh(platform.config.rack, platform.config.soc.capacity_ah) > 0


def test_compute_metrics_detects_spread(platform):
    cells = platform.racks["rk-01"].cells()
    cells[0].update(voltage_v=cells[0].voltage_v + 0.05, temperature_c=48.0)
    metrics = compute_metrics(cells)
    assert metrics.delta_mv == pytest.approx(50.0, abs=0.5)
    assert metrics.max_temperature_c == 48.0
    assert metrics.spread_c == 23.0


def test_replace_pack_rating_bumps_epoch(platform):
    rack = platform.racks["rk-01"]
    before = rack.rating_epoch
    change = rack.replace_pack_rating(0, 3.35)
    assert change["rating_epoch"] == before + 1
    assert change["rating_v"] == 3.35
    assert rack.rating_epoch == before + 1
    assert rack.rating_v() in (3.2, 3.35)


def test_collect_alarms_reports_over_temperature(platform):
    rack = platform.racks["rk-01"]
    rack.apply_temperature(platform.config.rack.temp_trip_c)
    alarms = collect_alarms(rack.rack_id, rack.metrics(), platform.config.rack, rack.soc_pct(), 60.0)
    codes = {alarm.code for alarm in alarms}
    assert "over_temp_trip" in codes
    assert alarms[0].as_dict()["rack_id"] == rack.rack_id


def test_mapping_tracks_latest_label():
    mapping = RackMapping()
    mapping.assign("rk-01", "R1", "Z1")
    mapping.assign("rk-02", "R2", "Z2")
    change = mapping.assign("rk-01", "R9", "Z2")
    assert change["previous_label"] == "R1"
    assert mapping.label_of("rk-01") == "R9"
    assert mapping.zone_of("rk-01") == "Z2"
    assert mapping.racks_of_zone("Z2") == ["rk-01", "rk-02"]
    assert mapping.resolve("R9") == "rk-01"
    assert len(mapping.history()) == 3
    assert mapping.snapshot()["epoch"] == 3
    with pytest.raises(NamespaceError):
        mapping.label_of("rk-99")
