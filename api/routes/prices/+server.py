from typing import Literal

from litestar.params import FromQuery

from api import database
from api.schemas import PriceHistory, PricePoint


def GET(destination: FromQuery[str], origin: FromQuery[str | None] = None,
        departure_date: FromQuery[str | None] = None, return_date: FromQuery[str | None] = None,
        period: FromQuery[Literal["today", "7d", "30d"]] = "7d") -> PriceHistory:
    """가격 추이 캔들 — today: 오늘 한 시간 단위 · 7d/30d: 하루 단위.
    특가가 사라져도 기록은 남는다 (database.py prices). 전체 평균으로 지금 가격이 얼마나 싼지 볼 수 있다."""
    rows = database.price_history(destination, origin, departure_date, return_date, period)
    points = [PricePoint(**r) for r in rows]
    total = sum(p.count for p in points)
    avg = round(sum(p.avg * p.count for p in points) / total) if total else None
    return PriceHistory(period, points, min((p.min for p in points), default=None), avg,
                        max((p.max for p in points), default=None))
