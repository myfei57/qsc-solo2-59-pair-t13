"""并离网切换的并发原子性、拒绝归因与确定性复位。"""

from __future__ import annotations

import threading
import time

import pytest

from batterystore.errors import InterlockError
from batterystore.ops.transfer import SYNC_SEQUENCE
from support import bring_online, connect_grid


def test_arbiter_only_one_token_holder_and_names_preemptor(platform):
    pcs = platform.pcs
    pcs.transfer("off_grid", "test")
    granted = pcs.acquire_transfer("cmd-A")
    assert granted["granted"] is True
    # 第二条指令进来：必须被拒绝，且说清是被谁抢先（不是条件不满足）。
    with pytest.raises(InterlockError) as raised:
        pcs.acquire_transfer("cmd-B")
    record = raised.value.as_record()
    assert record["reason"] == "transfer_preempted"
    assert record["preempted_by"] == "cmd-A"
    assert record["token"] == "cmd-B"
    # 非持有者不能替别人释放。
    with pytest.raises(InterlockError):
        pcs.release_transfer("cmd-B")
    assert pcs.release_transfer("cmd-A")["released"] is True
    assert pcs.arbiter.is_held() is False


def test_concurrent_platform_commands_only_one_takes_effect(platform):
    bring_online(platform)
    # 一条指令已经握住切换令牌（模拟切换进行中），另一条并网指令并发进来。
    pcs = platform.pcs
    pcs.transfer("off_grid", "test")
    pcs.acquire_transfer("in-flight-cmd")
    try:
        report = platform.transfer_grid_tie()
    finally:
        pcs.release_transfer("in-flight-cmd")
    assert not report["ok"]
    assert report["violations"] == ["transfer_preempted"]
    assert report["rejection"]["why"] == "preempted"
    assert report["rejection"]["preempted_by"] == "in-flight-cmd"
    # 被拒指令没有改变任何状态。
    assert platform.pcs.state_machine.state == "off_grid"
    assert platform.pcs.switch.is_closed() is False


def test_concurrent_transfers_never_observe_torn_state(platform):
    platform.start()
    pcs = platform.pcs
    pcs.transfer("off_grid", "setup")
    rounds = 80
    torn: list[dict] = []
    barrier = threading.Barrier(2)

    def hammer(target: str) -> None:
        barrier.wait()
        for index in range(rounds):
            token = f"{target}:{index}:{threading.get_ident()}"
            try:
                pcs.acquire_transfer(token)
            except InterlockError:
                continue
            try:
                # 持令牌停留一个小窗口，迫使另一路在令牌被占时并发申请。
                time.sleep(0.001)
                pcs.transfer(target, "hammer", token=token)
            except InterlockError:
                pass
            finally:
                pcs.release_transfer(token)
            state = pcs.state_machine.state
            closed = pcs.switch.is_closed()
            expect_closed = state == "grid_tie"
            if closed != expect_closed:
                torn.append({"state": state, "closed": closed})

    threads = [
        threading.Thread(target=hammer, args=("grid_tie",)),
        threading.Thread(target=hammer, args=("off_grid",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert torn == []
    assert pcs.arbiter.preempted_count() > 0
    pcs.transfer("stopped", "teardown")


def test_switch_closes_only_after_sync_passes(platform):
    bring_online(platform)
    report = platform.transfer_grid_tie(frequency_hz=52.0)
    assert not report["ok"]
    # 同期不满足时接触器一次都没闭合过。
    assert platform.pcs.switch.cycles() == 0
    good = platform.transfer_grid_tie(frequency_hz=50.0)
    assert good["ok"]
    assert platform.pcs.switch.cycles() == 1
    assert good["sequence"] == SYNC_SEQUENCE["selected"]


def test_trip_revokes_token_and_reset_lands_on_stopped(platform):
    bring_online(platform)
    connect_grid(platform)
    # 模拟切换进行中保护动作：跳闸强制收回令牌并分断开关。
    platform.pcs.acquire_transfer("mid-transfer")
    trip = platform.pcs.trip("phase_abnormal")
    assert trip["arbiter"]["revoked"] is True
    assert trip["arbiter"]["was_holder"] == "mid-transfer"
    assert platform.pcs.arbiter.is_held() is False
    assert platform.pcs.state_machine.state == "tripped"
    assert platform.pcs.switch.is_closed() is False
    # 复位走同一仲裁入口，落定在确定的停机态。
    release = platform.release_fire()
    assert release["pcs"]["state"] == "stopped"
    assert platform.pcs.state_machine.state == "stopped"
    assert platform.pcs.switch.is_closed() is False
    assert platform.pcs.arbiter.is_held() is False


def test_reset_preempted_while_transfer_in_flight(platform):
    bring_online(platform)
    connect_grid(platform)
    platform.pcs.acquire_transfer("tie-cmd")
    try:
        with pytest.raises(InterlockError) as raised:
            platform.pcs.reset_trip(token="reset-cmd")
        assert raised.value.as_record()["reason"] == "transfer_preempted"
        assert platform.pcs.state_machine.state == "grid_tie"
    finally:
        platform.pcs.release_transfer("tie-cmd")


def test_off_grid_command_uses_same_arbiter(platform):
    bring_online(platform)
    connect_grid(platform)
    platform.pcs.acquire_transfer("other-cmd")
    try:
        report = platform.transfer_off_grid()
        assert not report["ok"]
        assert report["violations"] == ["transfer_preempted"]
        assert report["rejection"]["preempted_by"] == "other-cmd"
    finally:
        platform.pcs.release_transfer("other-cmd")
    report = platform.transfer_off_grid()
    assert report["ok"]
    assert platform.pcs.state_machine.state == "off_grid"
    assert platform.pcs.switch.is_closed() is False
