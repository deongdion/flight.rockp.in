"""네이버항공권 예약 파트너(OTA/판매사) 목록.

bookingPartners GraphQL은 '한국어 예약 페이지가 있는 KR OTA' 26곳만 반환하지만,
실제 검색 결과의 partnerCode/agtCode 에는 추가 판매사가 더 있다 (2026-10-13 실측):
  - 해외 OTA (kayakaffiliates 게이트웨이 경유, “해외업체” 표기):
      BDC219 부킹닷컴 / ATK201 mytrip / GTG204 Gotogate
      SKP206 Kiwi.com / EDR215 eDreams
  - 항공사 공식 직접 판매 (코드 패턴 = "A" + 항공사 IATA):
      AYP134 에어프레미아 / A7C136 제주항공 / ATW133 티웨이 / AZE143 이스타항공
    (자사 항공편만 1건씩, 요금타입 A01)
국내선(domestic)도 같은 코드 체계를 쓴다(fares[].agtCode).
"""
from dataclasses import dataclass
from typing import Any, List

from curl_cffi.requests import AsyncSession

from .utils import as_dict, as_list, as_str, post_graphql

OPERATION_NAME = "bookingPartners"

QUERY = """query bookingPartners {
  bookingPartners {
    otaId
    expName
    __typename
  }
}"""


@dataclass
class BookingPartner:
    ota_id: str = ""      # 예: CTR013
    name: str = ""        # 예: 트립닷컴
    kind: str = "kr_ota"  # kr_ota / foreign_ota / airline_official

    @classmethod
    def from_dict(cls, d: Any) -> "BookingPartner":
        d = as_dict(d)
        return cls(
            ota_id=as_str(d.get("otaId")),
            name=as_str(d.get("expName")),
            kind=as_str(d.get("kind")) or "kr_ota",
        )

    @classmethod
    def list_from_data(cls, data: Any) -> List["BookingPartner"]:
        items = as_list(as_dict(data).get("bookingPartners"))
        return [cls.from_dict(x) for x in items if isinstance(x, dict)]


# bookingPartners 응답에 없는 추가 판매사 (2026-10-13 검색 실측)
EXTRA_PARTNERS = [
    BookingPartner("BDC219", "부킹닷컴", "foreign_ota"),
    BookingPartner("ATK201", "mytrip", "foreign_ota"),
    BookingPartner("GTG204", "Gotogate", "foreign_ota"),
    BookingPartner("SKP206", "Kiwi.com", "foreign_ota"),
    BookingPartner("EDR215", "eDreams", "foreign_ota"),
    BookingPartner("AYP134", "에어프레미아(공식)", "airline_official"),
    BookingPartner("A7C136", "제주항공(공식)", "airline_official"),
    BookingPartner("ATW133", "티웨이항공(공식)", "airline_official"),
    BookingPartner("AZE143", "이스타항공(공식)", "airline_official"),
]

AIRLINE_CODES = ("7C", "TW", "ZE", "LJ", "BX", "RS", "KE", "OZ", "YP", "WF", "MU")


def is_airline_official(code: str) -> bool:
    """코드가 'A' + 항공사 IATA 2자 로 시작하면 항공사 공식 판매로 추정."""
    c = (code or "").upper()
    return len(c) >= 3 and c.startswith("A") and c[1:3] in AIRLINE_CODES


async def booking_partners(session: AsyncSession, include_extras: bool = True) -> List[BookingPartner]:
    """네이버항공권 판매사 목록. include_extras=True 면 해외OTA/항공사공식 추가."""
    data = await post_graphql(session, OPERATION_NAME, QUERY, {})
    partners = BookingPartner.list_from_data(data)
    if include_extras:
        known = {p.ota_id for p in partners}
        partners += [p for p in EXTRA_PARTNERS if p.ota_id not in known]
    return partners


__all__ = ["BookingPartner", "booking_partners", "EXTRA_PARTNERS", "is_airline_official"]
