"""PCS 组件。

``Pcs`` 把状态机、接触器、爬坡器、电流阶梯、降额合成与保护判据收在一个
入口后面，对外只暴露四个动作：并离网切换、功率指令、降额下发与跳闸复位。

切换顺序选型为「先离网建压、同期核对通过后再闭合并网接触器」：闭合瞬间
两侧压差与相位差最小，冲击电流最低，保护不会因合闸冲击动作；若先并网再
调压，失配直接转化为冲击电流，正是保护被顶掉的来源。代价是并网前多一段
离网建压间隔。选型理由随每条切换记录落盘。

整次切换只占一把锁：条件核对、状态迁移、接触器动作在同一个临界区内落定，
并发指令先到先落，后到的一律拒绝——被抢先的带上持票人，条件不满足的带上
条件名。跳闸与复位走同一把锁，复位后状态、接触器、功率一起回到停机态。
"""

from __future__ import annotations

import threading

from ..errors import InterlockError
from ..config import PcsLimits
from .current import CurrentLadder
from .curve import EfficiencyCurve
from .cut import CutOff
from .derate import DerateFactor, combine_ratios
from .mode import MODES, ModeTable
from .power import PowerController
from .protection import PcsProtection
from .ramp import RampLimiter
from .snapshot import PcsSnapshot
from .state import PcsState
from .switch import TransferSwitch

TRANSFER_ORDER = "off_grid_first"
TRANSFER_ORDER_RATIONALE = (
    "先在离网态建立输出电压并核对同期窗口，再闭合并网接触器："
    "闭合瞬间两侧压差与相位差最小，冲击电流最低，保护不会因合闸冲击动作；"
    "若先并网再调压，失配直接转化为冲击电流，正是保护被顶掉的来源。"
    "代价是并网前多一段离网建压间隔。"
)


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
        self._transfer_lock = threading.Lock()
        self._transfer_holder: dict | None = None

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

    def is_consistent(self) -> bool:
        """状态机与接触器是否互相印证：并网当且仅当接触器闭合。"""

        with self._transfer_lock:
            return (self._state.state == "grid_tie") == self._switch.is_closed()

    def transfer(self, target: str, reason: str, *, sync: dict | None = None, actor: str | None = None) -> dict:
        """执行一次并离网切换，返回切换记录。

        临界区只容一路指令：锁被占时按"被抢先"拒绝并给出持票人；条件
        不满足时按"条件"拒绝并给出条件名。全部条件通过后才一次性落定
        状态与接触器，中途出错回滚到来态，不停在两个态之间。
        """

        if not self._transfer_lock.acquire(blocking=False):
            holder = dict(self._transfer_holder) if self._transfer_holder else {}
            who = holder.get("actor") or "另一路切换指令"
            raise InterlockError(
                f"并离网切换被 {who} 抢先占用，本次 {target} 未生效",
                component="pcs",
                detail={"rejected": "preempted", "holder": holder, "target": target},
            )
        self._transfer_holder = {"actor": actor or reason, "target": target, "reason": reason}
        try:
            return self._transfer_locked(target, reason, sync=sync, actor=actor)
        finally:
            self._transfer_holder = None
            self._transfer_lock.release()

    def _transfer_locked(self, target: str, reason: str, *, sync: dict | None, actor: str | None) -> dict:
        """在切换锁内核对条件并落定一次迁移。"""

        if self._cut.is_tripped():
            raise InterlockError(
                "PCS 处于跳闸态，需先复位",
                component="pcs",
                detail={"rejected": "condition", "condition": "tripped", "target": target},
            )
        if target not in MODES:
            raise InterlockError(
                f"未知的 PCS 模式: {target}",
                component="pcs",
                detail={"rejected": "condition", "condition": "unknown_mode", "target": target},
            )
        source = self._state.state
        if not self._state.table.allows(source, target):
            raise InterlockError(
                f"不允许从 {source} 迁移到 {target}",
                component="pcs",
                detail={"rejected": "condition", "condition": "illegal_transition", "from": source, "to": target},
            )
        sync_record = None
        if sync is not None:
            sync_record = {
                "ok": bool(sync.get("ok")),
                "frequency_hz": sync.get("frequency_hz"),
                "violations": list(sync.get("violations", [])),
            }
        if target == "grid_tie" and sync_record is not None and not sync_record["ok"]:
            raise InterlockError(
                "同期条件不满足，拒绝闭合并网接触器",
                component="pcs",
                detail={"rejected": "condition", "condition": "sync_not_met", "violations": sync_record["violations"]},
            )
        self._state.transition(target, reason)
        try:
            self._settle_switch(target)
            if target != "grid_tie":
                self._power.command(0.0)
                self._ramp.reset()
        except Exception:
            self._state.force(source, "transfer_rollback")
            self._settle_switch(source)
            raise
        self._transfers += 1
        return {
            "from": source,
            "to": target,
            "reason": reason,
            "actor": actor or reason,
            "order": TRANSFER_ORDER,
            "rationale": TRANSFER_ORDER_RATIONALE,
            "sync": sync_record,
            "generation": self._state.generation,
            "switch": self._switch.as_dict(),
            "transfers": self._transfers,
        }

    def _settle_switch(self, target: str) -> None:
        """让接触器与目标态一致：并网闭合，其余分断。"""

        if target == "grid_tie":
            if not self._switch.is_closed():
                self._switch.close()
        elif self._switch.is_closed():
            self._switch.open()

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
        """执行跳闸：先切到跳闸态再分断接触器。保护与切换共用一把锁，不会插在切换中途。"""

        with self._transfer_lock:
            self._protection.note_trip()
            self._cut.trip(reason)
            self._state.force("tripped", reason)
            if self._switch.is_closed():
                self._switch.open()
            self._power.command(0.0)
            self._ramp.reset()
            return {"state": self._state.state, "reasons": self._cut.reasons(), "trips": self._protection.trips()}

    def reset_trip(self) -> dict:
        """复位跳闸并回到确定的停机态：状态、接触器、功率一起落定。"""

        with self._transfer_lock:
            was_tripped = self._cut.clear()
            self._state.force("stopped", "trip_reset")
            if self._switch.is_closed():
                self._switch.open()
            self._power.command(0.0)
            self._ramp.reset()
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
