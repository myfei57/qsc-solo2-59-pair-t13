"""SOC 库仑累计、校准代际与历史。"""

from __future__ import annotations

import pytest

from batterystore.soc.coulomb import CoulombCounter
from batterystore.soc.estimate import estimate_soc


def test_coulomb_counter_tracks_both_directions():
    counter = CoulombCounter(0.5)
    charged = counter.through(100.0, 3600.0)
    discharged = counter.through(-100.0, 3600.0)
    assert charged == pytest.approx(50.0)
    assert discharged == pytest.approx(-100.0)
    assert counter.charged_ah() == pytest.approx(50.0)
    assert counter.discharged_ah() == pytest.approx(100.0)
    assert counter.net_ah() == pytest.approx(-50.0)
    assert counter.intervals() == 2
    assert counter.efficiency == 0.5
    assert counter.reset()["net_ah"] == pytest.approx(-50.0)
    assert counter.net_ah() == 0.0
    with pytest.raises(ValueError):
        CoulombCounter(0.0)
    with pytest.raises(ValueError):
        counter.through(1.0, 0.0)


def test_estimate_uses_latest_calibration_epoch(platform):
    limits = platform.config.soc
    stale = {"epoch": 1, "soc_pct": 45.0, "expired": True}
    estimate = estimate_soc(stale, 0.0, limits, reported_pct=45.0)
    assert estimate.soc_pct == 45.0
    assert estimate.calibration_epoch == 1
    assert estimate.stale is True
    assert estimate.as_dict()["drift_pct"] == 0.0


def test_soc_follows_new_calibration(platform):
    platform.calibrate_soc(30.0, "field")
    estimate = platform.soc.value(platform.clock.now())
    assert estimate.calibration_epoch == 2
    assert estimate.soc_pct == pytest.approx(30.0)
    assert platform.racks["rk-01"].soc_pct() == pytest.approx(30.0)


def test_soc_accumulates_after_calibration(platform):
    platform.calibrate_soc(50.0, "field")
    platform.soc.accumulate(140.0, 3600.0)
    estimate = platform.soc.value(platform.clock.now())
    assert estimate.delta_pct > 0
    assert estimate.soc_pct > 50.0
    assert platform.soc.drift_pct() >= 0.0


def test_soc_history_and_snapshot(platform):
    platform.calibrate_soc(60.0, "field")
    platform.soc.value(platform.clock.now())
    snapshot = platform.soc_snapshot()
    assert snapshot["samples"] >= 1
    assert snapshot["coulomb"]["intervals"] >= 0
    assert snapshot["calibration"]["epoch"] == 2
    assert platform.soc.history.series()[0]["epoch"] == 2
    assert platform.soc.reported_pct() == pytest.approx(60.0)
    assert platform.soc.reset()["net_ah"] == pytest.approx(0.0)
