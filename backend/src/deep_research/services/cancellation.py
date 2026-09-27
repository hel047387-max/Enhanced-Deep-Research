from __future__ import annotations

from threading import RLock


# 定义一个“取消状态注册表”类。
    # 作用：记录哪些 thread_id 对应的研究任务已经被取消。
class ResearchCancelled(RuntimeError):
    """Raised at a cooperative graph boundary after cancellation."""


class CancellationRegistry:
    """Thread-safe in-process cancellation flags keyed by conversation thread."""

    def __init__(self) -> None:
        self._cancelled: set[str] = set()
        self._lock = RLock()
# 标记取消
    def cancel(self, thread_id: str) -> None:
        with self._lock:
            self._cancelled.add(thread_id)
# 清除取消标记
    def clear(self, thread_id: str) -> None:
        with self._lock:
            self._cancelled.discard(thread_id)
 # 查询是否取消
    def is_cancelled(self, thread_id: str) -> bool:
        with self._lock:
            return thread_id in self._cancelled
# 已取消则抛异常
    def raise_if_cancelled(self, thread_id: str) -> None:
        if self.is_cancelled(thread_id):
            raise ResearchCancelled("research was cancelled")
