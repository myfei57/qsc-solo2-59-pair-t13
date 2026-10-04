"""平台统一异常类型。

储能电站的失败必须按性质分开：顺序或联锁条件不满足属于可恢复的运行期拒绝；
消防相关异常属于安全侧，必须保持状态直到人工复位；配额不足属于记账侧拒绝；
配置与持久化失败则属于装配期就要拦下的接线问题。审计按异常类型分别归类，
巡检时才能一眼分清责任面。
"""

from __future__ import annotations


class StoreError(Exception):
    """所有平台异常的基类，携带出错的组件名。"""

    def __init__(self, message: str, *, component: str = "batterystore") -> None:
        super().__init__(message)
        self.message = message
        self.component = component

    def as_record(self) -> dict:
        """转成审计可以直接落盘的一条记录。"""

        return {
            "type": type(self).__name__,
            "component": self.component,
            "message": self.message,
        }


class InterlockError(StoreError):
    """顺序或联锁条件不满足，动作被拒绝。"""


class FireError(StoreError):
    """消防联动顺序失败或灭火介质未到位。"""


class QuotaError(StoreError):
    """充放电配额不足或跨周期记账失败。"""


class StorageError(StoreError):
    """持久化读写失败。"""


class ConfigError(StoreError):
    """配置缺失或取值非法。"""


class NamespaceError(StoreError):
    """命名空间重复注册或解析失败。"""
