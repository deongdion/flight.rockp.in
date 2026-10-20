from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Union

from curl_cffi.requests import AsyncSession

GRAPHQL_URL = "https://flight-api.naver.com/graphql"
AIRLINE_LOGO_URL = "https://techminds.pstatic.net/flight/vertical-static/flight/airlines/{code}.png?v=3"

DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "content-type": "application/json",
    "origin": "https://flight.naver.com",
    "referer": "https://flight.naver.com/",
}

TripType = Literal["OW", "RT"]           # 편도 / 왕복
LocationType = Literal["city", "airport"]
DateLike = Union[str, date]              # "20261010", "2026-10-10" 또는 date


class NaverFlightError(Exception):
    pass


# ---------- 타입 변환 헬퍼 (None/타입 불일치 시 기본값) ----------

def as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def as_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return v if isinstance(v, str) else str(v)


def as_opt_str(v: Any) -> Optional[str]:
    return None if v is None else as_str(v)


def as_int(v: Any, default: int = 0) -> int:
    if v is None or isinstance(v, bool):
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def as_opt_int(v: Any) -> Optional[int]:
    return None if v is None else as_int(v)


def as_float(v: Any, default: float = 0.0) -> float:
    if v is None or isinstance(v, bool):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def as_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "y", "yes")
    return default


def as_str_list(v: Any) -> List[str]:
    return [as_str(x) for x in as_list(v) if x is not None]


def as_int_list(v: Any) -> List[int]:
    return [as_int(x) for x in as_list(v) if x is not None]


def airline_logo_url(code: str) -> str:
    """항공사 코드 -> 아이콘 URL (예: "7C" -> .../airlines/7C.png?v=3)"""
    return AIRLINE_LOGO_URL.format(code=code.strip().upper())


def to_date_str(v: Optional[DateLike]) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, date):
        return v.strftime("%Y%m%d")
    return v.replace("-", "")


# ---------- 공용 모델 ----------

@dataclass
class Coordinate:
    latitude: float = 0.0
    longitude: float = 0.0

    @classmethod
    def from_dict(cls, d: Any) -> "Coordinate":
        d = as_dict(d)
        return cls(
            latitude=as_float(d.get("latitude")),
            longitude=as_float(d.get("longitude")),
        )


@dataclass
class CityImage:
    image_url: Optional[str] = None
    copyright: Optional[str] = None
    copyright_url: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Any) -> "CityImage":
        d = as_dict(d)
        return cls(
            image_url=as_opt_str(d.get("imageUrl")),
            copyright=as_opt_str(d.get("copyright")),
            copyright_url=as_opt_str(d.get("copyrightUrl")),
        )


# ---------- GraphQL 요청 ----------

async def post_graphql(
    session: AsyncSession,
    operation_name: str,
    query: str,
    variables: Dict[str, Any],
) -> dict:
    payload = {
        "operationName": operation_name,
        # None 값은 보내지 않음 (서버 기본값 사용)
        "variables": {k: v for k, v in variables.items() if v is not None},
        "query": query,
    }
    resp = await session.post(GRAPHQL_URL, json=payload)
    if resp.status_code != 200:
        raise NaverFlightError(f"{operation_name}: HTTP {resp.status_code}")

    try:
        body = as_dict(resp.json())
    except ValueError as e:
        raise NaverFlightError(f"{operation_name}: JSON 파싱 실패") from e

    errors = as_list(body.get("errors"))
    if errors:
        messages = ", ".join(as_str(as_dict(e).get("message")) for e in errors)
        raise NaverFlightError(f"{operation_name}: {messages}")

    return as_dict(body.get("data"))
