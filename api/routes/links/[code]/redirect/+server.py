import logging
import time

from litestar.datastructures import State
from litestar.exceptions import NotFoundException
from litestar.params import FromPath

from api import database, redirect
from core.models import RedirectLink

log = logging.getLogger("redirect")


async def GET(state: State, code: FromPath[str]) -> RedirectLink:
    """예약 버튼 클릭 시점 실시간 재확인 → 예약 URL + 확인 가격·항공편.
    늦거나 실패해도 판매처 검색 링크를 준다 (에러 응답 없음, 최대 redirect.DEADLINE 초)."""
    link = database.get_link(code)
    if not link:
        raise NotFoundException("링크가 없거나 만료됐어요")
    t0 = time.monotonic()
    out = await redirect.resolve(state.naver, code, link)
    log.info("%s %s %s %.0fms price=%s→%s %s", code, link.offer.partner_code, out.kind,
             (time.monotonic() - t0) * 1000, link.offer.price, out.price, out.url[:70])
    return out
