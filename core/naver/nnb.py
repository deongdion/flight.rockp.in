"""
NNB(기기 식별자) 쿠키 발급

NNB 없이 flight-api GraphQL 을 부르면 HTTP 500 (10초 대기) 이 날 수 있음.
브라우저처럼 페이지 로딩 -> lcs.naver.com/m 비콘을 호출하면
Set-Cookie: NNB=... (domain=.naver.com, 2050년 만료) 로 발급됨.
"""
from typing import Optional

from curl_cffi.requests import AsyncSession

PAGE_URL = "https://flight.naver.com/flights/everywhere/monthly/SEL"
LCS_URL = "https://lcs.naver.com/m"


class NNBError(Exception):
    pass


def get_session_nnb(session: AsyncSession) -> Optional[str]:
    return session.cookies.get("NNB")


async def issue_nnb(session: AsyncSession, retries: int = 3) -> str:
    """세션에 NNB 쿠키를 발급받아 넣고 값을 반환 (이미 있으면 그대로 반환)"""
    nnb = get_session_nnb(session)
    if nnb:
        return nnb

    last_status = None
    for _ in range(retries):
        await session.get(
            PAGE_URL,
            headers={"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
            timeout=15,
        )
        resp = await session.get(
            LCS_URL,
            params={"u": PAGE_URL},
            headers={
                "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "sec-fetch-dest": "image",
                "sec-fetch-mode": "no-cors",
                "sec-fetch-site": "cross-site",
                "referer": "https://flight.naver.com/",
            },
            timeout=15,
        )
        last_status = resp.status_code
        nnb = get_session_nnb(session)
        if nnb:
            return nnb

    raise NNBError(f"NNB 발급 실패 (lcs status={last_status})")


def set_nnb(session: AsyncSession, nnb: str) -> None:
    """이미 가진 NNB 값을 세션에 주입"""
    session.cookies.set("NNB", nnb, domain=".naver.com", path="/")


__all__ = ["NNBError", "issue_nnb", "set_nnb", "get_session_nnb"]
