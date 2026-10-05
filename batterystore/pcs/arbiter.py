"""并离网切换仲裁器。

两路指令（并网/离网/跳闸复位）并发进来时，必须只有一条进入切换流程，另一条
在入口就拿到明确的拒绝答复。仲裁器发放单枚排他令牌：拿不到令牌的请求被拒绝，
拒绝细节里写清当前持有者是谁（``preempted_by``），与"同期/就绪条件不满足"的
拒绝区分开——前者是被谁抢先，后者是条件本身不成立，巡检时责任面不同。

仲裁器只负责"谁有资格动切换"，具体的状态迁移与接触器动作仍由 PCS 状态机的锁
兜底；两层合起来才能保证并发指令不会各写各的、交出"既并网又离网"的中间态。
"""

from __future__ import annotations

import threading

from ..errors import InterlockError


class TransferArbiter:
    """单令牌切换仲裁：并发切换只有一条生效。"""

    def __init__(self) -> None:
        self._gate = threading.Lock()
        self._holder: str | None = None
        self._since_generation = 0
        self._preempted = 0
        self._granted = 0

    def holder(self) -> str | None:
        """返回当前持有切换令牌的指令标识，空闲时为 None。"""

        with self._gate:
            return self._holder

    def is_held(self) -> bool:
        """切换令牌是否被某条指令持有。"""

        with self._gate:
            return self._holder is not None

    def acquire(self, token: str, generation: int) -> dict:
        """申请切换令牌；被抢先或重复申请时抛联锁错误。

        重复申请（同一指令重入）直接拒绝为 ``transfer_in_progress``，避免同一
        指令在异常路径上二次进入把自己的切换打断。
        """

        with self._gate:
            if self._holder is not None:
                self._preempted += 1
                if self._holder == token:
                    raise InterlockError(
                        f"切换令牌已被本指令持有: {token}",
                        component="pcs",
                        details={
                            "reason": "transfer_in_progress",
                            "token": token,
                            "preempted_by": self._holder,
                            "preempted_generation": self._since_generation,
                        },
                    )
                raise InterlockError(
                    f"切换被抢先：{token} 被 {self._holder} 拒绝",
                    component="pcs",
                    details={
                        "reason": "transfer_preempted",
                        "token": token,
                        "preempted_by": self._holder,
                        "preempted_generation": self._since_generation,
                    },
                )
            self._holder = token
            self._since_generation = generation
            self._granted += 1
            return {
                "token": token,
                "granted": True,
                "generation": generation,
                "granted_total": self._granted,
            }

    def release(self, token: str) -> dict:
        """归还令牌；非持有者不能释放，防止一条指令把另一条的切换解锁。"""

        with self._gate:
            previous = self._holder
            if previous is None:
                return {"token": token, "released": False, "was_holder": None}
            if previous != token:
                raise InterlockError(
                    f"非持有者不能释放切换令牌: {token} != {previous}",
                    component="pcs",
                    details={
                        "reason": "transfer_token_mismatch",
                        "token": token,
                        "preempted_by": previous,
                    },
                )
            self._holder = None
            self._since_generation = 0
            return {"token": token, "released": True, "was_holder": previous}

    def revoke(self, reason: str) -> dict:
        """保护跳闸等安全侧动作强制收回令牌，不校验持有者。"""

        with self._gate:
            previous = self._holder
            self._holder = None
            self._since_generation = 0
            return {"revoked": previous is not None, "was_holder": previous, "reason": reason}

    def preempted_count(self) -> int:
        """返回因被抢先而拒绝的次数。"""

        with self._gate:
            return self._preempted

    def granted_count(self) -> int:
        """返回令牌发放次数。"""

        with self._gate:
            return self._granted
