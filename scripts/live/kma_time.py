"""기상청 초단기실황·초단기예보 발표(base) 시각 후보 계산.

공식 안내(단기예보 조회서비스 활용가이드) 기준 — 실제 응답으로 재확인할 것:
  - 초단기실황 getUltraSrtNcst : 매시 정시(HH00) 자료, 매시 40분 이후 제공
  - 초단기예보 getUltraSrtFcst : 매시 30분(HH30) 발표, 매시 45분 이후 제공, 6시간 예보
현재 시각으로 바로 base_time 을 만들면 미발행일 수 있으므로, 제공 가능한 최근 발표부터
과거로 몇 개의 후보를 돌려주고 수집기가 순서대로 시도한다(NO_DATA 이면 다음 후보).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
SPEC = {
    "ncst": {"base_minute": 0, "available_after_min": 40},
    "fcst": {"base_minute": 30, "available_after_min": 45},
}


def base_candidates(kind: str, now: datetime, n: int = 3) -> list[datetime]:
    if now.tzinfo is None:
        raise ValueError("timezone-aware datetime 필요")
    s = SPEC[kind]
    now = now.astimezone(KST)
    hour = now.replace(minute=s["base_minute"], second=0, microsecond=0)
    # 이번 시각 발표가 '제공 시각'에 도달했는지
    avail = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=s["available_after_min"])
    if now < avail or hour > now:
        hour -= timedelta(hours=1)
    return [hour - timedelta(hours=i) for i in range(n)]


def fmt(dt: datetime) -> tuple[str, str]:
    dt = dt.astimezone(KST)
    return dt.strftime("%Y%m%d"), dt.strftime("%H%M")
