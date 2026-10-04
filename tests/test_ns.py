"""命名空间、拓扑与容量。"""

from __future__ import annotations

import pytest

from batterystore.errors import NamespaceError
from batterystore.config import default_config
from batterystore.ns.capacity import plan_capacity
from batterystore.ns.registry import NamespaceRegistry
from batterystore.ns.topology import Topology, build_default_topology


def test_registry_registers_and_resolves():
    registry = NamespaceRegistry("station1")
    address = registry.register("station", "pcs", "power-conversion")
    assert address == "station:pcs"
    assert registry.resolve(address)["kind"] == "power-conversion"
    assert registry.of_kind("power-conversion") == [address]
    assert registry.count() == 1
    assert registry.addresses()[0]["device"] == "pcs"


def test_registry_rejects_duplicate_address():
    registry = NamespaceRegistry("station1")
    registry.register("station", "pcs", "power-conversion")
    with pytest.raises(NamespaceError):
        registry.register("station", "pcs", "power-conversion")
    with pytest.raises(NamespaceError):
        registry.resolve("station:unknown")


def test_topology_order_and_verify():
    topology = build_default_topology()
    order = topology.order()
    assert order[0] == "rack"
    assert order.index("bms") < order.index("pcs") < order.index("grid")
    assert topology.verify({"rack", "bms"})["missing"] == []
    assert topology.verify({"bms"})["missing"] == ["rack"]
    assert topology.stages_after("pcs")[:2] == ["temp", "grid"]
    assert [stage["stage"] for stage in topology.describe()] == order


def test_topology_rejects_unknown_dependency():
    with pytest.raises(ValueError):
        Topology((("a", "detail", ("missing",)),))


def test_plan_capacity_scales_with_racks():
    config = default_config()
    single = plan_capacity(config, 1)
    double = plan_capacity(config, 2)
    assert double.rated_energy_kwh == pytest.approx(single.rated_energy_kwh * 2)
    assert double.usable_energy_kwh < double.rated_energy_kwh
    assert single.as_dict()["cells_per_rack"] == config.rack.cell_count
    with pytest.raises(ValueError):
        plan_capacity(config, 0)
