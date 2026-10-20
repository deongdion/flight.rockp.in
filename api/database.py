"""SQLite 저장소.

  deals         노선·날짜별 최신 특가 1건 (DESIGN.md 1·4번) — 키 (출발도시, 도착공항, 가는날, 오는날).
                확인한 지 DEAL_MAX_AGE 가 지났거나 출발일이 지난 건 지운다.
  offers        특가의 판매처별 요금 — code 가 짧은 링크(/r/<code>) 코드.
                코드는 (출발공항, 도착공항, 가는날, 오는날, 판매처, 항공편) 으로 정해져 다시 모아도 같다.
                짧은 링크를 따로 만들어 두지 않고, 열면 이 표에서 코드로 바로 찾는다.
  itineraries   항공편(편도 여정) — 항공편 ID 마다 1번만 둔다 (여러 특가·판매처가 같은 항공편을 같이 쓴다).
  destinations  도착지 이름·사진·나라 — 도착지마다 1번만.
  links         누가 연 짧은 링크의 그때 모습 — 특가가 내려가도 공유된 링크가 LINK_MAX_AGE 동안 살아 있게.
  prices        가격 기록 — 노선·날짜별 하루(한국 시각) 첫·마지막·최저·최고·합계·관측 수 (캔들).
                특가가 사라져도 남는다. PRICE_DAYS 일 둔다 → 7일·한 달 추이, 평균 대비 얼마나 싼지
  price_hours   노선(출발지→도착지)별 한 시간 캔들. HOUR_DAYS 일 둔다 → 오늘 추이
  관측 = 수집·15분 갱신·예약 버튼 실시간 확인에서 본 최저가 1번.

예전에는 판매처 요금마다 항공편까지 통째로 담은 링크를 수집할 때마다 새로 써서
링크가 34만 개·629MB 였다 (2026-10-20) → 판매처 요금은 작은 행, 항공편은 따로 한 번만.
"""

import hashlib
import time
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import msgspec

from core.models import Deal, Link, Offer
from core.naver import Itinerary, Segment

DB_PATH = Path(__file__).parent / "database.db"
DEAL_MAX_AGE = timedelta(days=1)
LINK_MAX_AGE = timedelta(days=7)
PRICE_DAYS = 90
HOUR_DAYS = 2
KST = timezone(timedelta(hours=9))

_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_KEY = "origin, destination, departure_date, return_date"      # 특가 키

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    origin           TEXT NOT NULL,             -- 출발 도시 (SEL)
    destination      TEXT NOT NULL,             -- 도착 공항 (NRT)
    departure_date   TEXT NOT NULL,             -- YYYY-MM-DD
    return_date      TEXT NOT NULL DEFAULT '',  -- 편도면 ''
    price            INTEGER NOT NULL,          -- 판매처 최저가 (정렬용)
    direct           INTEGER NOT NULL DEFAULT 0, -- 최저가 항공편이 가는편·오는편 모두 직항이면 1
    checked_at       TEXT NOT NULL,             -- ISO 8601 UTC
    PRIMARY KEY (origin, destination, departure_date, return_date)
);
CREATE INDEX IF NOT EXISTS deals_price ON deals (price);
CREATE INDEX IF NOT EXISTS deals_destination_price ON deals (destination, price);
CREATE INDEX IF NOT EXISTS deals_origin ON deals (origin);
CREATE INDEX IF NOT EXISTS deals_departure ON deals (departure_date);
CREATE INDEX IF NOT EXISTS deals_return ON deals (return_date);
CREATE INDEX IF NOT EXISTS deals_direct_price ON deals (direct, price);
CREATE INDEX IF NOT EXISTS deals_direct_destination_price ON deals (direct, destination, price);

