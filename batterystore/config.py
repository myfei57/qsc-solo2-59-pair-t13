"""配置模型。

电站参数按子系统分段，每段一个不可变 dataclass。装配时先把 JSON 读成映射，
再逐段校验：取值范围、段间关系（例如降额起点必须早于满额点、额定电压必须
落在单体上下限之间）在这里一次拦下，运行期不再重复判断接线错误。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import ConfigError


def _section(mapping: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise ConfigError(f"配置缺少段落 {key}", component="config")
    return value


def _number(section: Mapping[str, Any], key: str, minimum: float | None = None) -> float:
    raw = section.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ConfigError(f"{key} 必须是数值", component="config")
    value = float(raw)
    if minimum is not None and value < minimum:
        raise ConfigError(f"{key} 不能小于 {minimum}", component="config")
    return value


def _integer(section: Mapping[str, Any], key: str, minimum: int | None = None) -> int:
    raw = section.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ConfigError(f"{key} 必须是整数", component="config")
    if minimum is not None and raw < minimum:
        raise ConfigError(f"{key} 不能小于 {minimum}", component="config")
    return raw


@dataclass(frozen=True)
class RackLimits:
    """电池簇单体与温度约束。"""

    cell_count: int
    cell_nominal_v: float
    cell_v_max: float
    cell_v_min: float
    temp_warn_c: float
    temp_trip_c: float
    soc_min_pct: float
    soc_max_pct: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "RackLimits":
        limits = cls(
            cell_count=_integer(section, "cell_count", minimum=1),
            cell_nominal_v=_number(section, "cell_nominal_v", minimum=0.1),
            cell_v_max=_number(section, "cell_v_max", minimum=0.1),
            cell_v_min=_number(section, "cell_v_min", minimum=0.0),
            temp_warn_c=_number(section, "temp_warn_c"),
            temp_trip_c=_number(section, "temp_trip_c"),
            soc_min_pct=_number(section, "soc_min_pct", minimum=0.0),
            soc_max_pct=_number(section, "soc_max_pct", minimum=1.0),
        )
        if limits.cell_v_min >= limits.cell_v_max:
            raise ConfigError("单体电压下限必须小于上限", component="config")
        if not limits.cell_v_min <= limits.cell_nominal_v <= limits.cell_v_max:
            raise ConfigError("单体额定电压必须落在上下限之间", component="config")
        if limits.temp_warn_c >= limits.temp_trip_c:
            raise ConfigError("温度告警必须早于跳闸", component="config")
        if limits.soc_min_pct >= limits.soc_max_pct:
            raise ConfigError("SOC 下限必须小于上限", component="config")
        return limits

    def clamp_soc(self, soc_pct: float) -> float:
        """把 SOC 夹到允许区间。"""

        return max(self.soc_min_pct, min(self.soc_max_pct, float(soc_pct)))


@dataclass(frozen=True)
class BmsLimits:
    """BMS 就绪判据、闩锁保持与保护阈值。"""

    ready_delta_mv: float
    ready_temp_c: float
    ready_soc_min_pct: float
    ready_soc_max_pct: float
    fault_latch_s: float
    confirm_rounds: int
    protection_temp_c: float
    protection_delta_mv: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "BmsLimits":
        limits = cls(
            ready_delta_mv=_number(section, "ready_delta_mv", minimum=0.0),
            ready_temp_c=_number(section, "ready_temp_c"),
            ready_soc_min_pct=_number(section, "ready_soc_min_pct", minimum=0.0),
            ready_soc_max_pct=_number(section, "ready_soc_max_pct", minimum=1.0),
            fault_latch_s=_number(section, "fault_latch_s", minimum=1.0),
            confirm_rounds=_integer(section, "confirm_rounds", minimum=1),
            protection_temp_c=_number(section, "protection_temp_c"),
            protection_delta_mv=_number(section, "protection_delta_mv", minimum=0.0),
        )
        if limits.ready_soc_min_pct >= limits.ready_soc_max_pct:
            raise ConfigError("就绪 SOC 下限必须小于上限", component="config")
        return limits

    def soc_window_ok(self, soc_pct: float) -> bool:
        """SOC 是否落在就绪窗口内。"""

        return self.ready_soc_min_pct <= float(soc_pct) <= self.ready_soc_max_pct


@dataclass(frozen=True)
class PcsLimits:
    """PCS 功率、爬坡与电流阶梯约束。"""

    max_power_kw: float
    min_power_kw: float
    ramp_kw_per_s: float
    transfer_delay_s: float
    efficiency: float
    current_step_a: float
    current_tolerance_a: float
    current_max_a: float
    protection_current_a: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "PcsLimits":
        limits = cls(
            max_power_kw=_number(section, "max_power_kw", minimum=0.1),
            min_power_kw=_number(section, "min_power_kw", minimum=0.0),
            ramp_kw_per_s=_number(section, "ramp_kw_per_s", minimum=0.1),
            transfer_delay_s=_number(section, "transfer_delay_s", minimum=0.0),
            efficiency=_number(section, "efficiency", minimum=0.1),
            current_step_a=_number(section, "current_step_a", minimum=0.1),
            current_tolerance_a=_number(section, "current_tolerance_a", minimum=0.0),
            current_max_a=_number(section, "current_max_a", minimum=0.1),
            protection_current_a=_number(section, "protection_current_a", minimum=0.1),
        )
        if limits.min_power_kw >= limits.max_power_kw:
            raise ConfigError("最小功率必须小于最大功率", component="config")
        if limits.efficiency > 1.0:
            raise ConfigError("效率不能大于 1", component="config")
        if limits.current_max_a > limits.protection_current_a:
            raise ConfigError("电流上限必须小于保护阈值", component="config")
        return limits

    def clamp_power(self, power_kw: float) -> float:
        """把功率指令夹到 PCS 允许区间。"""

        magnitude = abs(float(power_kw))
        if magnitude == 0.0:
            return 0.0
        limited = min(magnitude, self.max_power_kw)
        if limited < self.min_power_kw:
            limited = self.min_power_kw
        return limited if power_kw >= 0 else -limited


@dataclass(frozen=True)
class TempLimits:
    """温度降额曲线与基线有效期。"""

    derate_start_c: float
    derate_full_c: float
    derate_floor_ratio: float
    baseline_ttl_s: float
    cool_rate_c_per_s: float
    warn_c: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "TempLimits":
        limits = cls(
            derate_start_c=_number(section, "derate_start_c"),
            derate_full_c=_number(section, "derate_full_c"),
            derate_floor_ratio=_number(section, "derate_floor_ratio", minimum=0.0),
            baseline_ttl_s=_number(section, "baseline_ttl_s", minimum=1.0),
            cool_rate_c_per_s=_number(section, "cool_rate_c_per_s", minimum=0.0),
            warn_c=_number(section, "warn_c"),
        )
        if limits.derate_start_c >= limits.derate_full_c:
            raise ConfigError("降额起点必须早于满额点", component="config")
        if limits.derate_floor_ratio > 1.0:
            raise ConfigError("降额下限系数不能大于 1", component="config")
        return limits


@dataclass(frozen=True)
class FireLimits:
    """消防探测阀值、阀行程与保持时长。"""

    smoke_ppm: float
    temp_trip_c: float
    valve_travel_mm: float
    valve_confirm_s: float
    hold_s: float
    zone_count: int

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "FireLimits":
        limits = cls(
            smoke_ppm=_number(section, "smoke_ppm", minimum=1.0),
            temp_trip_c=_number(section, "temp_trip_c"),
            valve_travel_mm=_number(section, "valve_travel_mm", minimum=1.0),
            valve_confirm_s=_number(section, "valve_confirm_s", minimum=0.0),
            hold_s=_number(section, "hold_s", minimum=1.0),
            zone_count=_integer(section, "zone_count", minimum=1),
        )
        if limits.valve_confirm_s >= limits.hold_s:
            raise ConfigError("开阀确认时长必须小于保持时长", component="config")
        return limits

    def detected(self, smoke_ppm: float, temperature_c: float) -> bool:
        """烟感或温感任一越线即判探测到火情。"""

        return float(smoke_ppm) >= self.smoke_ppm or float(temperature_c) >= self.temp_trip_c


@dataclass(frozen=True)
class GridLimits:
    """并网点功率限额与频率窗口。"""

    export_limit_kw: float
    import_limit_kw: float
    rated_frequency_hz: float
    frequency_band_hz: float
    monitor_window_s: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "GridLimits":
        limits = cls(
            export_limit_kw=_number(section, "export_limit_kw", minimum=0.1),
            import_limit_kw=_number(section, "import_limit_kw", minimum=0.1),
            rated_frequency_hz=_number(section, "rated_frequency_hz", minimum=1.0),
            frequency_band_hz=_number(section, "frequency_band_hz", minimum=0.0),
            monitor_window_s=_number(section, "monitor_window_s", minimum=0.1),
        )
        if limits.frequency_band_hz >= limits.rated_frequency_hz:
            raise ConfigError("频率窗口必须小于额定频率", component="config")
        return limits

    def frequency_ok(self, frequency_hz: float) -> bool:
        """频率是否落在允许窗口内。"""

        deviation = abs(float(frequency_hz) - self.rated_frequency_hz)
        return deviation <= self.frequency_band_hz


@dataclass(frozen=True)
class SocLimits:
    """SOC 容量、库仑效率与校准有效期。"""

    capacity_ah: float
    coulomb_efficiency: float
    calibrate_ttl_s: float
    drift_tolerance_pct: float
    initial_soc_pct: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "SocLimits":
        limits = cls(
            capacity_ah=_number(section, "capacity_ah", minimum=1.0),
            coulomb_efficiency=_number(section, "coulomb_efficiency", minimum=0.1),
            calibrate_ttl_s=_number(section, "calibrate_ttl_s", minimum=1.0),
            drift_tolerance_pct=_number(section, "drift_tolerance_pct", minimum=0.0),
            initial_soc_pct=_number(section, "initial_soc_pct", minimum=0.0),
        )
        if limits.coulomb_efficiency > 1.0:
            raise ConfigError("库仑效率不能大于 1", component="config")
        if not 0.0 <= limits.initial_soc_pct <= 100.0:
            raise ConfigError("初始 SOC 必须在 0 到 100 之间", component="config")
        return limits

    def amp_hours_to_percent(self, amp_hours: float) -> float:
        """把安时数换算成 SOC 百分点。"""

        return float(amp_hours) / self.capacity_ah * 100.0


@dataclass(frozen=True)
class BalanceLimits:
    """均衡压差目标、脉冲节拍与时长上限。"""

    target_delta_mv: float
    pulse_s: float
    rest_s: float
    max_duration_s: float
    min_cells: int

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "BalanceLimits":
        return cls(
            target_delta_mv=_number(section, "target_delta_mv", minimum=0.0),
            pulse_s=_number(section, "pulse_s", minimum=0.1),
            rest_s=_number(section, "rest_s", minimum=0.0),
            max_duration_s=_number(section, "max_duration_s", minimum=1.0),
            min_cells=_integer(section, "min_cells", minimum=1),
        )

    @property
    def cycle_s(self) -> float:
        """一个脉冲加一段静置的时长。"""

        return self.pulse_s + self.rest_s


@dataclass(frozen=True)
class QuotaLimits:
    """充放电配额与峰谷电价。"""

    period_hours: float
    charge_quota_kwh: float
    discharge_quota_kwh: float
    tariff_peak: float
    tariff_valley: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "QuotaLimits":
        limits = cls(
            period_hours=_number(section, "period_hours", minimum=0.1),
            charge_quota_kwh=_number(section, "charge_quota_kwh", minimum=0.1),
            discharge_quota_kwh=_number(section, "discharge_quota_kwh", minimum=0.1),
            tariff_peak=_number(section, "tariff_peak", minimum=0.0),
            tariff_valley=_number(section, "tariff_valley", minimum=0.0),
        )
        if limits.tariff_valley > limits.tariff_peak:
            raise ConfigError("谷电价不能高于峰电价", component="config")
        return limits


@dataclass(frozen=True)
class StationConfig:
    """一份完整的电站配置。"""

    name: str
    storage_root: str
    rack: RackLimits
    bms: BmsLimits
    pcs: PcsLimits
    temp: TempLimits
    fire: FireLimits
    grid: GridLimits
    soc: SocLimits
    balance: BalanceLimits
    quota: QuotaLimits

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "StationConfig":
        meta = _section(mapping, "station")
        name = meta.get("name")
        storage_root = meta.get("storage_root")
        if not isinstance(name, str) or not name:
            raise ConfigError("station.name 必须是非空字符串", component="config")
        if not isinstance(storage_root, str) or not storage_root:
            raise ConfigError("station.storage_root 必须是非空字符串", component="config")
        limits = _section(mapping, "limits")
        return cls(
            name=name,
            storage_root=storage_root,
            rack=RackLimits.from_mapping(_section(limits, "rack")),
            bms=BmsLimits.from_mapping(_section(limits, "bms")),
            pcs=PcsLimits.from_mapping(_section(limits, "pcs")),
            temp=TempLimits.from_mapping(_section(limits, "temp")),
            fire=FireLimits.from_mapping(_section(limits, "fire")),
            grid=GridLimits.from_mapping(_section(limits, "grid")),
            soc=SocLimits.from_mapping(_section(limits, "soc")),
            balance=BalanceLimits.from_mapping(_section(limits, "balance")),
            quota=QuotaLimits.from_mapping(_section(limits, "quota")),
        )


def load_config(path: str) -> StationConfig:
    """从 JSON 文件读取配置。"""

    if not os.path.isfile(path):
        raise ConfigError(f"配置文件不存在: {path}", component="config")
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise ConfigError("配置文件顶层必须是映射", component="config")
    return StationConfig.from_mapping(raw)


def default_config() -> StationConfig:
    """内置默认配置，供未指定配置文件时装配使用。"""

    return StationConfig(
        name="storage-control",
        storage_root="var/state",
        rack=RackLimits(96, 3.2, 3.65, 2.5, 45.0, 55.0, 10.0, 95.0),
        bms=BmsLimits(60.0, 35.0, 15.0, 92.0, 120.0, 2, 55.0, 120.0),
        pcs=PcsLimits(500.0, 5.0, 25.0, 2.0, 0.97, 40.0, 4.0, 200.0, 240.0),
        temp=TempLimits(40.0, 55.0, 0.25, 1800.0, 0.05, 45.0),
        fire=FireLimits(1200.0, 58.0, 30.0, 4.0, 60.0, 4),
        grid=GridLimits(400.0, 450.0, 50.0, 0.2, 10.0),
        soc=SocLimits(280.0, 0.98, 7200.0, 3.0, 50.0),
        balance=BalanceLimits(25.0, 4.0, 2.0, 600.0, 2),
        quota=QuotaLimits(24.0, 2000.0, 2000.0, 1.2, 0.4),
    )


def config_to_mapping(cfg: StationConfig) -> dict:
    """把配置还原成可打印的映射。"""

    return {
        "station": {"name": cfg.name, "storage_root": cfg.storage_root},
        "limits": {
            "rack": {
                "cell_count": cfg.rack.cell_count,
                "cell_nominal_v": cfg.rack.cell_nominal_v,
                "cell_v_max": cfg.rack.cell_v_max,
                "cell_v_min": cfg.rack.cell_v_min,
                "temp_warn_c": cfg.rack.temp_warn_c,
                "temp_trip_c": cfg.rack.temp_trip_c,
                "soc_min_pct": cfg.rack.soc_min_pct,
                "soc_max_pct": cfg.rack.soc_max_pct,
            },
            "bms": {
                "ready_delta_mv": cfg.bms.ready_delta_mv,
                "ready_temp_c": cfg.bms.ready_temp_c,
                "ready_soc_min_pct": cfg.bms.ready_soc_min_pct,
                "ready_soc_max_pct": cfg.bms.ready_soc_max_pct,
                "fault_latch_s": cfg.bms.fault_latch_s,
                "confirm_rounds": cfg.bms.confirm_rounds,
                "protection_temp_c": cfg.bms.protection_temp_c,
                "protection_delta_mv": cfg.bms.protection_delta_mv,
            },
            "pcs": {
                "max_power_kw": cfg.pcs.max_power_kw,
                "min_power_kw": cfg.pcs.min_power_kw,
                "ramp_kw_per_s": cfg.pcs.ramp_kw_per_s,
                "transfer_delay_s": cfg.pcs.transfer_delay_s,
                "efficiency": cfg.pcs.efficiency,
                "current_step_a": cfg.pcs.current_step_a,
                "current_tolerance_a": cfg.pcs.current_tolerance_a,
                "current_max_a": cfg.pcs.current_max_a,
                "protection_current_a": cfg.pcs.protection_current_a,
            },
            "temp": {
                "derate_start_c": cfg.temp.derate_start_c,
                "derate_full_c": cfg.temp.derate_full_c,
                "derate_floor_ratio": cfg.temp.derate_floor_ratio,
                "baseline_ttl_s": cfg.temp.baseline_ttl_s,
                "cool_rate_c_per_s": cfg.temp.cool_rate_c_per_s,
                "warn_c": cfg.temp.warn_c,
            },
            "fire": {
                "smoke_ppm": cfg.fire.smoke_ppm,
                "temp_trip_c": cfg.fire.temp_trip_c,
                "valve_travel_mm": cfg.fire.valve_travel_mm,
                "valve_confirm_s": cfg.fire.valve_confirm_s,
                "hold_s": cfg.fire.hold_s,
                "zone_count": cfg.fire.zone_count,
            },
            "grid": {
                "export_limit_kw": cfg.grid.export_limit_kw,
                "import_limit_kw": cfg.grid.import_limit_kw,
                "rated_frequency_hz": cfg.grid.rated_frequency_hz,
                "frequency_band_hz": cfg.grid.frequency_band_hz,
                "monitor_window_s": cfg.grid.monitor_window_s,
            },
            "soc": {
                "capacity_ah": cfg.soc.capacity_ah,
                "coulomb_efficiency": cfg.soc.coulomb_efficiency,
                "calibrate_ttl_s": cfg.soc.calibrate_ttl_s,
                "drift_tolerance_pct": cfg.soc.drift_tolerance_pct,
                "initial_soc_pct": cfg.soc.initial_soc_pct,
            },
            "balance": {
                "target_delta_mv": cfg.balance.target_delta_mv,
                "pulse_s": cfg.balance.pulse_s,
                "rest_s": cfg.balance.rest_s,
                "max_duration_s": cfg.balance.max_duration_s,
                "min_cells": cfg.balance.min_cells,
            },
            "quota": {
                "period_hours": cfg.quota.period_hours,
                "charge_quota_kwh": cfg.quota.charge_quota_kwh,
                "discharge_quota_kwh": cfg.quota.discharge_quota_kwh,
                "tariff_peak": cfg.quota.tariff_peak,
                "tariff_valley": cfg.quota.tariff_valley,
            },
        },
    }
