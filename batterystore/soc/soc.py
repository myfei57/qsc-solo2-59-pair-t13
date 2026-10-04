"""SOC 估算组件。

``SocEstimator`` 是 BMS 校准结果的下游：每次估算都取最近一代校准作为基准，
再把校准之后的库仑净增量叠上去。校准一换，下一轮估算立刻按新基准算，不会
继续沿用旧偏移。
"""

from __future__ import annotations

from ..config import SocLimits
from .coulomb import CoulombCounter
from .estimate import SocEstimate, estimate_soc
from .history import SocHistory
from .snapshot import SocSnapshot


class SocEstimator:
    """SOC 估算组件。"""

    def __init__(self, limits: SocLimits, calibration) -> None:
        self._limits = limits
        self._calibration = calibration
        self._counter = CoulombCounter(limits.coulomb_efficiency)
        self._history = SocHistory()
        self._reported_pct = float(limits.initial_soc_pct)

    @property
    def limits(self) -> SocLimits:
        return self._limits

    @property
    def counter(self) -> CoulombCounter:
        return self._counter

    @property
    def history(self) -> SocHistory:
        return self._history

    def accumulate(self, current_a: float, dt: float) -> float:
        """按电流与步长累计库仑量，返回本次净安时。"""

        return self._counter.through(current_a, dt)

    def value(self, now: float) -> SocEstimate:
        """按最近一代校准估算当前 SOC。"""

        latest = self._calibration.latest(now)
        estimate = estimate_soc(latest, self._counter.net_ah(), self._limits, self._reported_pct)
        self._history.record(estimate.soc_pct, self._reported_pct, now, estimate.calibration_epoch)
        return estimate

    def reported_pct(self) -> float:
        """返回上一次上报给调度的 SOC。"""

        return self._reported_pct

    def report(self, soc_pct: float) -> float:
        """更新上报值，返回被替换掉的旧值。"""

        previous = self._reported_pct
        self._reported_pct = float(soc_pct)
        return previous

    def drift_pct(self) -> float:
        """返回窗口内的漂移量。"""

        return self._history.drift_pct()

    def reset(self) -> dict:
        """清零库仑累计，返回清零前的值。"""

        return self._counter.reset()

    def snapshot(self, now: float) -> SocSnapshot:
        """返回 SOC 状态快照。"""

        estimate = self.value(now)
        return SocSnapshot(
            estimate=estimate.as_dict(),
            calibration=self._calibration.latest(now),
            coulomb={
                "charged_ah": round(self._counter.charged_ah(), 6),
                "discharged_ah": round(self._counter.discharged_ah(), 6),
                "net_ah": round(self._counter.net_ah(), 6),
                "intervals": self._counter.intervals(),
            },
            margin_pct=self._limits.drift_tolerance_pct - self.drift_pct(),
            samples=self._history.count(),
        )
