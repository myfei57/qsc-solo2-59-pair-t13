"""消防联动组件。

``FireLinkage`` 只做自己该做的三段：探测、开阀、确认到位。断 PCS 不在这个
组件里——它由联动编排在确认到位之后调用，避免消防组件反向依赖 PCS。开阀
没确认成功时 :meth:`FireLinkage.release_ready` 保持假，编排据此中止落停。
"""

from __future__ import annotations

from ..config import FireLimits
from .snapshot import FireSnapshot
from .stage import SuppressionStage
from .valve import SuppressionValve
from .zones import ZoneDetectors


class FireLinkage:
    """消防联动组件。"""

    def __init__(self, limits: FireLimits, zones: list[str]) -> None:
        self._limits = limits
        self._detectors = ZoneDetectors(zones)
        self._valve = SuppressionValve(limits.valve_travel_mm, limits.valve_confirm_s)
        self._stages = SuppressionStage()
        self._zone = ""
        self._pcs_tripped = False
        self._holds = 0
        self._aborts = 0

    @property
    def limits(self) -> FireLimits:
        return self._limits

    @property
    def detectors(self) -> ZoneDetectors:
        return self._detectors

    @property
    def valve(self) -> SuppressionValve:
        return self._valve

    @property
    def stages(self) -> SuppressionStage:
        return self._stages

    def detect(self, zone: str, smoke_ppm: float, temperature_c: float) -> dict:
        """写入某分区读数并判定是否起火。"""

        reading = self._detectors.update(zone, smoke_ppm, temperature_c)
        detected = self._limits.detected(reading["smoke_ppm"], reading["temperature_c"])
        if detected:
            self._zone = zone
            self._stages.enter("detect", {"zone": zone, **reading})
        return {"zone": zone, "detected": detected, **reading}

    def scan(self) -> list[str]:
        """扫描全部分区，返回越线分区。"""

        tripped = self._detectors.detections(self._limits)
        for zone in tripped:
            self._stages.enter("detect", {"zone": zone, "source": "scan"})
        if tripped:
            self._zone = tripped[0]
        return tripped

    def begin_suppression(self, now: float) -> dict:
        """发出开阀指令，返回指令记录。"""

        record = self._valve.open(now)
        self._stages.enter("valve_open", {"zone": self._zone, **record})
        return record

    def confirm_suppression(self, now: float) -> bool:
        """核对开阀到位，未确认时不计阶段。"""

        confirmed = self._valve.confirm(now)
        if confirmed:
            self._stages.enter(
                "valve_confirmed",
                {
                    "zone": self._zone,
                    "travel_mm": self._valve.travel_mm(),
                    "commanded": self._valve.is_commanded(),
                },
            )
            self._holds += 1
        else:
            self._aborts += 1
        return confirmed

    def release_ready(self) -> bool:
        """开阀是否已确认，可以继续断 PCS。"""

        return self._valve.is_confirmed()

    def mark_pcs_tripped(self, detail: dict | None = None) -> dict:
        """记录 PCS 已断开。"""

        self._pcs_tripped = True
        return self._stages.enter("pcs_trip", {"zone": self._zone, **dict(detail or {})})

    def mark_audited(self) -> dict:
        """记录审计已落盘。"""

        return self._stages.enter("audit", {"zone": self._zone, "completed": self._stages.completed()})

    def reset(self) -> dict:
        """复位联动：关阀、清阶段与标志。"""

        was_open = self._valve.close()
        self._stages = SuppressionStage()
        self._pcs_tripped = False
        self._zone = ""
        return {"was_open": was_open, "releases": self._holds}

    def snapshot(self) -> FireSnapshot:
        """返回消防状态快照。"""

        return FireSnapshot(
            detectors=self._detectors.snapshot(),
            valve=self._valve.as_dict(),
            stages=self._stages.entries(),
            sequence=self._stages.sequence(),
            release_ready=self._valve.is_confirmed(),
            pcs_tripped=self._pcs_tripped,
            holds=self._holds,
            aborts=self._aborts,
        )
