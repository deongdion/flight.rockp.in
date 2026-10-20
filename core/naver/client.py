import asyncio
import os
from typing import Iterable, List, Optional

from curl_cffi.requests import AsyncSession

from .airports import AirportDetail, airport_detail_list
from .destinations import DestinationPrice, min_prices_by_destination
from .utils import DEFAULT_HEADERS
from .nnb import issue_nnb, set_nnb
from .partners import BookingPartner, booking_partners as _booking_partners
from .search import RealtimeResult, search_domestic, search_international, search_selected


class NaverFlightClient:
    """
    async with NaverFlightClient() as client:
        flights = await client.min_prices_by_destination("SEL")

    NNB 쿠키: 인자 nnb > 환경변수 NAVER_NNB > 자동 발급 순으로 사용
    """

    def __init__(
        self,
        session: Optional[AsyncSession] = None,
        nnb: Optional[str] = None,
        auto_nnb: bool = True,
    ):
        self._own_session = session is None
        self.session = session or AsyncSession(impersonate="chrome", headers=DEFAULT_HEADERS)
        self.auto_nnb = auto_nnb
        self.nnb = nnb or os.environ.get("NAVER_NNB") or None
        self._renew_lock = asyncio.Lock()
        if self.nnb:
            set_nnb(self.session, self.nnb)

    async def __aenter__(self) -> "NaverFlightClient":
        if self.auto_nnb and not self.nnb:
            await self.ensure_nnb()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def ensure_nnb(self) -> str:
        self.nnb = await issue_nnb(self.session)
        return self.nnb

    async def renew_nnb(self) -> str:
        """503 등으로 NNB 가 막혔을 때 쿠키를 버리고 새로 발급."""
        self.session.cookies.clear()
        self.nnb = None
        return await self.ensure_nnb()

    async def close(self) -> None:
        if self._own_session:
            await self.session.close()

    async def min_prices_by_destination(self, departure_location_code: str = "SEL", **kwargs) -> List[DestinationPrice]:
        return await min_prices_by_destination(self.session, departure_location_code, **kwargs)

    async def airport_detail_list(self, airport_codes: Iterable[str]) -> List[AirportDetail]:
        return await airport_detail_list(self.session, airport_codes)

    async def booking_partners(self, include_extras: bool = True) -> List[BookingPartner]:
        """네이버항공권 판매사 목록 (한국OTA + 해외OTA + 항공사공식)."""
        return await _booking_partners(self.session, include_extras=include_extras)

    async def _retry_on_503(self, call) -> RealtimeResult:
        """503 은 NNB 단위 (pool.py 실측) → 새 NNB 로 1회 재시도."""
        r = await call()
        if r.error and "503" in r.error:
            async with self._renew_lock:
                await self.renew_nnb()
            r = await call()
        return r

    async def search_international(self, departure_location_code: str, arrival_location_code: str,
                                   departure_date, return_date=None, **kwargs) -> RealtimeResult:
        """국제선 실시간 최저가 (searchFlights SSE)."""
        return await self._retry_on_503(lambda: search_international(
            self.session, departure_location_code, arrival_location_code,
            departure_date, return_date, **kwargs))

    async def search_selected(self, departure_location_code: str, arrival_location_code: str,
                              departure_date, return_date, itinerary_ids: List[str],
                              **kwargs) -> RealtimeResult:
        """특정 항공편 조합 선택 조회 — 요금마다 reservation_url(판매처 예약 URL) 이 채워진다."""
        return await self._retry_on_503(lambda: search_selected(
            self.session, departure_location_code, arrival_location_code,
            departure_date, return_date, itinerary_ids, **kwargs))

    async def search_domestic(self, departure_airport: str, arrival_airport: str,
                              departure_date, return_date=None, **kwargs) -> RealtimeResult:
        """국내선 실시간 최저가 (searchFlights SSE)."""
        return await self._retry_on_503(lambda: search_domestic(
            self.session, departure_airport, arrival_airport, departure_date, return_date, **kwargs))
