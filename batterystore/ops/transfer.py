"""并离网切换编排。

并网顺序固定为「切换仲裁 → BMS 就绪确认 → 离网建压 → 同期（频率）校验 → 闭合并网
开关 → 功率输出」。关键约束：并网接触器只能在同期条件满足**之后**闭合，校验不过
开关永远不动，避免带着频差/相差合闸把冲击电流与相位异常送进保护。

并发进来的两路切换指令在仲裁令牌处分出胜负：只有一条进入流程，另一条立即拿到
``transfer_preempted`` 拒绝（记录里写清抢先者 token）；因就绪/同期等条件不满足的
拒绝则标 ``condition_not_met``。两类拒绝在切换记录里分开记，巡检时一眼分清是被谁
抢先还是条件本身不成立。

中途任何失败都回滚到确定的停机态，不留"既并网又离网"的中间态。
"""

from __future__ import annotations

from ..errors import InterlockError, StoreError

#: 顺序选型：先在离网态建立电压，同期条件满足后再闭合并网开关。
#:
#: 备选「先并网再调压」是把 PCS 先挂到带电电网再向电网电压/频率靠拢：并网点在
#: 合闸瞬间存在压差与相差，冲击电流直接流入电网，相位差会被保护判成异常并顶掉
#: 开关，风险落在网侧且不可控。选定方案先本地建压（冲击只发生在 PCS 与空母线
#: 之间），同期不过就不闭合开关，网侧零冲击；保护不会被合闸瞬态误触发。
SYNC_SEQUENCE = {
    "selected": "build_off_grid_voltage_then_close_tie",
    "rejected_alternative": "tie_first_then_regulate",
    "rationale": (
        "先本地离网建压，同期（频率/电压窗口）满足后再闭合并网开关：合闸前两侧"
        "已同期，冲击电流最小且不流入电网；先并网再调压会在带电并网点带相差合闸，"
        "冲击电流直接入网并触发相位异常保护。"
    ),
}


def _rejected(station: str, steps: list[dict], violation: str, why: str, **detail) -> dict:
    """构造一条带拒绝归因的报告。"""

    return {
        "station": station,
        "ok": False,
        "steps": steps,
        "violations": [violation],
        "rejection": {"why": why, "violation": violation, **detail},
        "sequence": SYNC_SEQUENCE["selected"],
    }


def _rollback_to_stopped(pcs, token: str, steps: list[dict], reason_tag: str) -> None:
    """切换中途失败后回滚到确定的停机态，并记一条回滚流水。"""

    state = pcs.state_machine.state
    if state == "stopped":
        return
    if state == "tripped":
        # 跳闸态只能经复位离开，强行动接触器会违反联锁；跳闸本身已分断开关。
        steps.append({"component": "pcs", "action": "rollback_skipped_tripped", "detail": {"reason": reason_tag}})
        return
    rolled = pcs.transfer("stopped", f"rollback:{reason_tag}", token=token)
    steps.append({"component": "pcs", "action": "rollback_stopped", "detail": rolled})


