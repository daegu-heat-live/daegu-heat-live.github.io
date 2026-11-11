"""D04 기상 관측 수집 — NOAA ISD(Global Hourly) 경유 대구 관측소 시간별 자료.

기상청 ASOS OpenAPI(D04 원 경로)는 인증키가 필요하다. 키가 없을 때의 대체 경로로
WMO 국제교환(SYNOP/METAR)된 기상청 관측을 NOAA NCEI ISD에서 받는다.
  - 47143 : 대구(기상청 ASOS 143) SYNOP
  - 47142 : 대구공항(RKTN) METAR
`KMA_API_KEY`가 .env 에 있으면 scripts/fetch/fetch_kma_asos.py 로 원 경로를 사용(후속).

ISD 품질코드: 1/5 = 검사 통과, 0/4 = 미검사, 2/3/6/7 = 의심/오류, 9 = 결측.
본 스크립트는 {0,1,4,5}만 채택하고 나머지는 결측 처리한다.
습도는 ISD에 직접 없으므로 기온·이슬점에서 Magnus 식으로 **계산**한다(derived 표기).
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import requests

from scripts.common import PROCESSED, RAW, USER_AGENT, WEB_DATA, register_dataset, write_json

STATIONS = {
    "47143099999": {"id": "47143", "name": "대구(ASOS 143)", "type": "SYNOP"},
    "47142099999": {"id": "47142", "name": "대구공항(RKTN)", "type": "METAR"},
}
YEARS = [2023, 2024, 2025]
BASE = "https://noaa-global-hourly-pds.s3.amazonaws.com/{year}/{st}.csv"
GOOD = set("0145")


def _val(series: pd.Series, idx: int, scale: float, missing: str) -> pd.Series:
    parts = series.fillna("").str.split(",", expand=True)
    raw = parts[idx]
    q = parts[idx + 1] if idx + 1 in parts.columns else pd.Series("9", index=series.index)
    v = pd.to_numeric(raw, errors="coerce")
    v[(raw == missing) | (~q.isin(GOOD))] = np.nan
    return v / scale


def parse(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "observed_at_utc": pd.to_datetime(df["DATE"], utc=True),
        "report_type": df["REPORT_TYPE"].str.strip(),
        "lat": df["LATITUDE"].astype(float),
        "lon": df["LONGITUDE"].astype(float),
    })
    out["air_temp_c"] = _val(df["TMP"], 0, 10, "+9999")
    out["dewpoint_c"] = _val(df["DEW"], 0, 10, "+9999")
    w = df["WND"].fillna("").str.split(",", expand=True)
    wd = pd.to_numeric(w[0], errors="coerce")
    wd[(w[0] == "999") | (~w[1].isin(GOOD))] = np.nan
    ws = pd.to_numeric(w[3], errors="coerce") / 10
    ws[(w[3] == "9999") | (~w[4].isin(GOOD))] = np.nan
    out["wind_direction_deg"] = wd
    out["wind_speed_ms"] = ws
    # Magnus (Alduchov & Eskridge 1996)
    a, b = 17.625, 243.04
    t, td = out["air_temp_c"], out["dewpoint_c"]
    out["humidity_pct_derived"] = (100 * np.exp(a * td / (b + td)) / np.exp(a * t / (b + t))).clip(0, 100)
    out["observed_at_kst"] = out["observed_at_utc"].dt.tz_convert("Asia/Seoul")
    return out


def main() -> None:
    frames = []
    for st, meta in STATIONS.items():
        for y in YEARS:
            p = RAW / "weather_isd" / f"{y}_{st}.csv"
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                r = requests.get(BASE.format(year=y, st=st), headers={"User-Agent": USER_AGENT}, timeout=120)
                if r.status_code != 200:
                    print("missing", y, st, r.status_code)
                    continue
                p.write_bytes(r.content)
            df = pd.read_csv(p, dtype=str)
            d = parse(df)
            d["station_id"] = meta["id"]
            d["station_name"] = meta["name"]
            frames.append(d)
    obs = pd.concat(frames, ignore_index=True)
    # 같은 시각 중복 보고(SYNOP+METAR 특보 등)는 정시값 우선, 시간 단위로 정규화
    obs["hour_kst"] = obs["observed_at_kst"].dt.floor("h")
    obs = obs.sort_values(["station_id", "hour_kst", "observed_at_kst"])
    obs["is_top"] = obs["observed_at_kst"].dt.minute == 0
    hourly = (obs.sort_values("is_top", ascending=False)
                 .groupby(["station_id", "hour_kst"], as_index=False).first())
    hourly = hourly.sort_values(["station_id", "hour_kst"])
    out = PROCESSED / "weather"
    out.mkdir(parents=True, exist_ok=True)
    cols = ["station_id", "station_name", "hour_kst", "observed_at_utc", "report_type", "air_temp_c",
            "dewpoint_c", "humidity_pct_derived", "wind_speed_ms", "wind_direction_deg", "lat", "lon"]
    hourly[cols].to_csv(out / "daegu_isd_hourly.csv", index=False, encoding="utf-8-sig")

    # ---- 웹용: 여름(6~8월) 시간별 + 일별 요약 ----
    stations_web, nulls = [], {}
    for sid, g in hourly.groupby("station_id"):
        g = g.set_index("hour_kst")
        meta = next(m for m in STATIONS.values() if m["id"] == sid)
        lat, lon = float(g["lat"].mode()[0]), float(g["lon"].mode()[0])
        series = {}
        for y in YEARS:
            s = g[(g.index.year == y) & (g.index.month.isin([6, 7, 8]))]
            if s.empty:
                continue
            # 6/1~8/31 전체 시간축에 맞춰 결측을 명시적으로 null
            idx = pd.date_range(f"{y}-06-01 00:00", f"{y}-08-31 23:00", freq="h", tz="Asia/Seoul")
            s = s.reindex(idx)
            def arr(c, nd=1):
                return [None if pd.isna(v) else round(float(v), nd) for v in s[c]]
            series[str(y)] = {
                "start_kst": idx[0].isoformat(),
                "step_h": 1,
                "air_temp_c": arr("air_temp_c"),
                "humidity_pct_derived": arr("humidity_pct_derived", 0),
                "wind_speed_ms": arr("wind_speed_ms"),
                "n_expected": len(idx),
                "n_temp_valid": int(s["air_temp_c"].notna().sum()),
            }
            nulls[f"{sid}_{y}"] = round(1 - series[str(y)]["n_temp_valid"] / len(idx), 4)
        stations_web.append({"station_id": sid, "station_name": meta["name"], "report": meta["type"],
                             "lat": lat, "lon": lon, "summer": series})
    write_json(WEB_DATA / "weather_summer.json", {
        "kind": "observed", "source": "NOAA NCEI ISD Global Hourly (WMO 교환 기상청 관측)",
        "timezone": "Asia/Seoul", "humidity_note": "습도는 기온·이슬점으로 계산한 파생값",
        "stations": stations_web})

    register_dataset(
        "D04_weather",
        name="대구 시간별 기상관측(기온·이슬점·풍향풍속)",
        provider="기상청 관측(WMO 국제교환) — NOAA NCEI ISD Global Hourly 경유",
        source_url="https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database",
        download_pattern=BASE,
        license="NOAA NCEI 공개자료(미국 정부 저작물, 이용 제한 없음). 원 관측: 기상청",
        observed_at=f"{hourly.hour_kst.min().isoformat()} ~ {hourly.hour_kst.max().isoformat()}",
        crs="EPSG:4326 (관측소 점)",
        fields=cols,
        row_count=int(len(hourly)),
        null_rate=nulls,
        quality_note=("ISD 품질코드 0/1/4/5만 채택. 습도는 파생값. ISD 관측소 좌표는 메타데이터 기준이며 "
                      "기상청 지점정보의 현재 좌표와 다를 수 있음. 기상청 ASOS OpenAPI(인증키 필요)로 교체 가능."),
        version="ISD v1 (S3 noaa-global-hourly-pds)",
        status="ok",
        layer_kind="observed",
    )
    print(hourly.groupby("station_id").agg(n=("air_temp_c", "size"), valid=("air_temp_c", "count"),
                                            first=("hour_kst", "min"), last=("hour_kst", "max")))
    print("summer temp null rates:", nulls)


if __name__ == "__main__":
    main()
