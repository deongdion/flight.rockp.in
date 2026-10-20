"""공개 응답 모양 — 화면에 필요한 것만 내보낸다.

저장 구조(core/models.py)에는 수집·예약 링크용 내부 값이 있다 (제휴 네트워크, 네이버 항공편 ID,
판매처별 여정 등). 이걸 그대로 내보내지 않고 여기서 골라 담는다.
web/src/lib/types.ts 가 이 파일과 같은 모양이어야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from core.models import Deal, Link, Offer
from core.naver import Itinerary


@dataclass
class OfferOut:
    partner_code: str               # 판매처 코드 (로고)
    seller: str
    price: int
    baggage: str                    # FREE / CHARGE / UNKNOWN
    code: str                       # 짧은 링크 → /r/<code>

    @classmethod
    def of(cls, o: Offer) -> OfferOut:
        return cls(o.partner_code, o.seller, o.price, o.baggage, o.code)


@dataclass
class DealOut:
    origin: str
    destination: str
    destination_name: str
    departure_date: date
    return_date: Optional[date]
    offers: list[OfferOut]          # 싼 순
    itineraries: list[Itinerary]    # 최저가의 가는편[, 오는편]
    image_url: Optional[str]
    country_code: Optional[str]
    checked_at: Optional[datetime]

    @classmethod
    def of(cls, d: Deal) -> DealOut:
        return cls(d.origin, d.destination, d.destination_name, d.departure_date, d.return_date,
                   [OfferOut.of(o) for o in d.offers], d.itineraries, d.image_url, d.country_code,
                   d.checked_at)


@dataclass
class DealPage:
    total: int                      # 조건에 맞는 개수 (group=destination 이면 도착지 수)
    deal_count: int                 # 조건에 맞는 특가 수 (묶지 않고)
    items: list[DealOut]


@dataclass
class LinkOut:
    code: str
    origin: str
    destination: str
    destination_name: str
    departure_date: date
    return_date: Optional[date]
    offer: OfferOut                 # 모을 때 가격
    itineraries: list[Itinerary]
    image_url: Optional[str]
    checked_at: Optional[datetime]

    @classmethod
    def of(cls, l: Link) -> LinkOut:
        return cls(l.code, l.origin, l.destination, l.destination_name, l.departure_date, l.return_date,
                   OfferOut.of(l.offer), l.itineraries, l.image_url, l.checked_at)


@dataclass
class PricePoint:
    """캔들 한 칸 — 하루 또는 한 시간."""
    t: str                          # YYYY-MM-DD / YYYY-MM-DDTHH (한국 시각)
    open: int                       # 첫 가격
    close: int                      # 마지막 가격
    min: int
    max: int
    avg: int
    count: int                      # 관측 수


@dataclass
class PriceHistory:
    period: str                     # today / 7d / 30d
    points: list[PricePoint]
    min: Optional[int]              # 기간 전체
    avg: Optional[int]
    max: Optional[int]