def transfer_to_grid(
    pcs,
    bms,
    rack,
    grid,
    station: str,
    *,
    token: str,
    frequency_hz: float,
    power_kw: float,
    dt: float,
    now: float,
) -> dict:
    """执行一次并网切换编排，返回带步骤、违约项与拒绝归因的报告。"""

    steps: list[dict] = []
    violations: list[str] = []

    # 1) 切换仲裁：并发指令只有一条拿到令牌，另一条立即知道被谁抢先。
    try:
        granted = pcs.acquire_transfer(token)
    except InterlockError as error:
        record = error.as_record()
        steps.append({"component": "pcs", "action": "transfer_arbitration_rejected", "detail": record})
        return _rejected(
            station,
            steps,
            "transfer_preempted",
            "preempted",
            token=record.get("token"),
            preempted_by=record.get("preempted_by"),
        )
    steps.append({"component": "pcs", "action": "transfer_arbitration", "detail": granted})

    try:
        # 2) BMS 就绪判据：不满足直接拒绝，不碰 PCS 状态与接触器。
        try:
            ready = bms.require_ready(rack)
        except StoreError as error:
            steps.append({"component": "bms", "action": "ready_rejected", "detail": error.as_record()})
            return _rejected(station, steps, "bms_not_ready", "condition_not_met", gate="bms_ready")
        steps.append(
            {
                "component": "bms",
                "action": "ready_confirmed",
                "detail": {"rack_id": rack.rack_id, "delta_mv": round(ready.delta_mv, 2)},
            }
        )

        # 3) 离网建压（选型顺序的前半步）：停机态不能直接并网，先在离网态起压。
        current = pcs.state_machine.state
        if current == "tripped":
            steps.append(
                {
                    "component": "pcs",
                    "action": "transfer_rejected",
                    "detail": {"reason": "pcs_tripped", "state": current},
                }
            )
            return _rejected(station, steps, "pcs_tripped", "condition_not_met", gate="pcs_not_tripped")
        if current == "grid_tie":
            steps.append(
                {
                    "component": "pcs",
                    "action": "already_tied",
                    "detail": {"state": current, "generation": pcs.state_machine.generation},
                }
            )
            return _rejected(station, steps, "already_grid_tie", "condition_not_met", gate="source_state")
        if current == "stopped":
            built = pcs.transfer("off_grid", "build_off_grid_voltage", token=token)
            steps.append({"component": "pcs", "action": "build_off_grid_voltage", "detail": built})

        # 4) 同期校验：频率窗口不满足就拒绝，并网开关保持分断，随后回滚停机态。
        check = grid.check(frequency_hz, power_kw, now)
        steps.append({"component": "grid", "action": "sync_check", "detail": check})
        if "frequency_out_of_band" in check["violations"]:
            _rollback_to_stopped(pcs, token, steps, "sync_check_failed")
            return _rejected(
                station,
                steps,
                "frequency_out_of_band",
                "condition_not_met",
                gate="grid_sync",
                frequency_hz=check["frequency_hz"],
            )

        # 5) 原子落定：状态迁移与接触器闭合在 PCS 同一把锁内一次走完。
        try:
            commit = pcs.transfer("grid_tie", "close_tie_after_sync", token=token)
        except StoreError as error:
            steps.append({"component": "pcs", "action": "transfer_rejected", "detail": error.as_record()})
            _rollback_to_stopped(pcs, token, steps, "tie_close_rejected")
            return _rejected(station, steps, "pcs_transfer_rejected", "condition_not_met", gate="mode_table")
        commit["sequence"] = SYNC_SEQUENCE
        steps.append({"component": "pcs", "action": "tie_closed", "detail": commit})

        # 6) 并网之后才钳位、降额与爬坡输出。
        clamped = grid.clamp_for_ramp(power_kw)
        steps.append({"component": "grid", "action": "clamp", "detail": clamped})
        derate = pcs.apply_derate(grid=clamped["ratio"])
        point = pcs.set_point(clamped["allowed_kw"], dt, derate)
        steps.append({"component": "pcs", "action": "power_output", "detail": point})
        if point["violations"]:
            violations.extend(point["violations"])
        return {
            "station": station,
            "ok": not violations,
            "steps": steps,
            "violations": violations,
            "sequence": SYNC_SEQUENCE["selected"],
        }
    finally:
        released = pcs.release_transfer(token)
        steps.append({"component": "pcs", "action": "transfer_arbitration_released", "detail": released})


def transfer_off_grid(pcs, station: str, *, token: str) -> dict:
    """执行一次离网切换编排：仲裁 → 分断并网开关 → 零功率。"""

    steps: list[dict] = []

    try:
        granted = pcs.acquire_transfer(token)
    except InterlockError as error:
        record = error.as_record()
        steps.append({"component": "pcs", "action": "transfer_arbitration_rejected", "detail": record})
        return _rejected(
            station,
            steps,
            "transfer_preempted",
            "preempted",
            token=record.get("token"),
            preempted_by=record.get("preempted_by"),
        )
    steps.append({"component": "pcs", "action": "transfer_arbitration", "detail": granted})

    try:
        current = pcs.state_machine.state
        if current == "tripped":
            steps.append(
                {"component": "pcs", "action": "transfer_rejected", "detail": {"reason": "pcs_tripped", "state": current}}
            )
            return _rejected(station, steps, "pcs_tripped", "condition_not_met", gate="pcs_not_tripped")
        if current == "off_grid":
            steps.append(
                {
                    "component": "pcs",
                    "action": "already_off_grid",
                    "detail": {"state": current, "generation": pcs.state_machine.generation},
                }
            )
            return _rejected(station, steps, "already_off_grid", "condition_not_met", gate="source_state")
        transfer = pcs.transfer("off_grid", "off_grid_request", token=token)
        steps.append({"component": "pcs", "action": "transfer", "detail": transfer})
        return {
            "station": station,
            "ok": True,
            "steps": steps,
            "violations": [],
            "sequence": SYNC_SEQUENCE["selected"],
        }
    finally:
        released = pcs.release_transfer(token)
        steps.append({"component": "pcs", "action": "transfer_arbitration_released", "detail": released})
