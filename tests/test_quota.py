"""配额周期、电价与结算。"""

from __future__ import annotations

import pytest

from batterystore.errors import QuotaError
from batterystore.quota.accounting import settle


def test_settle_computes_margin():
    report = settle(100.0, 80.0, 0.4, 1.2)
    assert report["charge_cost"] == pytest.approx(40.0)
    assert report["discharge_value"] == pytest.approx(96.0)
    assert report["margin"] == pytest.approx(56.0)
    assert settle(0.0, 0.0, 0.4, 1.2)["margin"] == 0.0


def test_tariff_switches_between_peak_and_valley(platform):
    tariff = platform.quota.tariff
    assert tariff.as_dict()["peak_window"] == [8, 22]
    assert tariff.kind(0.0) in ("peak", "valley")
    assert isinstance(tariff.rate(0.0), float)
    assert platform.config.quota.tariff_valley <= platform.config.quota.tariff_peak


def test_quota_records_and_limits(platform, clock):
    quota = platform.quota
    assert quota.can_charge(10.0, clock.now()) is True
    assert quota.record_charge(10.0, clock.now())["charged_kwh"] == 10.0
    assert quota.record_discharge(4.0, clock.now())["discharged_kwh"] == 4.0
    totals = quota.totals()
    assert totals["charge_kwh"] == 10.0
    assert totals["discharge_kwh"] == 4.0
    remaining = quota.remaining()
    assert remaining["charge_kwh"] == pytest.approx(platform.config.quota.charge_quota_kwh - 10.0)
    with pytest.raises(QuotaError):
        quota.record_charge(10_000.0, clock.now())
    assert quota.snapshot(clock.now()).rejections == 1


def test_quota_rolls_into_new_period(platform, clock):
    quota = platform.quota
    quota.record_charge(100.0, clock.now())
    clock.advance(platform.config.quota.period_hours * 3600.0 + 1.0)
    rolled = quota.roll(clock.now())
    assert rolled["rolled"] is True
    assert quota.totals()["charge_kwh"] == 0.0
    assert quota.period.rolls() == 1
    assert quota.period.history()[0]["charge_kwh"] == pytest.approx(100.0)
    assert quota.snapshot(clock.now()).totals["period"].startswith("p")
