"""平台装配与控制循环。

``Platform`` 把各组件按真实联控链接起来，并暴露五类动作：并离网切换、充放电、
均衡、温度采集与消防联动。控制循环每个周期做六件事：采集温度并刷新降额基线、
核对保护判据、核对各簇就绪、按校准估算 SOC、滚动配额周期、把计数落盘。跨模块
动作都由 :mod:`batterystore.ops` 的编排一次性走完并写审计。
"""

from __future__ import annotations

import threading

from .audit.log import AuditLog
from .audit.record import AuditRecord
from .balance.balance import Balancer
from .bms.bms import Bms
from .clock import Clock, SystemClock
from .config import StationConfig, config_to_mapping, default_config
from .errors import StoreError
from .eventbus import Event, EventBus
from .fire.fire import FireLinkage
from .grid.grid import GridTie
from .ids import IdFactory
from .ns.capacity import CapacityPlan, plan_capacity
from .ns.registry import NamespaceRegistry
from .ns.topology import Topology, build_default_topology
from .ops.charge import charge_rack
from .ops.discharge import discharge_rack
from .ops.suppression import suppress
from .ops.transfer import transfer_to_grid
from .pcs.pcs import Pcs
from .rack.cells import Cell
from .rack.mapping import RackMapping
from .rack.pack import Pack
from .rack.rack import Rack
from .soc.soc import SocEstimator
from .store.journal import JsonlJournal
from .store.jsonfile import JsonStore
from .temp.temp import TempControl
from .telemetry import TrendBuffer
from .quota.quota import QuotaLedger

DEFAULT_STATION = "station1"
DEFAULT_RACK = "rk-01"
DEFAULT_ZONE = "Z1"


