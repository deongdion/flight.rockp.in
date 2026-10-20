"""SSE 전역 속도 제한 + 503 페널티 쿨다운.

2026-10-15 실측:
  버스트 16~20개 1회성은 통과 / 지속 ~5/s 이상은 503 스톰 → 약 240초 전면 차단.
  따라서 상시 속도를 rate 이하로 묶어두고, 그래도 503이 나면
  쿨다운 동안 전 요청을 정지시켜 페널티가 길어지지 않게 한다.
"""
from __future__ import annotations

import asyncio
import time


class RateGate:
    """전역 속도 제한 + 503 페널티 쿨다운."""

    def __init__(self, rate: float):
        self.interval = 1.0 / rate
        self.cooldown_until = 0.0
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if now < self.cooldown_until:
                await asyncio.sleep(self.cooldown_until - now)
                now = time.monotonic()
            ready = max(now, self._next_at)
            if ready > now:
                await asyncio.sleep(ready - now)
            self._next_at = ready + self.interval

    @property
    def in_cooldown(self) -> bool:
        return time.monotonic() < self.cooldown_until

    def penalize(self, seconds: float) -> None:
        self.cooldown_until = time.monotonic() + seconds


__all__ = ["RateGate"]
