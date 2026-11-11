"""처음 설치 후 필요한 처리를 순서대로 실행한다.  python -m scripts.run_all

화면('지금')에 필요한 것만: 경계 → OSM(도로·건물 보조) → 건물 높이 → 실시간 수집 1회(오늘 그림자 자동 계산 시작)
오늘 그림자는 백그라운드로 약 30분 걸린다(data/live/daily_shadows.log). 이후에는
  python -m scripts.live.collect --loop 600
을 계속 실행해 두면 10분마다 날씨가, 날짜가 바뀌면 그림자가 자동 갱신된다.
(과거 위성·기상 분석 스크립트는 scripts/raster, scripts/analysis 에 남아 있으나 화면에서는 쓰지 않는다.)
"""
from __future__ import annotations

import importlib
import time

STEPS = [
    "scripts.fetch.fetch_boundaries",
    "scripts.fetch.fetch_osm",
    "scripts.preprocess.buildings",
    "scripts.live.collect",
]


def main() -> None:
    for mod in STEPS:
        t = time.time()
        print(f"
=== {mod} ===", flush=True)
        m = importlib.import_module(mod)
        m.run_once() if mod.endswith("collect") else m.main()
        print(f"--- {mod} 완료 ({time.time() - t:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
