"""充电电流阶梯。

阶梯切换有明确顺序：先降到目标电流，等电压核对通过，才允许再升流。核压
结果带状态，升流时若上一次核压不是通过状态就直接拒绝，避免"电压没稳定
电流又顶上去"。
"""

from __future__ import annotations

from ..errors import InterlockError


class CurrentLadder:
    """带顺序约束的充电电流阶梯。"""

    def __init__(self, step_a: float, tolerance_a: float, max_a: float) -> None:
        if step_a <= 0:
            raise ValueError("阶梯步长必须为正")
        self._step_a = float(step_a)
        self._tolerance_a = float(tolerance_a)
        self._max_a = float(max_a)
        self._current_a = 0.0
        self._target_a = 0.0
        self._voltage_ok = False
        self._checks = 0
        self._raises = 0
        self._lowers = 0
        self._sequence: list[dict] = []

    @property
    def step_a(self) -> float:
        return self._step_a

    @property
    def tolerance_a(self) -> float:
        return self._tolerance_a

    def current_a(self) -> float:
        """返回当前电流。"""

        return self._current_a

    def target_a(self) -> float:
        """返回当前目标电流。"""

        return self._target_a

    def begin(self, target_a: float) -> float:
        """设定目标电流并复位核压标志，返回目标值。"""

        self._target_a = max(0.0, min(self._max_a, float(target_a)))
        self._voltage_ok = False
        self._sequence.append({"action": "begin", "target_a": self._target_a})
        return self._target_a

    def lower_to(self, target_a: float) -> float:
        """把电流降到目标值：降流本身不要求先核压。"""

        self._target_a = max(0.0, min(self._max_a, float(target_a)))
        if self._current_a > self._target_a:
            self._lowers += 1
        self._current_a = self._target_a
        self._voltage_ok = False
        self._sequence.append({"action": "lower", "current_a": self._current_a, "target_a": self._target_a})
        return self._current_a

    def verify_voltage(self, measured_v: float, expected_v: float, tolerance_v: float) -> bool:
        """核对电压是否落在期望带内，返回是否通过。"""

        self._checks += 1
        self._voltage_ok = abs(float(measured_v) - float(expected_v)) <= float(tolerance_v)
        self._sequence.append(
            {
                "action": "verify_voltage",
                "measured_v": round(float(measured_v), 4),
                "expected_v": round(float(expected_v), 4),
                "ok": self._voltage_ok,
            }
        )
        return self._voltage_ok

    def raise_to(self, target_a: float) -> float:
        """升流：上一次核压必须通过才允许上调。"""

        if not self._voltage_ok:
            raise InterlockError("电压核对未通过，不允许升流", component="pcs")
        wanted = max(0.0, min(self._max_a, float(target_a)))
        if wanted - self._current_a > self._step_a + self._tolerance_a:
            raise InterlockError(f"单次升流超过阶梯步长 {self._step_a}A", component="pcs")
        self._target_a = wanted
        self._current_a = wanted
        self._raises += 1
        self._voltage_ok = False
        self._sequence.append({"action": "raise", "current_a": self._current_a})
        return self._current_a

    def sequence(self, limit: int = 20) -> list[dict]:
        """返回最近的阶梯动作序列。"""

        return [dict(item) for item in self._sequence[-limit:]]

    def counts(self) -> dict:
        """返回核压与升降流计数。"""

        return {"checks": self._checks, "raises": self._raises, "lowers": self._lowers}
