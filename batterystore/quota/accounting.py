"""结算。

结算把本周期充放电电量与峰谷电价折成电费与套利收益：充电按当时电价计费，
放电按当时电价计价，两者的差额是本周期收益。控制台与配额封顶判据都读这一份。
"""

from __future__ import annotations


def settle(charge_kwh: float, discharge_kwh: float, charge_rate: float, discharge_rate: float) -> dict:
    """按峰谷电价结算一次充放电。"""

    charge_cost = max(0.0, float(charge_kwh)) * float(charge_rate)
    discharge_value = max(0.0, float(discharge_kwh)) * float(discharge_rate)
    return {
        "charge_cost": round(charge_cost, 4),
        "discharge_value": round(discharge_value, 4),
        "margin": round(discharge_value - charge_cost, 4),
        "charge_rate": float(charge_rate),
        "discharge_rate": float(discharge_rate),
    }