CREATE TABLE IF NOT EXISTS offers (
    code             TEXT PRIMARY KEY,          -- 짧은 링크 코드
    origin           TEXT NOT NULL,             -- 특가 키
    destination      TEXT NOT NULL,
    departure_date   TEXT NOT NULL,
    return_date      TEXT NOT NULL,
    partner_code     TEXT NOT NULL,             -- CTR013
    seller           TEXT NOT NULL,             -- 트립닷컴
    price            INTEGER NOT NULL,
    baggage          TEXT NOT NULL,             -- FREE / CHARGE / UNKNOWN
    outbound_id      TEXT NOT NULL,             -- 가는편 항공편 ID (itineraries)
    inbound_id       TEXT NOT NULL DEFAULT ''   -- 오는편 항공편 ID, 편도면 ''
);
CREATE INDEX IF NOT EXISTS offers_deal ON offers (origin, destination, departure_date, return_date);
CREATE INDEX IF NOT EXISTS offers_outbound ON offers (outbound_id);
CREATE INDEX IF NOT EXISTS offers_inbound ON offers (inbound_id);

CREATE TABLE IF NOT EXISTS itineraries (
    id               TEXT PRIMARY KEY,          -- 20261028CJUNGB9C6172 (앞 8자리가 출발일)
    duration         INTEGER NOT NULL,          -- 초
    segments         TEXT NOT NULL              -- JSON list[Segment]
);

CREATE TABLE IF NOT EXISTS destinations (
    code             TEXT PRIMARY KEY,          -- 도착 공항
    name             TEXT NOT NULL,
    image_url        TEXT,
    country_code     TEXT
);

CREATE TABLE IF NOT EXISTS links (
    code             TEXT PRIMARY KEY,
    departure_date   TEXT NOT NULL,
    opened_at        TEXT NOT NULL,             -- 마지막으로 연 시각
    link             TEXT NOT NULL              -- JSON Link (그때 모습)
);

CREATE TABLE IF NOT EXISTS prices (
    origin           TEXT NOT NULL,
    destination      TEXT NOT NULL,
    departure_date   TEXT NOT NULL,
    return_date      TEXT NOT NULL DEFAULT '',
    day              TEXT NOT NULL,             -- 관측한 날 YYYY-MM-DD (한국 시각)
    min_price        INTEGER NOT NULL,
    max_price        INTEGER NOT NULL,
    sum_price        INTEGER NOT NULL,          -- 평균 = sum_price / count
    count            INTEGER NOT NULL,
    last_price       INTEGER NOT NULL,
    first_price      INTEGER NOT NULL,
    PRIMARY KEY (origin, destination, departure_date, return_date, day)
);
CREATE INDEX IF NOT EXISTS prices_route_day ON prices (destination, origin, day);

CREATE TABLE IF NOT EXISTS price_hours (
    origin           TEXT NOT NULL,
    destination      TEXT NOT NULL,
    hour             TEXT NOT NULL,             -- YYYY-MM-DDTHH (한국 시각)
    min_price        INTEGER NOT NULL,
    sum_price        INTEGER NOT NULL,
    count            INTEGER NOT NULL,
    max_price        INTEGER NOT NULL,
    first_price      INTEGER NOT NULL,
    last_price       INTEGER NOT NULL,
    PRIMARY KEY (destination, origin, hour)
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate() -> None:
    """표 만들기 + 예전 구조(deals 에 판매처·항공편 JSON, 수집마다 쓰는 links) 를 새 구조로 옮긴다 (서버 시작 시)."""
    with closing(connect()) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(deals)")}
        old = "offers" in cols
        if old:
            conn.execute("ALTER TABLE deals RENAME TO deals_old")
            conn.execute("DROP TABLE IF EXISTS links")
            for name in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' "
                                                    "AND tbl_name = 'deals_old' AND sql IS NOT NULL")]:
                conn.execute(f"DROP INDEX {name}")
        conn.executescript(SCHEMA)
        _add_columns(conn)
        if not old:
            return
        deals = []
        for r in conn.execute("SELECT * FROM deals_old"):
            offers = msgspec.json.decode(r["offers"], type=list[Offer])
            its = msgspec.json.decode(r["itineraries"], type=list[Itinerary])
            for o in offers:                    # 예전엔 최저가 항공편만 남았다 — 같은 항공편 판매처에만 붙인다
                o.itineraries = its if o.itinerary_ids == offers[0].itinerary_ids else []
            deals.append(Deal(r["origin"], r["destination"], r["destination_name"],
                              date.fromisoformat(r["departure_date"]),
                              date.fromisoformat(r["return_date"]) if r["return_date"] else None,
                              offers, its, r["image_url"], r["country_code"],
                              datetime.fromisoformat(r["checked_at"])))
        _save(conn, deals, record=False)
        conn.execute("DROP TABLE deals_old")
        conn.commit()
        conn.execute("VACUUM")


