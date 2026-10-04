"""均衡组件。

``Balancer`` 把目标选择、脉冲节拍与状态机串成一条链：启动时选出需要放电的
单体，之后每个控制周期推进一个节拍并把被选单体的电压往簇内最低值拉。压差
回到目标带内即判完成，超时则中止；充电放行只认"完成"这一档。
"""

from __future__ import annotations

from ..config import BalanceLimits
from ..rack.cells import Cell
from .run import BalanceRun
from .select import cell_delta_mv, select_cells
from .snapshot import BalanceSnapshot
from .state import BalanceState


class Balancer:
    """电池均衡组件。"""

    def __init__(self, limits: BalanceLimits) -> None:
        self._limits = limits
        self._state = BalanceState()
        self._run = BalanceRun(limits)
        self._delta_mv = 0.0

    @property
    def limits(self) -> BalanceLimits:
        return self._limits

    @property
    def state(self) -> BalanceState:
        return self._state

    def is_complete(self) -> bool:
        """均衡是否已完成。"""

        return self._state.is_complete()

    def delta_mv(self) -> float:
        """返回最近一次测得的压差。"""

        return self._delta_mv

    def start(self, cells: list[Cell]) -> dict:
        """启动一次均衡，返回选定目标。"""

        targets = select_cells(cells, self._limits.target_delta_mv, self._limits.min_cells)
        self._delta_mv = cell_delta_mv(cells)
        if not targets:
            self._state.transition("complete", "delta_within_target")
            return {"targets": [], "delta_mv": round(self._delta_mv, 2), "started": False}
        self._run.begin(targets)
        self._state.transition("running", "targets_selected")
        return {"targets": targets, "delta_mv": round(self._delta_mv, 2), "started": True}

    def advance(self, dt: float, cells: list[Cell]) -> dict:
        """推进一个均衡节拍，返回本拍结果。"""

        if not self._state.state == "running":
            return {"phase": "idle", "delta_mv": round(self._delta_mv, 2), "complete": self.is_complete()}
        phase = self._run.advance(dt)
        if phase == "pulse":
            self._apply_pulse(cells)
        self._delta_mv = cell_delta_mv(cells)
        complete = self._delta_mv <= self._limits.target_delta_mv
        if complete:
            self._state.transition("complete", "delta_within_target")
        elif self._run.overrun():
            self._state.transition("aborted", "duration_exceeded")
        return {
            "phase": phase,
            "delta_mv": round(self._delta_mv, 2),
            "complete": complete,
            "run": self._run.summary(),
        }

    def reset(self) -> dict:
        """复位均衡状态，返回复位前的档位。"""

        previous = self._state.state
        self._run.begin([])
        self._state.transition("idle", "reset")
        return {"previous": previous, "counts": self._state.counts()}

    def _apply_pulse(self, cells: list[Cell]) -> None:
        """给被选中的单体放电一个步长。"""

        targets = set(self._run.targets())
        if not targets:
            return
        floor = min(cell.voltage_v for cell in cells)
        for cell in cells:
            if cell.cell_id in targets and cell.voltage_v > floor:
                cell.update(voltage_v=cell.voltage_v - min(0.002, (cell.voltage_v - floor) / 2.0))

    def snapshot(self) -> BalanceSnapshot:
        """返回均衡状态快照。"""

        return BalanceSnapshot(
            state=self._state.state,
            counts=self._state.counts(),
            run=self._run.summary(),
            targets=self._run.targets(),
            delta_mv=self._delta_mv,
            target_delta_mv=self._limits.target_delta_mv,
        )
