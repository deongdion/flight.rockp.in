from litestar.datastructures import State
from litestar.exceptions import NotFoundException
from litestar.params import FromPath

from api import database, redirect
from api.schemas import LinkOut


async def GET(state: State, code: FromPath[str], warm: bool = False) -> LinkOut:
    """짧은 링크 정보 — 모을 때 본 판매처 요금·항공편. 이동 화면이 실시간 확인 전에 먼저 보여 준다.
    warm=true 면 실시간 확인을 미리 시작한다 (화면이 뜨는 동안 확인이 진행돼 브라우저는 결과만 받는다)."""
    link = database.get_link(code)
    if not link:
        raise NotFoundException("링크가 없거나 만료됐어요")
    if warm:
        redirect.start(state.naver, code, link)
    return LinkOut.of(link)
