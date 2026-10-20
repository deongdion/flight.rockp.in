"""공개 사이트(flight.rockp.in → :5173) 를 빌드본으로 띄우고, 코드를 저장하면 다시 빌드해 반영한다.

    uv run python web/serve.py

개발 모드(npm run dev)는 화면 코드를 모듈 140여 개로 따로 보내서 터널 너머에서는 화면이
동작하기까지 8~10초가 걸린다 (2026-10-19 HAR 실측). 그래서 공개는 빌드본으로 하고,
src/·static/·vite.config.ts 가 바뀌면 [미리보기 끄기 → 빌드 → 다시 켜기] 를 한다.
빌드하는 몇 초 동안은 사이트가 잠깐 내려간다. 빌드가 실패하면 로그를 남기고 전 빌드로 다시 켠다.

고치면서 바로 보려면 따로 npm run dev -- --port 5174 (저장 즉시 반영, 이 PC 에서만).
"""

import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from watchfiles import watch

WEB = Path(__file__).parent
WATCH = [WEB / "src", WEB / "static", WEB / "vite.config.ts"]
NPM = "npm.cmd" if sys.platform == "win32" else "npm"
PORT = 5173


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def build() -> bool:
    t = time.monotonic()
    r = subprocess.run([NPM, "run", "build"], cwd=WEB, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log("빌드 실패 — 전 빌드로 다시 켭니다\n" + (r.stdout + r.stderr)[-2000:])
        return False
    log(f"빌드 완료 ({time.monotonic() - t:.1f}초)")
    return True


def start() -> subprocess.Popen:
    return subprocess.Popen([NPM, "run", "preview", "--", "--strictPort"], cwd=WEB)


def _port_busy() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _port_owners() -> set[str]:
    """PORT 에서 듣고 있는 프로세스 ID (Windows netstat)."""
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace").stdout
    return {m[1] for m in re.finditer(rf"\S+:{PORT}\s+\S+\s+LISTENING\s+(\d+)", out)}


def stop(p: subprocess.Popen) -> None:
    """npm → node 로 이어진 프로세스를 통째로 끄고, 포트가 비었는지 확인한다.
    Windows 는 npm.cmd 가 먼저 끝나 node 가 고아로 남아 포트를 계속 잡는 일이 있다
    (그러면 새 미리보기가 'Port in use' 로 못 뜨고 옛 빌드가 계속 나간다) → 포트 주인까지 끈다."""
    if sys.platform == "win32":
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        for pid in _port_owners():
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    elif p.poll() is None:
        p.terminate()
    for _ in range(50):
        if not _port_busy():
            return
        time.sleep(0.2)
    log(f"포트 {PORT} 가 아직 사용 중입니다")


def main() -> None:
    for pid in _port_owners() if sys.platform == "win32" else ():    # 전에 남은 미리보기
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    build()
    server = start()
    log("공개 사이트 켜짐 — 저장하면 다시 빌드해 반영합니다")
    try:
        for changes in watch(*WATCH, debounce=1200):
            log(f"바뀜: {', '.join(sorted({Path(p).name for _, p in changes}))[:120]}")
            stop(server)
            build()
            server = start()
    except KeyboardInterrupt:
        pass
    finally:
        stop(server)


if __name__ == "__main__":
    main()
