"""공항/도시 코드 상세 (GetAirportDetailList) + 국내 공항 코드 목록."""
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple, get_args

from curl_cffi.requests import AsyncSession

from .utils import CityImage, as_bool, as_dict, as_list, as_opt_str, as_str, as_str_list, post_graphql

OPERATION_NAME = "GetAirportDetailList"

QUERY = """query GetAirportDetailList($airportCodes: [String!]!) {
  airportDetailList(airportCodes: $airportCodes) {
    iataCode
    airportName
    airports
    cityCode
    cityImage {
      copyright
      copyrightUrl
      imageUrl
      __typename
    }
    cityName
    countryName
    event
    isDomestic
    type
    __typename
  }
}"""


@dataclass
class AirportDetail:
    iata_code: str = ""
    airport_name: Optional[str] = None       # 도시 코드(SEL 등)면 None
    airports: List[str] = field(default_factory=list)  # SEL -> ["ICN", "GMP"]
    city_code: str = ""
    city_image: CityImage = field(default_factory=CityImage)
    city_name: str = ""
    country_name: str = ""
    event: bool = False
    is_domestic: bool = False
    type: str = ""                           # "city" / "airport"

    @classmethod
    def from_dict(cls, d: Any) -> "AirportDetail":
        d = as_dict(d)
        return cls(
            iata_code=as_str(d.get("iataCode")),
            airport_name=as_opt_str(d.get("airportName")),
            airports=as_str_list(d.get("airports")),
            city_code=as_str(d.get("cityCode")),
            city_image=CityImage.from_dict(d.get("cityImage")),
            city_name=as_str(d.get("cityName")),
            country_name=as_str(d.get("countryName")),
            event=as_bool(d.get("event")),
            is_domestic=as_bool(d.get("isDomestic")),
            type=as_str(d.get("type")),
        )

    @classmethod
    def list_from_data(cls, data: Any) -> List["AirportDetail"]:
        items = as_list(as_dict(data).get("airportDetailList"))
        return [cls.from_dict(x) for x in items if isinstance(x, dict)]


async def airport_detail_list(
    session: AsyncSession,
    airport_codes: Iterable[str],
) -> List[AirportDetail]:
    """공항/도시 코드 상세 (이름, 국가, 소속 공항, 도시 이미지)"""
    codes = [c for c in airport_codes if c]
    if not codes:
        return []
    data = await post_graphql(session, OPERATION_NAME, QUERY, {"airportCodes": codes})
    return AirportDetail.list_from_data(data)


# ── 국내 공항 ──
DomesticCode = Literal[
    "SEL",  # 서울 (도시)
    "ICN",  # 인천
    "GMP",  # 김포
    "PUS",  # 부산
    "CJU",  # 제주
    "CJJ",  # 청주
    "TAE",  # 대구
    "MWX",  # 무안
    "KWJ",  # 광주
    "RSU",  # 여수
    "KUV",  # 군산
    "USN",  # 울산
    "KPO",  # 포항
    "WJU",  # 원주
    "HIN",  # 사천
    "YNY",  # 양양
]

DomesticType = Literal["city", "airport"]

DOMESTIC_CODES: Tuple[DomesticCode, ...] = get_args(DomesticCode)

DOMESTIC_NAMES: Dict[DomesticCode, str] = {
    "SEL": "서울",
    "ICN": "인천",
    "GMP": "김포",
    "PUS": "부산",
    "CJU": "제주",
    "CJJ": "청주",
    "TAE": "대구",
    "MWX": "무안",
    "KWJ": "광주",
    "RSU": "여수",
    "KUV": "군산",
    "USN": "울산",
    "KPO": "포항",
    "WJU": "원주",
    "HIN": "사천",
    "YNY": "양양",
}

DOMESTIC_TYPES: Dict[DomesticCode, DomesticType] = {
    code: "city" if code == "SEL" else "airport" for code in DOMESTIC_CODES
}


def is_domestic(code: str) -> bool:
    return code in DOMESTIC_NAMES
