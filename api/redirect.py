"""예약 버튼 클릭 시점 — 실시간 재확인 후 우리 제휴 추적이 붙은 예약 URL 을 만든다.

  1) 선택 검색으로 판매처 예약 URL + 실시간 요금 확보
     저장된 항공편 ID 가 만료됐으면 전체 검색으로 지금 최저가 항공편을 다시 찾는다 (네이버 방식).
  2) 네이버 추적 파라미터를 지우고 판매처별로 우리 제휴 추적을 붙인다
     (서버가 LP/TP 클릭을 대신 따라가 추적값을 얻으므로 사용자는 팝업 없이 한 번에 이동).
  3) 어떤 단계가 실패해도 판매처 검색 페이지 제휴 링크로 보낸다 — 에러 페이지는 없다.

속도 (2026-10-20 실측: 예전엔 중앙값 10초, 길면 20~60초):
  · 네이버 검색은 판매처 19곳이 다 끝날 때까지 8~15초 → 우리 판매처가 들어오면 바로 끊는다 (until)
  · 예약 URL 이 필요 없는 LP 랜딩 클릭은 네이버 검색과 동시에 시작한다 (_LP_LANDING)
  · 같은 링크는 진행 중인 확인을 같이 기다리고, 끝난 결과는 REUSE 초 재사용한다 (resolve)
  · 그래도 DEADLINE 을 넘기면 판매처 검색 페이지로 보낸다
  · 확인 결과는 목록에 반영한다 — 요금이 사라졌으면 그 판매처를 빼고(남은 게 없으면 특가를 내리고),
    같은 항공편 가격이 바뀌었으면 그 가격으로 (database.apply_check)

판매처별 처리 (2026-10-19 실측):
  트립닷컴 CTR013  네이버 예약 URL(ShoppingID) + LP 클릭 대행으로 얻은 allianceid/sid/ouid
                   ⚠️ LP 딥링크(tu=)로 감싸면 LP 가 URL 을 통째로 소문자로 바꿔 ShoppingID 가 깨진다
                      ("판매 완료") → LP 를 거치지 않고 대소문자 그대로 트립닷컴으로 보낸다
  Kiwi    SKP206  kayak 리다이렉트 → kiwi 예약 세션 → tp.media 클릭 대행으로 affilid 부착
  NOL     YNJ035/INT005  bridge URL + LP 클릭 대행으로 얻은 AppsFlyer 파라미터
  마이리얼트립 MRT023  LP bridge 의 return_url 에 세션 예약 URL 을 넣어 재조립
  아고다   AGD217  네이버 예약 URL(flightbookings/details) 의 CID·affsid 를 LP 클릭 대행으로 얻은 cid·tag 로
                   (예약 URL 이 없으면 LP 랜딩 → flights 페이지)
                   예약 화면의 가격은 아고다가 항공사에 다시 확인하느라 10초 넘게 걸려 뜬다 (네이버 링크도 같음)
"""

import asyncio
import re
import time
from datetime import date
from typing import Optional
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

from curl_cffi.requests import AsyncSession

from core.affiliates import PARTNERS, TP_KIWI_P, affiliate_link, lp_deeplink, tp_link
from api import database
from core.models import Link, RedirectLink
from core.naver import Itinerary, NaverFlightClient

DEADLINE = 15          # 초 — 넘기면 판매처 검색 페이지로
REUSE = 180            # 초 — 끝난 확인 결과 재사용 (판매처 예약 URL 토큰은 20분쯤 유효)
CONCURRENCY = 6        # 동시에 도는 실시간 확인 — 링크를 마구 열어도 네이버 검색이 몰려 막히지 않게

# 네이버 추적 파라미터
_NAVER_TRACKING = re.compile(
    r"[?&](?:allianceid|sid|ouid|TrackerType|TrackerTag|uuid"
    r"|utm_source|utm_medium|utm_campaign|utm_content|trackcode)=[^&]*")

# LP 클릭 대행 후 예약 URL 에 옮겨 붙일 AppsFlyer 파라미터
_APPSFLYER_KEYS = ("clickid", "pid", "af_siteid", "advertising_id", "c",
                   "af_click_lookback", "af_reengagement_window", "af_adset")

