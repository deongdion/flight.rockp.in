"""수집기(update.py) · api · web 이 같이 쓰는 데이터 구조.

  Deal          노선·날짜 1건 — (출발도시, 도착공항, 가는날, 오는날) 키로 최신 1건만 저장
  Offer         판매처 1곳의 요금 — code 는 짧은 링크(/r/<code>) 코드
  Link          짧은 링크 1개 = 판매처 요금 1건을 모을 때 본 그대로 (이동 화면이 먼저 보여 준다)
  RedirectLink  예약 버튼 클릭 시점의 실시간 확인 결과 (이동할 URL + 확인 가격 + 항공편)

여정(가는편/오는편)은 core.naver.Itinerary 를 그대로 쓴다.
web/src/lib/types.ts 가 이 파일과 같은 모양이어야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional

from .affiliates import PARTNERS
from .naver import Itinerary, RealtimeFare, RealtimeResult


@dataclass
class Offer:
    partner_code: str               # 네이버 판매처 코드 (CTR013)
    seller: str                     # 판매처 이름 (트립닷컴)
    price: int                      # 성인 1명 총액
    network: str = ""               # 제휴 네트워크 LP / TP
    itinerary_ids: str = ""         # "가는편ID-오는편ID" — 예약 링크 만들 때 같은 항공편으로 다시 조회
    baggage: str = ""               # FREE / CHARGE / UNKNOWN
    # 이 판매처 요금의 가는편[, 오는편] — 수집기가 보내면 api 가 짧은 링크 정보에만 쓰고 deals 에는 저장 안 함
    itineraries: list[Itinerary] = field(default_factory=list)
    code: str = ""                  # 짧은 링크 코드 (api 가 채운다)

    @classmethod
    def from_fare(cls, f: RealtimeFare, sellers: dict[str, str],
                  itineraries: Optional[list[Itinerary]] = None) -> Offer:
        p = PARTNERS.get(f.partner_code)
        return cls(partner_code=f.partner_code, seller=sellers.get(f.partner_code, f.partner_code),
                   price=f.total_fare, network=p.network if p else "",
                   itinerary_ids=f.itinerary_ids, baggage=f.baggage_fee_type,
                   itineraries=itineraries or [])


@dataclass
class Deal:
    origin: str                     # 출발 도시 (SEL)
    destination: str                # 도착 공항 (NRT)
    destination_name: str           # 도착 도시 이름 (도쿄)
    departure_date: date
    return_date: Optional[date]     # 편도면 None
    offers: list[Offer] = field(default_factory=list)              # 싼 순
    itineraries: list[Itinerary] = field(default_factory=list)     # 최저가의 가는편[, 오는편]
    image_url: Optional[str] = None                                # 도착 도시 사진 (네이버 cityImage)
    country_code: Optional[str] = None                             # 도착 나라 (JP, CN …) — 카드 국기
    checked_at: Optional[datetime] = None                          # 실시간 확인 시각 (api 가 채운다)

    @property
    def price(self) -> int:
        return self.offers[0].price if self.offers else 0

    @property
    def nights(self) -> int:
        return (self.return_date - self.departure_date).days if self.return_date else 0


@dataclass
class Link:
    code: str
    origin: str                     # 출발 공항 (ICN) — 예약 조회는 공항 코드로
    destination: str                # 도착 공항
    destination_name: str
    departure_date: date
    return_date: Optional[date]
    offer: Offer                    # 이 링크의 판매처 요금 (모을 때 가격)
    itineraries: list[Itinerary] = field(default_factory=list)
    image_url: Optional[str] = None
    checked_at: Optional[datetime] = None


@dataclass
class RedirectLink:
    url: str                        # 이동할 예약 페이지 (제휴 추적 포함)
    price: Optional[int]            # 실시간 확인 가격 (확인 못 하면 None)
    kind: Literal["booking", "search"]   # 예약 페이지 / 판매처 검색 페이지
    itineraries: list[Itinerary] = field(default_factory=list)   # 실시간 확인한 항공편
    sold_out: bool = False          # 네이버 조회는 됐지만 이 판매처 요금이 없다 (매진·내림)


# ── RealtimeResult → 공통 구조 ──────────────────────────────────────
def affiliate_fares(r: RealtimeResult) -> list[RealtimeFare]:
    """확정된 제휴 판매처 요금만, 싼 순 (r.fares 는 이미 싼 순)."""
    return [f for f in r.fares if f.is_confirmed and f.partner_code in PARTNERS]


def cheapest_per_seller(fares: list[RealtimeFare], n: Optional[int] = None) -> list[RealtimeFare]:
    """판매처마다 가장 싼 1건 (입력이 싼 순이어야 한다), 상위 n."""
    picked: dict[str, RealtimeFare] = {}
    for f in fares:
        picked.setdefault(f.partner_code, f)
    return list(picked.values())[:n]
