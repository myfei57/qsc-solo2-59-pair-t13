"""温控组件。

``TempControl`` 负责一条完整的降额链：采集温度 → 核对额定值基线是否最新 →
按曲线算系数 → 启动冷却。基线一旦发现过期（额定值代际变化或超时）会立即
按最新额定值重标，所以温度刚回到正常区间时不会继续被旧基线压着。
"""

from __future__ import annotations

from ..config import TempLimits
from ..pcs.derate import combine_ratios
from .baseline import TempBaseline
from .control import Cooler
from .curve import DerateCurve
from .snapshot import TempSnapshot


class TempControl:
    """温控与降额组件。"""

    def __init__(self, limits: TempLimits) -> None:
        self._limits = limits
        self._curve = DerateCurve(limits)
        self._baseline = TempBaseline(limits.baseline_ttl_s)
        self._cooler = Cooler(limits.cool_rate_c_per_s)
        self._temperature_c = 25.0
        self._refreshes = 0
        self._stale_hits = 0

    @property
    def limits(self) -> TempLimits:
        return self._limits

    @property
    def curve(self) -> DerateCurve:
        return self._curve

    @property
    def baseline(self) -> TempBaseline:
        return self._baseline

    @property
    def cooler(self) -> Cooler:
        return self._cooler

    def temperature_c(self) -> float:
        """返回当前温度。"""

        return self._temperature_c

    def ratio(self) -> float:
        """返回当前温度下的降额系数。"""

        return self._curve.ratio(self._temperature_c)

    def charge_limit_ratio(self) -> float:
        """返回充电限制系数：基线过期时按最严系数处理。"""

        if self._baseline.epoch == 0:
            return self._limits.derate_floor_ratio
        return self.ratio()

    def apply_temperature(self, temperature_c: float, now: float, rating_v: float, rating_epoch: int) -> dict:
        """写入温度采集，必要时重标基线，返回本次采集结果。"""

        self._temperature_c = float(temperature_c)
        refreshed = False
        if self._baseline.stale(rating_epoch, now):
            self._stale_hits += 1
            self._baseline.refresh(rating_v, rating_epoch, now)
            self._refreshes += 1
            refreshed = True
        if self._temperature_c >= self._limits.derate_start_c:
            self._cooler.start()
        elif self._temperature_c <= self._limits.derate_start_c - 5.0:
            self._cooler.stop()
        return {
            "temperature_c": round(self._temperature_c, 2),
            "ratio": round(self.ratio(), 4),
            "band": self._curve.band(self._temperature_c),
            "baseline_refreshed": refreshed,
            "cooling": self._cooler.is_running(),
        }

    def cool(self, dt: float) -> float:
        """推进一个冷却步长，返回冷却后的温度。"""

        self._temperature_c = self._cooler.tick(dt, self._temperature_c)
        return self._temperature_c

    def combined_ratio(self, **ratios: float) -> dict:
        """把温控系数与其它系数一起合成。"""

        return combine_ratios(temperature=self.charge_limit_ratio(), **ratios).as_dict()

    def baseline_report(self, now: float, rating_epoch: int) -> dict:
        """返回基线现状与重标计数。"""

        report = self._baseline.latest(now, rating_epoch)
        report["refreshes"] = self._refreshes
        report["stale_hits"] = self._stale_hits
        return report

    def snapshot(self, now: float, rating_epoch: int) -> TempSnapshot:
        """返回温控状态快照。"""

        return TempSnapshot(
            temperature_c=self._temperature_c,
            ratio=self.ratio(),
            charge_limit_ratio=self.charge_limit_ratio(),
            band=self._curve.band(self._temperature_c),
            cooling=self._cooler.is_running(),
            cooler_ticks=self._cooler.ticks(),
            removed_c=self._cooler.removed_c(),
            baseline=self.baseline_report(now, rating_epoch),
        )
