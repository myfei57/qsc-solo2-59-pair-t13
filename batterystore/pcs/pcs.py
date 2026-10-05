"""PCS 组件。

``Pcs`` 把状态机、接触器、爬坡器、电流阶梯、降额合成与保护判据收在一个
入口后面，对外只暴露四个动作：并离网切换、功率指令、降额下发与跳闸复位。
切换先看状态机再动接触器，顺序写死在方法里，调用方无法把它调反。
"""

from __future__ import annotations

from ..errors import InterlockError
from ..config import PcsLimits
from .arbiter import TransferArbiter
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
        self._arbiter = TransferArbiter()
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

    @property
    def arbiter(self) -> TransferArbiter:
        return self._arbiter

    def acquire_transfer(self, token: str) -> dict:
        """申请切换令牌：并发指令只有一条拿得到，拿不到的拿到明确拒绝。"""

        return self._arbiter.acquire(token, self._state.generation)

    def release_transfer(self, token: str) -> dict:
        """归还切换令牌。"""

        return self._arbiter.release(token)

    def is_tied(self) -> bool:
        """是否处于并网态。"""

        return self._state.is_tied()

    def transfer(self, target: str, reason: str, *, token: str | None = None) -> dict:
        """执行一次并离网切换，返回切换记录。

        状态迁移与接触器动作在状态机的同一把锁内一次走完，中间不释放，因此外部
        观察不到"状态已切、接触器没动"的撕裂中间态。``token`` 非空时必须与当前
        切换令牌持有者一致——并发进来的另一条指令即使绕过编排直接调本体，也会
        以 ``transfer_preempted`` 被挡下。
        """

        if self._cut.is_tripped():
            raise InterlockError("PCS 处于跳闸态，需先复位", component="pcs")
        if token is not None and self._arbiter.holder() not in (None, token):
            raise InterlockError(
                f"切换被抢先：{token} 被 {self._arbiter.holder()} 拒绝",
                component="pcs",
                details={
                    "reason": "transfer_preempted",
                    "token": token,
                    "preempted_by": self._arbiter.holder(),
                },
            )
        with self._state.locked():
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
        """执行跳闸：先切到跳闸态再分断接触器，全程同一把锁。"""

        self._protection.note_trip()
        self._cut.trip(reason)
        revoked = self._arbiter.revoke(reason)
        with self._state.locked():
            self._state.force("tripped", reason)
            if self._switch.is_closed():
                self._switch.open()
            self._power.command(0.0)
            self._ramp.reset()
            state = self._state.state
        return {
            "state": state,
            "reasons": self._cut.reasons(),
            "trips": self._protection.trips(),
            "arbiter": revoked,
        }

    def reset_trip(self, token: str | None = None) -> dict:
        """复位跳闸并回到确定的停机态。

        复位与并网/离网共用同一枚切换令牌：切换进行中的复位请求会被明确拒绝
        （``transfer_preempted``），反之亦然。复位落定在停机态，绝不留在跳闸态与
        停机态之间。
        """

        if token is not None:
            self._arbiter.acquire(token, self._state.generation)
        try:
            with self._state.locked():
                was_tripped = self._cut.clear()
                self._state.force("stopped", "trip_reset")
                if self._switch.is_closed():
                    self._switch.open()
                self._power.command(0.0)
                self._ramp.reset()
                state = self._state.state
        finally:
            if token is not None:
                self._arbiter.release(token)
        return {"was_tripped": was_tripped, "state": state, "resets": self._cut.resets()}

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