# 예약 URL 없이 할 수 있는 LP 랜딩 클릭 (판매처 → 머천트, 랜딩) — 네이버 검색과 동시에 시작한다
_LP_LANDING = {
    "CTR013": ("ctrip", "https://kr.trip.com/flights/"),
    "AGD217": ("agoda", "https://www.agoda.com/ko-kr/flights"),
    "YNJ035": ("yanolja", "https://air.nol.kr/"),
    "INT005": ("yanolja", "https://air.nol.kr/"),
    "MRT023": ("myrealtrip", "https://flights.myrealtrip.com/"),
}


def strip_naver_tracking(url: str) -> str:
    prev = None
    while prev != url:
        prev = url
        url = _NAVER_TRACKING.sub("", url)
    return url.replace("?&", "?").rstrip("?")


def _add_query(url: str, query: str) -> str:
    return url + ("&" if "?" in url else "?") + query if query else url


def search_page_link(partner_code: str, origin: str, destination: str,
                     departure_date: date, return_date: date) -> str:
    """판매처 검색 페이지 제휴 링크. 모르는 판매처면 네이버 항공권."""
    return (affiliate_link(partner_code, origin, destination, departure_date, return_date)
            or "https://flight.naver.com/")


# ── 짧은 링크 단위: 같이 기다리기 · 잠깐 재사용 · 시간 제한 ─────────────────
_jobs: dict[str, tuple[float, asyncio.Task]] = {}
_slots = asyncio.Semaphore(CONCURRENCY)


def start(naver: NaverFlightClient, code: str, link: Link) -> asyncio.Task:
    """이 링크의 실시간 확인을 시작한다. 진행 중이거나 REUSE 초 안에 끝난 확인이 있으면 그걸 준다
    (이동 화면을 여는 순간 미리 시작하고, 브라우저가 물어보면 같은 작업을 기다린다)."""
    now = time.monotonic()
    for k, (t, task) in list(_jobs.items()):
        if task.done() and (now - t > REUSE or task.exception()):
            del _jobs[k]
    if code not in _jobs:
        _jobs[code] = (now, asyncio.create_task(_check(naver, link)))
    return _jobs[code][1]


async def _check(naver: NaverFlightClient, link: Link) -> RedirectLink:
    o = link.offer
    async with _slots:
        out = await build_redirect(naver, link.origin, link.destination, link.departure_date,
                                   link.return_date or link.departure_date, o.partner_code, o.itinerary_ids or None)
    same_flight = "-".join(i.itinerary_id for i in out.itineraries) == o.itinerary_ids
    if out.sold_out:
        await asyncio.to_thread(database.apply_check, o.code, None)
    elif out.price and same_flight and out.price != o.price:
        await asyncio.to_thread(database.apply_check, o.code, out.price)
    return out


async def resolve(naver: NaverFlightClient, code: str, link: Link) -> RedirectLink:
    """실시간 확인 결과. 시작부터 DEADLINE 을 넘기거나 실패하면 판매처 검색 페이지
    (확인은 뒤에서 마저 끝나 다시 누르면 쓴다)."""
    task = start(naver, code, link)
    left = DEADLINE - (time.monotonic() - _jobs[code][0])
    try:
        return await asyncio.wait_for(asyncio.shield(task), max(1.0, left))
    except asyncio.TimeoutError:
        out = None
    except Exception:
        out = None
    route = (link.origin, link.destination, link.departure_date, link.return_date or link.departure_date)
    return out or RedirectLink(search_page_link(link.offer.partner_code, *route), None, "search")


