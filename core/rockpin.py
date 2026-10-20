"""Rockpin(록핀) 서버 API — 급락항공 외부 프로그램 연동.

명세: https://rockpin.ai/dist/document/api.yaml  (태그 10.급락항공_외부)
인증: IP 화이트리스트 + X-API-KEY 헤더 (env X_API_KEY)
서버: https://rockpin.ai/ (env ROCKPIN_API_BASE 로 교체)
응답: {"result": "Y"|"N", "message", "ErrCODE", "data"}  — result 가 N 이면 RockpinError(err_code)

    async with Rockpin() as rp:
        items = await rp.tracking_flights()                  # 추적 중인 항공편 (활성)
        await rp.send_flight_prices([{"fc_idx": .., "m_idx": .., "price": ..}])   # receive-price2
        await rp.send_flight_routes([{"trip_id": .., "source": .., ...}])          # receive-flights
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Any, Optional

from curl_cffi.requests import AsyncSession

DEFAULT_BASE = "https://rockpin.ai/"
TIMEOUT = 30
ROUTE_CHUNK = 50              # receive-flights 요청당 노선 수
BULK_TIMEOUT = 90


def _load_env() -> None:
    """프로젝트 루트(Redirect/)의 .env 에서 X_API_KEY / ROCKPIN_API_BASE 만 읽는다 (이미 있는 값은 유지)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, ".env")
    if not os.path.isfile(path):
        return
    for line in open(path, encoding="utf-8-sig"):
        k, sep, v = line.strip().partition("=")
        if sep and k in ("X_API_KEY", "ROCKPIN_API_BASE") and k not in os.environ:
            os.environ[k] = v.strip().strip("\"'")


class RockpinError(Exception):
    def __init__(self, message: str, err_code: Optional[str] = None):
        super().__init__(f"[{err_code}] {message}" if err_code else message)
        self.err_code = err_code


@dataclass
class TrackingFlight:
    """tracking-flights 1건. receive-price2 키는 fc_idx + m_idx."""
    fct_idx: int = 0
    m_idx: int = 0
    m_id: str = ""
    fc_idx: int = 0
    fct_target_price: Optional[int] = None     # 목표가
    fct_is_active: Optional[str] = None
    fct_dep_date: Optional[str] = None          # 추적 출발일 (null 이면 전체)
    fct_arr_date: Optional[str] = None
    fct_regdate: Optional[str] = None
    fc_trip_id: Optional[str] = None
    fc_source: Optional[str] = None             # trip | mrt | local
    fc_dep_city: Optional[str] = None           # 공항 코드 (ICN, PUS ...)
    fc_dep_city_name: Optional[str] = None
    fc_arr_city: Optional[str] = None
    fc_arr_city_name: Optional[str] = None
    fc_dep_date: Optional[str] = None           # YYYY-MM-DD
    fc_arr_date: Optional[str] = None           # 편도면 None
    fc_detail_url: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "TrackingFlight":
        out = {}
        for f in fields(cls):
            v = d.get(f.name)
            if v in ("", None):
                continue
            out[f.name] = int(v) if f.name in ("fct_idx", "m_idx", "fc_idx", "fct_target_price") else str(v)
        return cls(**out)

    @property
    def route(self) -> str:
        return f"{self.fc_dep_city}→{self.fc_arr_city}"


class Rockpin:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        _load_env()
        self.api_key = api_key or os.getenv("X_API_KEY") or ""
        self.base = (base_url or os.getenv("ROCKPIN_API_BASE") or DEFAULT_BASE).rstrip("/") + "/"
        self.session: Optional[AsyncSession] = None

    async def __aenter__(self) -> "Rockpin":
        if not self.api_key:
            raise RockpinError("X_API_KEY 가 없습니다 (.env)", "AUTH_TOKEN_MISSING")
        self.session = AsyncSession()
        return self

    async def __aexit__(self, *_) -> None:
        if self.session:
            await self.session.close()

    async def _call(self, path: str, body: Optional[dict] = None, timeout: int = TIMEOUT) -> Any:
        """POST → result 검증 → data 반환."""
        assert self.session, "async with Rockpin() 안에서 호출"
        headers = {"X-API-KEY": self.api_key, "Accept": "application/json"}
        r = await self.session.post(self.base + path, headers=headers, json=body, timeout=timeout)
        try:
            payload = r.json()
        except Exception:
            raise RockpinError(f"JSON 아님 HTTP {r.status_code}: {r.text[:200]}", "BAD_RESPONSE")
        if not isinstance(payload, dict) or payload.get("result") != "Y":
            p = payload if isinstance(payload, dict) else {}
            raise RockpinError(p.get("message") or f"HTTP {r.status_code}", p.get("ErrCODE"))
        return payload.get("data")

    # ── 급락항공 외부 ───────────────────────────────────────────────
    async def tracking_flights(self) -> list[TrackingFlight]:
        """POST api/web/flightcrash/tracking-flights — 목표가 설정된 활성 추적 목록."""
        return [TrackingFlight.from_dict(d) for d in await self._call("api/web/flightcrash/tracking-flights") or []]

    async def send_flight_prices(self, items: list[dict]) -> dict:
        """POST api/web/flightcrash/receive-price2 — 회원별 추적 가격 (이력 누적).
        항목: fc_idx, m_idx, price (필수), collect_date (생략 시 오늘)."""
        return await self._call("api/web/flightcrash/receive-price2", {"flights": items}) or {}

    async def send_flight_routes(self, items: list[dict], chunk: int = ROUTE_CHUNK) -> dict:
        """POST api/web/flightcrash/receive-flights — 노선 현재가 upsert (+ 이력).
        upsert 키는 서버가 source+dep_city+arr_city+dep_date+arr_date 로 계산.
        필수: trip_id, source(trip|mrt), dep_city, arr_city, dep_date, price.
        청크로 나눠 보내고 합산. 청크 하나가 실패해도 나머지는 보낸다."""
        total = {"success": 0, "failed": 0, "errors": []}
        for i in range(0, len(items), chunk):
            part = items[i:i + chunk]
            try:
                r = await self._call("api/web/flightcrash/receive-flights", {"flights": part}, BULK_TIMEOUT)
            except Exception as e:
                r = {"failed": len(part), "errors": [{"message": f"{type(e).__name__}: {e}"}]}
            total["success"] += int(r.get("success") or 0)
            total["failed"] += int(r.get("failed") or 0)
            total["errors"] += r.get("errors") or []
        return total
