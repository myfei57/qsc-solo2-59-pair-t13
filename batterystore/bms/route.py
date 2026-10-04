"""告警路由。

告警的展示编号一律按编号映射的最新代际解析：重编号之后仍按旧编号路由会让
运维找到错误的簇。路由结果只增加展示字段，不修改告警本身的簇标识，历史
回放依然能定位到真实设备。
"""

from __future__ import annotations

from ..rack.alarms import RackAlarm
from ..rack.mapping import RackMapping


def route_alarm(alarm: RackAlarm, mapping: RackMapping) -> dict:
    """把一条告警按最新编号映射成展示记录。"""

    payload = alarm.as_dict()
    payload["label"] = mapping.label_of(alarm.rack_id)
    payload["zone"] = mapping.zone_of(alarm.rack_id)
    payload["mapping_epoch"] = mapping.epoch
    return payload


def route_alarms(alarms: list[RackAlarm], mapping: RackMapping) -> list[dict]:
    """批量路由告警。"""

    return [route_alarm(alarm, mapping) for alarm in alarms]
