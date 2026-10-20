from litestar.params import FromQuery

from api import database


def GET(origin: FromQuery[str | None] = None, destination: FromQuery[str | None] = None,
        departure_date: FromQuery[str | None] = None,
        return_date: FromQuery[str | None] = None) -> dict[str, list[dict]]:
    """조건 칩 목록 — 출발지·도착지·가는 날·오는 날 값마다 특가 수·최저가."""
    return database.deal_facets({"origin": origin, "destination": destination,
                                 "departure_date": departure_date, "return_date": return_date})
