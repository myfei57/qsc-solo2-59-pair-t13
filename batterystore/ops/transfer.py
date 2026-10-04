"""并离网切换编排。

顺序固定为「BMS 就绪确认 → PCS 切换 → 并网校验 → 功率输出」。BMS 没就绪
就直接返回拒绝，不碰 PCS；并网校验不通过则把 PCS 退回离网态，避免带着越限
的并网点继续输出。每一步都写进步骤流水，审计据此核对先后。
"""

from __future__ import annotations

from ..errors import StoreError


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

    try:
        if pcs.state_machine.state == "stopped":
            # 停机态不能直接并网：先在离网态建立输出电压，再闭合并网接触器。
            steps.append(
                {
                    "component": "pcs",
                    "action": "transfer",
                    "detail": pcs.transfer("off_grid", "build_off_grid_voltage"),
                }
            )
        transfer = pcs.transfer("grid_tie", "transfer_request")
    except StoreError as error:
        steps.append({"component": "pcs", "action": "transfer_rejected", "detail": error.as_record()})
        return {"station": station, "ok": False, "steps": steps, "violations": ["pcs_transfer_rejected"]}
    steps.append({"component": "pcs", "action": "transfer", "detail": transfer})

    check = grid.check(frequency_hz, power_kw, now)
    steps.append({"component": "grid", "action": "tie_check", "detail": check})
    if "frequency_out_of_band" in check["violations"]:
        pcs.transfer("off_grid", "tie_check_failed")
        violations.append("frequency_out_of_band")
        return {"station": station, "ok": False, "steps": steps, "violations": violations}

    clamped = grid.clamp_for_ramp(power_kw)
    steps.append({"component": "grid", "action": "clamp", "detail": clamped})
    derate = pcs.apply_derate(grid=clamped["ratio"])
    point = pcs.set_point(clamped["allowed_kw"], dt, derate)
    steps.append({"component": "pcs", "action": "power_output", "detail": point})
    if point["violations"]:
        violations.extend(point["violations"])
    return {"station": station, "ok": not violations, "steps": steps, "violations": violations}
