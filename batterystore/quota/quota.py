"""充放电配额台账。

台账按周期滚动，并在放行前核对剩余额度：额度不足直接拒绝，不做"先用了再说"
的记账。周期切换时把上一周期的用量归档，本周期累计量清零，跨周期不会串账。
"""

from __future__ import annotations

from ..config import QuotaLimits
from ..errors import QuotaError
from .accounting import settle
from .period import PeriodTracker
from .snapshot import QuotaSnapshot
from .tariff import Tariff


class QuotaLedger:
    """充放电配额台账。"""

    def __init__(self, limits: QuotaLimits) -> None:
        self._limits = limits
        self._period = PeriodTracker(limits.period_hours)
        self._tariff = Tariff(limits)
        self._charge_kwh = 0.0
        self._discharge_kwh = 0.0
        self._charge_rate = limits.tariff_valley
        self._discharge_rate = limits.tariff_peak
        self._rejections = 0

    @property
    def limits(self) -> QuotaLimits:
        return self._limits

    @property
    def period(self) -> PeriodTracker:
        return self._period

    @property
    def tariff(self) -> Tariff:
        return self._tariff

    def totals(self) -> dict:
        """返回本周期累计电量。"""

        return {
            "charge_kwh": round(self._charge_kwh, 6),
            "discharge_kwh": round(self._discharge_kwh, 6),
            "period": self._period.current(),
        }

    def remaining(self) -> dict:
        """返回本周期剩余额度。"""

        return {
            "charge_kwh": round(max(0.0, self._limits.charge_quota_kwh - self._charge_kwh), 6),
            "discharge_kwh": round(max(0.0, self._limits.discharge_quota_kwh - self._discharge_kwh), 6),
        }

    def roll(self, now: float) -> dict:
        """按当前时间滚动周期，返回滚动结果。"""

        result = self._period.switch(now, self.totals())
        if result["rolled"]:
            self._charge_kwh = 0.0
            self._discharge_kwh = 0.0
        return result

    def can_charge(self, kwh: float, now: float) -> bool:
        """本周期是否还有足够充电额度。"""

        self.roll(now)
        if float(kwh) <= self.remaining()["charge_kwh"]:
            return True
        self._rejections += 1
        return False

    def can_discharge(self, kwh: float, now: float) -> bool:
        """本周期是否还有足够放电额度。"""

        self.roll(now)
        if float(kwh) <= self.remaining()["discharge_kwh"]:
            return True
        self._rejections += 1
        return False

    def record_charge(self, kwh: float, now: float) -> dict:
        """登记一段充电电量，超额时抛配额错误。"""

        if not self.can_charge(kwh, now):
            raise QuotaError("本周期充电额度不足", component="quota")
        self._charge_kwh += float(kwh)
        self._charge_rate = self._tariff.rate(now)
        return {"charged_kwh": round(float(kwh), 6), "totals": self.totals()}

    def record_discharge(self, kwh: float, now: float) -> dict:
        """登记一段放电电量，超额时抛配额错误。"""

        if not self.can_discharge(kwh, now):
            raise QuotaError("本周期放电额度不足", component="quota")
        self._discharge_kwh += float(kwh)
        self._discharge_rate = self._tariff.rate(now)
        return {"discharged_kwh": round(float(kwh), 6), "totals": self.totals()}

    def settlement(self, now: float) -> dict:
        """按已记录的电价结算本周期。"""

        report = settle(self._charge_kwh, self._discharge_kwh, self._charge_rate, self._discharge_rate)
        report["current_rate"] = self._tariff.rate(now)
        report["kind"] = self._tariff.kind(now)
        return report

    def snapshot(self, now: float) -> QuotaSnapshot:
        """返回配额状态快照。"""

        self.roll(now)
        return QuotaSnapshot(
            period=self._period.current(),
            rolls=self._period.rolls(),
            totals=self.totals(),
            remaining=self.remaining(),
            tariff=self._tariff.as_dict(),
            settlement=self.settlement(now),
            rejections=self._rejections,
            history=self._period.history(),
        )
