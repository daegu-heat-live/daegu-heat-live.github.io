"""시범 구역 × 날짜 × 시각별 일조/그늘 UTCI(모델) — SHADOW·HISTORY 화면용.

기상 입력(구역 하나에 하나의 값을 동일 적용 — 공간 기상 차이는 모델링하지 않음):
  - 과거 날짜(2025 등): 대구 ASOS 143(NOAA ISD) 정시 기온·이슬점 기반 습도·풍속 + **관측 전운량(GF1, oktas)**
      프레임 시각과 가장 가까운 정시(±30분) 기상, 운량은 ±3시간 내 가장 가까운 관측
  - 오늘 날짜: 수집기 아카이브의 기상청 초단기실황(지난 시각) / 최신 초단기예보(남은 시각),
      운량은 같은 시각을 유효시각으로 하는 가장 최근 초단기예보의 하늘상태(SKY)
그늘 비율(shadow_fraction)은 그림자 엔진 결과를 그대로 쓰고,
면적가중 UTCI = 그늘비율·UTCI_그늘 + (1−그늘비율)·UTCI_일조  (지면 평균의 단순 가중, 모델값)
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timedelta

import pandas as pd

from scripts.common import PROCESSED, RAW, ROOT, WEB_DATA, register_dataset, write_json
from scripts.comfort.utci_model import ASSUMPTIONS, MODEL_VERSION, compute
from scripts.live.kma_grid import to_grid
from scripts.live.kma_time import KST

ARCH = ROOT / "data" / "live"


def isd_weather():
    df = pd.read_csv(PROCESSED / "weather" / "daegu_isd_hourly.csv", dtype={"station_id": str})
    df = df[df.station_id == "47143"].copy()
    df["t"] = pd.to_datetime(df["hour_kst"], utc=True).dt.tz_convert("Asia/Seoul")
    met = df.set_index("t")[["air_temp_c", "humidity_pct_derived", "wind_speed_ms"]]
    rows = []
    for f in sorted(glob.glob(str(RAW / "weather_isd" / "*_47143099999.csv"))):
        d = pd.read_csv(f, dtype=str, usecols=lambda c: c in ("DATE", "GF1"))
        if "GF1" not in d:
            continue
        code = d["GF1"].str.split(",").str[0]
        v = pd.to_numeric(code, errors="coerce")
        v = v.where(v <= 9).replace(9, 8)  # 9=하늘 가림 → 8 oktas, 99=결측
        rows.append(pd.DataFrame({"t": pd.to_datetime(d["DATE"]).dt.tz_localize("UTC").dt.tz_convert("Asia/Seoul"), "okta": v}))
    cloud = pd.concat(rows).dropna().set_index("t").sort_index()["okta"]
    cloud = cloud[~cloud.index.duplicated()]
    return met, cloud


def nearest(series_or_df, t, tol):
    idx = series_or_df.index.get_indexer([t], method="nearest")[0]
    if idx < 0:
        return None
    if abs(series_or_df.index[idx] - t) > tol:
        return None
    return series_or_df.iloc[idx]


def today_weather(grid_xy):
    """오늘: {valid_at: (T,RH,WS, sky, pty, source)} 를 실황·예보 아카이브에서 구성."""
    out = {}
    for f in sorted((ARCH / "nowcast").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        g = next((x for x in d["grids"] if (x["nx"], x["ny"]) == grid_xy), None)
        if g:
            out[d["base_at_kst"]] = {"T": g.get("T1H"), "RH": g.get("REH"), "WS": g.get("WSD"), "PTY": g.get("PTY"),
                                     "src": f"기상청 초단기실황 {d['base_at_kst'][11:16]}"}
    sky = {}
    latest_fc = None
    for f in sorted((ARCH / "forecast").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        latest_fc = d
        g = next((x for x in d["grids"] if (x["nx"], x["ny"]) == grid_xy), None)
        if not g:
            continue
        for k, va in enumerate(d["valid_at_kst"]):
            sky[va] = g["series"]["SKY"][k]  # 뒤 발표가 덮어씀 = 가장 최근 발표값
    if latest_fc:
        g = next((x for x in latest_fc["grids"] if (x["nx"], x["ny"]) == grid_xy), None)
        for k, va in enumerate(latest_fc["valid_at_kst"]):
            if va not in out and g:
                s = g["series"]
                out[va] = {"T": s["T1H"][k], "RH": s["REH"][k], "WS": s["WSD"][k], "PTY": s["PTY"][k],
                           "src": f"기상청 초단기예보(발표 {latest_fc['issued_at_kst'][11:16]})", "forecast": True}
    for va, w in out.items():
        w["SKY"] = sky.get(va)
    return out


import sys

ONLY_TODAY = "--all-dates" not in sys.argv  # 화면은 '오늘'만 사용


def main():
    summ = json.loads((WEB_DATA / "shadows" / "shadow_summary.json").read_text(encoding="utf-8"))
    met, cloud = (None, None) if ONLY_TODAY else isd_weather()  # 과거 재현(--all-dates) 때만 관측 기록 사용
    today = datetime.now(KST).date().isoformat()
    grids = json.loads((WEB_DATA / "live" / "grids.json").read_text(encoding="utf-8"))["grids"] \
        if (WEB_DATA / "live" / "grids.json").exists() else []
    index = {}
    for a in summ["aois"]:
        lon, lat = a["center"]
        gxy = to_grid(lat, lon)
        if grids and gxy not in {(g["nx"], g["ny"]) for g in grids}:  # 수집 격자 중 가장 가까운 것
            gxy = min(((g["nx"], g["ny"]) for g in grids), key=lambda xy: (xy[0] - gxy[0]) ** 2 + (xy[1] - gxy[1]) ** 2)
        tw = today_weather(gxy) if any(d["date"] == today for d in a["dates"]) else {}
        for d in a["dates"]:
            if ONLY_TODAY and d["date"] != today:
                continue
            res = []
            for c in d["curve"]:
                t = datetime.fromisoformat(f"{d['date']}T{c['time']}:00").replace(tzinfo=KST)
                th = t.replace(minute=0) + (timedelta(hours=1) if t.minute >= 30 else timedelta())
                if d["date"] == today:
                    w = tw.get(th.isoformat())
                    if w is None:
                        r = {"valid_at_kst": t.isoformat(), "quality_flag": "insufficient_data", "flags": ["해당 시각 실황·예보 없음"],
                             "sun": None, "shade": None, "delta_utci": None, "inputs": {}}
                    else:
                        r = compute(w["T"], w["RH"], w["WS"], t, lat, lon, sky=w.get("SKY"), pty=w.get("PTY"))
                        r["input_source"] = w["src"]
                        r["provenance_weather"] = "forecast" if w.get("forecast") else "nowcast"
                else:
                    m = nearest(met, pd.Timestamp(th), pd.Timedelta(minutes=30))
                    ok = nearest(cloud, pd.Timestamp(t), pd.Timedelta(hours=3))
                    if m is None:
                        r = {"valid_at_kst": t.isoformat(), "quality_flag": "insufficient_data", "flags": ["관측 없음"],
                             "sun": None, "shade": None, "delta_utci": None, "inputs": {}}
                    else:
                        T, RH, WS = (None if pd.isna(m[k]) else float(m[k]) for k in ("air_temp_c", "humidity_pct_derived", "wind_speed_ms"))
                        r = compute(T, RH, WS, t, lat, lon, okta=None if ok is None else float(ok))
                        r["input_source"] = f"대구 ASOS 143(NOAA ISD) {th.strftime('%H:%M')} 관측, 운량 관측"
                        r["provenance_weather"] = "observed"
                f = c.get("shadow_fraction_pct")
                r["shadow_fraction_pct"] = f
                su, sh = (r.get("sun") or {}).get("utci_c"), (r.get("shade") or {}).get("utci_c")
                r["area_weighted_utci"] = round(f / 100 * sh + (1 - f / 100) * su, 1) if None not in (f, su, sh) else None
                r["time"] = c["time"]
                res.append(r)
            key = f"{a['id']}_{d['date']}"
            write_json(WEB_DATA / "comfort" / f"{key}.json", {
                "aoi": a["id"], "date": d["date"], "model_version": MODEL_VERSION, "provenance": "simulated",
                "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"), "weather_grid": list(gxy),
                "assumptions": ASSUMPTIONS, "frames": res})
            day = [x for x in res if x.get("delta_utci") is not None and (x["inputs"].get("sun_elevation_deg") or 0) > 0]
            index[key] = {"max_delta": max((x["delta_utci"] for x in day), default=None),
                          "n_ok": sum(1 for x in res if x.get("quality_flag") == "estimated"), "n": len(res)}
            print(key, index[key])
    write_json(WEB_DATA / "comfort" / "index.json", {"model_version": MODEL_VERSION, "assumptions": ASSUMPTIONS, "items": index}, compact=False)
    register_dataset("M01_utci", name="시범구역 일조/그늘 UTCI(물리 모델 추정)", provider="본 프로젝트 계산",
                     source_url="scripts/comfort/utci_model.py", license="본 프로젝트 산출물(입력 데이터 라이선스 승계)",
                     crs="-", quality_note="모의값. MRT·UTCI 실측 검증 자료 없음(미검증 추정). 가정: " + " / ".join(ASSUMPTIONS),
                     version=MODEL_VERSION, status="ok", layer_kind="simulation")


if __name__ == "__main__":
    main()
