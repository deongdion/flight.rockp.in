# Redirect — 실시간 항공특가

네이버 항공권 실시간 최저가를 수집해 보여주고, 예약 버튼을 누르면 가격을 다시 확인한 뒤
우리 제휴 링크로 판매처 예약 페이지에 보낸다.

```
update.py ──POST /api/deals──▶ api ◀──fetch /api/*── web
(수집기)                       (Litestar · SQLite)     (SvelteKit)
```

사이트: **https://flight.rockp.in** — Cloudflare 터널 `rockpin-deals` (`~/.cloudflared/rockpin-deals.yml`) 가 이 PC 의 5173 으로 연결

## 폴더

```
Redirect/
├── update.py          수집기 — 네이버 실시간 가격 수집 → api 로 전송 (1시간마다)
├── api/               서버 (Litestar + LiteKit 파일 라우팅)
│   ├── app.py         앱 · 네이버 세션 · 만료 데이터 정리
│   ├── database.py    SQLite (database.db) — 특가 · 판매처 요금(=짧은 링크) · 항공편 · 도착지 · 가격 기록
│   ├── schemas.py     공개 응답 모양 — 화면에 필요한 것만 (내부 값은 내보내지 않는다)
│   ├── redirect.py    예약 버튼 → 실시간 재확인 → 제휴 예약 URL
│   └── routes/        /api, /api/deals, /api/deals/facets, /api/prices, /api/links/{code}, /api/links/{code}/redirect
├── core/              api 와 수집기가 같이 쓰는 코드
│   ├── models.py      저장 구조 Deal · Offer · Link · RedirectLink
│   ├── affiliates.py  제휴 판매처 목록 · 제휴 링크
│   ├── rockpin.py     록핀 API (트래킹)
│   └── naver/         네이버 항공권 클라이언트
├── web/               화면 (SvelteKit)
│   └── src/
│       ├── lib/       types.ts · format.ts · icons.ts · components/
│       └── routes/    / (특가) · /r/{code} (예약 이동 — 짧은 링크)
├── scripts/
│   └── fake_prices.py 가격 추이 화면 확인용 가짜 가격 기록 넣기 / --clear 로 지우기
├── .env.example       환경 변수 목록 → .env 로 복사해 채운다
├── .env               록핀 키 등 (git 제외)
└── proxies.txt        수집용 프록시 한 줄에 하나 (git 제외, 없으면 프록시 없이)
```

## 실행

```sh
cp .env.example .env                                            # 처음 한 번 — 값 채우기
uv sync                                                         # 처음 한 번
uv run watchfiles --filter python "uvicorn api.app:app --port 8000" api core
                                                                # api → :8000 (api/·core/ 파이썬 저장하면 자동 재시작)
                                                                # uvicorn --reload 는 Windows 백그라운드 실행에서 재시작이 멈춘다
uv run update.py                                                # 수집기 — 1시간마다 수집 + 15분마다 갱신
                                                                # (--once: 1회만, --no-send: 전송 안 함 · 코드 고치면 직접 재시작)
cd web && npm install && cd ..                                  # 처음 한 번
uv run python web/serve.py                                      # 공개 화면 → :5173 (빌드본, 저장하면 자동으로 다시 빌드)
cd web && npm run dev -- --port 5174                            # 고치면서 보기 → localhost:5174 (저장 즉시 반영)
                                                                # 개발 모드는 스크립트를 140여 개로 쪼개 보내 터널 너머에선 8~10초 걸린다
cloudflared tunnel --config ~/.cloudflared/rockpin-deals.yml run   # flight.rockp.in → :5173
```

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/deals?origin=SEL&group=destination&direct=true&sort=price&offset=0` | 특가 한 쪽 `{total, items}` (24장) |
| GET | `/api/deals/facets?origin=SEL` | 출발지·도착지·날짜별 특가 수·최저가 (검색 상자) |
| POST · DELETE | `/api/deals` | 수집기 전용 — 저장(같은 노선·날짜면 덮어씀) · 내리기. 사이트를 거친 요청은 403 |
| GET | `/api/prices?destination=NRT&origin=SEL&period=today\|7d\|30d` | 노선 가격 추이 캔들 (한 시간·하루 단위) |
| GET | `/api/links/{code}` | 짧은 링크 정보 — 모을 때 본 판매처 요금·항공편 (`warm=true` 면 실시간 확인 미리 시작) |
| GET | `/api/links/{code}/redirect` | 실시간 재확인 → 예약 URL + 지금 가격·항공편 (최대 15초, 넘기면 판매처 검색 페이지) |

저장 규칙: 특가 키는 (출발도시, 도착공항, 가는날, 오는날) — 확인한 지 하루가 지났거나 출발일이 지난 건 지운다.
짧은 링크는 따로 만들지 않는다 — 판매처 요금(offers) 의 코드가 곧 링크 코드 ((출발공항, 도착공항, 날짜, 판매처, 항공편) 으로 정해짐).
누가 연 링크만 그때 모습을 남겨 특가가 내려가도 7일 동안 열린다. 항공편은 항공편 ID 마다 한 번만 저장한다.
가격 기록(prices·price_hours)은 특가가 지워져도 남는다 (하루 단위 90일, 한 시간 단위 2일).
예약 버튼·자세히 보기의 실시간 확인 결과는 목록에 반영된다 — 요금이 사라지면 그 판매처를 빼고(다 사라지면 특가를 내리고), 가격이 바뀌면 그 가격으로.
