"""电化学储能电站簇级联控服务。

对外只暴露装配入口 ``Platform`` 与工厂 ``build_platform``。各组件包
（ns、rack、bms、pcs、temp、fire、grid、soc、balance、quota、audit、
store、ops、console）由 ``Platform`` 的真实调用链串联：组件之间不互相导入
对方的私有实现，只依赖对方暴露的状态查询与动作接口。
"""

from __future__ import annotations

__version__ = "1.0.0"

from .app import Platform, build_platform

__all__ = ["Platform", "build_platform", "__version__"]
