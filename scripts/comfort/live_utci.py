"""지금 — 구·군 대표 격자의 햇볕/그늘 UTCI(모델). 수집기가 매 회 호출.

LIVE   : 최신 초단기실황(기온·습도·풍속) + 같은 시각을 유효시각으로 하는 가장 최근 초단기예보의 하늘상태(SKY)
지점의 실제 그늘 여부는 모르므로 '완전 일조'와 '건물 그늘' 두 조건을 나란히 제시한다(모델값).
"""
from __future__ import annotations

import json
from datetime import datetime

from scripts.common import ROOT, WEB_DATA, write_json
from scripts.comfort.utci_model import ASSUMPTIONS, MODEL_VERSION, compute
from scripts.live.kma_time import KST

ARCH = ROOT / "data" / "live"


def _sky_lookup():
    sky = {}
    for f in sorted((ARCH / "forecast").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for g in d["grids"]:
            for k, va in enumerate(d["valid_at_kst"]):
                sky[(g["nx"], g["ny"], va)] = g["series"]["SKY"][k]
    return sky


def main():
    live = WEB_DATA / "live"
    nc_p, fc_p = live / "nowcast_latest.json", live / "forecast_latest.json"
    if not nc_p.exists():
        return
    nc = json.loads(nc_p.read_text(encoding="utf-8"))
    sky = _sky_lookup()
    t = datetime.fromisoformat(nc["base_at_kst"])
    rows = []
    for g in nc["grids"]:
        s = sky.get((g["nx"], g["ny"], nc["base_at_kst"]))
        r = compute(g.get("T1H"), g.get("REH"), g.get("WSD"), t, g["grid_lat"], g["grid_lon"], sky=s, pty=g.get("PTY"))
        r["gu"], r["nx"], r["ny"] = g["gu"], g["nx"], g["ny"]
        r["cloud_source"] = "초단기예보 SKY(같은 유효시각, 최근 발표)" if s is not None else None
        rows.append(r)
    write_json(WEB_DATA / "comfort" / "live_utci.json", {
        "kind": "simulated", "model_version": MODEL_VERSION, "weather_base_at_kst": nc["base_at_kst"],
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"), "assumptions": ASSUMPTIONS, "grids": rows})


if __name__ == "__main__":
    main()
