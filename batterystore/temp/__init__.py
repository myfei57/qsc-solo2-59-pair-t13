"""温控：降额曲线、额定值基线与冷却。"""

from __future__ import annotations

from .baseline import TempBaseline
from .control import Cooler
from .curve import DerateCurve
from .snapshot import TempSnapshot
from .temp import TempControl

__all__ = ["Cooler", "DerateCurve", "TempBaseline", "TempControl", "TempSnapshot"]