# ── 네이버: 예약 URL / 실시간 요금 ───────────────────────────────────
async def reservation_url(naver: NaverFlightClient, origin: str, destination: str,
                          departure_date: date, return_date: date,
                          partner_code: str, itinerary_ids: Optional[str]
                          ) -> tuple[Optional[str], Optional[int], list[Itinerary], bool]:
    """선택 검색 → (예약 URL, 요금, 항공편, 매진). 예약 URL 이 없어도 전체 검색에서 본 요금·항공편은 돌려준다.
    매진 = 네이버 전체 검색은 됐는데 이 판매처 요금이 하나도 없음.
    두 검색 모두 이 판매처 요금이 들어오면 나머지 판매처를 기다리지 않고 끊는다."""
    has_fare = lambda r: any(f.partner_code == partner_code for f in r.fares)
    has_url = lambda r: any(f.partner_code == partner_code and f.reservation_url for f in r.fares)
    stored, price, legs = itinerary_ids, None, []
    for _ in range(2):                          # 2회차: 만료된 항공편 ID 를 버리고 다시 찾는다
        if not itinerary_ids:
            r = await naver.search_international(origin, destination, departure_date, return_date,
                                                 limit=30, until=has_fare)
            mine = [f for f in r.fares if f.partner_code == partner_code]
            if not mine:
                return None, price, legs, not r.error and r.is_complete
            price, itinerary_ids, legs = mine[0].total_fare, mine[0].itinerary_ids, r.legs(mine[0])
        outbound, _, inbound = (itinerary_ids or "").partition("-")
        r = await naver.search_selected(origin, destination, departure_date, return_date,
                                        [outbound, inbound], location_type="airport", until=has_url)
        hit = next((f for f in r.fares if f.partner_code == partner_code and f.reservation_url), None)
        if hit:
            return hit.reservation_url, hit.total_fare, r.legs(hit), False
        if not stored:
            break
        itinerary_ids = stored = None
    return None, price, legs, False


# ── 제휴 클릭 대행 ──────────────────────────────────────────────────
async def _follow_redirects(url: str, timeout: int = 10) -> Optional[str]:
    """리다이렉트를 끝까지 따라간 최종 URL (실패면 None). 클릭마다 새 세션 — 쿠키를 섞지 않는다."""
    try:
        async with AsyncSession(impersonate="chrome", timeout=timeout) as s:
            r = await s.get(url, allow_redirects=True)
            return str(r.url)
    except Exception:
        return None


async def kayak_to_kiwi(kayak_url: str) -> Optional[str]:
    """kayakaffiliates 리다이렉트 → kiwi 예약 세션 URL (네이버 쪽 affilid/clickid 제거)."""
    final = await _follow_redirects(kayak_url)
    if not final or "kiwi.com" not in final or "deeplinkId" not in final:
        return None
    p = urlparse(final)
    qs = [(k, v) for k, v in parse_qsl(p.query) if k not in ("affilid", "clickid")]
    return urlunparse(p._replace(query=urlencode(qs)))


async def kiwi_with_affiliate(target: str) -> Optional[str]:
    """tp.media 클릭 대행 → 우리 affilid 가 붙은 kiwi 최종 URL."""
    final = await _follow_redirects(tp_link(TP_KIWI_P, target))
    return final if final and "kiwi.com" in final and "affilid=" in final else None


def trip_with_affiliate(reservation: str, land: Optional[str]) -> Optional[str]:
    """LP 랜딩(land) 에서 트립닷컴이 받는 우리 추적값(allianceid·sid·ouid) 을 꺼내
    네이버 예약 URL 에 대소문자 그대로 붙인다. criteriatoken 안의 네이버 aid/sid 도 우리 값으로."""
    if not land:
        return None
    q = dict(parse_qsl(urlparse(land).query))
    alliance, sid, ouid = q.get("allianceid"), q.get("sid"), q.get("ouid")
    if not (alliance and sid and ouid):
        return None
    url = strip_naver_tracking(reservation)
    url = re.sub(r"aid:\d+(\||%7C)sid:\d+", rf"aid:{alliance}\g<1>sid:{sid}", url)
    return _add_query(url, urlencode({"allianceid": alliance, "sid": sid, "ouid": ouid}))


