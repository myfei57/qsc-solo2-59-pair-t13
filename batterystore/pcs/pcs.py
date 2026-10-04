"""PCS 组件。

``Pcs`` 把状态机、接触器、爬坡器、电流阶梯、降额合成与保护判据收在一个
入口后面，对外只暴露四个动作：并离网切换、功率指令、降额下发与跳闸复位。
切换先看状态机再动接触器，顺序写死在方法里，调用方无法把它调反。
"""

from __future__ import annotations

from ..errors import InterlockError
from ..config import PcsLimits
from .current import CurrentLadder
from .curve import EfficiencyCurve
from .cut import CutOff
from .derate import DerateFactor, combine_ratios
from .mode import ModeTable
from .power import PowerController
from .protection import PcsProtection
from .ramp import RampLimiter
from .snapshot import PcsSnapshot
from .state import PcsState
from .switch import TransferSwitch


class Pcs:
    """储能变流器组件。"""

    def __init__(self, limits: PcsLimits) -> None:
        self._limits = limits
        self._state = PcsState(ModeTable())
        self._switch = TransferSwitch()
        self._ramp = RampLimiter(limits.ramp_kw_per_s)
        self._curve = EfficiencyCurve.from_limits(limits)
        self._power = PowerController(limits.max_power_kw, self._curve)
        self._ladder = CurrentLadder(limits.current_step_a, limits.current_tolerance_a, limits.current_max_a)
        self._cut = CutOff()
        self._protection = PcsProtection(limits)
        self._derate = DerateFactor(1.0, {})
        self._transfers = 0

    @property
    def limits(self) -> PcsLimits:
        return self._limits

    @property
    def state_machine(self) -> PcsState:
        return self._state

    @property
    def switch(self) -> TransferSwitch:
        return self._switch

    @property
    def ladder(self) -> CurrentLadder:
        return self._ladder

    @property
    def cut(self) -> CutOff:
        return self._cut

    @property
    def protection(self) -> PcsProtection:
        return self._protection

    def is_tied(self) -> bool:
        """是否处于并网态。"""

        return self._state.is_tied()

    def transfer(self, target: str, reason: str) -> dict:
        """执行一次并离网切换，返回切换记录。"""

        if self._cut.is_tripped():
            raise InterlockError("PCS 处于跳闸态，需先复位", component="pcs")
        source = self._state.state
        self._state.transition(target, reason)
        if target == "grid_tie" and not self._switch.is_closed():
            self._switch.close()
        elif target in ("off_grid", "stopped") and self._switch.is_closed():
            self._switch.open()
        if target != "grid_tie":
            self._power.command(0.0)
            self._ramp.reset()
        self._transfers += 1
        return {
            "from": source,
            "to": target,
            "reason": reason,
            "generation": self._state.generation,
            "switch": self._switch.as_dict(),
            "transfers": self._transfers,
        }

    def set_point(self, power_kw: float, dt: float, derate: DerateFactor | None = None) -> dict:
        """按限额与降额下发功率指令并爬坡一步。"""

        factor = derate or self._derate
        clamped = self._limits.clamp_power(power_kw)
        self._power.with_derate(factor.ratio)
        self._power.command(clamped)
        ramped = self._ramp.step(self._power.output_kw(), dt)
        violations = self._protection.check(self._ladder.current_a(), ramped)
        return {
            "requested_kw": round(float(power_kw), 3),
            "clamped_kw": round(clamped, 3),
            "ramped_kw": round(ramped, 3),
            "derate": factor.as_dict(),
            "violations": violations,
        }

    def apply_derate(self, **ratios: float) -> DerateFactor:
        """合成降额系数并写入功率控制器。"""

        self._derate = combine_ratios(**ratios)
        self._power.with_derate(self._derate.ratio)
        return self._derate

    def trip(self, reason: str) -> dict:
        """执行跳闸：先切到跳闸态再分断接触器。"""

        self._protection.note_trip()
        self._cut.trip(reason)
        self._state.force("tripped", reason)
        if self._switch.is_closed():
            self._switch.open()
        self._power.command(0.0)
        self._ramp.reset()
        return {"state": self._state.state, "reasons": self._cut.reasons(), "trips": self._protection.trips()}

    def reset_trip(self) -> dict:
        """复位跳闸并回到停机态。"""

        was_tripped = self._cut.clear()
        self._state.force("stopped", "trip_reset")
        return {"was_tripped": was_tripped, "state": self._state.state, "resets": self._cut.resets()}

    def snapshot(self) -> PcsSnapshot:
        """返回 PCS 状态快照。"""

        return PcsSnapshot(
            state=self._state.state,
            generation=self._state.generation,
            derate_ratio=self._derate.ratio,
            output_kw=self._power.output_kw(),
            delivered_kw=self._power.delivered_kw(),
            reactive_kvar=self._power.reactive_kvar(),
            efficient_at=self._power.efficiency(),
            switch=self._switch.as_dict(),
            ramp_kw=self._ramp.current(),
            ramp_steps=self._ramp.steps_taken(),
            ramp_traveled_kw=self._ramp.traveled_kw(),
            power_commands=self._power.commands(),
            ladder=self._ladder.counts(),
            tripped=self._cut.is_tripped(),
            trip_reasons=self._cut.reasons(),
        )
