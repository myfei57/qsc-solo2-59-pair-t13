"""并网点组件。

``GridTie`` 把限额、频率与电量流向收在一起，对外给两个判断：这次并网条件
成不成立、这个功率指令要不要先钳位。两条判断都在爬坡之前调用，所以并网点
不会出现"先越限再回调"的瞬间。
"""

from __future__ import annotations

from ..config import GridLimits
from .flow import PowerFlow
from .limit import PowerLimit
from .monitor import FrequencyMonitor
from .snapshot import GridSnapshot


class GridTie:
    """并网点组件。"""

    def __init__(self, limits: GridLimits) -> None:
        self._limits = limits
        self._limit = PowerLimit(limits)
        self._flow = PowerFlow()
        self._monitor = FrequencyMonitor(limits)
        self._checks = 0
        self._rejections = 0

    @property
    def limits(self) -> GridLimits:
        return self._limits

    @property
    def limit(self) -> PowerLimit:
        return self._limit

    @property
    def flow(self) -> PowerFlow:
        return self._flow

    def monitor_frequency(self, frequency_hz: float, now: float) -> dict:
        """记一次频率采样。"""

        return self._monitor.sample(frequency_hz, now)

    def check(self, frequency_hz: float, power_kw: float, now: float) -> dict:
        """核对并网条件与功率越限，返回判定结果。"""

        self._checks += 1
        sample = self.monitor_frequency(frequency_hz, now)
        violations: list[str] = []
        if not sample["ok"]:
            violations.append("frequency_out_of_band")
        allowed = self._limit.clamp(power_kw)
        if abs(allowed - float(power_kw)) > 1e-9:
            violations.append("power_clamped")
        if violations and "frequency_out_of_band" in violations:
            self._rejections += 1
        return {
            "requested_kw": round(float(power_kw), 3),
            "allowed_kw": round(allowed, 3),
            "headroom_kw": round(self._limit.headroom_kw(allowed), 3),
            "ratio": round(self._limit.ratio(allowed), 4),
            "frequency_hz": sample["frequency_hz"],
            "violations": violations,
        }

    def clamp_for_ramp(self, power_kw: float) -> dict:
        """在爬坡之前钳位，返回钳位记录。"""

        allowed = self._limit.clamp(power_kw)
        return {
            "requested_kw": round(float(power_kw), 3),
            "allowed_kw": round(allowed, 3),
            "clamped": abs(allowed - float(power_kw)) > 1e-9,
            "ratio": round(self._limit.ratio(allowed), 4),
        }

    def record_flow(self, power_kw: float, dt: float) -> dict:
        """按功率方向累计电量。"""

        if float(power_kw) >= 0:
            energy = self._flow.discharge(power_kw, dt)
            direction = "export"
        else:
            energy = self._flow.charge(power_kw, dt)
            direction = "import"
        return {"direction": direction, "energy_kwh": round(energy, 6), "totals": self._flow.totals()}

    def snapshot(self) -> GridSnapshot:
        """返回并网点状态快照。"""

        return GridSnapshot(
            limit=self._limit.as_dict(),
            flow=self._flow.totals(),
            frequency=self._monitor.snapshot(),
            checks=self._checks,
            rejections=self._rejections,
        )
