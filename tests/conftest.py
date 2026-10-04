"""测试夹具：所有用例都从干净存储和可推进时钟起步。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from batterystore.app import build_platform  # noqa: E402
from batterystore.clock import ManualClock  # noqa: E402
from batterystore.config import default_config  # noqa: E402


@pytest.fixture()
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture()
def config():
    return default_config()


@pytest.fixture()
def platform(tmp_path, clock, config):
    return build_platform(config, clock=clock, storage_root=str(tmp_path / "state"), rack_count=2)
