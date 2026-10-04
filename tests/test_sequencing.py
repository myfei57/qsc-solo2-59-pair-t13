"""端到端联控编排。"""

from __future__ import annotations

from support import bring_online, connect_grid, prepare_charge


def test_grid_tie_chain_runs_in_order(platform):
    bring_online(platform)
    report = connect_grid(platform)
    actions = [step["action"] for step in report["steps"]]
    assert actions.index("ready_confirmed") < actions.index("transfer")
    assert actions.index("transfer") < actions.index("tie_check")
    assert actions.index("tie_check") < actions.index("clamp")
    assert platform.pcs.is_tied()


def test_grid_tie_refused_when_bms_not_ready(platform):
    bring_online(platform)
    platform.racks["rk-01"].apply_temperature(platform.config.bms.ready_temp_c + 5.0)
    report = platform.transfer_grid_tie()
    assert not report["ok"]
    assert report["violations"] == ["bms_not_ready"]
    assert platform.pcs.state_machine.state == "stopped"


def test_grid_tie_returns_off_grid_when_frequency_out_of_band(platform):
    bring_online(platform)
    report = platform.transfer_grid_tie(frequency_hz=52.0)
    assert not report["ok"]
    assert "frequency_out_of_band" in report["violations"]
    assert platform.pcs.state_machine.state == "off_grid"


def test_charge_and_discharge_chain(platform):
    bring_online(platform)
    connect_grid(platform)
    prepare_charge(platform)
    charge = platform.charge(steps=3, dt=600.0)
    assert charge["ok"], charge["violations"]
    actions = [step["action"] for step in charge["steps"]]
    assert actions.index("charge_plan") < actions.index("derate")
    assert actions.index("derate") < actions.index("verify_voltage")
    discharge = platform.discharge(power_kw=300.0, dt=600.0)
    assert discharge["ok"], discharge["violations"]
    discharge_actions = [step["action"] for step in discharge["steps"]]
    assert discharge_actions.index("clamp_before_ramp") < discharge_actions.index("ramp")
    platform.transfer_off_grid()
    assert platform.pcs.state_machine.state == "off_grid"


def test_temperature_chain_refreshes_baseline(platform):
    bring_online(platform)
    report = platform.sample_temperature(temperature_c=50.0, dt=5.0)
    actions = [step["action"] for step in report["steps"]]
    assert actions == ["temperature", "derate", "cool"]
    assert report["charge_limit_ratio"] < 1.0
    replaced = platform.replace_pack_rating(pack_index=0, rating_v=3.4)
    assert replaced["ok"]
    assert [step["action"] for step in replaced["steps"]] == ["replace_pack", "baseline_refresh"]
    assert platform.temp.baseline.rating_v == 3.4


def test_cycle_and_concurrency_probes(platform):
    bring_online(platform)
    cycle = platform.cycle()
    assert cycle["cycle"] == 1
    assert platform.trend_snapshot()
    probe = platform.concurrency_probe(rounds=12)
    assert probe["ok"], probe
    assert probe["illegal_states"] == []
    fault_probe = platform.concurrency_fault_probe(rounds=6)
    assert fault_probe["ok"], fault_probe
    assert set(fault_probe["latched"]) == {"rk-01", "rk-02"}
    platform.sample_temperature(temperature_c=30.0)
    status = platform.status()
    assert status["station"] == "station1"
    assert status["ids_issued"] > 0
    blocked = platform.readiness()
    assert blocked["all_ready"] is False
    assert all("fault_latched" in item["reasons"] for item in blocked["racks"].values())
    platform.clear_fault("rk-01")
    platform.clear_fault("rk-02")
    assert platform.readiness()["all_ready"] is True
