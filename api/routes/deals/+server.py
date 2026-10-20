from litestar import Request
from litestar.exceptions import PermissionDeniedException
from litestar.params import FromQuery

from api import database
from api.schemas import DealOut, DealPage
from core.models import Deal


def _collector_only(request: Request) -> None:
    """저장·삭제는 이 PC 의 수집기(update.py)만 — 사이트(터널·web 프록시)를 거쳐 온 요청은 막는다.
    Cloudflare 는 cf-connecting-ip 를, 프록시는 x-forwarded-for 를 붙인다."""
    client = request.client.host if request.client else ""
    forwarded = any(h in request.headers for h in ("cf-connecting-ip", "x-forwarded-for", "cf-ray"))
    if client not in ("127.0.0.1", "::1") or forwarded:
        raise PermissionDeniedException()


def GET(origin: FromQuery[str | None] = None, destination: FromQuery[str | None] = None,
        departure_date: FromQuery[str | None] = None, return_date: FromQuery[str | None] = None,
        group: FromQuery[str | None] = None, direct: FromQuery[bool] = False,
        sort: FromQuery[str] = "price", offset: FromQuery[int] = 0, limit: FromQuery[int] = 24) -> DealPage:
    """특가 한 쪽 (싼 순 / sort=date 빠른 출발순). 조건은 모두 선택 사항.
    group=destination 이면 도착지마다 최저 1건. 화면은 처음 한 쪽만 받고 스크롤하면 다음 쪽을 이어 받는다.
    하루 지난 것·출발일 지난 것은 서버가 1시간마다 지운다 (app.py cleanup_loop)."""
    filters = {"origin": origin, "destination": destination,
               "departure_date": departure_date, "return_date": return_date}
    per_destination = group == "destination"
    deals = database.list_deals(origin, destination, min(limit, 100), departure_date, return_date,
                                per_destination, direct, sort, offset)
    total = database.count_deals(filters, per_destination, direct)
    deal_count = database.count_deals(filters, False, direct) if per_destination else total
    return DealPage(total, deal_count, [DealOut.of(d) for d in deals])


def POST(request: Request, data: list[Deal]) -> dict:
    """수집기(update.py)가 보낸 특가 저장 — 같은 노선·날짜면 덮어쓴다."""
    _collector_only(request)
    saved = database.save_deals(data)
    return {"saved": saved, "deleted": database.delete_expired()}


def DELETE(request: Request, origin: FromQuery[str], destination: FromQuery[str],
           departure_date: FromQuery[str], return_date: FromQuery[str] = "") -> None:
    """갱신(update.py)에서 제휴 요금이 사라진 특가를 내린다."""
    _collector_only(request)
    database.delete_deal(origin, destination, departure_date, return_date)
