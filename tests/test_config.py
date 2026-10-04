"""配置解析与校验。"""

from __future__ import annotations

import json

import pytest

from batterystore.config import StationConfig, config_to_mapping, default_config, load_config
from batterystore.errors import ConfigError


def test_default_config_is_self_consistent():
    config = default_config()
    assert config.rack.cell_v_min < config.rack.cell_nominal_v < config.rack.cell_v_max
    assert config.temp.derate_start_c < config.temp.derate_full_c
    assert config.pcs.current_max_a < config.pcs.protection_current_a
    assert config.pcs.clamp_power(1000.0) == config.pcs.max_power_kw
    assert config.pcs.clamp_power(0.0) == 0.0
    assert config.rack.clamp_soc(0.0) == config.rack.soc_min_pct
    assert config.rack.clamp_soc(200.0) == config.rack.soc_max_pct


def test_config_roundtrip_through_mapping(tmp_path):
    config = default_config()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config_to_mapping(config)), encoding="utf-8")
    reloaded = load_config(str(path))
    assert reloaded == config


def test_load_config_rejects_missing_file():
    with pytest.raises(ConfigError):
        load_config("does-not-exist.json")


def test_config_rejects_inconsistent_rack_limits():
    raw = config_to_mapping(default_config())
    raw["limits"]["rack"]["cell_v_max"] = 2.0
    with pytest.raises(ConfigError):
        StationConfig.from_mapping(raw)


def test_config_rejects_inconsistent_derate_band():
    raw = config_to_mapping(default_config())
    raw["limits"]["temp"]["derate_start_c"] = 60.0
    with pytest.raises(ConfigError):
        StationConfig.from_mapping(raw)


def test_config_rejects_current_above_protection():
    raw = config_to_mapping(default_config())
    raw["limits"]["pcs"]["protection_current_a"] = 100.0
    with pytest.raises(ConfigError):
        StationConfig.from_mapping(raw)
