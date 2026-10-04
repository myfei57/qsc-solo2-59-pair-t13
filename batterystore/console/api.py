"""控制台接口处理器。

每个接口都是对平台公开方法的一次调用；动作类接口把请求体里的参数透传给
平台，缺少必填字段时返回 ``400``，平台异常统一转成 ``409`` 并在响应里带上
组件名。页面清单与键值清单也在这里暴露，便于交付自检核对接口齐全。
"""

from __future__ import annotations

from ..audit.timeline import build_timeline
from ..errors import StoreError
from ..store.index import summarize_documents
from .pages import PageLibrary
from .router import Router


def _as_float(body: dict, key: str, default: float) -> float:
    value = body.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise StoreError(f"参数 {key!r} 必须是数值", component="console") from error


def _as_int(body: dict, key: str, default: int) -> int:
    value = body.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise StoreError(f"参数 {key!r} 必须是整数", component="console") from error


class Api:
    """把 HTTP 请求翻译成平台调用。"""

    def __init__(self, platform, pages: PageLibrary) -> None:
        self._platform = platform
        self._pages = pages
        self._router = Router()
        self._register()

    @property
    def platform(self):
        return self._platform

    @property
    def pages(self) -> PageLibrary:
        return self._pages

    def _register(self) -> None:
        add = self._router.add
        add("GET", "/api/status", lambda params, body: self._platform.status())
        add("GET", "/api/snapshot", lambda params, body: self._platform.snapshot())
        add("GET", "/api/readiness", lambda params, body: self._platform.readiness())
        add("GET", "/api/topology", lambda params, body: self._platform.topology_summary())
        add("GET", "/api/namespaces", lambda params, body: {"devices": self._platform.namespaces_describe()})
        add("GET", "/api/namespace/{address}", lambda params, body: self._platform.namespace(str(params.get("address", ""))))
        add("GET", "/api/capacity", lambda params, body: self._platform.capacity().as_dict())
        add("GET", "/api/racks", lambda params, body: {"racks": self._platform.rack_snapshots()})
        add("GET", "/api/rack/{rack_id}", lambda params, body: self._platform.rack_snapshot(str(params.get("rack_id", ""))))
        add("GET", "/api/mapping", lambda params, body: self._platform.rack_mapping())
        add("GET", "/api/bms", lambda params, body: self._platform.bms_snapshot())
        add("GET", "/api/pcs", lambda params, body: self._platform.pcs_snapshot())
        add("GET", "/api/temp", lambda params, body: self._platform.temp_snapshot())
        add("GET", "/api/fire", lambda params, body: self._platform.fire_snapshot())
        add("GET", "/api/grid", lambda params, body: self._platform.grid_snapshot())
        add("GET", "/api/soc", lambda params, body: self._platform.soc_snapshot())
        add("GET", "/api/balance", lambda params, body: self._platform.balance_snapshot())
        add("GET", "/api/quota", lambda params, body: self._platform.quota_snapshot())
        add("GET", "/api/audit", self._audit)
        add("GET", "/api/audit/report", lambda params, body: self._platform.audit.report())
        add("GET", "/api/audit/operations", self._operations)
        add("GET", "/api/alarms", lambda params, body: {"alarms": self._platform.audit.alarms()})
        add("GET", "/api/alerts", lambda params, body: {"alerts": self._platform.alerts()})
        add("GET", "/api/events", self._events)
        add("GET", "/api/trend", self._trend)
        add("GET", "/api/store", self._store)
        add("GET", "/api/timeline", self._timeline)
        add("GET", "/api/journal", self._journal)
        add("GET", "/api/config", lambda params, body: self._platform.config_export())
        add("GET", "/api/pages", lambda params, body: {"pages": self._pages.index(), "routes": self.routes()})
        add("POST", "/api/start", lambda params, body: self._platform.start())
        add("POST", "/api/stop", lambda params, body: self._platform.stop())
        add("POST", "/api/reset", lambda params, body: self._platform.reset_state())
        add("POST", "/api/step", self._cycle)
        add("POST", "/api/transfer", self._transfer)
        add("POST", "/api/off-grid", lambda params, body: self._platform.transfer_off_grid())
        add("POST", "/api/discharge", self._discharge)
        add("POST", "/api/charge", self._charge)
        add("POST", "/api/balance", self._balance)
        add("POST", "/api/temperature", self._temperature)
        add("POST", "/api/replace-pack", self._replace_pack)
        add("POST", "/api/calibrate", self._calibrate)
        add("POST", "/api/fault", self._fault)
        add("POST", "/api/fault/clear", self._fault_clear)
        add("POST", "/api/fire/drill", self._drill)
        add("POST", "/api/fire/release", lambda params, body: self._platform.release_fire())
        add("POST", "/api/frequency", self._frequency)
        add("POST", "/api/soc", self._soc)
        add("POST", "/api/disturb", self._disturb)
        add("POST", "/api/probe/pcs", self._probe_pcs)
        add("POST", "/api/probe/fault", self._probe_fault)

    def routes(self) -> list[dict]:
        """返回接口清单，供自检与文档核对。"""

        return [route.as_dict() for route in self._router.routes()]

    def handle(self, method: str, path: str, query: dict, body: dict) -> tuple[int, dict]:
        """处理一次请求，返回状态码与响应体。"""

        matched = self._router.match(method, path)
        if matched is None:
            return 404, {"error": "not_found", "path": path}
        handler, params = matched
        merged = {**query, **params}
        try:
            payload = handler(merged, body)
        except StoreError as error:
            # 控制台拒绝的动作也要留痕，便于巡检区分"谁触发了哪条联锁"。
            self._platform.note_error(error)
            return 409, {"error": type(error).__name__, **error.as_record()}
        return 200, payload

    def _audit(self, params: dict, body: dict) -> dict:
        return {
            "entries": self._platform.audit.query(
                component=params.get("component"),
                severity=params.get("severity"),
                action=params.get("action"),
                limit=int(params.get("limit", 100)),
            )
        }

    def _operations(self, params: dict, body: dict) -> dict:
        return {"operations": self._platform.audit.operations(limit=int(params.get("limit", 20)))}

    def _events(self, params: dict, body: dict) -> dict:
        topic = params.get("topic")
        return {"events": [event.as_dict() for event in self._platform.bus.history(topic)]}

    def _trend(self, params: dict, body: dict) -> dict:
        signal = params.get("signal", "rk-01.temperature")
        samples = self._platform.trend.series(signal, limit=int(params.get("limit", 60)))
        filled = self._platform.trend.fill_gaps(signal, samples)
        return {
            "signal": signal,
            "period_s": self._platform.trend.period_s,
            "mean": self._platform.trend.mean(signal),
            "samples": [sample.as_dict() for sample in filled],
        }

    def _store(self, params: dict, body: dict) -> dict:
        store = self._platform.store
        return {
            "root": store.root,
            "documents": summarize_documents(store),
            "platform_state_path": store.path_of("platform_state"),
            "platform_state": store.read("platform_state"),
        }

    def _timeline(self, params: dict, body: dict) -> dict:
        records = self._platform.audit.records(limit=int(params.get("limit", 200)))
        return {"timeline": build_timeline(records, station=params.get("station"))}

    def _journal(self, params: dict, body: dict) -> dict:
        journal = self._platform.audit.journal
        payload: dict = {
            "topic": journal.topic,
            "count": journal.count(),
            "active_segment": journal.active_segment(),
            "segments": journal.segments(),
        }
        segment = params.get("segment")
        if segment is not None:
            payload["records"] = self._platform.audit.replay_segment(int(segment))
        return payload

    def _cycle(self, params: dict, body: dict) -> dict:
        return self._platform.cycle(dt=_as_float(body, "dt", 5.0))

    def _transfer(self, params: dict, body: dict) -> dict:
        return self._platform.transfer_grid_tie(
            power_kw=_as_float(body, "power_kw", 120.0),
            frequency_hz=_as_float(body, "frequency_hz", 50.0),
            dt=_as_float(body, "dt", 1.0),
        )

    def _discharge(self, params: dict, body: dict) -> dict:
        return self._platform.discharge(
            power_kw=_as_float(body, "power_kw", 200.0),
            dt=_as_float(body, "dt", 60.0),
        )

    def _charge(self, params: dict, body: dict) -> dict:
        return self._platform.charge(
            rack_id=body.get("rack_id"),
            steps=_as_int(body, "steps", 3),
            dt=_as_float(body, "dt", 60.0),
        )

    def _balance(self, params: dict, body: dict) -> dict:
        return self._platform.balance(
            rack_id=body.get("rack_id"),
            dt=_as_float(body, "dt", 2.0),
            max_steps=_as_int(body, "max_steps", 400),
        )

    def _temperature(self, params: dict, body: dict) -> dict:
        return self._platform.sample_temperature(
            rack_id=body.get("rack_id"),
            temperature_c=_as_float(body, "temperature_c", 30.0),
            dt=_as_float(body, "dt", 5.0),
        )

    def _replace_pack(self, params: dict, body: dict) -> dict:
        return self._platform.replace_pack_rating(
            pack_index=_as_int(body, "pack_index", 0),
            rating_v=_as_float(body, "rating_v", 3.35),
            rack_id=body.get("rack_id"),
        )

    def _calibrate(self, params: dict, body: dict) -> dict:
        return self._platform.calibrate_soc(
            soc_pct=_as_float(body, "soc_pct", 50.0),
            source=str(body.get("source", "console")),
        )

    def _fault(self, params: dict, body: dict) -> dict:
        return self._platform.report_fault(
            rack_id=body.get("rack_id"),
            code=str(body.get("code", "bms_fault")),
        )

    def _fault_clear(self, params: dict, body: dict) -> dict:
        return self._platform.clear_fault(rack_id=body.get("rack_id"))

    def _drill(self, params: dict, body: dict) -> dict:
        return self._platform.fire_drill(
            zone=str(body.get("zone", "Z1")),
            smoke_ppm=_as_float(body, "smoke_ppm", 1500.0),
            temperature_c=_as_float(body, "temperature_c", 30.0),
            confirm_dt=_as_float(body, "confirm_dt", 5.0),
        )

    def _frequency(self, params: dict, body: dict) -> dict:
        return self._platform.monitor_frequency(frequency_hz=_as_float(body, "frequency_hz", 50.0))

    def _soc(self, params: dict, body: dict) -> dict:
        return self._platform.set_soc(rack_id=body.get("rack_id"), soc_pct=_as_float(body, "soc_pct", 50.0))

    def _disturb(self, params: dict, body: dict) -> dict:
        return self._platform.disturb_cell(
            rack_id=body.get("rack_id"),
            cell_index=_as_int(body, "cell_index", 0),
            delta_v=_as_float(body, "delta_v", 0.03),
        )

    def _probe_pcs(self, params: dict, body: dict) -> dict:
        return self._platform.concurrency_probe(rounds=_as_int(body, "rounds", 32))

    def _probe_fault(self, params: dict, body: dict) -> dict:
        return self._platform.concurrency_fault_probe(rounds=_as_int(body, "rounds", 16))
