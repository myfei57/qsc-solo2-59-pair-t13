"""消防联动：探测、开阀确认与阶段顺序。"""

from __future__ import annotations

import pytest

from batterystore.errors import FireError
from batterystore.fire.stage import SuppressionStage


def test_detection_requires_smoke_or_temperature(platform):
    fire = platform.fire
    assert fire.detect("Z1", 10.0, 25.0)["detected"] is False
    assert fire.detect("Z1", 9999.0, 25.0)["detected"] is True
    assert fire.detect("Z2", 0.0, platform.config.fire.temp_trip_c + 1.0)["detected"] is True
    assert fire.scan() == ["Z1", "Z2"]
    assert set(fire.detectors.zones()) == {"Z1", "Z2", "Z3", "Z4"}
    with pytest.raises(KeyError):
        fire.detectors.update("Z9", 0.0, 25.0)


def test_valve_requires_confirmation_window(platform):
    valve = platform.fire.valve
    assert valve.confirm(0.0) is False
    valve.open(100.0)
    assert valve.is_commanded() is True
    assert valve.confirm(101.0) is False
    assert valve.is_confirmed() is False
    assert valve.confirm(100.0 + platform.config.fire.valve_confirm_s) is True
    assert valve.travel_mm() == platform.config.fire.valve_travel_mm
    assert valve.cycles() == 1
    with pytest.raises(FireError):
        valve.open(200.0)
    assert valve.close() is True
    assert valve.as_dict()["confirmed"] is False


def test_stage_sequence_detects_out_of_order():
    stages = SuppressionStage()
    stages.enter("valve_open")
    stages.enter("detect")
    assert stages.violations() == ["stage_out_of_order"]
    assert stages.has("valve_open")
    assert stages.completed() is False
    with pytest.raises(ValueError):
        stages.enter("unknown")


def test_suppression_opens_valve_before_tripping_pcs(platform):
    report = platform.fire_drill(zone="Z1", smoke_ppm=2000.0, confirm_dt=5.0)
    actions = [step["action"] for step in report["steps"]]
    assert report["ok"], report["violations"]
    assert actions.index("valve_confirm") < actions.index("trip")
    assert platform.pcs.cut.is_tripped()
    assert platform.fire.snapshot().release_ready is True
    assert platform.fire.stages.completed() is True


def test_suppression_aborts_when_valve_not_confirmed(platform):
    report = platform.fire_drill(zone="Z1", smoke_ppm=2000.0, confirm_dt=0.5)
    assert not report["ok"]
    assert report["violations"] == ["valve_not_confirmed"]
    assert platform.pcs.cut.is_tripped() is False
    assert platform.fire.snapshot().aborts == 1
    assert platform.fire.snapshot().pcs_tripped is False


def test_release_resets_fire_and_pcs(platform):
    platform.fire_drill(zone="Z1", smoke_ppm=2000.0, confirm_dt=5.0)
    released = platform.release_fire()
    assert released["fire"]["was_open"] is True
    assert released["pcs"]["was_tripped"] is True
    assert platform.pcs.cut.is_tripped() is False
    assert platform.fire.snapshot().sequence == []
