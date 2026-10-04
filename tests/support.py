"""测试公共步骤。"""

from __future__ import annotations


def bring_online(platform) -> dict:
    """启动平台并把第一簇推到可并网状态，返回启动报告。"""

    startup = platform.start()
    assert startup["running"], startup
    return startup


def connect_grid(platform, power_kw: float = 120.0, frequency_hz: float = 50.0) -> dict:
    """跑一遍并网编排并断言成功。"""

    report = platform.transfer_grid_tie(power_kw=power_kw, frequency_hz=frequency_hz)
    assert report["ok"], report["violations"]
    return report


def prepare_charge(platform, temperature_c: float = 30.0) -> None:
    """把温控与均衡调到可充电状态。"""

    platform.sample_temperature(temperature_c=temperature_c, dt=5.0)
    report = platform.balance(max_steps=400)
    assert report["ok"], report["violations"]
