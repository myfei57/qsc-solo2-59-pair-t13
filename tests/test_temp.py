"""温控降额与额定值基线。"""

from __future__ import annotations

import pytest


def test_cooler_only_cools_when_running(platform):
    cooler = platform.temp.cooler
    assert cooler.tick(5.0, 40.0) == 40.0
    cooler.start()
    cooled = cooler.tick(5.0, 40.0)
    assert cooled < 40.0
    assert cooler.is_running() is True
    assert cooler.ticks() == 2
    assert cooler.removed_c() > 0
    cooler.stop()
    assert cooler.is_running() is False
    with pytest.raises(ValueError):
        cooler.tick(0.0, 40.0)


def test_derate_curve_shape(platform):
    curve = platform.temp.curve
    limits = platform.config.temp
    assert curve.ratio(limits.derate_start_c - 1.0) == 1.0
    assert curve.ratio(limits.derate_full_c + 1.0) == limits.derate_floor_ratio
    middle = curve.ratio((limits.derate_start_c + limits.derate_full_c) / 2.0)
    assert limits.derate_floor_ratio < middle < 1.0
    assert curve.band(limits.derate_full_c) == "full_derate"
    assert curve.band(limits.warn_c + 1.0) == "derated"
    assert curve.band(0.0) == "normal"
    assert len(curve.points()) == 2


def test_baseline_refreshes_after_rating_change(platform, clock):
    rack = platform.racks["rk-01"]
    first = platform.temp.apply_temperature(38.0, clock.now(), rack.rating_v(), rack.rating_epoch)
    assert first["baseline_refreshed"] is True
    assert platform.temp.baseline.epoch == 1
    assert platform.temp.baseline.stale(rack.rating_epoch, clock.now()) is False
    rack.replace_pack_rating(0, 3.35)
    report = platform.temp.baseline_report(clock.now(), rack.rating_epoch)
    assert report["stale"] is True
    assert report["reason"] == "rating_changed"
    second = platform.temp.apply_temperature(38.0, clock.now(), rack.rating_v(), rack.rating_epoch)
    assert second["baseline_refreshed"] is True
    assert platform.temp.baseline.epoch == 2
    assert platform.temp.baseline_report(clock.now(), rack.rating_epoch)["reason"] == "fresh"


def test_baseline_expires_by_time(platform, clock):
    rack = platform.racks["rk-01"]
    platform.temp.apply_temperature(30.0, clock.now(), rack.rating_v(), rack.rating_epoch)
    clock.advance(platform.config.temp.baseline_ttl_s + 1.0)
    report = platform.temp.baseline_report(clock.now(), rack.rating_epoch)
    assert report["stale"] is True
    assert report["reason"] == "expired"
    assert platform.temp.charge_limit_ratio() == pytest.approx(platform.temp.ratio())


def test_charge_limit_uses_floor_before_first_calibration(platform):
    baseline = type(platform.temp.baseline)(platform.config.temp.baseline_ttl_s)
    assert baseline.epoch == 0
    assert baseline.stale(0, platform.clock.now()) is True
    assert baseline.latest(platform.clock.now(), 0)["reason"] == "uninitialised"
    with pytest.raises(ValueError):
        baseline.refresh(0.0, 0, 0.0)
    baseline.refresh(3.2, 0, 0.0)
    assert baseline.latest(0.0, 0)["reason"] == "fresh"