def _add_columns(conn: sqlite3.Connection) -> None:
    """가격 기록에 캔들 칸(첫·마지막·최고가)이 생기기 전 표 — 칸을 더하고 있는 값으로 채운다."""
    for table, cols in (("prices", ("first_price",)), ("price_hours", ("max_price", "first_price", "last_price"))):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col in cols:
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                src = "last_price" if col == "first_price" and table == "prices" else "min_price"
                conn.execute(f"UPDATE {table} SET {col} = {src}")
    conn.commit()


def link_code(origin: str, destination: str, departure_date: date, return_date: Optional[date],
              partner_code: str, itinerary_ids: str) -> str:
    """같은 노선·날짜·판매처·항공편이면 늘 같은 8자 코드."""
    key = "|".join([origin, destination, departure_date.isoformat(),
                    return_date.isoformat() if return_date else "", partner_code, itinerary_ids])
    n = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
    out = ""
    for _ in range(8):
        n, r = divmod(n, 62)
        out += _BASE62[r]
    return out


def _is_direct(its: list[Itinerary]) -> int:
    return int(bool(its) and all(len(i.segments) == 1 for i in its))


# ── 저장 ────────────────────────────────────────────────────────────
def save_deals(deals: list[Deal]) -> int:
    """특가 저장 — 같은 키면 덮어쓰고 판매처 요금은 새로 받은 것으로 바꾼다. checked_at 이 없으면 지금."""
    with closing(connect()) as conn, conn:
        n = _save(conn, deals)
    _cache.clear()
    return n


def _save(conn: sqlite3.Connection, deals: list[Deal], record: bool = True) -> int:
    now = datetime.now(timezone.utc)
    deal_rows, offer_rows, keys, dests, observed = [], [], [], {}, []
    itins: dict[str, Itinerary] = {}
    for d in deals:
        if not d.offers:
            continue
        checked = d.checked_at or now
        key = (d.origin.upper(), d.destination.upper(), d.departure_date.isoformat(),
               d.return_date.isoformat() if d.return_date else "")
        offers = sorted(d.offers, key=lambda o: o.price)
        for o in offers:
            # 판매처 항공편 — 수집기가 보낸 게 없으면 최저가 항공편과 같을 때만 그걸 쓴다
            its = o.itineraries or (d.itineraries if o.itinerary_ids == offers[0].itinerary_ids else [])
            for i in its:
                itins[i.itinerary_id] = i
            airport = its[0].segments[0].dep_airport if its and its[0].segments else key[0]
            o.code = link_code(airport, key[1], d.departure_date, d.return_date, o.partner_code, o.itinerary_ids)
            out_id, _, in_id = o.itinerary_ids.partition("-")
            offer_rows.append((o.code, *key, o.partner_code, o.seller, o.price, o.baggage, out_id, in_id))
        for i in d.itineraries:
            itins[i.itinerary_id] = i
        keys.append(key)
        dests[key[1]] = (key[1], d.destination_name, d.image_url, d.country_code)
        deal_rows.append((*key, offers[0].price, _is_direct(d.itineraries), checked.isoformat()))
        observed.append((*key, offers[0].price, checked))
    conn.executemany(
        """
        INSERT INTO deals VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO UPDATE SET price = excluded.price, direct = excluded.direct, checked_at = excluded.checked_at
        """, deal_rows)
    conn.executemany(f"DELETE FROM offers WHERE ({_KEY}) = (?, ?, ?, ?)", keys)
    conn.executemany("INSERT OR REPLACE INTO offers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", offer_rows)
    conn.executemany("INSERT OR IGNORE INTO itineraries VALUES (?, ?, ?)",
                     [(i.itinerary_id, i.duration, msgspec.json.encode(i.segments).decode()) for i in itins.values()])
    conn.executemany(
        """
        INSERT INTO destinations VALUES (?, ?, ?, ?)
        ON CONFLICT DO UPDATE SET name = excluded.name, image_url = COALESCE(excluded.image_url, image_url),
                                  country_code = COALESCE(excluded.country_code, country_code)
        """, list(dests.values()))
    if record:
        _record_prices(conn, observed)
    return len(deal_rows)


