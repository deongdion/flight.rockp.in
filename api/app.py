"""api 서버 — uv run litestar --app api.app:app run --reload"""

import asyncio
from contextlib import asynccontextmanager

from litekit import file_router
from litestar import Litestar
from litestar.config.compression import CompressionConfig
from litestar.logging import LoggingConfig

from api import database
from core.naver import NaverFlightClient

CLEANUP_INTERVAL = 60 * 60  # 초


@asynccontextmanager
async def lifespan(app: Litestar):
    async def cleanup_loop() -> None:
        while True:
            await asyncio.to_thread(database.delete_expired)
            await asyncio.sleep(CLEANUP_INTERVAL)

    await asyncio.to_thread(database.migrate)          # 표 만들기 · 예전 구조 옮기기
    # 네이버 세션은 앱 전체에서 1개 — 핸들러는 state.naver / state.sellers 로 쓴다
    async with NaverFlightClient() as naver:
        app.state.naver = naver
        try:
            app.state.sellers = {p.ota_id: p.name for p in await naver.booking_partners()}
        except Exception:
            app.state.sellers = {}
        task = asyncio.create_task(cleanup_loop())
        try:
            yield
        finally:
            task.cancel()


app = Litestar(
    route_handlers=[file_router("routes", path="/api", sync_to_thread=True)],
    lifespan=[lifespan],
    # 특가 목록 JSON 이 수백 KB — gzip 으로 줄여 보낸다
    compression_config=CompressionConfig(backend="gzip", minimum_size=1024),
    logging_config=LoggingConfig(loggers={"redirect": {"level": "INFO", "handlers": ["queue_listener"]}}),
)
