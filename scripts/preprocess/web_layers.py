"""웹 표시용 보조 레이어: OSM 공원 폴리곤, OSM 수목 점(위치만), 시범 구역 경계."""
from __future__ import annotations

import json

import geopandas as gpd
from shapely.geometry import box

from scripts.common import PROCESSED, RAW, ROOT, WEB_DATA, WORK_CRS, register_dataset

AOIS = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))


def main():
    city = gpd.read_file(PROCESSED / "boundaries" / "daegu_city_5179.gpkg")
    parks = gpd.read_file(RAW / "osm" / "daegu_parks.gpkg").to_crs(WORK_CRS)
    parks = parks[parks.intersects(city.geometry.iloc[0])].copy()
    parks["area_m2"] = parks.area.round()
    parks["geometry"] = parks.geometry.simplify(3)
    parks.to_crs("EPSG:4326")[["osm_id", "name", "area_m2", "geometry"]].to_file(
        WEB_DATA / "parks.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

    trees = gpd.read_file(RAW / "osm" / "daegu_trees_all.gpkg").to_crs(WORK_CRS)
    trees = trees[trees.within(city.geometry.iloc[0])]
    for c in ("species", "genus", "height:tree", "diameter_crown"):
        if c not in trees:
            trees[c] = None
    t = trees.to_crs("EPSG:4326")[["osm_id", "species", "genus", "height:tree", "diameter_crown", "geometry"]]
    t.to_file(WEB_DATA / "trees_osm.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)
    n_h = int(t["height:tree"].notna().sum())
    n_c = int(t["diameter_crown"].notna().sum())

    feats = [{"id": a["id"], "name": a["name"], "geometry": box(*a["bbox"])} for a in AOIS["aois"]]
    gpd.GeoDataFrame(feats, crs="EPSG:4326").to_file(WEB_DATA / "aois.geojson", driver="GeoJSON")

    register_dataset(
        "D07_trees",
        name="가로수 위치(임시: OSM natural=tree) — 산림청 가로수 현황 적용 대기",
        provider="OpenStreetMap contributors",
        source_url="https://www.data.go.kr/data/15120900/fileData.do",
        license="OSM ODbL 1.0 (산림청 자료 확보 시 공공누리 조건 적용)",
        crs="EPSG:4326",
        row_count={"trees": int(len(t)), "with_height": n_h, "with_crown": n_c},
        quality_note=("산림청 가로수 CSV는 공공데이터포털 로그인 후 다운로드 필요. OSM 수목점은 대구 전역 극소수로 "
                      "분포 분석에 부적합. 수고·수관폭 보유 거의 없음 → tree_shadow_mode = disabled."),
        status="interim_osm", layer_kind="reference", tree_shadow_mode="disabled")
    register_dataset(
        "D09_parks",
        name="공원 폴리곤(임시: OSM leisure=park) — 대구 도시공원 공간정보 적용 대기",
        provider="OpenStreetMap contributors",
        source_url="https://www.data.go.kr/data/15117091/fileData.do",
        license="OSM ODbL 1.0", crs="EPSG:4326", row_count=int(len(parks)),
        quality_note="OSM 공원 경계는 공식 도시공원 결정 구역과 다를 수 있음.",
        status="interim_osm", layer_kind="reference")
    print("parks", len(parks), "trees", len(t), "with height", n_h, "crown", n_c)


if __name__ == "__main__":
    main()
