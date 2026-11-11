"""HISTORY — 연도별 폭염일·열대야 일수와 일별 최고/최저 (관측소 시간별 자료 기반 근사).

정의(기상청 용어):
  폭염일 : 일 최고기온 ≥ 33 °C
  열대야 : 18:01~익일 09:00 최저기온 ≥ 25 °C (날짜는 저녁이 속한 날)
본 집계는 NOAA ISD **정시 관측**만 사용하므로 분 단위 극값을 쓰는 기상청 공식 통계와 다를 수 있다
(최고기온은 과소, 최저기온은 과대 가능). 결측 시간이 많은 날은 판정에서 제외한다:
  낮 판정: 해당 일 24시간 중 ≥ 20시간 관측
  밤 판정: 19:00~09:00 15시간 중 ≥ 13시간 관측
"""
from __future__ import annotations

import pandas as pd

from scripts.common import PROCESSED, WEB_DATA, register_dataset, write_json

HOT, TROP = 33.0, 25.0


def main():
    df = pd.read_csv(PROCESSED / "weather" / "daegu_isd_hourly.csv", dtype={"station_id": str})
    df["t"] = pd.to_datetime(df["hour_kst"], utc=True).dt.tz_convert("Asia/Seoul")
    out = {"kind": "observed", "definitions": __doc__, "stations": []}
    for sid, g in df.groupby("station_id"):
        g = g.set_index("t").sort_index()["air_temp_c"]
        day = g.groupby(g.index.date).agg(["max", "count"])
        day.index = pd.to_datetime(day.index)
        # 밤: 19시~익일 09시 → 18시간 당겨서 날짜 귀속
        night = g[(g.index.hour >= 19) | (g.index.hour <= 9)]
        nkey = (night.index - pd.Timedelta(hours=10)).date
        nt = night.groupby(nkey).agg(["min", "count"])
        nt.index = pd.to_datetime(nt.index)
        daily = pd.DataFrame({"tmax": day["max"].where(day["count"] >= 20),
                              "tmin_night": nt["min"].where(nt["count"] >= 13)})
        years = []
        for y, d in daily.groupby(daily.index.year):
            if d["tmax"].notna().sum() < 60:  # 자료 기간 경계의 잔여 일자(예: 2022-12-31) 제외
                continue
            summer = d[(d.index.month >= 5) & (d.index.month <= 9)]
            years.append({
                "year": int(y),
                "period": f"{d.index.min().date()} ~ {d.index.max().date()}",
                "heat_days": int((d["tmax"] >= HOT).sum()),
                "tropical_nights": int((d["tmin_night"] >= TROP).sum()),
                "days_valid_max": int(d["tmax"].notna().sum()),
                "nights_valid": int(d["tmin_night"].notna().sum()),
                "summer_days_excluded": int(summer["tmax"].isna().sum()),
                "max_tmax": round(float(d["tmax"].max()), 1),
                "first_heat_day": str(d.index[d["tmax"] >= HOT].min().date()) if (d["tmax"] >= HOT).any() else None,
                "last_heat_day": str(d.index[d["tmax"] >= HOT].max().date()) if (d["tmax"] >= HOT).any() else None,
            })
        jja = daily[(daily.index.month >= 6) & (daily.index.month <= 8)]
        out["stations"].append({
            "station_id": sid, "years": years,
            "daily_summer": {"dates": [str(x.date()) for x in jja.index],
                             "tmax": [None if pd.isna(v) else round(v, 1) for v in jja["tmax"]],
                             "tmin_night": [None if pd.isna(v) else round(v, 1) for v in jja["tmin_night"]]},
        })
        print(sid, [(y["year"], y["heat_days"], y["tropical_nights"], y["period"]) for y in years])
    write_json(WEB_DATA / "history" / "heat_days.json", out)
    register_dataset("A02_heat_days", name="연도별 폭염일·열대야(관측소 시간별 자료 근사)",
                     provider="본 프로젝트 집계(원자료 D04)", source_url="scripts/analysis/heat_days.py",
                     license="본 프로젝트 산출물", crs="-", quality_note="정시 관측 기반 근사, 결측일 제외. 기상청 공식 통계와 다를 수 있음. 2025년은 8/25까지.",
                     status="ok", layer_kind="observed")


if __name__ == "__main__":
    main()
