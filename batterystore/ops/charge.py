"""温控充电编排。

顺序固定为「均衡完成核对 → 温控降额 → 电压核对 → 电流阶梯升流 → 库仑累计 →
配额记账」。电压没稳定到期望带内就不允许升流，升流被拒即中止整条链；充电
电量按每段实际功率与步长记账，配额不足时同样中止。
"""

from __future__ import annotations

from ..errors import StoreError


def charge_rack(
    pcs,
    bms,
    temp,
    balance,
    quota,
    soc,
    rack,
    grid,
    station: str,
    *,
    steps: int,
    dt: float,
    now: float,
) -> dict:
    """执行一次充电编排，返回带步骤与违约项的报告。"""

    flow: list[dict] = []
    violations: list[str] = []

    derate_ratio = temp.charge_limit_ratio()
    plan = bms.charge_plan(
        rack,
        pcs.limits,
        balance_complete=balance.is_complete(),
        temp_derate_ratio=derate_ratio,
        balance_min_delta_mv=balance.limits.target_delta_mv,
    )
    flow.append({"component": "bms", "action": "charge_plan", "detail": plan.as_dict()})
    if not plan.allowed:
        return {"station": station, "ok": False, "steps": flow, "violations": list(plan.reasons)}

    derate = pcs.apply_derate(temperature=derate_ratio, grid=1.0)
    flow.append({"component": "temp", "action": "derate", "detail": derate.as_dict()})

    ladder = pcs.ladder
    ladder.begin(plan.current_a)
    current = ladder.lower_to(min(plan.current_a, pcs.limits.current_step_a))
    expected_v = sum(cell.rating_v for cell in rack.cells())
    tolerance_v = 0.02 * len(rack.cells())

    for index in range(steps):
        settled = ladder.verify_voltage(rack.voltage_v(), expected_v, tolerance_v)
        flow.append(
            {
                "component": "pcs",
                "action": "verify_voltage",
                "detail": {"index": index + 1, "settled": settled, "current_a": round(current, 3)},
            }
        )
        if not settled:
            violations.append(f"voltage_not_settled_step_{index + 1}")
            break
        try:
            current = ladder.raise_to(current + pcs.limits.current_step_a)
        except StoreError as error:
            violations.append("current_raise_rejected")
            flow.append({"component": "pcs", "action": "raise_rejected", "detail": error.as_record()})
            break
        energy_kwh = abs(current) * rack.voltage_v() * dt / 3600.0 / 1000.0
        try:
            quota.record_charge(energy_kwh, now)
        except StoreError as error:
            violations.append("quota_exceeded")
            flow.append({"component": "quota", "action": "charge_rejected", "detail": error.as_record()})
            break
        delta_ah = soc.accumulate(abs(current), dt)
        flow.append(
            {
                "component": "soc",
                "action": "accumulate",
                "detail": {"index": index + 1, "current_a": round(current, 3), "delta_ah": round(delta_ah, 6)},
            }
        )
        grid.record_flow(-abs(current) * rack.voltage_v() / 1000.0, dt)

    estimate = soc.value(now)
    rack.set_soc(estimate.soc_pct)
    flow.append({"component": "soc", "action": "estimate", "detail": estimate.as_dict()})
    return {"station": station, "ok": not violations, "steps": flow, "violations": violations}
