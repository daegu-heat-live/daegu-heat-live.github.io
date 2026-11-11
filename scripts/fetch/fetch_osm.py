"""D13 OpenStreetMap — 시범 구역 건물 윤곽·도로·수목 점, 대구 전역 공원·건물 윤곽.

Overpass API 사용(소량·저빈도 요청, User-Agent 명시). © OpenStreetMap contributors, ODbL 1.0.
OSM 건물 높이는 대부분 비어 있으므로 **건물 높이의 1차 원본이 아니다** (preprocess/buildings.py 참조).
"""
from __future__ import annotations

import json
import time

import geopandas as gpd
import requests
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import linemerge, polygonize, unary_union

from scripts.common import RAW, ROOT, USER_AGENT, register_dataset

OVERPASS = "https://overpass-api.de/api/interpreter"
DAEGU_BBOX = (35.56, 128.34, 36.33, 128.79)  # s,w,n,e (군위 포함)


def overpass(q: str, cache_name: str) -> dict:
    p = RAW / "osm" / f"{cache_name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    for attempt in range(4):
        r = requests.post(OVERPASS, data={"data": q}, headers={"User-Agent": USER_AGENT}, timeout=600)
        if r.status_code == 200:
            p.write_text(r.text, encoding="utf-8")
            return r.json()
        time.sleep(20 * (attempt + 1))
    r.raise_for_status()


def _way_geom(el):
    return [(n["lon"], n["lat"]) for n in el.get("geometry", [])]


def to_gdf(data: dict, kind: str) -> gpd.GeoDataFrame:
    rows = []
    for el in data["elements"]:
        tags = el.get("tags", {})
        g = None
        if el["type"] == "node":
            g = Point(el["lon"], el["lat"])
        elif el["type"] == "way":
            cs = _way_geom(el)
            if len(cs) < 2:
                continue
            if kind == "area" and len(cs) >= 4 and cs[0] == cs[-1]:
                g = Polygon(cs)
            elif kind == "line":
                g = LineString(cs)
        elif el["type"] == "relation" and kind == "area":
            outers = [LineString(_way_geom(m)) for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
            inners = [LineString(_way_geom(m)) for m in el.get("members", []) if m.get("role") == "inner" and m.get("geometry")]
            if not outers:
                continue
            outer = unary_union(list(polygonize(linemerge(outers))))
            if inners:
                outer = outer.difference(unary_union(list(polygonize(linemerge(inners)))))
            g = outer
        if g is None or g.is_empty:
            continue
        rows.append({"osm_id": f"{el['type'][0]}{el['id']}", **{k: tags.get(k) for k in KEEP_TAGS}, "geometry": g})
    if not rows:
        return gpd.GeoDataFrame({"osm_id": []}, geometry=gpd.GeoSeries([], crs="EPSG:4326"))
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


KEEP_TAGS = ["building", "name", "height", "building:levels", "highway", "footway", "sidewalk", "natural",
             "species", "genus", "leisure", "landuse", "circumference", "height:tree", "diameter_crown"]


def main() -> None:
    aois = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))
    buf_deg = 0.004  # 그림자 유입 여유(약 350 m)
    out = RAW / "osm"
    counts = {}
    for a in aois["aois"]:
        w, s, e, n = a["bbox"]
        bb = f"{s - buf_deg},{w - buf_deg},{n + buf_deg},{e + buf_deg}"
        b = to_gdf(overpass(f'[out:json][timeout:180];(way["building"]({bb});relation["building"]({bb}););out geom;',
                            f"{a['id']}_buildings"), "area")
        r = to_gdf(overpass(f'[out:json][timeout:180];way["highway"]({bb});out geom;', f"{a['id']}_roads"), "line")
        t = to_gdf(overpass(f'[out:json][timeout:180];node["natural"="tree"]({bb});out;', f"{a['id']}_trees"), "point")
        b.to_file(out / f"{a['id']}_buildings.gpkg", driver="GPKG")
        r.to_file(out / f"{a['id']}_roads.gpkg", driver="GPKG")
        if len(t):
            t.to_file(out / f"{a['id']}_trees.gpkg", driver="GPKG")
        counts[a["id"]] = {"buildings": len(b), "roads": len(r), "trees": len(t)}
        print(a["id"], counts[a["id"]])

    s, w, n, e = DAEGU_BBOX
    bb = f"{s},{w},{n},{e}"
    parks = to_gdf(overpass(f'[out:json][timeout:300];(way["leisure"="park"]({bb});relation["leisure"="park"]({bb}););out geom;',
                            "daegu_parks"), "area")
    parks.to_file(out / "daegu_parks.gpkg", driver="GPKG")
    bld_all = to_gdf(overpass(f'[out:json][timeout:600][maxsize:1073741824];(way["building"]({bb}););out geom;',
                              "daegu_buildings_all"), "area")
    bld_all.to_file(out / "daegu_buildings_all.gpkg", driver="GPKG")
    trees_all = to_gdf(overpass(f'[out:json][timeout:300];node["natural"="tree"]({bb});out;', "daegu_trees_all"), "point")
    trees_all.to_file(out / "daegu_trees_all.gpkg", driver="GPKG")
    counts["daegu"] = {"parks": len(parks), "buildings": len(bld_all), "trees": len(trees_all)}
    print("daegu", counts["daegu"])

    register_dataset(
        "D13_osm",
        name="OpenStreetMap 건물 윤곽·도로·수목점·공원",
        provider="OpenStreetMap contributors (Overpass API)",
        source_url="https://www.openstreetmap.org/",
        license="ODbL 1.0 — 출처표시 ‘© OpenStreetMap contributors’ 및 동일조건 공유 의무",
        crs="EPSG:4326",
        fields=KEEP_TAGS,
        row_count=counts,
        quality_note=("자원봉사 기반으로 대구 건물 수록이 불완전(전역 약 5.2만 동). 높이·층수 태그 보유율 낮음. "
                      "수목 점은 극소수. 건물 높이·가로수의 공식 원본 대체 아님."),
        version=time.strftime("%Y-%m-%d"),
        status="ok",
        layer_kind="reference",
    )


if __name__ == "__main__":
    main()
