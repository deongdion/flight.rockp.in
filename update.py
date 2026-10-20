"""
네이버항공권 실시간 최저가 수집기 → api(/api/deals) 로 전송
=========================================

  collect_naver_flights  전 노선 (HOOK all-flights) — 1시간마다 새로 찾아 모은다
  refresh_deals          갱신 — 15분마다 화면에 보이는 특가만 실시간으로 다시 확인해 덮어쓴다
  track_flights          트래킹 항공편 (HOOK tracked-flights) — 록핀 추적 목록을 실시간 조회
                         → receive-price2 (SEND_TRACKED 일 때만 전송)

두 작업은 SSE 속도 제한(GATE)을 같이 쓴다 → 합쳐서 초당 SSE_RATE 건.

[전 노선] 조회 방식은 통합(HOOK) jobs/flights.py 의 all-flights 와 동일하되, 가격은 캐시가 아니라
네이버 실시간(SSE)으로 확인한다.

  [0 사전점검] 출발도시별 2개 날짜(오늘+30/60일, 3박)를 찔러 전부 0건이면 이번 사이클 제외
  [1 발견]     (출발도시 × 오늘~93일 × 1~6박) 슬롯을 통째로 셔플해 캐시 1회씩 → 노선 목록
               귀국일은 박수별로 고정 조회 (HOOK 과 동일)
  [2 실시간]   발견된 노선·날짜 전부 SSE 로 가격 확인 → Deal 로 만들어 SEND_BATCH 건씩 api 로 전송
               api 는 같은 노선·날짜를 덮어쓰고, 하루 지난 건 지운다.

  예약 링크는 저장하지 않는다 — 사용자가 클릭할 때 api /api/resolve 가 만든다.

실행:
    uv run update.py            # 1시간마다 반복
    uv run update.py --once     # 1회만
    uv run update.py --no-send  # api 로 보내지 않고 로그만
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import inspect
import os
import random
import sys
import time
import traceback
import unicodedata
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, Optional

import httpx

from core.affiliates import PARTNERS
from core.models import Deal, Offer, affiliate_fares, cheapest_per_seller
from core.naver import (DOMESTIC_CODES, DestinationPrice, Itinerary, NaverFlightClient,
                        NaverFlightError, NNBPool, RateGate, RealtimeResult, load_proxies,
                        search_domestic, search_international)
from core.rockpin import Rockpin, TrackingFlight

# ── 수집 범위 (HOOK all-flights 와 동일) ─────────────────────────────
FLIGHT_DAYS = 93              # 오늘부터 3개월
FLIGHT_NIGHTS = range(1, 7)   # 1~6박 → 출발일당 6슬롯
PROBE_OFFSETS = (30, 60)      # 출발도시 사전점검 날짜(오늘+N일). () 이면 점검 안 함
PROBE_NIGHTS = 3
CITY_FOLD = {"ICN": "SEL", "GMP": "SEL"}   # 공항 → 도시 통합

# ── 실시간 (2026-10-16 실측) ────────────────────────────────────────
# 직접 연결 NNB 8개: 초당 4건이 한계 (그 이상 503).
# 프록시 197개(프록시당 NNB 1개) + LIGHT: 초당 8건 → 성공 ~7건/s, 503 0건.
#   (12건/s 는 80초 뒤부터 타임아웃 급증 — 네이버 쪽 한계로 보임)
PROXIES_FILE = "proxies.txt"  # 이 폴더 기준. 없거나 비면 직접 연결 NNB_POOL 개
NNB_POOL = 8                  # 직접 연결일 때 NNB 수. 15는 연결 리셋, 8 안정
SSE_RATE = 8.0                # 초당 SSE 시작 수 상한 (직접 연결이면 4.0)
SSE_CONCURRENCY = 300         # 동시 조회 수 (LIGHT 1건 ≈ 15~30초 → SSE_RATE × 30 이상)
LIGHT = True                  # 검색 시작 후 끊고 LIGHT_WAIT 초 뒤 재요청 → 수신량 3~11MB → ~0.4MB
LIGHT_WAIT = 13               # 10~20초 (짧으면 다시 스트리밍, 35초~ 면 서버 캐시 만료)
BENCH_503 = 300               # 503 받은 NNB 만 쉬게 하는 시간 (실측 회복 4~5분)
CACHE_CONCURRENCY = 3         # 발견(캐시 GraphQL) 동시 수 — 3 초과 시 HTTP 500 위험
CACHE_RETRY = 3               # 발견 슬롯 1건당 시도 수 (실패 시 다른 NNB 로)

# ── 판매처 / 출력 ───────────────────────────────────────────────────
# 판매처는 제휴(core/affiliates.py PARTNERS) 요금만 수집한다.
PREFILTER_ROUTES = True       # 노선별 첫 조회에 제휴 판매처 없으면 그 노선 나머지 날짜 생략
TOP_FARES = 5                 # 노선·날짜당 판매처별 최저가 몇 개
OTA_TOP = 5                   # 트래킹: 최저가 운행 1개를 파는 OTA 몇 곳까지 출력 (전송은 최저가 1건 그대로)
SUMMARY_TOP = 20              # 사이클 끝 요약 개수
# 네이버가 도시 이름을 한국어로 안 주는 곳 (공항 이름만 한국어) — 화면에 영어가 섞이지 않게
CITY_NAMES = {"Basel/Mulhouse": "바젤·뮐루즈"}

# ── 전송 ────────────────────────────────────────────────────────────
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000/api/deals")
SEND_BATCH = 50               # 이만큼 모이면 api 로 전송
SEND = True                   # --no-send 면 False

# ── 갱신 ────────────────────────────────────────────────────────────
REFRESH_MINUTES = 15
REFRESH_LIMIT = 500           # 화면 첫 화면(도착지마다 최저 1건) 싼 순으로 이만큼 — 스크롤 20쪽 남짓
REFRESH_CONCURRENCY = 100

# ── 트래킹 ──────────────────────────────────────────────────────────
SEND_TRACKED = False          # True 면 receive-price2 로 전송 (False 면 조회·로그만)
TRACKING = False              # 트래킹 작업 자체를 끈다 (Rockpin 추적 조회)
DOMESTIC_AIRPORT = {"SEL": "GMP"}   # 국내선 API 는 공항 코드만 받는다

PROXIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), PROXIES_FILE)
WEEKDAY = "월화수목금토일"


# ── 로그 / 주기 실행 ────────────────────────────────────────────────
JOB = contextvars.ContextVar("JOB", default="")   # 로그 앞 [작업] 태그 (background 가 채움)


def log(emoji: str, msg: str, indent: int = 0) -> None:
    """10-16 13:05:12 [전체] 💰 메시지  — indent 1단계 = 공백 4칸. emoji 가 없으면 자리만 비운다."""
    tag = pad(f"[{JOB.get()}]", 9) if JOB.get() else ""
    print(f"{datetime.now():%m-%d %H:%M:%S} {tag}{emoji or '  '} {'    ' * indent}{msg}", flush=True)


def width(s: str) -> int:
    """터미널 표시 폭 (한글 등 전각 2칸)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(0, n - width(s))


