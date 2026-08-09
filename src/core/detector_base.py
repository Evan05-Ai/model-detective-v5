"""
检测器抽象基类

ActiveDetector: 主动发起请求的检测器
PassiveDetector: 被动观察其他检测器请求/响应的检测器

两阶段执行：
  阶段一：所有 ActiveDetector 并行执行，请求/响应推入 observe_queue
  阶段二：所有 ActiveDetector 完成后，串行调用 PassiveDetector.finalize()
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from .models import CheckResultV2


class ActiveDetector(ABC):
    """主动检测器 - 发起 API 请求进行检测"""

    name: str = ""
    category: str = ""
    weight: float = 1.0
    modes: list[str] = ["standard", "full"]
    timeout: int = 30
    estimated_tokens: int = 1000       # 预估 token 消耗（用于预算预分配）
    budget_limit: int = 0              # 运行时由 Runner 注入的 token 预算上限（0=不限）

    @abstractmethod
    def run(self, client: Any) -> CheckResultV2:
        """执行检测，返回结果"""
        ...

    def is_active(self) -> bool:
        return True


class PassiveDetector(ABC):
    """被动检测器 - 观察其他检测器的请求/响应"""

    name: str = ""
    category: str = ""
    weight: float = 1.0
    modes: list[str] = ["standard", "full"]

    def __init__(self):
        self._observations: list[tuple[dict, dict, str]] = []

    def observe(self, request: dict, response: dict, detector_name: str):
        """接收其他检测器的请求/响应观察数据"""
        self._observations.append((request, response, detector_name))

    @abstractmethod
    def finalize(self) -> CheckResultV2:
        """汇总所有观察数据，返回检测结果"""
        ...

    def is_active(self) -> bool:
        return False
