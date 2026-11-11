"""시범 구역 도로 완충영역(보행공간 대리지표) 폴리곤을 웹용으로 내보낸다."""
from __future__ import annotations

import json

import geopandas as gpd
import shapely

from scripts.common import PROCESSED, ROOT, WEB_DATA, WORK_CRS
from scripts.preprocess.buildings import aoi_polys
from scripts.shadows.build_aoi_shadows import road_area
from scripts.shadows.engine import GRID_M


def main():
    cfg = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))
    for a in cfg["aois"]:
        aoi, _ = aoi_polys(a)
        b = gpd.read_file(PROCESSED / "buildings" / f"{a['id']}_buildings.gpkg")
        fp = shapely.unary_union(b.geometry.values, grid_size=GRID_M)
        roads, n = road_area(a["id"], aoi, fp)
        g = gpd.GeoDataFrame({"kind": ["road_buffer_proxy"]}, geometry=[roads.simplify(0.3)], crs=WORK_CRS).to_crs("EPSG:4326")
        g.to_file(WEB_DATA / "shadows" / f"{a['id']}_roads.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)
        print(a["id"], n, round(roads.area))


if __name__ == "__main__":
    main()