class background:
    """@background.task(hours=1) — 시작 즉시 1회 실행 후 주기마다 반복.
    이전 실행이 다음 주기까지 살아있으면 취소하고 새로 시작 (HOOK scheduler 와 동일)."""

    jobs: list[tuple[Callable[[], Awaitable[None]], float, str]] = []

    @classmethod
    def task(cls, *, hours: float = 0, minutes: float = 0, seconds: float = 0,
             name: str = "", enabled: bool = True):
        """name: 로그 태그 (없으면 함수 이름). enabled=False 면 등록 안 함."""
        interval = hours * 3600 + minutes * 60 + seconds

        def decorator(func):
            assert inspect.iscoroutinefunction(func) and interval > 0
            if enabled:
                cls.jobs.append((func, interval, name or func.__name__))
            return func
        return decorator

    @staticmethod
    async def _safe(func, name: str) -> None:
        JOB.set(name)
        t0 = time.monotonic()
        mins = lambda: f"{(time.monotonic() - t0) / 60:.0f}분"
        log("▶️", "시작 " + "─" * 50)
        try:
            await func()
            log("✅", f"완료 ({mins()})")
        except asyncio.CancelledError:
            log("⏹️", f"취소 ({mins()} 진행)")
            raise
        except Exception as e:
            log("💥", f"예외 ({mins()}) — {type(e).__name__}: {e}")
            traceback.print_exc()

    @classmethod
    async def _loop(cls, func, interval: float, name: str) -> None:
        current: Optional[asyncio.Task] = None
        while True:
            if current and not current.done():
                JOB.set(name)
                log("⏱️", "주기 안에 안 끝남 → 취소 후 새로 시작")
                current.cancel()
                await asyncio.gather(current, return_exceptions=True)
            current = asyncio.create_task(cls._safe(func, name))
            await asyncio.sleep(interval)

    @classmethod
    def run(cls, once: bool = False) -> None:
        """once=True 면 등록된 작업을 1회씩만 돌리고 끝낸다."""
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
            except Exception:
                pass
        try:
            asyncio.run(cls._gather(once))
        except KeyboardInterrupt:
            log("🛑", "중단 — 종료")

    @classmethod
    async def _gather(cls, once: bool) -> None:
        if once:
            await asyncio.gather(*(cls._safe(func, name) for func, _, name in cls.jobs))
        else:
            await asyncio.gather(*(cls._loop(*job) for job in cls.jobs))