def agoda_with_affiliate(reservation: str, land: Optional[str]) -> Optional[str]:
    """LP 랜딩(land) 의 우리 추적값(cid·tag) 으로 네이버 예약 URL 의 CID·affsid 를 바꾼다."""
    if not land:
        return None
    q = dict(parse_qsl(urlparse(land).query))
    if not (q.get("cid") and q.get("tag")):
        return None
    p = urlparse(reservation)
    qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in ("cid", "affsid")]
    return urlunparse(p._replace(query=urlencode(qs + [("cid", q["cid"]), ("tag", q["tag"])])))


def appsflyer_params(land: Optional[str]) -> str:
    """LP 랜딩(land) 의 AppsFlyer 추적 파라미터 (clickid 등)."""
    if not land:
        return ""
    q = dict(parse_qsl(urlparse(land).query))
    return "&".join(f"{k}={v}" for k, v in q.items() if k in _APPSFLYER_KEYS and v)


# ── 판매처별 최종 URL ────────────────────────────────────────────────
async def build_redirect(naver: NaverFlightClient, origin: str, destination: str,
                         departure_date: date, return_date: date,
                         partner_code: str, itinerary_ids: Optional[str]) -> RedirectLink:
    route = (origin, destination, departure_date, return_date)
    if partner_code not in PARTNERS:
        return RedirectLink(search_page_link(partner_code, *route), None, "search")
    lp = _LP_LANDING.get(partner_code)
    land = asyncio.create_task(_follow_redirects(lp_deeplink(*lp))) if lp else None
    try:
        url, price, legs, sold_out = await reservation_url(naver, *route, partner_code, itinerary_ids)
        if sold_out:
            return RedirectLink(search_page_link(partner_code, *route), None, "search", sold_out=True)
        link = await _seller_link(partner_code, route, url, price, land)
    finally:
        if land:
            land.cancel()
    link.itineraries = legs
    return link


async def _seller_link(partner_code: str, route: tuple, url: Optional[str],
                       price: Optional[int], land: Optional[asyncio.Task]) -> RedirectLink:
    """판매처별로 우리 제휴 추적을 붙인 최종 URL. 실패하면 판매처 검색 페이지.
    land = 미리 시작한 LP 랜딩 클릭 (_LP_LANDING)."""
    fallback = search_page_link(partner_code, *route)

    if url and partner_code == "CTR013":        # 트립닷컴: url = ShoppingID 예약 URL
        final = trip_with_affiliate(url, await land)
        if final:
            return RedirectLink(final, price, "booking")

    if url and partner_code == "SKP206":        # Kiwi: url = kayak 리다이렉트
        clean = await kayak_to_kiwi(url)
        if clean:
            final = (await kiwi_with_affiliate(clean)
                     or _add_query(clean, "affilid=travelpayoutsdeeplink__rockpin-703382"))
            return RedirectLink(final, price, "booking")

    if url and partner_code in ("YNJ035", "INT005"):    # NOL: url = bridge
        params = appsflyer_params(await land)
        return RedirectLink(_add_query(strip_naver_tracking(url), params), price, "booking")

    if partner_code == "MRT023":                # 마이리얼트립: LP bridge 재조립
        landed = await land
        if url and landed and "bridge/marketing" in landed and "return_url=" in landed:
            return_url = unquote(dict(parse_qsl(urlparse(landed).query)).get("return_url", ""))
            tracking = dict(parse_qsl(urlparse(return_url).query))
            if tracking.get("utm_content"):
                target = _add_query(strip_naver_tracking(url), urlencode(tracking))
                return RedirectLink("https://www.myrealtrip.com/main/bridge/marketing?return_url="
                                    + quote(target, safe=""), price, "booking")
        return RedirectLink(lp_deeplink("myrealtrip", "https://flights.myrealtrip.com/"), price, "search")

    if url and partner_code == "AGD217":        # 아고다: url = flightbookings/details 예약 URL
        final = agoda_with_affiliate(url, await land)
        if final:
            return RedirectLink(final, price, "booking")

    if partner_code == "AGD217":                # 아고다 예약 URL 이 없으면: LP 랜딩 → flights 페이지
        landed = await land
        if landed:
            return RedirectLink(urlunparse(urlparse(landed)._replace(path="/ko-kr/flights")), price, "search")

    return RedirectLink(fallback, price, "search")
