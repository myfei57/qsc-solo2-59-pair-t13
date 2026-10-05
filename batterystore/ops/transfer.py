"""并离网切换编排。

顺序固定为「BMS 就绪确认 → 离网建压 → 同期校验 → 原子并网 → 功率输出」。
选型定为先建压后合闸：离网态先把输出电压建起来，同期窗口（频率）核对通过
后，PCS 在临界区内一次性完成状态迁移与接触器闭合——闭合瞬间压差最小，
冲击电流最低，保护不会因合闸冲击动作。BMS 没就绪就直接拒绝，不碰 PCS；
同期不满足就停在离网态，离网是确定态，不是两态之间，无需回滚。切换被拒
时分清"被谁抢先"与"条件不满足"，每一步都写进步骤流水，审计据此核对先后。
"""

from __future__ import annotations

from ..errors import StoreError


def _transfer_rejection(error: StoreError) -> tuple[dict, str]:
    """把一次切换拒绝翻译成步骤与违约项：被抢先与条件不满足分开记账。"""

    if error.detail.get("rejected") == "preempted":
        return {"component": "pcs", "action": "transfer_preempted", "detail": error.as_record()}, "pcs_transfer_preempted"
    return {"component": "pcs", "action": "transfer_rejected", "detail": error.as_record()}, "pcs_transfer_rejected"


def transfer_to_grid(
    pcs,
    bms,
    rack,
    grid,
    station: str,
    *,
    frequency_hz: float,
    power_kw: float,
    dt: float,
    now: float,
    actor: str | None = None,
) -> dict:
    """执行一次并网切换编排，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []

    try:
        ready = bms.require_ready(rack)
    except StoreError as error:
        steps.append({"component": "bms", "action": "ready_rejected", "detail": error.as_record()})
        return {"station": station, "ok": False, "steps": steps, "violations": ["bms_not_ready"]}
    steps.append(
        {
            "component": "bms",
            "action": "ready_confirmed",
            "detail": {"rack_id": rack.rack_id, "delta_mv": round(ready.delta_mv, 2)},
        }
    )

    if pcs.state_machine.state == "stopped":
        # 停机态不能直接并网：先在离网态建立输出电压，再核对同期、闭合并网接触器。
        try:
            built = pcs.transfer("off_grid", "build_off_grid_voltage", actor=actor)
        except StoreError as error:
            step, violation = _transfer_rejection(error)
            steps.append(step)
            return {"station": station, "ok": False, "steps": steps, "violations": [violation]}
        steps.append({"component": "pcs", "action": "transfer", "detail": built})

    check = grid.check(frequency_hz, power_kw, now)
    steps.append({"component": "grid", "action": "tie_check", "detail": check})
    sync = {
        "ok": "frequency_out_of_band" not in check["violations"],
        "frequency_hz": check["frequency_hz"],
        "violations": list(check["violations"]),
    }
    if not sync["ok"]:
        violations.append("frequency_out_of_band")
        if pcs.is_tied():
            # 已在并网态时频率越窗：退回离网，不带着越限的并网点继续输出。
            steps.append(
                {"component": "pcs", "action": "transfer", "detail": pcs.transfer("off_grid", "tie_check_failed", actor=actor)}
            )
        return {"station": station, "ok": False, "steps": steps, "violations": violations}

    try:
        transfer = pcs.transfer("grid_tie", "transfer_request", sync=sync, actor=actor)
    except StoreError as error:
        step, violation = _transfer_rejection(error)
        steps.append(step)
        return {"station": station, "ok": False, "steps": steps, "violations": [violation]}
    steps.append({"component": "pcs", "action": "transfer", "detail": transfer})

    clamped = grid.clamp_for_ramp(power_kw)
    steps.append({"component": "grid", "action": "clamp", "detail": clamped})
    derate = pcs.apply_derate(grid=clamped["ratio"])
    point = pcs.set_point(clamped["allowed_kw"], dt, derate)
    steps.append({"component": "pcs", "action": "power_output", "detail": point})
    if point["violations"]:
        violations.extend(point["violations"])
    return {"station": station, "ok": not violations, "steps": steps, "violations": violations}


def transfer_to_offgrid(pcs, station: str, *, actor: str | None = None) -> dict:
    """执行一次离网切换编排：跳闸态直接拒绝，其余经切换临界区原子分断。"""

    steps: list[dict] = []
    violations: list[str] = []
    if pcs.state_machine.state == "tripped":
        violations.append("pcs_tripped")
        return {"station": station, "ok": False, "steps": steps, "violations": violations}
    try:
        transfer = pcs.transfer("off_grid", "off_grid_request", actor=actor)
    except StoreError as error:
        step, violation = _transfer_rejection(error)
        steps.append(step)
        violations.append(violation)
    else:
        steps.append({"component": "pcs", "action": "transfer", "detail": transfer})
    return {"station": station, "ok": not violations, "steps": steps, "violations": violations}
