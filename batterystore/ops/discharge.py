"""限额放电编排。

顺序固定为「并网限额钳位 → 爬坡 → 电量累计 → 配额记账」。钳位必须在爬坡
之前完成：带限功率参数的放电指令如果先爬坡再钳位，并网点会在一瞬间越限。
"""

from __future__ import annotations

from ..errors import StoreError


def discharge_rack(
    pcs,
    grid,
    quota,
    soc,
    rack,
    station: str,
    *,
    power_kw: float,
    dt: float,
    now: float,
) -> dict:
    """执行一次放电编排，返回带步骤与违约项的报告。"""

    flow: list[dict] = []
    violations: list[str] = []

    if pcs.cut.is_tripped():
        return {"station": station, "ok": False, "steps": flow, "violations": ["pcs_tripped"]}

    if not pcs.is_tied():
        pcs.transfer("off_grid", "discharge_request")
        pcs.transfer("grid_tie", "discharge_request")
    clamped = grid.clamp_for_ramp(abs(float(power_kw)))
    flow.append({"component": "grid", "action": "clamp_before_ramp", "detail": clamped})
    derate = pcs.apply_derate(grid=clamped["ratio"], temperature=1.0)
    point = pcs.set_point(clamped["allowed_kw"], dt, derate)
    flow.append({"component": "pcs", "action": "ramp", "detail": point})
    if point["violations"]:
        violations.extend(point["violations"])

    energy_kwh = abs(point["ramped_kw"]) * dt / 3600.0
    arc = grid.record_flow(point["ramped_kw"], dt)
    flow.append({"component": "grid", "action": "energy", "detail": arc})
    try:
        quota.record_discharge(energy_kwh, now)
    except StoreError as error:
        violations.append("quota_exceeded")
        flow.append({"component": "quota", "action": "discharge_rejected", "detail": error.as_record()})
        return {"station": station, "ok": False, "steps": flow, "violations": violations}

    delta_ah = soc.accumulate(-abs(point["ramped_kw"]) * 1000.0 / max(rack.voltage_v(), 1e-9), dt)
    estimate = soc.value(now)
    rack.set_soc(estimate.soc_pct)
    flow.append(
        {
            "component": "soc",
            "action": "estimate",
            "detail": {**estimate.as_dict(), "delta_ah": round(delta_ah, 6)},
        }
    )
    return {"station": station, "ok": not violations, "steps": flow, "violations": violations}
