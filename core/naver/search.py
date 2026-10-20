"""네이버항공권 실시간 검색 (searchFlights SSE) - 국제선/국내선.

2026-10-13 실측 검증된 호출 규칙:

  국제선 POST https://flight-api.naver.com/flight/international/searchFlights
    - 첫 요청에 version 필드가 없어야 한다. version:0 을 넣으면
      isExpired:true + 빈 결과가 돌아온다 (실측).
    - status.isCompleted 가 아니면 initialRequest=false, version=1,2,... 로 폴맵.
      보통 첫 요청 한 번에 20/20 파트너 완료로 끝난다.
    - 응답은 SSE. 이벤트마다 status/itineraries/fareMappings 가 누적 전체로 온다
      -> 마지막 이벤트만 보면 된다.
    - 왕복은 itineraries 2개(가는편/오는편). fareMappings.itineraryIds 는
      "가는편ID-오는편ID" 형태로 결합된다.
    - 실최저가 = fareMappings[].fares[].adult.totalFare 최소값 (partnerCode = 판매사).
    - 파라미터: seatClass Y/P/C/F, adultCount/childCount/infantCount, isNonstop,
      flightFilter(limit/skip/sort).

  국내선 POST https://flight-api.naver.com/flight/domestic/searchFlights
    - type:"domestic", fareType:"YC"(일반석), person:{adult,child,infant}
    - status.isComplete, 최저가 = status.departure.price.min (+ 왕복: arrival.price.min)
    - 국내선은 요금이 항공사/대리점(agtCode)별로 flights[].fares 에 붙지만
      여기선 compare_live.py 와 동일하게 status 레벨 최저가를 쓴다.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from curl_cffi.requests import AsyncSession

from .utils import NaverFlightError, as_dict, as_int, as_list, as_str
from .utils import to_date_str as to_ymd

INTL_URL = "https://flight-api.naver.com/flight/international/searchFlights"
DOM_URL = "https://flight-api.naver.com/flight/domestic/searchFlights"

SeatClass = str          # "Y" 일반 / "P" 프리미엄 / "C" 비즈니스 / "F" 퍼스트
DateLike = Optional[Any]  # "20261115" / "2026-11-15" / date


@dataclass
class RealtimeFare:
    partner_code: str = ""      # 예: TBK033 (트래블버킷)
    fare_type: str = ""         # 예: A01
    total_fare: int = 0         # 성인 1인 총액
    baggage_fee_type: str = ""  # FREE / CHARGE / UNKNOWN
    itinerary_ids: str = ""     # "20261115ICNNRTLJ0211-20261119NRTICNLJ0236"
    reservation_url: str = ""   # OTA 딥링크 (search_selected 선택검색 시에만 채워짐)
    is_confirmed: bool = True   # False 면 확정 전 요금 (예약 단계에서 바뀔 수 있음)


@dataclass
class Segment:
    """구간 1개 (경유면 여정당 여러 개)."""
    dep_airport: str = ""
    dep_date: str = ""          # YYYYMMDD
    dep_time: str = ""          # HHMM (현지)
    arr_airport: str = ""
    arr_date: str = ""
    arr_time: str = ""
    airline: str = ""           # 판매(marketing) 항공사 IATA
    flight_no: str = ""

    @classmethod
    def from_dict(cls, d: Any) -> "Segment":
        d = as_dict(d)
        dep, arr = as_dict(d.get("departure")), as_dict(d.get("arrival"))
        mc = as_dict(d.get("marketingCarrier"))
        return cls(
            dep_airport=as_str(dep.get("airportCode")), dep_date=as_str(dep.get("date")),
            dep_time=as_str(dep.get("time")),
            arr_airport=as_str(arr.get("airportCode")), arr_date=as_str(arr.get("date")),
            arr_time=as_str(arr.get("time")),
            airline=as_str(mc.get("airlineCode")), flight_no=as_str(mc.get("flightNumber")),
        )


@dataclass
class Itinerary:
    """편도 여정 1개 (가는편 또는 오는편)."""
    itinerary_id: str = ""      # 예: 20261029NRTICNZE0602
    duration: int = 0           # 총 소요시간(초, 경유 대기 포함)
    segments: List[Segment] = field(default_factory=list)

    @property
    def airlines(self) -> List[str]:
        return list(dict.fromkeys(s.airline for s in self.segments if s.airline))

    @property
    def stops(self) -> int:
        return max(0, len(self.segments) - 1)

    @property
    def first(self) -> Segment:
        return self.segments[0] if self.segments else Segment()

    @property
    def last(self) -> Segment:
        return self.segments[-1] if self.segments else Segment()

    @classmethod
    def from_dict(cls, d: Any) -> "Itinerary":
        d = as_dict(d)
        return cls(
            itinerary_id=as_str(d.get("itineraryId")),
            duration=as_int(d.get("duration")),
            segments=[Segment.from_dict(s) for s in as_list(d.get("segments"))],
        )


@dataclass
class RealtimeResult:
    is_domestic: bool = False
    is_complete: bool = False
    min_fare: Optional[int] = None       # 왕복 국내선은 양편 합계
    min_partner_code: str = ""           # 국내선은 빈 값 (판매사 집계 아님)
    fares: List[RealtimeFare] = field(default_factory=list)
    itineraries: Dict[str, Itinerary] = field(default_factory=dict)   # itineraryId → 여정
    itinerary_count: int = 0
    partners_done: int = 0
    partners_total: int = 0
    polls: int = 0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.is_complete and self.min_fare and self.min_fare > 0)

    def legs(self, fare: RealtimeFare) -> List[Itinerary]:
        """요금의 여정 (가는편[, 오는편]). 응답에 없는 ID 는 빈 Itinerary."""
        return [self.itineraries.get(i) or Itinerary(itinerary_id=i)
                for i in fare.itinerary_ids.split("-") if i]


def _sse_events(text: str) -> List[dict]:
    """SSE 본문 -> data: JSON 이벤트 리스트."""
    out: List[dict] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            import json
            try:
                ev = json.loads(line[5:])
                if isinstance(ev, dict):
                    out.append(ev)
            except ValueError:
                continue
    return out


def _last_event(text: str) -> Optional[dict]:
    """마지막 data: 이벤트만 파싱. 이벤트마다 누적 전체가 오므로 앞쪽은 볼 필요 없다.
    (응답 3~7MB · 이벤트 ~20개 — 전부 json.loads 하면 이벤트 루프가 막힌다, 2026-10-16 실측)"""
    import json
    end = len(text)
    while True:
        i = text.rfind("data:", 0, end)
        if i < 0:
            return None
        if i == 0 or text[i - 1] == "\n":
            line = text[i + 5:text.find("\n", i) if text.find("\n", i) >= 0 else len(text)]
            try:
                ev = json.loads(line)
                if isinstance(ev, dict):
                    return ev
            except ValueError:
                pass
        end = i


async def _post_sse(session: AsyncSession, url: str, payload: dict, timeout: int) -> str:
    """searchFlights POST. 503은 재시도하지 않는다 (패널티 악화).
    Connection reset은 1회 재시도 (일시적)."""
    import asyncio as _aio
    try:
        resp = await session.post(url, json=payload, timeout=timeout)
    except Exception:
        await _aio.sleep(1)
        resp = await session.post(url, json=payload, timeout=timeout)
    if resp.status_code not in (200, 201):
        raise NaverFlightError(f"searchFlights: HTTP {resp.status_code} {resp.text[:150]}")
    return resp.text


async def _kick_sse(session: AsyncSession, url: str, payload: dict,
                    kick_timeout: float = 1.5) -> None:
    """검색만 시작시키고 짧은 타임아웃으로 연결을 끊는다.

    서버는 연결이 끊겨도 검색을 끝까지 돌려(10~15초) 결과를 잠깐 캐시한다. 그 뒤 같은 요청을
    다시 보내면 완료된 결과가 이벤트 1개로 0.2~0.4초 만에 온다 (2026-10-16 실측).
    SSE 는 판매사가 끝날 때마다 누적 전체를 다시 보내서 그냥 받으면 3~11MB(비압축)인데,
    이렇게 하면 0.3~0.8MB 로 줄어든다.
    ⚠️ stream=True 로 받다 끊으면 curl_cffi 세션 슬롯이 반환되지 않아 세션이 멈춘다 → 타임아웃으로 끊는다.
    """
    try:
        resp = await session.post(url, json=payload, timeout=kick_timeout)
    except Exception:
        return                      # 의도한 타임아웃 — 서버는 검색을 계속한다
    if resp.status_code not in (200, 201):
        raise NaverFlightError(f"searchFlights: HTTP {resp.status_code} {resp.text[:150]}")


async def _stream_until(session: AsyncSession, url: str, payload: dict, timeout: int,
                        until: Callable[[RealtimeResult], bool]) -> Optional[dict]:
    """SSE 를 이벤트마다 읽다가 until(결과) 가 참이면 바로 끊고 그 이벤트를 돌려준다 (못 찾으면 마지막 이벤트).

    판매처는 끝나는 대로 하나씩 이벤트로 오고(이벤트마다 누적 전체), 19곳이 다 끝나기까지 8~15초가 걸린다.
    한 판매처만 필요하면 그 판매처가 들어온 이벤트에서 끊으면 된다 (2026-10-20 실측: 4초대에 오는 일이 많다).
    ⚠️ 받다가 끊으면 curl_cffi 세션 슬롯이 반환되지 않는다 (_kick_sse) → 쿠키만 복사한 1회용 세션으로 받고 닫는다.
    """
    import json
    async with AsyncSession(impersonate="chrome", headers=dict(session.headers),
                            cookies=dict(session.cookies)) as s:
        resp = await s.post(url, json=payload, timeout=timeout, stream=True)
        if resp.status_code not in (200, 201):
            raise NaverFlightError(f"searchFlights: HTTP {resp.status_code}")
        last, buf = None, b""
        async for chunk in resp.aiter_content():
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.startswith(b"data:"):
                    continue
                try:
                    ev = json.loads(line[5:])
                except ValueError:
                    continue
                if isinstance(ev, dict):
                    last = ev
                    if until(_parse_intl(ev)):
                        return ev
        return last


def _parse_intl(ev: dict) -> RealtimeResult:
    st = as_dict(ev.get("status"))
    fares: List[RealtimeFare] = []
    for fm in as_list(ev.get("fareMappings")):
        fm = as_dict(fm)
        itin = as_str(fm.get("itineraryIds"))
        for f in as_list(fm.get("fares")):
            f = as_dict(f)
            total = as_int(as_dict(f.get("adult")).get("totalFare"))
            if total > 0:
                fares.append(RealtimeFare(
                    partner_code=as_str(f.get("partnerCode")),
                    fare_type=as_str(f.get("fareType")),
                    total_fare=total,
                    baggage_fee_type=as_str(f.get("baggageFeeType")),
                    itinerary_ids=itin,
                    reservation_url=as_str(f.get("reservationUrl")),
                    is_confirmed=f.get("isConfirmed") is not False,
                ))
    fares.sort(key=lambda x: x.total_fare)
    itins = [Itinerary.from_dict(x) for x in as_list(ev.get("itineraries"))]
    return RealtimeResult(
        is_domestic=False,
        is_complete=bool(st.get("isCompleted")),
        min_fare=fares[0].total_fare if fares else None,
        min_partner_code=fares[0].partner_code if fares else "",
        fares=fares,
        itineraries={i.itinerary_id: i for i in itins},
        itinerary_count=len(itins),
        partners_done=as_int(st.get("completedPartnerCount")),
        partners_total=as_int(st.get("requestedPartnerCount")),
    )


def _parse_dom(ev: dict, has_return: bool) -> RealtimeResult:
    st = as_dict(ev.get("status"))
    dep = as_dict(as_dict(st.get("departure")).get("price"))
    arr = as_dict(as_dict(st.get("arrival")).get("price"))
    dep_min = as_int(dep.get("min"))
    arr_min = as_int(arr.get("min"))
    total = (dep_min + arr_min) if (has_return and dep_min and arr_min) else (dep_min or None)
    return RealtimeResult(
        is_domestic=True,
        is_complete=bool(st.get("isComplete")),
        min_fare=total if total and total > 0 else None,
        itinerary_count=len(as_list(ev.get("flights"))),
        partners_done=as_int(st.get("availablePartnerCount")),
        partners_total=as_int(st.get("availablePartnerCount")),
    )


async def search_international(
    session: AsyncSession,
    departure_location_code: str,
    arrival_location_code: str,
    departure_date,
    return_date=None,
    *,
    departure_location_type: str = "airport",
    arrival_location_type: str = "airport",
    seat_class: SeatClass = "Y",
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    is_nonstop: bool = False,
    max_polls: int = 4,
    poll_interval: float = 1.0,
    timeout: int = 40,
    until: Optional[Callable[[RealtimeResult], bool]] = None,
    light: bool = False,
    light_wait: float = 13.0,
    limit: int = 3,
) -> RealtimeResult:
    """국제선 실시간 최저가. 왕복은 return_date 지정 (양편 합산 요금).

        r = await search_international(s, "ICN", "NRT", "2026-11-15", "2026-11-19")
        r.min_fare, r.min_partner_code, r.ok

    light=True: 검색 시작 후 바로 끊고 light_wait 초 뒤 재요청해 완료 결과만 받는다
    (전송량 1/5~1/10, _kick_sse 참고). 대기가 짧으면(0~5초) 재요청이 다시 스트리밍으로 받고,
    너무 길면(≈35초~) 서버 캐시가 사라져 빈 응답 → 10~20초가 적당.
    """
    dep = to_ymd(departure_date)          # type: ignore[arg-type]
    ret = to_ymd(return_date) if return_date is not None else None
    itins = [{
        "departureLocationCode": departure_location_code.upper(),
        "departureLocationType": departure_location_type,
        "arrivalLocationCode": arrival_location_code.upper(),
        "arrivalLocationType": arrival_location_type,
        "departureDate": dep,
    }]
    if ret:
        itins.append({
            "departureLocationCode": arrival_location_code.upper(),
            "departureLocationType": arrival_location_type,
            "arrivalLocationCode": departure_location_code.upper(),
            "arrivalLocationType": departure_location_type,
            "departureDate": ret,
        })
    base: Dict[str, Any] = {
        "device": "pc",
        "seatClass": seat_class,
        "adultCount": adults, "childCount": children, "infantCount": infants,
        "isNonstop": is_nonstop,
        "itineraries": itins,
        "tripType": "RT" if ret else "OW",
        "flightFilter": {"limit": limit, "skip": 0, "sort": {"minFare": 1}},   # 운행(가는+오는 조합) 개수
    }
    try:
        import asyncio as _aio
        if light:
            await _kick_sse(session, INTL_URL, {**base, "initialRequest": True})
            await _aio.sleep(light_wait)
        # ⚠️ 첫 요청에는 version 이 없어야 한다 (넣으면 isExpired 빈 응답).
        if until:
            ev = await _stream_until(session, INTL_URL, {**base, "initialRequest": True}, timeout, until)
        else:
            ev = _last_event(await _post_sse(session, INTL_URL, {**base, "initialRequest": True}, timeout))
        result = _parse_intl(ev) if ev else RealtimeResult(error="빈 응답")
        if until and until(result):
            return result
        polls = 0
        while ev and not result.is_complete and polls < max_polls:
            await _aio.sleep(poll_interval)
            polls += 1
            text = await _post_sse(session, INTL_URL,
                                   {**base, "initialRequest": False, "version": polls}, timeout)
            ev = _last_event(text)
            if ev:
                result = _parse_intl(ev)
        result.polls = polls
        return result
    except NaverFlightError as e:
        return RealtimeResult(error=str(e))


async def search_selected(
    session: AsyncSession,
    departure_city: str,
    arrival_city: str,
    departure_date,
    return_date,
    itinerary_ids: List[str],
    *,
    location_type: str = "city",
    seat_class: SeatClass = "Y",
    adults: int = 1,
    max_polls: int = 4,
    poll_interval: float = 1.0,
    timeout: int = 40,
    until: Optional[Callable[[RealtimeResult], bool]] = None,
) -> RealtimeResult:
    """특정 여정(편도 조합) 선택 조회 — 상세 페이지 방식.

    fareMappings 에 reservationUrl(OTA 딥링크)이 채워져 돌아온다
    (2026-10-13 검증: 도시코드 + selectedItineraries + hasCardBenefit 조합).
    location_type="airport" 면 공항 코드로 조회 (예약 링크 서버가 쓰는 방식).
        r = await search_selected(s, "CJJ", "SHA", "2026-10-20", "2026-10-21",
                                  ["20261020CJJPVG9C7050", "20261021PVGCJJ9C7049"])
        r.fares[0].reservation_url
    """
    dep = to_ymd(departure_date)          # type: ignore[arg-type]
    ret = to_ymd(return_date)             # type: ignore[arg-type]
    base: Dict[str, Any] = {
        "tripType": "RT", "device": "pc", "seatClass": seat_class,
        "adultCount": adults, "childCount": 0, "infantCount": 0,
        "isNonstop": False, "openReturnDays": 0,
        "itineraries": [
            {"departureLocationCode": departure_city.upper(), "departureLocationType": location_type,
             "arrivalLocationCode": arrival_city.upper(), "arrivalLocationType": location_type,
             "departureDate": dep},
            {"departureLocationCode": arrival_city.upper(), "departureLocationType": location_type,
             "arrivalLocationCode": departure_city.upper(), "arrivalLocationType": location_type,
             "departureDate": ret},
        ],
        "flightFilter": {
            "filter": {
                "airlines": [], "departureAirports": [], "arrivalAirports": [],
                "departureTime": [], "fareTypes": [], "flightDurationSeconds": [],
                "hasCardBenefit": True, "isIndividual": False,
                "isLowCarbonEmission": False, "isSameAirlines": False,
                "isSameDepArrAirport": False, "isTravelClub": False,
                "minFare": {}, "viaCount": [],
                "selectedItineraries": itinerary_ids,
            },
            "limit": 200, "skip": 0, "sort": {"adultMinFare": 1},
        },
    }
    try:
        if until:
            ev = await _stream_until(session, INTL_URL, {**base, "initialRequest": True}, timeout, until)
        else:
            ev = _last_event(await _post_sse(session, INTL_URL, {**base, "initialRequest": True}, timeout))
        result = _parse_intl(ev) if ev else RealtimeResult(error="빈 응답")
        if until and until(result):
            return result
        polls = 0
        import asyncio as _aio
        while ev and not result.is_complete and polls < max_polls:
            await _aio.sleep(poll_interval)
            polls += 1
            text = await _post_sse(session, INTL_URL,
                                   {**base, "initialRequest": False, "version": polls}, timeout)
            ev = _last_event(text)
            if ev:
                result = _parse_intl(ev)
        result.polls = polls
        return result
    except NaverFlightError as e:
        return RealtimeResult(error=str(e))


async def search_domestic(
    session: AsyncSession,
    departure_airport: str,
    arrival_airport: str,
    departure_date,
    return_date=None,
    *,
    fare_type: str = "YC",
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    max_polls: int = 8,
    poll_interval: float = 1.5,
    timeout: int = 30,
) -> RealtimeResult:
    """국내선 실시간 최저가. 왕복은 양편 각각 최저의 합 (compare_live 방식)."""
    dep = to_ymd(departure_date)          # type: ignore[arg-type]
    ret = to_ymd(return_date) if return_date is not None else None
    itins = [{"departureAirport": departure_airport.upper(),
              "arrivalAirport": arrival_airport.upper(), "departureDate": dep}]
    if ret:
        itins.append({"departureAirport": arrival_airport.upper(),
                      "arrivalAirport": departure_airport.upper(), "departureDate": ret})
    payload: Dict[str, Any] = {
        "type": "domestic",
        "device": "pc",
        "fareType": fare_type,
        "itineraries": itins,
        "person": {"adult": adults, "child": children, "infant": infants},
        "tripType": "RT" if ret else "OW",
        "flightFilter": {"filter": {"type": "departure"}, "limit": 1, "skip": 0,
                         "sort": {"segment.departure.time": 1, "minFare": 1}},
    }
    try:
        text = await _post_sse(session, DOM_URL, {**payload, "initialRequest": True}, timeout)
        ev = _last_event(text)
        result = _parse_dom(ev, bool(ret)) if ev else RealtimeResult(is_domestic=True, error="빈 응답")
        polls = 0
        import asyncio as _aio
        while ev and not result.is_complete and polls < max_polls:
            await _aio.sleep(poll_interval)
            polls += 1
            text = await _post_sse(session, DOM_URL, {**payload, "initialRequest": False}, timeout)
            ev = _last_event(text)
            if ev:
                result = _parse_dom(ev, bool(ret))
        result.polls = polls
        return result
    except NaverFlightError as e:
        return RealtimeResult(is_domestic=True, error=str(e))


__all__ = ["RealtimeFare", "RealtimeResult", "search_international",
           "search_domestic", "search_selected"]