def delete_deal(origin: str, destination: str, departure_date: str, return_date: str = "") -> int:
    key = (origin.upper(), destination.upper(), departure_date, return_date)
    with closing(connect()) as conn, conn:
        conn.execute(f"DELETE FROM offers WHERE ({_KEY}) = (?, ?, ?, ?)", key)
        n = conn.execute(f"DELETE FROM deals WHERE ({_KEY}) = (?, ?, ?, ?)", key).rowcount
    _cache.clear()
    return n


def delete_expired() -> int:
    """오래됐거나 출발일이 지난 특가·판매처 요금·연 링크, 아무도 안 쓰는 항공편, 기간 지난 가격 기록."""
    now = datetime.now(timezone.utc)
    today = date.today().isoformat()
    kst = now.astimezone(KST)
    with closing(connect()) as conn, conn:
        n = conn.execute("DELETE FROM deals WHERE checked_at < ? OR departure_date < ?",
                         ((now - DEAL_MAX_AGE).isoformat(), today)).rowcount
        conn.execute(f"DELETE FROM offers WHERE NOT EXISTS (SELECT 1 FROM deals d WHERE ({_KEY}) = "
                     "(d.origin, d.destination, d.departure_date, d.return_date))")
        conn.execute("DELETE FROM itineraries WHERE NOT EXISTS (SELECT 1 FROM offers WHERE outbound_id = id)"
                     " AND NOT EXISTS (SELECT 1 FROM offers WHERE inbound_id = id)")
        conn.execute("DELETE FROM links WHERE opened_at < ? OR departure_date < ?",
                     ((now - LINK_MAX_AGE).isoformat(), today))
        conn.execute("DELETE FROM prices WHERE day < ?", ((kst - timedelta(days=PRICE_DAYS)).date().isoformat(),))
        conn.execute("DELETE FROM price_hours WHERE hour < ?",
                     ((kst - timedelta(days=HOUR_DAYS)).strftime("%Y-%m-%dT%H"),))
    if n:
        _cache.clear()
    return n


# ── 읽기 ────────────────────────────────────────────────────────────
def _itineraries(conn: sqlite3.Connection, ids: Iterable[str]) -> dict[str, Itinerary]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    rows = conn.execute(f"SELECT * FROM itineraries WHERE id IN ({','.join('?' * len(ids))})", ids)
    return {r["id"]: Itinerary(r["id"], r["duration"], msgspec.json.decode(r["segments"], type=list[Segment]))
            for r in rows}


def _legs(itins: dict[str, Itinerary], out_id: str, in_id: str) -> list[Itinerary]:
    return [itins[i] for i in (out_id, in_id) if i and i in itins]


def _offer(r: sqlite3.Row) -> Offer:
    ids = f"{r['outbound_id']}-{r['inbound_id']}" if r["inbound_id"] else r["outbound_id"]
    return Offer(r["partner_code"], r["seller"], r["price"], itinerary_ids=ids, baggage=r["baggage"], code=r["code"])


def _deals(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[Deal]:
    """deals 행 → Deal (판매처 요금 싼 순 + 최저가 항공편)."""
    if not rows:
        return []
    keys = [(r["origin"], r["destination"], r["departure_date"], r["return_date"]) for r in rows]
    offers: dict[tuple, list[sqlite3.Row]] = {}
    for o in conn.execute(f"SELECT * FROM offers WHERE ({_KEY}) IN (VALUES {','.join(['(?, ?, ?, ?)'] * len(keys))})"
                          " ORDER BY price", [v for k in keys for v in k]):
        offers.setdefault((o["origin"], o["destination"], o["departure_date"], o["return_date"]), []).append(o)
    firsts = [offers[k][0] for k in keys if offers.get(k)]
    itins = _itineraries(conn, [x for o in firsts for x in (o["outbound_id"], o["inbound_id"])])
    out = []
    for r, k in zip(rows, keys):
        os = offers.get(k, [])
        out.append(Deal(
            origin=r["origin"], destination=r["destination"], destination_name=r["name"] or r["destination"],
            departure_date=date.fromisoformat(r["departure_date"]),
            return_date=date.fromisoformat(r["return_date"]) if r["return_date"] else None,
            offers=[_offer(o) for o in os],
            itineraries=_legs(itins, os[0]["outbound_id"], os[0]["inbound_id"]) if os else [],
            image_url=r["image_url"], country_code=r["country_code"],
            checked_at=datetime.fromisoformat(r["checked_at"])))
    return out


# 특가 목록 조건 — 넷 다 선택 사항. 값은 코드/날짜 그대로 (origin=SEL, destination=NRT, YYYY-MM-DD)
FILTERS = ("origin", "destination", "departure_date", "return_date")


def _where(filters: dict[str, Optional[str]], skip: str = "") -> tuple[str, list]:
    """조건 → WHERE 절. skip 은 집계할 때 그 조건 자신은 빼기 위해."""
    sql, params = " WHERE 1=1", []
    for key in FILTERS:
        value = filters.get(key)
        if value and key != skip:
            sql += f" AND {key} = ?"
            params.append(value.upper() if key in ("origin", "destination") else value)
    return sql, params


def _deals_sql(filters: dict[str, Optional[str]], per_destination: bool, direct: bool) -> tuple[str, list]:
    """조건에 맞는 특가 SELECT (정렬·LIMIT 전). per_destination 이면 도착지마다 가장 싼 1건만."""
    where, params = _where(filters)
    if direct:
        where += " AND direct = 1"
    if per_destination:
        # SQLite 는 MIN() 과 함께 고른 다른 칸을 최솟값 행에서 가져온다 → 도착지마다 가장 싼 행 (색인으로 빠르다)
        return f"SELECT * FROM (SELECT *, MIN(price) AS min_price FROM deals{where} GROUP BY destination)", params
    return f"SELECT * FROM deals{where}", params


def list_deals(origin: Optional[str] = None, destination: Optional[str] = None,
               limit: int = 60, departure_date: Optional[str] = None,
               return_date: Optional[str] = None, per_destination: bool = False,
               direct: bool = False, sort: str = "price", offset: int = 0) -> list[Deal]:
    """sort=price 싼 순 / date 빠른 출발순. per_destination 이면 도착지마다 가장 싼 1건만."""
    sql, params = _deals_sql({"origin": origin, "destination": destination,
                              "departure_date": departure_date, "return_date": return_date},
                             per_destination, direct)
    order = "departure_date, price" if sort == "date" else "price"
    with closing(connect()) as conn:
        rows = conn.execute(f"SELECT d.*, t.name, t.image_url, t.country_code FROM ({sql} ORDER BY {order}"
                            " LIMIT ? OFFSET ?) d LEFT JOIN destinations t ON t.code = d.destination",
                            [*params, limit, offset]).fetchall()
        return _deals(conn, rows)


# 집계(개수·조건 칩)는 몇십 초 사이에 거의 안 바뀐다 → 잠깐 들고 있다가 그대로 준다 (저장하면 비운다)
CACHE_SECONDS = 30
_cache: dict[tuple, tuple[float, object]] = {}


def _cached(key: tuple, compute):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = compute()
    _cache[key] = (now, value)
    if len(_cache) > 500:                          # 조건 조합이 많아도 메모리가 늘지 않게
        _cache.clear()
    return value


def count_deals(filters: dict[str, Optional[str]], per_destination: bool = False, direct: bool = False) -> int:
    def compute() -> int:
        sql, params = _deals_sql(filters, per_destination, direct)
        with closing(connect()) as conn:
            return conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
    return _cached(("count", tuple(sorted(filters.items())), per_destination, direct), compute)


def deal_facets(filters: dict[str, Optional[str]]) -> dict[str, list[dict]]:
    return _cached(("facets", tuple(sorted(filters.items()))), lambda: _deal_facets(filters))


def _deal_facets(filters: dict[str, Optional[str]]) -> dict[str, list[dict]]:
    """조건 칩 목록용 — 값마다 특가 수·최저가. 각 칩은 자기 조건만 빼고 나머지 조건을 적용한다
    (도착지를 고른 상태에서도 다른 도착지 목록을 볼 수 있게)."""
    out: dict[str, list[dict]] = {}
    with closing(connect()) as conn:
        for key in FILTERS:
            where, params = _where(filters, skip=key)
            order = "value" if key.endswith("_date") else "count DESC, value"
            sql = f"SELECT {key} AS value, COUNT(*) AS count, MIN(price) AS min_price FROM deals{where}" \
                  f" AND {key} != '' GROUP BY {key}"
            if key == "destination":
                sql = f"SELECT f.*, t.name, t.country_code AS country FROM ({sql}) f" \
                      " LEFT JOIN destinations t ON t.code = f.value"
            out[key] = [dict(r) for r in conn.execute(f"{sql} ORDER BY {order}", params)]
    return out


def get_link(code: str) -> Optional[Link]:
    """짧은 링크 → 판매처 요금 1건. 특가가 살아 있으면 지금 값으로, 내려갔으면 마지막으로 열었을 때 모습으로.
    열 때마다 그 모습을 links 에 남긴다 (공유된 링크가 특가가 내려간 뒤에도 열리게)."""
    with closing(connect()) as conn, conn:
        o = conn.execute("SELECT o.*, d.checked_at, t.name, t.image_url FROM offers o"
                         " JOIN deals d USING (origin, destination, departure_date, return_date)"
                         " LEFT JOIN destinations t ON t.code = o.destination WHERE o.code = ?", (code,)).fetchone()
        if not o:
            row = conn.execute("SELECT link FROM links WHERE code = ?", (code,)).fetchone()
            return msgspec.json.decode(row["link"], type=Link) if row else None
        legs = _legs(_itineraries(conn, (o["outbound_id"], o["inbound_id"])), o["outbound_id"], o["inbound_id"])
        link = Link(code=code, origin=legs[0].segments[0].dep_airport if legs and legs[0].segments else o["origin"],
                    destination=o["destination"], destination_name=o["name"] or o["destination"],
                    departure_date=date.fromisoformat(o["departure_date"]),
                    return_date=date.fromisoformat(o["return_date"]) if o["return_date"] else None,
                    offer=_offer(o), itineraries=legs, image_url=o["image_url"],
                    checked_at=datetime.fromisoformat(o["checked_at"]))
        conn.execute("INSERT OR REPLACE INTO links VALUES (?, ?, ?, ?)",
                     (code, o["departure_date"], datetime.now(timezone.utc).isoformat(),
                      msgspec.json.encode(link).decode()))
        return link


# ── 예약 버튼 실시간 확인 반영 ───────────────────────────────────────
def apply_check(code: str, price: Optional[int]) -> None:
    """실시간 확인 결과를 목록에 반영한다 (다음 사람은 바뀐 값을 본다).
    price=None 이면 이 판매처 요금이 사라졌다 → 그 판매처를 빼고, 남은 판매처가 없으면 특가를 내린다.
    값이 있으면 그 가격으로 바꾸고, 특가 가격·직항 여부는 남은 판매처 최저가로 다시."""
    now = datetime.now(timezone.utc)
    with closing(connect()) as conn, conn:
        o = conn.execute("SELECT * FROM offers WHERE code = ?", (code,)).fetchone()
        if not o:
            return
        key = (o["origin"], o["destination"], o["departure_date"], o["return_date"])
        if price is None:
            conn.execute("DELETE FROM offers WHERE code = ?", (code,))
        else:
            conn.execute("UPDATE offers SET price = ? WHERE code = ?", (price, code))
        first = conn.execute(f"SELECT * FROM offers WHERE ({_KEY}) = (?, ?, ?, ?) ORDER BY price LIMIT 1",
                             key).fetchone()
        if not first:
            conn.execute(f"DELETE FROM deals WHERE ({_KEY}) = (?, ?, ?, ?)", key)
        else:
            legs = _legs(_itineraries(conn, (first["outbound_id"], first["inbound_id"])),
                         first["outbound_id"], first["inbound_id"])
            conn.execute(f"UPDATE deals SET price = ?, direct = ? WHERE ({_KEY}) = (?, ?, ?, ?)",
                         (first["price"], _is_direct(legs), *key))
            if price is not None:
                _record_prices(conn, [(*key, first["price"], now)])
    _cache.clear()


# ── 가격 기록 ───────────────────────────────────────────────────────
def _record_prices(conn: sqlite3.Connection, rows: list[tuple[str, str, str, str, int, datetime]]) -> None:
    """가격 관측 기록 — (출발, 도착, 가는날, 오는날, 최저가, 관측 시각)."""
    day_rows, hour_rows = [], []
    for origin, destination, dep, ret, price, at in rows:
        kst = at.astimezone(KST)
        day_rows.append((origin, destination, dep, ret, kst.date().isoformat(), price, price, price, 1, price, price))
        hour_rows.append((origin, destination, kst.strftime("%Y-%m-%dT%H"), price, price, 1, price, price, price))
    conn.executemany(
        """
        INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO UPDATE SET
            min_price = MIN(min_price, excluded.min_price),
            max_price = MAX(max_price, excluded.max_price),
            sum_price = sum_price + excluded.sum_price,
            count = count + 1,
            last_price = excluded.last_price
        """, day_rows)
    conn.executemany(
        """
        INSERT INTO price_hours VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO UPDATE SET
            min_price = MIN(min_price, excluded.min_price),
            max_price = MAX(max_price, excluded.max_price),
            sum_price = sum_price + excluded.sum_price,
            count = count + 1,
            last_price = excluded.last_price
        """, hour_rows)


_CANDLE = ("CAST(AVG(first_price) AS INTEGER) AS open, CAST(AVG(last_price) AS INTEGER) AS close,"
           " MIN(min_price) AS min, MAX(max_price) AS max, SUM(sum_price) / SUM(count) AS avg, SUM(count) AS count")


def price_history(destination: str, origin: Optional[str] = None, departure_date: Optional[str] = None,
                  return_date: Optional[str] = None, period: str = "7d") -> list[dict]:
    """가격 추이 캔들 — period=today 면 오늘 한 시간 단위, 7d·30d 면 하루 단위.
    조건(출발지·가는날·오는날)에 맞는 관측을 합쳐 칸마다 {t, open, close, min, max, avg, count}.
    여러 날짜가 섞이므로 시가·종가는 날짜별 첫·마지막 가격의 평균 (그 칸에 오르는 흐름이었는지 내리는 흐름이었는지)."""
    kst = datetime.now(KST)
    with closing(connect()) as conn:
        if period == "today":
            sql = (f"SELECT hour AS t, {_CANDLE} FROM price_hours WHERE destination = ? AND hour >= ?")
            params: list = [destination.upper(), kst.strftime("%Y-%m-%dT00")]
            if origin:
                sql += " AND origin = ?"
                params.append(origin.upper())
            return [dict(r) for r in conn.execute(sql + " GROUP BY hour ORDER BY hour", params)]
        days = 30 if period == "30d" else 7
        sql = f"SELECT day AS t, {_CANDLE} FROM prices WHERE destination = ? AND day > ?"
        params = [destination.upper(), (kst - timedelta(days=days)).date().isoformat()]
        for key, value in (("origin", origin), ("departure_date", departure_date), ("return_date", return_date)):
            if value is not None and value != "":
                sql += f" AND {key} = ?"
                params.append(value.upper() if key == "origin" else value)
        return [dict(r) for r in conn.execute(sql + " GROUP BY day ORDER BY day", params)]
