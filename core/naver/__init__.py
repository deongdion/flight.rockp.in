"""네이버 항공권 비공식 클라이언트 (flight-api.naver.com)."""
from .airports import DOMESTIC_CODES, AirportDetail, airport_detail_list
from .client import NaverFlightClient
from .destinations import Airport, DestinationPrice, min_prices_by_destination
from .nnb import NNBError, issue_nnb
from .partners import BookingPartner, booking_partners
from .pool import NNBPool, load_proxies
from .ratelimit import RateGate
from .search import (Itinerary, RealtimeFare, RealtimeResult, Segment, search_domestic,
                     search_international, search_selected)
from .utils import NaverFlightError, airline_logo_url

__all__ = [
    "NaverFlightClient", "NaverFlightError", "NNBError", "issue_nnb",
    "NNBPool", "load_proxies", "RateGate",
    "min_prices_by_destination", "DestinationPrice", "Airport",
    "airport_detail_list", "AirportDetail", "DOMESTIC_CODES",
    "booking_partners", "BookingPartner",
    "search_international", "search_domestic", "search_selected",
    "RealtimeResult", "RealtimeFare", "Itinerary", "Segment",
    "airline_logo_url",
]
