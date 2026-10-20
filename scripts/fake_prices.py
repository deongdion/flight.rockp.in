"""가격 추이 화면 확인용 가짜 가격 기록 — 노선(출발지→도착지)마다 지난 29일 하루 캔들 + 어제·오늘 한 시간 캔들.

    uv run python scripts/fake_prices.py           넣기 (다시 넣으면 지우고 새로)
    uv run python scripts/fake_prices.py --clear   가짜만 지우기

실제 기록과 섞이지 않게:
  하루 기록  가는날·오는날을 '-' 로 넣는다 (실제는 YYYY-MM-DD) → 그걸로 지운다
  한 시간    실제 기록이 없는 칸에만 넣고, 넣은 칸을 fake_price_hours 표에 적어 둔다 → 그걸로 지운다
값: 실제 기록처럼 노선의 모든 날짜를 합친 수준(평균·최저·최고)을 기준으로,
    과거가 대체로 5~25% 비쌌다가 내려온 흐름 (급락) + 출렁임.
"""

import random
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.database import KST, connect, migrate  # noqa: E402

DAYS = 29
FAKE = "-"


def clear(conn) -> tuple[int, int]:
    days = conn.execute("DELETE FROM prices WHERE departure_date = ?", (FAKE,)).rowcount
    conn.execute("CREATE TABLE IF NOT EXISTS fake_price_hours (origin TEXT, destination TEXT, hour TEXT)")
    hours = conn.execute("DELETE FROM price_hours WHERE (origin, destination, hour) IN "
                         "(SELECT origin, destination, hour FROM fake_price_hours)").rowcount
    conn.execute("DROP TABLE fake_price_hours")
    return days, hours


def main() -> None:
    migrate()
    rng = random.Random(20261020)
    now = datetime.now(KST)
    this_hour = now.replace(minute=0, second=0, microsecond=0)
    with closing(connect()) as conn, conn:
        if "--clear" in sys.argv:
            print("지움 — 하루 %d · 한 시간 %d" % clear(conn))
            return
        clear(conn)
        conn.execute("CREATE TABLE fake_price_hours (origin TEXT, destination TEXT, hour TEXT)")
        # 실제 기록처럼 노선의 모든 날짜를 합친 값 — 시가·종가는 평균 근처, 저가는 최저가 근처, 고가는 최고가 근처
        routes = conn.execute("SELECT origin, destination, MIN(price), AVG(price), MAX(price) FROM deals"
                              " GROUP BY origin, destination").fetchall()

        def row(level: float, prev: float, lo: float, hi: float, count: int) -> tuple:
            open_, close = int(prev), int(level)
            low = int(min(lo * (1 + rng.uniform(0, 0.05)), open_, close))
            high = int(max(hi * (1 - rng.uniform(0, 0.05)), open_, close))
            avg = int((open_ + close) / 2)
            return low, high, avg * count, count, close, open_

        day_rows, hour_rows = [], []
        for origin, destination, lo, avg, hi in routes:
            # 하루 — 과거로 갈수록 비싸게 (오늘 기준 +5~25%) 흐르다 내려온다 + 출렁임
            peak = rng.uniform(0.05, 0.25)
            level = avg * (1 + peak)
            for i in range(DAYS, 0, -1):
                f = 1 + peak * i / DAYS
                prev = level
                level = max(avg * 0.92, level + (avg * f - level) * 0.5 + avg * rng.uniform(-0.04, 0.04))
                low, high, total, count, close, open_ = row(level, prev, lo * f, hi * f, rng.randint(8, 40))
                day = (now - timedelta(days=i)).date().isoformat()
                day_rows.append((origin, destination, FAKE, FAKE, day, low, high, total, count, close, open_))
            # 한 시간 — 어제 0시 ~ 지금 직전, 지금 수준 근처에서 출렁임
            level = avg * (1 + peak / DAYS)
            hour = this_hour - timedelta(days=1, hours=now.hour)
            while hour < this_hour:
                prev = level
                level = max(avg * 0.95, level + (avg - level) * 0.2 + avg * rng.uniform(-0.02, 0.02))
                low, high, total, count, close, open_ = row(level, prev, lo, hi, rng.randint(1, 6))
                hour_rows.append((origin, destination, hour.strftime("%Y-%m-%dT%H"), low, total, count, high, open_, close))
                hour += timedelta(hours=1)
        conn.executemany("INSERT OR IGNORE INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", day_rows)
        added = 0
        for r in hour_rows:                     # 실제 기록이 있는 칸은 건드리지 않는다
            if conn.execute("INSERT OR IGNORE INTO price_hours VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", r).rowcount:
                conn.execute("INSERT INTO fake_price_hours VALUES (?, ?, ?)", r[:3])
                added += 1
        print(f"노선 {len(routes):,}개 · 하루 {len(day_rows):,}칸 · 한 시간 {added:,}칸 넣음")


if __name__ == "__main__":
    main()
