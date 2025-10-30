"""简单事件总线 (第一阶段骨架)

特性:
- on(event, callback)
- off(event, callback) 可选
- emit(event, payload)
- once(event, callback) 简易实现

后续可扩展: 异步队列、日志记录、性能计数、事件优先级。
"""
from __future__ import annotations
from typing import Callable, Dict, List, Any, DefaultDict
from collections import defaultdict
import threading

Callback = Callable[[Any], None]

class EventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subs: DefaultDict[str, List[Callback]] = defaultdict(list)

    def on(self, event: str, cb: Callback) -> None:
        if not callable(cb):
            raise TypeError("callback must be callable")
        with self._lock:
            self._subs[event].append(cb)

    def once(self, event: str, cb: Callback) -> None:
        def _wrap(payload: Any):
            try:
                cb(payload)
            finally:
                self.off(event, _wrap)
        self.on(event, _wrap)

    def off(self, event: str, cb: Callback) -> None:
        with self._lock:
            if event in self._subs:
                try:
                    self._subs[event].remove(cb)
                except ValueError:
                    pass
                if not self._subs[event]:
                    self._subs.pop(event, None)

    def emit(self, event: str, payload: Any = None) -> None:
        # 拷贝列表避免回调中修改订阅导致迭代冲突
        with self._lock:
            callbacks = list(self._subs.get(event, []))
        for cb in callbacks:
            try:
                cb(payload)
            except Exception:
                # 首阶段静默，后期可接入日志
                pass

# 全局单例（第一阶段简单方式）
_global_bus: EventBus | None = None

def get_global_bus() -> EventBus:
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus
