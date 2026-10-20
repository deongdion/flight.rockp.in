"""어디든지 검색 — 출발지 기준 목적지별 최저가 (minPricesByDestination, 캐시)."""
from dataclasses import dataclass, field
from typing import Any, List, Optional

from curl_cffi.requests import AsyncSession

from .utils import (CityImage, Coordinate, DateLike, TripType, airline_logo_url, as_bool, as_dict,
                    as_int, as_int_list, as_list, as_opt_int, as_opt_str, as_str, as_str_list,
                    post_graphql, to_date_str)

OPERATION_NAME = "minPricesByDestination"

QUERY = """query minPricesByDestination($departureLocationCode: String, $arrivalLocationCode: String, $continentIds: [Int!], $countryCodes: [String!], $departureDate: String, $returnDate: String, $departureMonths: [String!], $duration: [Int!], $isDomestic: Boolean, $isMappable: Boolean, $isNonstop: Boolean, $price: [Int!], $size: Int, $themeIds: [Int!], $timeCategories: [DepartureTimeCategory!], $tripDays: [Int!], $tripType: String) {
  minPricesByDestination(
    departureLocationCode: $departureLocationCode
    arrivalLocationCode: $arrivalLocationCode
    continentIds: $continentIds
    countryCodes: $countryCodes
    departureDate: $departureDate
    returnDate: $returnDate
    departureMonths: $departureMonths
    duration: $duration
    isDomestic: $isDomestic
    isMappable: $isMappable
    isNonstop: $isNonstop
    price: $price
    size: $size
    themeIds: $themeIds
    timeCategories: $timeCategories
    tripDays: $tripDays
    tripType: $tripType
  ) {
    origin {
      airportCode
      airportName
      cityName
      isDomestic
      location {
        latitude
        longitude
        __typename
      }
      popularity
      type
      __typename
    }
    destination {
      airportCode
      airportName
      cityImage {
        imageUrl
        __typename
      }
      cityName
      event
      isDomestic
      location {
        latitude
        longitude
        __typename
      }
      popularity
      type
      __typename
    }
    departureDate
    airlineCodes
    continentId
    countryCode
    duration
    isDomestic
    minPrice
    returnDate
    stops
    themeIds
    timeCategory
    tripDays
    tripType
    __typename
  }
}"""


@dataclass
class Airport:
    airport_code: str = ""
    airport_name: str = ""
    city_name: str = ""
    city_image: CityImage = field(default_factory=CityImage)  # origin 에는 없음
    event: bool = False                                        # origin 에는 없음
    is_domestic: bool = False
    location: Coordinate = field(default_factory=Coordinate)
    popularity: int = 0
    type: str = ""

    @classmethod
    def from_dict(cls, d: Any) -> "Airport":
        d = as_dict(d)
        return cls(
            airport_code=as_str(d.get("airportCode")),
            airport_name=as_str(d.get("airportName")),
            city_name=as_str(d.get("cityName")),
            city_image=CityImage.from_dict(d.get("cityImage")),
            event=as_bool(d.get("event")),
            is_domestic=as_bool(d.get("isDomestic")),
            location=Coordinate.from_dict(d.get("location")),
            popularity=as_int(d.get("popularity")),
            type=as_str(d.get("type")),
        )


@dataclass
class DestinationPrice:
    origin: Airport = field(default_factory=Airport)
    destination: Airport = field(default_factory=Airport)
    departure_date: str = ""                 # YYYYMMDD
    airline_codes: List[str] = field(default_factory=list)
    continent_id: int = 0
    country_code: str = ""
    duration: int = 0                        # 초 단위 (21900 = 6시간 5분)
    is_domestic: bool = False
    min_price: int = 0
    return_date: Optional[str] = None        # 편도(OW)면 None
    stops: int = 0
    theme_ids: List[int] = field(default_factory=list)
    time_category: Optional[str] = None      # 예: "18-21"
    trip_days: Optional[int] = None
    trip_type: str = ""                      # "OW" / "RT"

    @classmethod
    def from_dict(cls, d: Any) -> "DestinationPrice":
        d = as_dict(d)
        return cls(
            origin=Airport.from_dict(d.get("origin")),
            destination=Airport.from_dict(d.get("destination")),
            departure_date=as_str(d.get("departureDate")),
            airline_codes=as_str_list(d.get("airlineCodes")),
            continent_id=as_int(d.get("continentId")),
            country_code=as_str(d.get("countryCode")),
            duration=as_int(d.get("duration")),
            is_domestic=as_bool(d.get("isDomestic")),
            min_price=as_int(d.get("minPrice")),
            return_date=as_opt_str(d.get("returnDate")),
            stops=as_int(d.get("stops")),
            theme_ids=as_int_list(d.get("themeIds")),
            time_category=as_opt_str(d.get("timeCategory")),
            trip_days=as_opt_int(d.get("tripDays")),
            trip_type=as_str(d.get("tripType")),
        )

    @property
    def airline_logo_urls(self) -> List[str]:
        return [airline_logo_url(c) for c in self.airline_codes if c]

    @classmethod
    def list_from_data(cls, data: Any) -> List["DestinationPrice"]:
        items = as_list(as_dict(data).get("minPricesByDestination"))
        return [cls.from_dict(x) for x in items if isinstance(x, dict)]


async def min_prices_by_destination(
    session: AsyncSession,
    departure_location_code: str = "SEL",
    *,
    arrival_location_code: Optional[str] = None,
    continent_ids: Optional[List[int]] = None,
    country_codes: Optional[List[str]] = None,
    departure_date: Optional[DateLike] = None,
    return_date: Optional[DateLike] = None,
    departure_months: Optional[List[str]] = None,
    duration: Optional[List[int]] = None,
    is_domestic: Optional[bool] = None,
    is_mappable: Optional[bool] = True,
    is_nonstop: Optional[bool] = None,
    price: Optional[List[int]] = None,       # [최소, 최대]
    size: Optional[int] = None,
    theme_ids: Optional[List[int]] = None,
    time_categories: Optional[List[str]] = None,
    trip_days: Optional[List[int]] = None,   # [최소, 최대]
    trip_type: Optional[TripType] = None,
) -> List[DestinationPrice]:
    """출발지 기준 목적지별 최저가 (어디든지 검색)"""
    data = await post_graphql(session, OPERATION_NAME, QUERY, {
        "departureLocationCode": departure_location_code,
        "arrivalLocationCode": arrival_location_code,
        "continentIds": continent_ids,
        "countryCodes": country_codes,
        "departureDate": to_date_str(departure_date),
        "returnDate": to_date_str(return_date),
        "departureMonths": departure_months,
        "duration": duration,
        "isDomestic": is_domestic,
        "isMappable": is_mappable,
        "isNonstop": is_nonstop,
        "price": price,
        "size": size,
        "themeIds": theme_ids,
        "timeCategories": time_categories,
        "tripDays": trip_days,
        "tripType": trip_type,
    })
    return DestinationPrice.list_from_data(data)
