"""NNB 세션 풀 — 세션마다 독립 NNB, 라운드로빈. 프록시를 주면 프록시당 NNB 1개.

2026-10-16 실측:
  - 503 은 NNB 단위 (3/s 에서 8개 중 2개만 503, 새 NNB 는 즉시 정상, 503 난 NNB 는 4~5분 뒤 회복)
  - 너무 빠르면(≈7/s, 직접 연결) IP 단위로도 잠깐 막힘 → 프록시로 IP 를 나누면 503 0건
  - 프록시 197개 중 ~26개는 SSE 가 계속 타임아웃

그래서 풀은 503 난 NNB 를 bench_503 초 쉬게 하고, 연속 실패 fail_limit 번이면 bench_fail 초 뺀다.

    async with NNBPool(8) as pool:                           # 직접 연결 8개
    async with NNBPool(proxies=load_proxies(path)) as pool:   # 프록시마다 1개
        c = await pool.pick()          # 쉬는 중이 아닌 다음 클라이언트
        ... c.session ...
        pool.report(c, ok=True)        # 또는 pool.bench(c, 300) (503)
"""
from __future__ import annotations

import asyncio
import itertools
import time
from typing import Optional

from curl_cffi.requests import AsyncSession

from .client import NaverFlightClient
from .utils import DEFAULT_HEADERS


def load_proxies(path: str) -> list[str]:
    """한 줄에 하나. host:port / host:port:user:pass / http://user:pass@host:port. # 은 주석."""
    out = []
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "://" not in line:
            p = line.split(":")
            line = f"http://{p[2]}:{p[3]}@{p[0]}:{p[1]}" if len(p) == 4 else f"http://{line}"
        out.append(line)
    return out


class NNBPool:
    def __init__(self, size: int = 8, proxies: Optional[list[str]] = None, *,
                 issue_timeout: float = 20, fail_limit: int = 3, bench_fail: float = 600):
        self.targets: list[Optional[str]] = list(proxies) if proxies else [None] * size
        self.issue_timeout = issue_timeout
        self.fail_limit = fail_limit
        self.bench_fail = bench_fail
        self.clients: list[NaverFlightClient] = []
        self.failed = 0                                 # NNB 발급 실패 수
        self._until: dict[int, float] = {}              # id(client) → 쉬는 끝 시각
        self._fails: dict[int, int] = {}                # id(client) → 연속 실패
        self._rr = itertools.count()

    async def _make(self, proxy: Optional[str]) -> None:
        sess = AsyncSession(impersonate="chrome", headers=DEFAULT_HEADERS, proxy=proxy)
        c = NaverFlightClient(session=sess)
        try:
            await asyncio.wait_for(c.ensure_nnb(), self.issue_timeout)
            self.clients.append(c)
        except Exception:
            self.failed += 1
            await sess.close()

    async def __aenter__(self) -> "NNBPool":
        await asyncio.gather(*(self._make(p) for p in self.targets))
        if not self.clients:
            raise RuntimeError(f"NNB 발급 전부 실패 ({self.failed}건)")
        return self

    async def __aexit__(self, *_) -> None:
        for c in self.clients:
            try:
                await c.session.close()
            except Exception:
                pass

    async def pick(self) -> NaverFlightClient:
        """쉬는 중이 아닌 다음 클라이언트. 전부 쉬는 중이면 가장 먼저 풀리는 것까지 대기."""
        while True:
            now = time.monotonic()
            n = len(self.clients)
            for _ in range(n):
                c = self.clients[next(self._rr) % n]
                if self._until.get(id(c), 0) <= now:
                    return c
            await asyncio.sleep(max(0.5, min(self._until.values()) - now))

    def session(self) -> AsyncSession:
        """쉬는 상태 무시하고 라운드로빈 (발견 등 가벼운 호출용)."""
        return self.clients[next(self._rr) % len(self.clients)].session

    def bench(self, c: NaverFlightClient, seconds: float) -> None:
        self._until[id(c)] = time.monotonic() + seconds
        self._fails[id(c)] = 0

    def report(self, c: NaverFlightClient, ok: bool) -> None:
        """연속 fail_limit 번 실패하면 bench_fail 초 뺀다 (죽은 프록시 걸러내기)."""
        if ok:
            self._fails[id(c)] = 0
            return
        self._fails[id(c)] = self._fails.get(id(c), 0) + 1
        if self._fails[id(c)] >= self.fail_limit:
            self.bench(c, self.bench_fail)

    @property
    def active(self) -> int:
        now = time.monotonic()
        return sum(1 for c in self.clients if self._until.get(id(c), 0) <= now)

    @property
    def nnbs(self) -> list[str]:
        return [c.nnb or "" for c in self.clients]

    def __len__(self) -> int:
        return len(self.clients)


__all__ = ["NNBPool", "load_proxies"]