def build_rack(rack_id: str, label: str, zone: str, config: StationConfig, packs: int = 8) -> Rack:
    """按配置造一簇电池：每包若干单体，电压初始等于当前额定值。"""

    per_pack = max(1, config.rack.cell_count // packs)
    built: list[Pack] = []
    for pack_index in range(packs):
        cells = [
            Cell(
                cell_id=f"{rack_id}-p{pack_index + 1}c{cell_index + 1}",
                nominal_v=config.rack.cell_nominal_v,
                rating_v=config.rack.cell_nominal_v,
                voltage_v=config.rack.cell_nominal_v,
                soc_pct=config.soc.initial_soc_pct,
            )
            for cell_index in range(per_pack)
        ]
        built.append(Pack(f"{rack_id}-p{pack_index + 1}", cells))
    rack = Rack(rack_id, built, zone)
    rack.set_soc(config.soc.initial_soc_pct)
    return rack


class Platform:
    """电化学储能电站簇级联控平台。"""

    def __init__(
        self,
        config: StationConfig | None = None,
        clock: Clock | None = None,
        station: str = DEFAULT_STATION,
        rack_count: int = 2,
    ) -> None:
        self.config = config or default_config()
        self.clock = clock or SystemClock()
        self.bus = EventBus()
        self.station = station

        store = JsonStore(self.config.storage_root)
        self.store = store
        self.audit = AuditLog(self.clock, self.bus, JsonlJournal(store.root, "audit", segment_limit=512))
        self.namespaces = NamespaceRegistry(station)
        self.topology: Topology = build_default_topology()
        self.trend = TrendBuffer(period_s=5.0)
        self.ids = IdFactory("op")
        self.mapping = RackMapping()

        self.racks: dict[str, Rack] = {}
        for index in range(max(1, rack_count)):
            rack_id = f"rk-{index + 1:02d}"
            zone = f"Z{(index % self.config.fire.zone_count) + 1}"
            self.racks[rack_id] = build_rack(rack_id, f"R{index + 1}", zone, self.config)
            self.mapping.assign(rack_id, f"R{index + 1}", zone)

        self.bms = Bms(self.config.bms, self.clock, self.config.rack, self.config.soc.calibrate_ttl_s)
        self.pcs = Pcs(self.config.pcs)
        self.temp = TempControl(self.config.temp)
        self.fire = FireLinkage(self.config.fire, [f"Z{i + 1}" for i in range(self.config.fire.zone_count)])
        self.grid = GridTie(self.config.grid)
        self.soc = SocEstimator(self.config.soc, self.bms.calibration)
        self.balancer = Balancer(self.config.balance)
        self.quota = QuotaLedger(self.config.quota)

        self._cycles = 0
        self._operations = 0
        self._faults_reported = 0
        self._drills = 0
        self._last_audit_ts = 0.0
        self._running = False
        self._lock = threading.RLock()
        self._register_namespaces()
        self._restore()
        self.bms.calibration.record(self.config.soc.initial_soc_pct, self.clock.now(), "startup")

    def _register_namespaces(self) -> None:
        """登记现场设备命名空间（控制台与审计共用同一套名字）。"""

        for area, device, kind in (
            ("station", "bms", "battery-management"),
            ("station", "pcs", "power-conversion"),
            ("station", "temp", "thermal-control"),
            ("station", "fire", "suppression-panel"),
            ("station", "grid", "tie-point"),
            ("station", "soc", "state-of-charge"),
            ("station", "balance", "cell-balancer"),
            ("station", "quota", "quota-ledger"),
            ("station", "audit", "run-audit"),
        ):
            self.namespaces.register(area, device, kind)
        for rack_id, rack in self.racks.items():
            self.namespaces.register("rack", rack_id, "battery-cluster")
            self.namespaces.register(rack.zone, rack_id, "fire-zone-member")

    def _restore(self) -> None:
        """从落盘状态恢复平台计数，保证重启后计数连续。"""

        tail = self.audit.replay_from_journal(limit=1)
        if tail:
            self._last_audit_ts = AuditRecord.from_dict(tail[-1]).ts
        state = self.store.read("platform_state")
        if self.store.exists("platform_state") and isinstance(state, dict):
            self._operations = int(state.get("operations", 0))
            self._cycles = int(state.get("cycles", 0))
            self._drills = int(state.get("drills", 0))

    def _persist(self) -> None:
        """落盘平台计数，供重启后对照。"""

        self.store.write(
            "platform_state",
            {
                "operations": self._operations,
                "cycles": self._cycles,
                "drills": self._drills,
                "station": self.station,
            },
        )

    def _rack(self, rack_id: str | None) -> Rack:
        """按标识取簇，缺省取第一簇。"""

        key = rack_id or DEFAULT_RACK
        if key not in self.racks:
            raise KeyError(f"未知的簇: {key}")
        return self.racks[key]

    def _record_operation(self, op_id: str, operation: str, report: dict) -> dict:
        """把编排步骤逐条写审计，并记一条汇总事件。"""

        for step in report.get("steps", []):
            detail = {
                key: value
                for key, value in step.get("detail", {}).items()
                if not isinstance(value, (dict, list))
                and key not in ("message", "component", "type", "topic", "action")
            }
            self.bus.publish(
                Event.of(
                    step["component"],
                    step["component"],
                    step["action"],
                    station=self.station,
                    op_id=op_id,
                    severity="notice",
                    **detail,
                )
            )
        for violation in report.get("violations", []):
            self.bus.publish(
                Event.of(
                    "audit",
                    "audit",
                    "interlock_rejected",
                    station=self.station,
                    op_id=op_id,
                    severity="alarm",
                    message=f"{operation} 被拒绝：{violation}",
                    violation=violation,
                )
            )
        summary = {
            "op_id": op_id,
            "operation": operation,
            "station": self.station,
            "ok": bool(report.get("ok")),
            "violations": list(report.get("violations", [])),
        }
        self.bus.publish(
            Event.of(
                "audit",
                "audit",
                f"{operation}_complete",
                severity="notice" if report.get("ok") else "warning",
                message=f"{operation} 完成" if report.get("ok") else f"{operation} 未完成",
                **summary,
            )
        )
        self._operations += 1
        self._persist()
        return summary

    def note_error(self, error: StoreError) -> dict:
        """把一次组件异常写进审计，返回落盘记录。"""

        payload = error.as_record()
        self.bus.publish(
            Event.of(
                payload["component"],
                payload["component"],
                "error",
                station=self.station,
                severity="warning",
                message=payload["message"],
            )
        )
        return payload

    def start(self) -> dict:
        """启动平台：核对拓扑与命名空间。"""

        with self._lock:
            self._running = True
            self.bms.online()
            ready = {name: True for name in self.topology.order()}
            topology = self.topology.verify(set(ready))
            self.bus.publish(Event.of("station", "station", "started", severity="notice", unit=self.station))
            return {
                "running": self._running,
                "station": self.station,
                "now_iso": self.clock.utc_iso(),
                "topology_order": self.topology.order(),
                "namespaces": self.namespaces.count(),
                "pending_stages": topology["missing"],
            }

    def stop(self) -> dict:
        """停运平台。"""

        with self._lock:
            self._running = False
            self.bms.offline()
            if self.pcs.state_machine.state in ("grid_tie", "off_grid"):
                self.pcs.transfer("stopped", "platform_stop")
            self.bus.publish(Event.of("station", "station", "stopped", severity="notice", unit=self.station))
            return {
                "running": self._running,
                "operations": self._operations,
                "cycles": self._cycles,
                "last_audit_ts": round(self._last_audit_ts, 3),
            }

    def reset_state(self) -> dict:
        """清掉落盘的平台计数。"""

        with self._lock:
            previous = {"operations": self._operations, "cycles": self._cycles, "drills": self._drills}
            self._operations = 0
            self._cycles = 0
            self._drills = 0
            self.store.remove("platform_state")
            return previous

    def transfer_grid_tie(self, power_kw: float = 120.0, frequency_hz: float = 50.0, dt: float = 1.0) -> dict:
        """并网编排：BMS 就绪 → PCS 切换 → 并网校验 → 功率输出。"""

        with self._lock:
            op_id = self.ids.next()
            rack = self._rack(DEFAULT_RACK)
            report = transfer_to_grid(
                self.pcs,
                self.bms,
                rack,
                self.grid,
                self.station,
                frequency_hz=frequency_hz,
                power_kw=power_kw,
                dt=dt,
                now=self.clock.now(),
            )
            summary = self._record_operation(op_id, "grid_tie", report)
            return {**report, **summary}

    def transfer_off_grid(self) -> dict:
        """离网编排：先回到离网态，再清零功率。"""

        with self._lock:
            op_id = self.ids.next()
            steps: list[dict] = []
            violations: list[str] = []
            if self.pcs.state_machine.state == "tripped":
                violations.append("pcs_tripped")
            else:
                steps.append({"component": "pcs", "action": "transfer", "detail": self.pcs.transfer("off_grid", "off_grid_request")})
            summary = self._record_operation(op_id, "off_grid", {"ok": not violations, "steps": steps, "violations": violations})
            return {"station": self.station, "ok": not violations, "steps": steps, "violations": violations, **summary}

    def discharge(self, power_kw: float = 200.0, dt: float = 60.0) -> dict:
        """放电编排：并网限额钳位 → 爬坡 → 电量累计 → 配额记账。"""

        with self._lock:
            op_id = self.ids.next()
            rack = self._rack(DEFAULT_RACK)
            report = discharge_rack(
                self.pcs,
                self.grid,
                self.quota,
                self.soc,
                rack,
                self.station,
                power_kw=power_kw,
                dt=dt,
                now=self.clock.now(),
            )
            summary = self._record_operation(op_id, "discharge", report)
            return {**report, **summary}

    def charge(self, rack_id: str | None = None, steps: int = 3, dt: float = 60.0) -> dict:
        """充电编排：均衡核对 → 温控降额 → 电压核对 → 电流阶梯 → 配额记账。"""

        with self._lock:
            op_id = self.ids.next()
            rack = self._rack(rack_id)
            report = charge_rack(
                self.pcs,
                self.bms,
                self.temp,
                self.balancer,
                self.quota,
                self.soc,
                rack,
                self.grid,
                self.station,
                steps=steps,
                dt=dt,
                now=self.clock.now(),
            )
            summary = self._record_operation(op_id, "charge", report)
            return {**report, **summary}

    def balance(self, rack_id: str | None = None, dt: float = 2.0, max_steps: int = 400) -> dict:
        """跑一次均衡直到压差回到目标带内或超时中止。"""

        with self._lock:
            op_id = self.ids.next()
            rack = self._rack(rack_id)
            started = self.balancer.start(rack.cells())
            steps: list[dict] = [{"component": "balance", "action": "start", "detail": started}]
            progressed: list[dict] = []
            for _ in range(max_steps):
                if self.balancer.is_complete() or self.balancer.state.state == "aborted":
                    break
                progressed.append(self.balancer.advance(dt, rack.cells()))
            violations = [] if self.balancer.is_complete() else ["balance_incomplete"]
            steps.append(
                {
                    "component": "balance",
                    "action": "advance",
                    "detail": {
                        "rounds": len(progressed),
                        "delta_mv": round(self.balancer.delta_mv(), 2),
                        "state": self.balancer.state.state,
                    },
                }
            )
            report = {"station": self.station, "ok": not violations, "steps": steps, "violations": violations}
            summary = self._record_operation(op_id, "balance", report)
            return {**report, **summary}

    def sample_temperature(self, rack_id: str | None = None, temperature_c: float = 30.0, dt: float = 5.0) -> dict:
        """温控降额编排：温度采集 → 基线读取 → 降额 → 充电限制。"""

        with self._lock:
            op_id = self.ids.next()
            rack = self._rack(rack_id)
            rack.apply_temperature(temperature_c)
            applied = self.temp.apply_temperature(temperature_c, self.clock.now(), rack.rating_v(), rack.rating_epoch)
            cooled = self.temp.cool(dt)
            combined = self.temp.combined_ratio(grid=1.0)
            steps = [
                {"component": "rack", "action": "temperature", "detail": {"temperature_c": round(temperature_c, 2)}},
                {"component": "temp", "action": "derate", "detail": applied},
                {
                    "component": "temp",
                    "action": "cool",
                    "detail": {
                        "temperature_c": round(cooled, 2),
                        "cooling": self.temp.cooler.is_running(),
                        "combined": combined,
                    },
                },
            ]
            ratio = self.temp.charge_limit_ratio()
            self.pcs.apply_derate(temperature=ratio, grid=1.0)
            report = {"station": self.station, "ok": True, "steps": steps, "violations": []}
            summary = self._record_operation(op_id, "temperature", report)
            return {**report, **summary, "charge_limit_ratio": round(ratio, 4)}

    def replace_pack_rating(self, pack_index: int = 0, rating_v: float = 3.35, rack_id: str | None = None) -> dict:
        """更换整包电芯并立即刷新降额基线。"""

        with self._lock:
            op_id = self.ids.next()
            rack = self._rack(rack_id)
            change = rack.replace_pack_rating(pack_index, rating_v)
            baseline = self.temp.apply_temperature(rack.temperature_c(), self.clock.now(), rack.rating_v(), rack.rating_epoch)
            steps = [
                {"component": "rack", "action": "replace_pack", "detail": change},
                {"component": "temp", "action": "baseline_refresh", "detail": baseline},
            ]
            report = {"station": self.station, "ok": True, "steps": steps, "violations": []}
            summary = self._record_operation(op_id, "replace_pack", report)
            return {**report, **summary}

    def calibrate_soc(self, soc_pct: float, source: str = "manual") -> dict:
        """登记一次 SOC 校准并按新基准重估。"""

        with self._lock:
            op_id = self.ids.next()
            record = self.bms.calibrate(soc_pct, source)
            self.soc.reset()
            estimate = self.soc.value(self.clock.now())
            for rack in self.racks.values():
                rack.set_soc(estimate.soc_pct)
            self.soc.report(soc_pct)
            steps = [
                {"component": "bms", "action": "calibrate", "detail": record},
                {"component": "soc", "action": "estimate", "detail": estimate.as_dict()},
            ]
            report = {"station": self.station, "ok": True, "steps": steps, "violations": []}
            summary = self._record_operation(op_id, "calibrate", report)
            return {**report, **summary}

    def report_fault(self, rack_id: str | None = None, code: str = "bms_fault") -> dict:
        """登记一次故障上报（可并发调用）。"""

        with self._lock:
            result = self.bms.report_fault(rack_id or DEFAULT_RACK, code)
            self._faults_reported += 1
            self.bus.publish(
                Event.of(
                    "bms",
                    "bms",
                    "fault_report",
                    station=self.station,
                    severity="warning" if result["latched"] else "notice",
                    **result,
                )
            )
            return result

    def clear_fault(self, rack_id: str | None = None) -> dict:
        """清除某簇故障计数与闩锁。"""

        with self._lock:
            key = rack_id or DEFAULT_RACK
            cleared = self.bms.clear_fault(key)
            self.bus.publish(Event.of("bms", "bms", "fault_clear", station=self.station, severity="notice", rack_id=key))
            return {"rack_id": key, "cleared": cleared}

    def fire_drill(
        self,
        zone: str = DEFAULT_ZONE,
        smoke_ppm: float = 1500.0,
        temperature_c: float = 30.0,
        confirm_dt: float = 5.0,
    ) -> dict:
        """消防联动编排：探测 → 开阀 → 确认 → 断 PCS → 审计。"""

        with self._lock:
            op_id = self.ids.next()
            report = suppress(
                self.fire,
                self.pcs,
                self.station,
                zone=zone,
                smoke_ppm=smoke_ppm,
                temperature_c=temperature_c,
                now=self.clock.now(),
                confirm_dt=confirm_dt,
            )
            summary = self._record_operation(op_id, "fire_suppression", report)
            if report["ok"]:
                self._drills += 1
                self._persist()
            return {**report, **summary}

    def release_fire(self) -> dict:
        """复位消防联动与 PCS 跳闸。"""

        with self._lock:
            released = self.fire.reset()
            reset = self.pcs.reset_trip()
            self.bus.publish(Event.of("fire", "fire", "released", station=self.station, severity="notice"))
            return {"fire": released, "pcs": reset}

    def monitor_frequency(self, frequency_hz: float = 50.0) -> dict:
        """记一次并网点频率采样。"""

        with self._lock:
            return self.grid.monitor_frequency(frequency_hz, self.clock.now())

    def set_soc(self, rack_id: str | None = None, soc_pct: float = 50.0) -> dict:
        """直接写入某簇 SOC（现场标定用）。"""

        with self._lock:
            rack = self._rack(rack_id)
            bounded = self.config.rack.clamp_soc(soc_pct)
            previous = rack.set_soc(bounded)
            self.soc.report(bounded)
            return {"rack_id": rack.rack_id, "previous_pct": round(previous, 3), "soc_pct": round(rack.soc_pct(), 3)}

    def disturb_cell(self, rack_id: str | None = None, cell_index: int = 0, delta_v: float = 0.03) -> dict:
        """人为制造单体偏差，用于复现压差越限与均衡场景。"""

        with self._lock:
            rack = self._rack(rack_id)
            cells = rack.cells()
            if not 0 <= cell_index < len(cells):
                raise IndexError(f"单体序号越界: {cell_index}")
            cell = cells[cell_index]
            cell.update(voltage_v=cell.voltage_v + float(delta_v))
            metrics = rack.metrics()
            return {
                "rack_id": rack.rack_id,
                "cell_id": cell.cell_id,
                "voltage_v": round(cell.voltage_v, 4),
                "delta_mv": round(metrics.delta_mv, 2),
            }

    def cycle(self, dt: float = 5.0) -> dict:
        """推进一个控制周期。"""

        with self._lock:
            self._cycles += 1
            now = self.clock.now()
            temperatures: dict[str, float] = {}
            ratios: dict[str, float] = {}
            trips: list[str] = []
            for rack_id, rack in self.racks.items():
                applied = self.temp.apply_temperature(rack.temperature_c(), now, rack.rating_v(), rack.rating_epoch)
                temperatures[rack_id] = applied["temperature_c"]
                ratios[rack_id] = round(self.temp.charge_limit_ratio(), 4)
                self.trend.append(f"{rack_id}.temperature", now, rack.temperature_c())
                self.trend.append(f"{rack_id}.voltage", now, rack.voltage_v())
                violations = self.bms.protection(rack)
                if violations:
                    trips.append(f"{rack_id}:{','.join(violations)}")
                    self.pcs.trip(f"protection:{rack_id}")
                self.bms.ready(rack)
                estimate = self.soc.value(now)
                rack.set_soc(estimate.soc_pct)
            rolled = self.quota.roll(now)
            self.grid.monitor_frequency(50.0, now)
            self._persist()
            return {
                "cycle": self._cycles,
                "temperatures": temperatures,
                "charge_limit_ratio": ratios,
                "trips": trips,
                "quota_rolled": rolled["rolled"],
                "pcs_state": self.pcs.state_machine.state,
            }

    def concurrency_probe(self, rounds: int = 32) -> dict:
        """并发探测：多个线程同时切 PCS，核对状态迁移是否原子落定。"""

        observed: list[str] = []
        lock = threading.Lock()
        errors: list[str] = []

        def worker(target: str) -> None:
            for _ in range(rounds):
                try:
                    self.pcs.transfer(target, "concurrency_probe")
                except StoreError as error:
                    errors.append(f"{target}:{type(error).__name__}")
                with lock:
                    observed.append(self.pcs.state_machine.state)

        if self.pcs.state_machine.state == "stopped":
            self.pcs.transfer("off_grid", "probe_setup")
        threads = [
            threading.Thread(target=worker, args=("grid_tie",), name="probe-tie"),
            threading.Thread(target=worker, args=("off_grid",), name="probe-off"),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        illegal = sorted({state for state in observed if state not in ("grid_tie", "off_grid")})
        return {
            "rounds": rounds,
            "samples": len(observed),
            "states": sorted({state for state in observed}),
            "illegal_states": illegal,
            "rejections": len(errors),
            "ok": not illegal,
        }

    def concurrency_fault_probe(self, rounds: int = 16) -> dict:
        """并发探测：多簇同时上报故障，核对闩锁是否每簇独立咬合。"""

        lock = threading.Lock()
        results: list[dict] = []

        def worker(rack_id: str) -> None:
            for _ in range(rounds):
                outcome = self.bms.report_fault(rack_id, "cell_over_temp")
                with lock:
                    results.append(outcome)

        rack_ids = sorted(self.racks)
        threads = [threading.Thread(target=worker, args=(rack_id,), name=f"fault-{rack_id}") for rack_id in rack_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        coverage = {rack_id: self.bms.faults.counter(rack_id) for rack_id in rack_ids}
        missing = [rack_id for rack_id, count in coverage.items() if count < self.bms.faults.confirm_rounds]
        return {
            "rounds": rounds,
            "reports": len(results),
            "coverage": coverage,
            "missing": missing,
            "latched": sorted(rack_id for rack_id in rack_ids if self.bms.latched(rack_id)),
            "ok": not missing,
        }

    def alerts(self) -> list[dict]:
        """汇总全部簇的告警并按最新编号路由。"""

        routed: list[dict] = []
        for rack in self.racks.values():
            routed.extend(self.bms.alarm_report(rack, self.mapping, self.config.bms.ready_delta_mv))
        return routed

    def readiness(self) -> dict:
        """返回各簇就绪判据与联控链核对结果。"""

        reports = {rack_id: self.bms.ready(rack).as_dict() for rack_id, rack in self.racks.items()}
        topology = self.topology.verify({name for name in self.topology.order()})
        return {"racks": reports, "topology": topology, "all_ready": all(item["ready"] for item in reports.values())}

    def topology_summary(self) -> dict:
        """返回联控链描述与各簇消防分区。"""

        return {
            "order": self.topology.order(),
            "stages": self.topology.describe(),
            "after_pcs": self.topology.stages_after("pcs"),
            "zones": {rack_id: rack.zone for rack_id, rack in sorted(self.racks.items())},
            "zone_racks": {
                zone: self.mapping.racks_of_zone(zone)
                for zone in sorted(set(self.mapping.snapshot()["zones"].values()))
            },
            "battery_clusters": self.namespaces.of_kind("battery-cluster"),
        }

    def namespaces_describe(self) -> list[dict]:
        """返回全部设备地址。"""

        return self.namespaces.addresses()

    def namespace(self, address: str) -> dict:
        """按地址取设备描述。"""

        return self.namespaces.resolve(address)

    def capacity(self) -> CapacityPlan:
        """返回站容量核算。"""

        return plan_capacity(self.config, len(self.racks))

    def rack_snapshots(self) -> list[dict]:
        """返回全部簇快照。"""

        return [self.racks[rack_id].snapshot().as_dict() for rack_id in sorted(self.racks)]

    def rack_snapshot(self, rack_id: str | None = None) -> dict:
        """返回单簇快照。"""

        return self._rack(rack_id).snapshot().as_dict()

    def rack_mapping(self) -> dict:
        """返回簇编号映射。"""

        return self.mapping.snapshot()

    def bms_snapshot(self) -> dict:
        return self.bms.snapshot().as_dict()

    def pcs_snapshot(self) -> dict:
        return {**self.pcs.snapshot().as_dict(), "mode_matrix": self.pcs.state_machine.table.matrix()}

    def temp_snapshot(self) -> dict:
        rack = self._rack(DEFAULT_RACK)
        return self.temp.snapshot(self.clock.now(), rack.rating_epoch).as_dict()

    def fire_snapshot(self) -> dict:
        return self.fire.snapshot().as_dict()

    def grid_snapshot(self) -> dict:
        return self.grid.snapshot().as_dict()

    def soc_snapshot(self) -> dict:
        return self.soc.snapshot(self.clock.now()).as_dict()

    def balance_snapshot(self) -> dict:
        return self.balancer.snapshot().as_dict()

    def quota_snapshot(self) -> dict:
        return self.quota.snapshot(self.clock.now()).as_dict()

    def audit_snapshot(self) -> dict:
        return self.audit.snapshot().as_dict()

    def trend_snapshot(self) -> dict:
        return self.trend.snapshot()

    def config_export(self) -> dict:
        """返回生效配置，供控制台与交付自检核对。"""

        return config_to_mapping(self.config)

    def status(self) -> dict:
        """返回平台总状态。"""

        return {
            "station": self.station,
            "running": self._running,
            "operations": self._operations,
            "cycles": self._cycles,
            "faults_reported": self._faults_reported,
            "drills": self._drills,
            "ids_issued": self.ids.issued(),
            "racks": self.rack_snapshots(),
            "bms": self.bms_snapshot(),
            "pcs": self.pcs_snapshot(),
            "temp": self.temp_snapshot(),
            "fire": self.fire_snapshot(),
            "grid": self.grid_snapshot(),
            "soc": self.soc_snapshot(),
            "balance": self.balance_snapshot(),
        }

    def snapshot(self) -> dict:
        """返回平台完整快照（状态 + 容量 + 配额 + 审计）。"""

        return {
            "status": self.status(),
            "capacity": self.capacity().as_dict(),
            "quota": self.quota_snapshot(),
            "audit": self.audit_snapshot(),
            "mapping": self.rack_mapping(),
            "config": config_to_mapping(self.config),
        }


def build_platform(
    config: StationConfig | None = None,
    clock: Clock | None = None,
    storage_root: str | None = None,
    rack_count: int = 2,
) -> Platform:
    """按配置装配平台；``storage_root`` 可覆盖落盘目录。"""

    resolved = config or default_config()
    if storage_root:
        resolved = StationConfig(
            name=resolved.name,
            storage_root=storage_root,
            rack=resolved.rack,
            bms=resolved.bms,
            pcs=resolved.pcs,
            temp=resolved.temp,
            fire=resolved.fire,
            grid=resolved.grid,
            soc=resolved.soc,
            balance=resolved.balance,
            quota=resolved.quota,
        )
    return Platform(config=resolved, clock=clock, rack_count=rack_count)
