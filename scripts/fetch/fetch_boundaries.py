"""D06 대구 행정구역 경계 수집.

원본: 통계청 SGIS 행정동 경계를 시점별로 정리한 공개 저장소 vuski/admdongkor
(ver20261001, EPSG:4326 GeoJSON). 대구광역시(군위군 편입 반영)만 추출하고
행정동 → 구·군 단위로 dissolve 한다.
"""
from __future__ import annotations

import geopandas as gpd
import requests

from scripts.common import PROCESSED, RAW, USER_AGENT, WEB_DATA, WORK_CRS, register_dataset

VERSION = "ver20261001"
URL = f"https://raw.githubusercontent.com/vuski/admdongkor/master/{VERSION}/HangJeongDong_{VERSION}.geojson"


def main() -> None:
    raw = RAW / "boundaries" / f"HangJeongDong_{VERSION}.geojson"
    raw.parent.mkdir(parents=True, exist_ok=True)
    if not raw.exists():
        r = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=300)
        r.raise_for_status()
        raw.write_bytes(r.content)

    gdf = gpd.read_file(raw)
    src_crs = str(gdf.crs)
    dong = gdf[gdf["sidonm"] == "대구광역시"].copy()
    assert len(dong) > 100, f"대구 행정동 수가 비정상: {len(dong)}"
    dong["geometry"] = dong.geometry.make_valid()
    dong = dong.to_crs(WORK_CRS)
    dong["area_km2"] = dong.area / 1e6

    gu = dong.dissolve(by=["sgg", "sggnm"], as_index=False)[["sgg", "sggnm", "geometry"]]
    gu["area_km2"] = gu.area / 1e6
    gu["n_dong"] = gu["sgg"].map(dong.groupby("sgg").size())
    city = gu.dissolve()[["geometry"]]
    city["name"] = "대구광역시"

    out = PROCESSED / "boundaries"
    out.mkdir(parents=True, exist_ok=True)
    dong.to_file(out / "daegu_dong_5179.gpkg", driver="GPKG")
    gu.to_file(out / "daegu_gu_5179.gpkg", driver="GPKG")
    city.to_file(out / "daegu_city_5179.gpkg", driver="GPKG")

    # 웹: 단순화(약 20m) 후 WGS84
    for name, g, tol in (("gu", gu, 20), ("dong", dong, 10)):
        w = g.copy()
        w["geometry"] = w.geometry.simplify(tol, preserve_topology=True)
        w = w.to_crs("EPSG:4326")
        keep = [c for c in ("adm_cd2", "adm_nm", "sgg", "sggnm", "area_km2", "n_dong") if c in w.columns]
        w[keep + ["geometry"]].to_file(WEB_DATA / f"boundaries_{name}.geojson", driver="GeoJSON",
                                       COORDINATE_PRECISION=5)

    register_dataset(
        "D06_boundaries",
        name="대구 행정구역 경계(행정동·구군)",
        provider="통계청 SGIS 행정동 경계(시점별 정리: vuski/admdongkor)",
        source_url=URL,
        license="원본: 통계청 SGIS 공공누리; 정리본 저장소의 이용조건을 따름(README 참조)",
        valid_period=VERSION.replace("ver", ""),
        crs=f"원본 {src_crs} → 작업 {WORK_CRS}",
        fields=["adm_cd2", "adm_nm", "sgg", "sggnm"],
        row_count={"dong": int(len(dong)), "gu": int(len(gu))},
        null_rate=0.0,
        quality_note="군위군(2023.7 편입) 포함. 웹용은 형상 단순화(구 20m, 동 10m).",
        version=VERSION,
        status="ok",
        layer_kind="reference",
    )
    print(f"dong={len(dong)} gu={len(gu)} area={gu.area_km2.sum():.1f} km2")
    print(gu[["sggnm", "n_dong", "area_km2"]].to_string(index=False))


if __name__ == "__main__":
    main()