# ── 콘솔 표시 ───────────────────────────────────────────────────────
def _day(d: date) -> str:
    return f"{d:%m-%d}({WEEKDAY[d.weekday()]})"


def _leg(it: Itinerary) -> str:
    """LJ0211 09:05→10:10 1h05 직항 (도착일이 다르면 +1)."""
    if not it.segments:
        return it.itinerary_id or "-"
    a, b = it.first, it.last
    plus = ""
    if a.dep_date and b.arr_date and b.arr_date != a.dep_date:
        plus = f"+{(datetime.strptime(b.arr_date, '%Y%m%d') - datetime.strptime(a.dep_date, '%Y%m%d')).days}"
    h, m = divmod(it.duration // 60, 60)
    stops = "직항" if not it.stops else f"경유{it.stops}"
    flights = "/".join(f"{s.airline}{s.flight_no}" for s in it.segments)
    times = f"{a.dep_time[:2]}:{a.dep_time[2:]}→{b.arr_time[:2]}:{b.arr_time[2:]}{plus}"
    return f"{pad(flights, 13)} {pad(times, 13)} {h:>2}h{m:02d} {stops}"


def route(d: Deal) -> str:
    if not d.itineraries or not d.itineraries[0].segments:
        return f"{d.origin}→{d.destination}"
    return f"{d.itineraries[0].first.dep_airport}→{d.itineraries[0].last.arr_airport}"


def head(d: Deal) -> str:
    """ICN→KIX 오사카 · 11-25(수) → 11-28(토) 3박"""
    when = (f"{_day(d.departure_date)} → {_day(d.return_date)} {d.nights}박" if d.return_date
            else f"{_day(d.departure_date)} 편도")
    return f"{route(d)} {d.destination_name} · {when}"


def flights(d: Deal) -> str:
    """가는 ZE0613  15:05→17:00   1h55 직항  │  오는 ..."""
    return "  │  ".join(f"{tag} {_leg(l)}" for tag, l in zip(("가는", "오는"), d.itineraries))


def price_seller(f: Offer) -> str:
    tag = f"[{f.network}]" if f.network else ""
    return f"{f.price:>9,}원  {pad(f.seller, 12)}{tag}"


def print_deal(d: Deal) -> None:
    """노선·날짜 1건 = 머리줄 + 항공편 + 판매처별 줄. 최저가와 다른 항공편이면 표시."""
    log("💰", head(d))
    if d.itineraries:
        log("", flights(d), 1)
    for f in d.offers:
        other = "" if f.itinerary_ids == d.offers[0].itinerary_ids else "  (다른 항공편)"
        log("", price_seller(f) + other, 1)


# ── 전송 ────────────────────────────────────────────────────────────
class Sender:
    """Deal 을 모아 SEND_BATCH 건씩 api 로 POST. 실패분은 다음 전송 때 다시 보낸다."""

    def __init__(self, url: str = API_URL):
        self.url = url
        self.buf: list[Deal] = []
        self.saved = self.failed = 0
        self.http = httpx.AsyncClient(timeout=30)
        self._lock = asyncio.Lock()

    async def add(self, d: Deal) -> None:
        self.buf.append(d)
        if len(self.buf) >= SEND_BATCH:
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            if not self.buf or not SEND:
                return
            batch, self.buf = self.buf, []
            try:
                r = await self.http.post(self.url, json=[_json(d) for d in batch])
                r.raise_for_status()
                self.saved += r.json().get("saved", 0)
            except httpx.HTTPError as e:
                self.buf[:0] = batch
                self.failed += 1
                log("⚠️", f"api 전송 실패 ({len(self.buf)}건 대기) — {type(e).__name__}: {e}")

    async def close(self) -> None:
        await self.flush()
        await self.http.aclose()
        if self.buf:
            log("⚠️", f"api 로 못 보낸 {len(self.buf)}건 버림 ({self.url})")


def _json(d: Deal) -> dict:
    """Deal → api 요청 JSON (date 는 ISO 문자열로)."""
    out = asdict(d)
    out["departure_date"] = d.departure_date.isoformat()
    out["return_date"] = d.return_date.isoformat() if d.return_date else None
    out.pop("checked_at")
    return out


# ── [0] 출발도시 / 슬롯 ─────────────────────────────────────────────
def depart_cities() -> list[str]:
    return sorted({CITY_FOLD.get(c, c) for c in DOMESTIC_CODES})


async def intl_routes(client: NaverFlightClient, city: str,
                      depart: date, nights: int) -> list[DestinationPrice]:
    """슬롯 1건 캐시 조회 → 가격 있는 해외 노선 (노선 목록 용도)."""
    rows = await client.min_prices_by_destination(
        city, trip_type="RT", departure_date=depart,
        return_date=depart + timedelta(days=nights))
    return [f for f in rows if not f.is_domestic and f.min_price and f.min_price > 0]


async def probe_cities(client: NaverFlightClient, cities: list[str],
                       today: date) -> list[str]:
    """HOOK _probe_departures 와 동일 — 전 날짜 0건이면 제외, 조회 실패는 살림."""
    alive, dead = [], []
    for city in cities:
        found = 0
        for off in PROBE_OFFSETS:
            try:
                found = len(await intl_routes(client, city, today + timedelta(days=off),
                                              PROBE_NIGHTS))
            except Exception:
                found = -1
            if found:
                break
        (alive if found else dead).append(city)
    log("🧭", f"사전점검  대상 {len(alive)}곳: {', '.join(alive)}")
    if dead:
        log("", f"제외 {len(dead)}곳 (노선 0개): {', '.join(dead)}", 1)
    return alive


# ── [1] 발견 ────────────────────────────────────────────────────────
# (도시, 출발공항, 도착공항, 가는날, 오는날, 도착도시명, 도시사진, 도착나라)
Query = tuple[str, str, str, date, Optional[date], str, Optional[str], Optional[str]]


async def discover(pool: NNBPool, cities: list[str], today: date,
                   out: asyncio.Queue, shared: dict) -> None:
    """(도시 × 출발일 × 박수) 통째로 셔플 → 슬롯마다 캐시 1회 → 발견 즉시 out 큐로 push (실시간과 동시 실행).
    한 IP 로 연속 호출하면 ~18초 뒤부터 503 이 쏟아진다 (실측 600슬롯 중 293) →
    NNB 풀(프록시)로 나눠 보내고, 503/429 면 그 NNB 를 쉬게 하고 다른 NNB 로 재시도."""
    pairs = [(city, today + timedelta(days=d), n)
             for city in cities for d in range(FLIGHT_DAYS) for n in FLIGHT_NIGHTS]
    random.shuffle(pairs)
    sem = asyncio.Semaphore(CACHE_CONCURRENCY)
    done = errors = pushed = 0
    seen: set[Query] = set()
    t0 = time.monotonic()

    async def one(city: str, dep: date, n: int) -> None:
        nonlocal done, errors, pushed
        rows = None
        for _ in range(CACHE_RETRY):
            c = await pool.pick()
            try:
                async with sem:
                    rows = await intl_routes(c, city, dep, n)
                break
            except NaverFlightError as e:
                if "503" in str(e) or "429" in str(e):
                    pool.bench(c, BENCH_503)
            except Exception:
                # 프록시 연결 끊김(curl 55 등) — 그 NNB 만 실패로 치고 다른 NNB 로 재시도.
                # 여기서 놓치면 gather 전체가 깨져 사이클이 통째로 멈춘다 (2026-10-19 실측)
                pool.report(c, False)
        if rows is None:
            rows = []
            errors += 1
        done += 1
        for r in rows:
            q = (city, r.origin.airport_code, r.destination.airport_code,
                 dep, dep + timedelta(days=n), CITY_NAMES.get(r.destination.city_name, r.destination.city_name),
                 r.destination.city_image.image_url, r.country_code or None)
            if q not in seen:
                seen.add(q)
                pushed += 1
                shared["discovered"] = pushed
                await out.put(q)
        if done % 500 == 0:
            log("⏳", progress("발견", done, len(pairs), t0) + f" · 실패 {errors}")

    await asyncio.gather(*(one(*p) for p in pairs))
    log("🔎", f"발견 완료  {len(pairs):,}슬롯 → 실시간 대상 {pushed:,}건 "
             f"(캐시 실패 {errors:,} · {time.monotonic() - t0:.0f}초)")


def progress(what: str, done: int, total: int, t0: float) -> str:
    """실시간 1,500/3,979 (38%) · 7.6/s · 남은 약 5분"""
    rate = done / max(time.monotonic() - t0, 1e-6)
    left = (total - done) / rate / 60 if rate else 0
    return f"{what} {done:,}/{total:,} ({done / max(total, 1):.0%}) · {rate:.1f}/s · 남은 약 {left:.0f}분"


# ── [2] 실시간 ──────────────────────────────────────────────────────
GATE = RateGate(SSE_RATE)     # 모든 작업 공용 — 합쳐서 초당 SSE_RATE 건


class Searcher:
    """초당 SSE_RATE 건으로 묶은 SSE 호출.
    503 이면 그 NNB 만 BENCH_503 초 쉬게 하고 다른 NNB 로 재시도 (503 은 NNB 단위, 실측).
    실패가 이어지는 NNB(죽은 프록시)는 풀이 알아서 뺀다."""

    def __init__(self, pool: NNBPool):
        self.pool = pool
        self.gate = GATE
        self.benched = 0

    async def search(self, dep: str, arr: str, d1: date, d2: Optional[date], *,
                     domestic: bool = False, dep_type: str = "airport",
                     arr_type: str = "airport") -> RealtimeResult:
        """domestic: 국내선 API (최저가 숫자만). dep_type/arr_type: "city" 면 도시 단위 (TYO, OSA)."""
        r = RealtimeResult(error="미조회")
        for _ in range(3):
            await self.gate.wait()
            c = await self.pool.pick()
            try:
                if domestic:
                    r = await search_domestic(c.session, dep, arr, d1, d2)
                else:
                    r = await search_international(c.session, dep, arr, d1, d2,
                                                   departure_location_type=dep_type,
                                                   arrival_location_type=arr_type,
                                                   light=LIGHT, light_wait=LIGHT_WAIT)
            except Exception as e:
                r = RealtimeResult(error=f"{type(e).__name__}: {e}")
            if r.error and "503" in r.error:
                self.pool.bench(c, BENCH_503)
                self.benched += 1
                continue
            self.pool.report(c, r.ok)
            if r.ok or not r.error:
                return r
        return r


def make_deal(q: Query, r: RealtimeResult, sellers: dict[str, str],
              same_flight: bool = False, n: int = TOP_FARES) -> Optional[Deal]:
    """판매처별 최저가 상위 n 개 → Deal. 제휴 판매처 요금이 없으면 None.
    same_flight: 최저가 운행(가는편+오는편 조합) 1개를 파는 판매처만 (트래킹용)."""
    city, _, dest, d1, d2, name, image, country = q
    ok = affiliate_fares(r)
    if not ok:
        return None
    if same_flight:
        ok = [f for f in ok if f.itinerary_ids == ok[0].itinerary_ids]
    picked = cheapest_per_seller(ok, n)
    return Deal(origin=city, destination=dest, destination_name=name,
                departure_date=d1, return_date=d2,
                offers=[Offer.from_fare(f, sellers, r.legs(f)) for f in picked],
                itineraries=r.legs(picked[0]), image_url=image, country_code=country)


async def realtime(pool: NNBPool, queue: asyncio.Queue, sellers: dict[str, str],
                   on_deal: Callable[[Deal], Awaitable[None]], shared: dict) -> dict[str, int]:
    """큐에서 조회를 뽑아 실시간 조회. 발견이 push 하는 대로 즉시 처리 (파이프라인).
    종료: 발견 완료 후 sentinel(None) 이 worker 수만큼 들어오면 끝.
    PREFILTER_ROUTES: 노선별 첫 도착 조합이 head — 제휴 판매처 없으면 이후 동일 노선 생략."""
    s = Searcher(pool)
    stats = dict(searched=0, skipped=0, failed=0, dead_routes=0)
    t0 = time.monotonic()
    route_key = lambda q: q[:3]
    probed: dict[tuple, asyncio.Event] = {}
    alive: dict[tuple, bool] = {}

    async def worker() -> None:
        while True:
            q = await queue.get()
            if q is None:
                return
            k, is_head = route_key(q), False
            if PREFILTER_ROUTES:
                if k in probed:
                    await probed[k].wait()
                    if not alive[k]:
                        stats["skipped"] += 1
                        continue
                else:
                    probed[k], is_head = asyncio.Event(), True
            deal, ok = None, True
            try:
                r = await s.search(q[1], q[2], q[3], q[4])
                stats["searched"] += 1
                if r.ok:
                    deal = make_deal(q, r, sellers)
                    ok = deal is not None
                else:
                    stats["failed"] += 1
            except Exception:
                stats["failed"] += 1
            if is_head:
                alive[k] = ok
                stats["dead_routes"] += not ok
                probed[k].set()
            if deal:
                await on_deal(deal)
            done = stats["searched"] + stats["skipped"]
            if done % 500 == 0:
                total = shared["discovered"]
                pct = f" ({done / total:.0%})" if total else ""
                rate = done / max(time.monotonic() - t0, 1e-6)
                tail = "" if shared["done"] else " · 발견 진행중"
                left = f" · 남은 약 {(total - done) / rate / 60:.0f}분" if shared["done"] and total > done else ""
                log("⏳", f"실시간 {done:,}/{total:,}{pct} · {rate:.1f}/s{left}{tail}"
                          f" · 실패 {stats['failed']} · 503 {s.benched}")

    await asyncio.gather(*(worker() for _ in range(SSE_CONCURRENCY)))
    stats["benched"] = s.benched
    return stats


# ── 작업 ────────────────────────────────────────────────────────────
@background.task(hours=1, name="전체")
async def collect_naver_flights() -> None:
    today = date.today()
    proxies = load_proxies(PROXIES_PATH) if os.path.isfile(PROXIES_PATH) else []
    log("⚙️", f"범위  오늘~{FLIGHT_DAYS}일 × {FLIGHT_NIGHTS.start}~{FLIGHT_NIGHTS.stop - 1}박 · "
             f"제휴 판매처 {len(PARTNERS)}곳 · 노선·날짜당 상위 {TOP_FARES}곳")
    log("", f"속도  초당 {SSE_RATE:g}건 · 동시 {SSE_CONCURRENCY} · LIGHT {'켬' if LIGHT else '끔'}", 1)
    log("", f"전송  {API_URL if SEND else '끔 (--no-send)'}", 1)

    sender = Sender()
    async with NaverFlightClient() as client, NNBPool(NNB_POOL, proxies) as pool:
        log("🔑", f"NNB {len(pool)}개 ({'프록시' if proxies else '직접 연결'}"
                 + (f", 발급 실패 {pool.failed}" if pool.failed else "") + ")")
        try:
            sellers = {p.ota_id: p.name for p in await client.booking_partners()}
        except Exception:
            sellers = {}

        cities = depart_cities()
        if PROBE_OFFSETS:
            cities = await probe_cities(client, cities, today)

        t = time.monotonic()
        results: list[Deal] = []

        async def on_deal(d: Deal) -> None:
            results.append(d)
            print_deal(d)
            await sender.add(d)

        # 발견→실시간 파이프라인: 발견 즉시 실시간 조회 (전체 발견 완료 대기 없음)
        q: asyncio.Queue = asyncio.Queue()
        shared = {"discovered": 0, "done": False}

        async def discover_and_close() -> None:
            try:
                await discover(pool, cities, today, q, shared)
            finally:
                shared["done"] = True
                for _ in range(SSE_CONCURRENCY):
                    q.put_nowait(None)

        try:
            disc = asyncio.create_task(discover_and_close())
            stats = await realtime(pool, q, sellers, on_deal, shared)
            await disc
        finally:
            await sender.close()
        sec = time.monotonic() - t
        log("📊", f"실시간 완료  {sec / 60:.0f}분 · {stats['searched'] / max(sec, 1):.1f}건/s")
        log("", f"조회 {stats['searched']:,} · 실패 {stats['failed']:,} · 503 {stats['benched']:,}", 1)
        log("", f"생략 {stats['skipped']:,} (제휴 판매처 없는 노선 {stats['dead_routes']:,}개)", 1)
        log("", f"결과 {len(results):,}건 → api 저장 {sender.saved:,}건", 1)

    log("🏆", f"최저가 TOP {SUMMARY_TOP}")
    for i, d in enumerate(sorted(results, key=lambda d: d.price)[:SUMMARY_TOP], 1):
        log("", f"{i:>2}. {price_seller(d.offers[0])}  {head(d)}  │  {flights(d)}", 1)


@background.task(minutes=REFRESH_MINUTES, name="갱신")
async def refresh_deals() -> None:
    """화면에 보이는 특가(도착지마다 최저 1건, 싼 순 REFRESH_LIMIT 개)를 실시간으로 다시 확인해 덮어쓴다.
    제휴 요금이 사라진 특가는 내린다. 조회 자체가 실패한 건 그대로 둔다.
    속도 제한(GATE)은 수집과 같이 써서 합쳐도 초당 SSE_RATE 건을 넘지 않는다."""
    async with httpx.AsyncClient(timeout=30) as http:
        rows: list[dict] = []
        for attempt in range(10):                    # api 가 아직 안 떴으면 잠깐 기다린다
            try:
                while len(rows) < REFRESH_LIMIT:        # 한 쪽 최대 100건씩
                    r = await http.get(API_URL, params={"group": "destination", "offset": len(rows), "limit": 100})
                    r.raise_for_status()
                    items = r.json()["items"]
                    rows += items
                    if len(items) < 100:
                        break
                break
            except httpx.HTTPError:
                if attempt == 9:
                    raise
                rows = []
                await asyncio.sleep(3)
        rows = rows[:REFRESH_LIMIT]
        if not rows:
            log("📭", "갱신할 특가가 없음")
            return
        log("🔄", f"갱신 대상 {len(rows)}건 (화면에 보이는 싼 순)")

        proxies = load_proxies(PROXIES_PATH) if os.path.isfile(PROXIES_PATH) else []
        sender = Sender()
        stats = dict(same=0, changed=0, removed=0, failed=0)
        async with NaverFlightClient() as client, NNBPool(NNB_POOL, proxies) as pool:
            try:
                sellers = {p.ota_id: p.name for p in await client.booking_partners()}
            except Exception:
                sellers = {}
            s = Searcher(pool)
            sem = asyncio.Semaphore(REFRESH_CONCURRENCY)

            async def one(row: dict) -> None:
                its = row["itineraries"]
                dep = its[0]["segments"][0]["dep_airport"] if its and its[0]["segments"] else row["origin"]
                d1 = date.fromisoformat(row["departure_date"])
                d2 = date.fromisoformat(row["return_date"]) if row["return_date"] else None
                q: Query = (row["origin"], dep, row["destination"], d1, d2,
                            row["destination_name"], row.get("image_url"), row.get("country_code"))
                async with sem:
                    res = await s.search(dep, row["destination"], d1, d2)
                if not res.ok:
                    stats["failed"] += 1
                    return
                deal = make_deal(q, res, sellers)
                if deal:
                    stats["same" if deal.price == row["offers"][0]["price"] else "changed"] += 1
                    await sender.add(deal)
                    return
                stats["removed"] += 1                    # 제휴 요금이 더는 없다 → 내린다
                if SEND:
                    await http.delete(API_URL, params={
                        "origin": row["origin"], "destination": row["destination"],
                        "departure_date": row["departure_date"], "return_date": row["return_date"] or ""})

            try:
                await asyncio.gather(*(one(row) for row in rows))
            finally:
                await sender.close()
    log("📊", f"갱신 완료  그대로 {stats['same']:,} · 가격 바뀜 {stats['changed']:,} · "
              f"내림 {stats['removed']:,} · 조회 실패 {stats['failed']:,}")


@background.task(hours=1, name="트래킹", enabled=TRACKING)
async def track_flights() -> None:
    """HOOK sync_tracked_flights 와 동일: 추적 목록 → 셔플 → 지난 출발일 스킵 → 1건씩 가격.
    같은 노선·날짜를 여러 회원이 추적하면 한 번만 조회해 회원마다 보낸다."""
    async with Rockpin() as rp:
        items = await rp.tracking_flights()
    today = date.today().isoformat()
    groups: dict[tuple, list[TrackingFlight]] = {}
    skipped = 0
    for t in items:
        if not (t.fc_dep_city and t.fc_arr_city and t.fc_dep_date) or t.fc_dep_date < today:
            skipped += 1
            continue
        groups.setdefault((t.fc_dep_city, t.fc_arr_city, t.fc_dep_date, t.fc_arr_date), []).append(t)
    keys = list(groups)
    random.shuffle(keys)
    log("📋", f"추적 {len(items)}건 → 조회 {len(keys)}건 (지난 날짜·누락 {skipped}건 제외)")

    proxies = load_proxies(PROXIES_PATH) if os.path.isfile(PROXIES_PATH) else []
    payloads: list[dict] = []
    failed = 0
    async with NaverFlightClient() as client, NNBPool(NNB_POOL, proxies) as pool:
        try:
            sellers = {p.ota_id: p.name for p in await client.booking_partners()}
        except Exception:
            sellers = {}
        s = Searcher(pool)
        # 코드 종류 — 트립닷컴발 추적은 TYO/OSA 같은 도시 코드가 섞여 있다 → 도시 단위로 검색
        codes = sorted({c for k in keys for c in k[:2]})
        try:
            kinds = {a.iata_code: a.type for a in await client.airport_detail_list(codes)}
        except Exception as e:
            kinds = {}
            log("⚠️", f"공항/도시 구분 실패 — 전부 공항으로 검색 ({type(e).__name__})")

        async def one(key: tuple) -> None:
            nonlocal failed
            dep, arr, d1, d2 = key
            ts = groups[key]
            name = ts[0].fc_arr_city_name or arr
            go, back = date.fromisoformat(d1), date.fromisoformat(d2) if d2 else None
            q: Query = (dep, dep, arr, go, back, name, None, None)
            if dep in DOMESTIC_CODES and arr in DOMESTIC_CODES:
                # 국내선: 국내선 API 로 최저가만 (판매처·항공편 정보 없음). SEL 은 김포로
                r = await s.search(DOMESTIC_AIRPORT.get(dep, dep), DOMESTIC_AIRPORT.get(arr, arr),
                                   go, back, domestic=True)
                deal = (Deal(dep, arr, name, go, back, [Offer("", "국내선 최저가", r.min_fare)])
                        if r.min_fare else None)
            else:
                r = await s.search(dep, arr, go, back, dep_type=kinds.get(dep, "airport"),
                                   arr_type=kinds.get(arr, "airport"))
                deal = make_deal(q, r, sellers, same_flight=True, n=OTA_TOP) if r.ok else None
            if not deal:
                failed += 1
                log("⚠️", f"{dep}→{arr} {d1}~{d2 or ''} — {r.error or '요금 없음'}")
                return
            print_deal(deal)                             # 전송 가격 = 최저가 1건
            for t in ts:
                goal = t.fct_target_price
                gap = (f"🎯 목표 {goal:,}원 도달" if goal and deal.price <= goal else
                       f"목표 {goal:,}원까지 {deal.price - goal:,}원" if goal else "목표가 없음")
                log("", f"fct#{t.fct_idx} · {gap}", 1)
                payloads.append({"fc_idx": t.fc_idx, "m_idx": t.m_idx, "price": deal.price,
                                 "collect_date": today})

        await asyncio.gather(*(one(k) for k in keys))

    if SEND_TRACKED and payloads:
        async with Rockpin() as rp:
            r = await rp.send_flight_prices(payloads)
        log("📦", f"전송  성공 {r.get('success', 0)} · 실패 {r.get('failed', 0)}")
    log("📊", f"가격 {len(payloads)}건 · 실패 {failed}건"
              + ("" if SEND_TRACKED else " · 전송 꺼짐 (SEND_TRACKED)"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="네이버항공권 실시간 최저가 수집기")
    ap.add_argument("--once", action="store_true", help="1회만 실행하고 끝낸다")
    ap.add_argument("--no-send", action="store_true", help="api 로 보내지 않고 로그만")
    args = ap.parse_args()
    SEND = not args.no_send
    background.run(once=args.once)
