"""오늘 날짜 그림자 자동 계산(하루 한 번) — 수집기가 별도 프로세스로 실행한다.

1) 오늘 그림자(06~20시 30분 간격, 시범 구역 전체) 계산  2) 좌표 압축  3) 오늘 체감(UTCI) 계산
4) 지난 날짜의 웹용 그림자·체감 파일 정리(화면은 '오늘'만 사용)
잠금 파일(data/live/daily_shadows.lock)로 중복 실행을 막는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

from scripts.common import ROOT, WEB_DATA
from scripts.live.kma_time import KST

LOCK = ROOT / "data" / "live" / "daily_shadows.lock"


def today() -> str:
    return datetime.now(KST).date().isoformat()


def ready(day: str) -> bool:
    summ = WEB_DATA / "shadows" / "shadow_summary.json"
    if not summ.exists():
        return False
    ids = [a["id"] for a in json.loads(summ.read_text(encoding="utf-8"))["aois"]]
    return all((WEB_DATA / "shadows" / f"{i}_{day}.json").exists() for i in ids)


def start_if_needed() -> str:
    """수집기에서 호출. 필요하면 백그라운드로 시작하고 상태 문자열을 돌려준다."""
    day = today()
    if ready(day):
        return "ready"
    if LOCK.exists():
        return "running"
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(day, encoding="utf-8")
    log = open(ROOT / "data" / "live" / "daily_shadows.log", "a", encoding="utf-8")
    subprocess.Popen([sys.executable, "-m", "scripts.live.daily_shadows"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                     env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return "started"


def cleanup(day: str):
    for d in (WEB_DATA / "shadows", WEB_DATA / "comfort"):
        for p in d.glob("*_20??-??-??*"):
            if day not in p.name:
                p.unlink()


def main():
    day = today()
    try:
        py = sys.executable
        subprocess.run([py, "-m", "scripts.shadows.build_aoi_shadows", "--dates", day], cwd=ROOT, check=True)
        subprocess.run([py, "-m", "scripts.shadows.compact"], cwd=ROOT, check=True)
        subprocess.run([py, "-m", "scripts.comfort.aoi_utci"], cwd=ROOT, check=True)
        cleanup(day)
        print("daily shadows done", day, flush=True)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
