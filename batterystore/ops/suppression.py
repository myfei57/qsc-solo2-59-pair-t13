"""消防联动编排。

顺序固定为「烟温探测 → 开阀 → 开阀确认 → 断 PCS → 审计」。开阀没确认成功
就停在原地，不执行断 PCS，也不写"已落停"的假记录；确认成功后才断 PCS，
这样电池不会在灭火介质没到位时继续放电。
"""

from __future__ import annotations

from ..errors import StoreError


def suppress(
    fire,
    pcs,
    station: str,
    *,
    zone: str,
    smoke_ppm: float,
    temperature_c: float,
    now: float,
    confirm_dt: float,
) -> dict:
    """执行一次消防联动编排，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []

    detection = fire.detect(zone, smoke_ppm, temperature_c)
    steps.append({"component": "fire", "action": "detect", "detail": detection})
    if not detection["detected"]:
        return {"station": station, "ok": False, "steps": steps, "violations": ["not_detected"]}

    try:
        command = fire.begin_suppression(now)
    except StoreError as error:
        steps.append({"component": "fire", "action": "valve_rejected", "detail": error.as_record()})
        return {"station": station, "ok": False, "steps": steps, "violations": ["valve_command_rejected"]}
    steps.append({"component": "fire", "action": "valve_open", "detail": command})

    confirmed = fire.confirm_suppression(now + confirm_dt)
    steps.append(
        {
            "component": "fire",
            "action": "valve_confirm",
            "detail": {"confirmed": confirmed, "travel_mm": fire.valve.travel_mm()},
        }
    )
    if not confirmed:
        violations.append("valve_not_confirmed")
        return {"station": station, "ok": False, "steps": steps, "violations": violations}

    trip = pcs.trip(f"fire_suppression:{zone}")
    steps.append({"component": "pcs", "action": "trip", "detail": trip})
    mark = fire.mark_pcs_tripped({"state": trip["state"]})
    steps.append({"component": "fire", "action": "pcs_tripped", "detail": mark})
    audited = fire.mark_audited()
    steps.append({"component": "audit", "action": "marked", "detail": audited})
    return {"station": station, "ok": not violations, "steps": steps, "violations": violations}
