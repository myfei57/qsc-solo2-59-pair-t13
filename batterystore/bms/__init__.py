"""BMS：就绪判据、故障闩锁、校准、保护与告警路由。"""

from __future__ import annotations

from .bms import Bms
from .calibrate import Calibration
from .charge import ChargePlan, build_charge_plan
from .fault import FaultRegistry
from .latch import FaultLatch
from .protection import evaluate_protection
from .ready import ReadyGate, ReadyReport
from .route import route_alarm, route_alarms
from .snapshot import BmsSnapshot
from .status import BmsStatus
from .voltage import charge_headroom_mv

__all__ = [
    "Bms",
    "BmsSnapshot",
    "BmsStatus",
    "Calibration",
    "ChargePlan",
    "FaultLatch",
    "FaultRegistry",
    "ReadyGate",
    "ReadyReport",
    "build_charge_plan",
    "charge_headroom_mv",
    "evaluate_protection",
    "route_alarm",
    "route_alarms",
]
