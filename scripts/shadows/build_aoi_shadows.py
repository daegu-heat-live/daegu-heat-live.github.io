"""시범 구역 시각별 건물 예상 그림자 사전 계산 + 그늘 지표.

출력(web/data/shadows/):
  {aoi}_{date}.json    : 시각별 그림자 합집합(GeoJSON) + 태양 위치 + 지표
  {aoi}_{date}_exposure.png : 09~18시 누적 직접일조 노출시간(모의) 래스터
  shadow_summary.json  : AOI·날짜별 지표 곡선 요약, 정의, 모델 버전

지표 정의
  area_basis_m2        = AOI 면적 − 모든 건물 바닥(높이 유무 무관)        → ‘지면’ 기준
  shadow_area_m2       = (높이 확인 건물 그림자 합집합 − 모든 건물 바닥) ∩ AOI
  shadow_fraction_pct  = shadow_area_m2 / area_basis_m2 × 100   (건물 내부 제외, 사유지·수면 포함)
  road_shadow_pct      = 그림자 ∩ 도로 완충영역 / 도로 완충영역 × 100  (보행공간 **대리지표**)
  exposure_h           = 09:00~17:30 30분 표본마다 비그림자면 +0.5 h (최대 9 h, 모의값)
높이 미확인 건물은 그림자를 만들지 않으므로 실제보다 그늘이 **과소** 추정된다(하한값).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import shapely
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import mapping

from scripts.common import PROCESSED, RAW, ROOT, WEB_DATA, WORK_CRS, register_dataset, write_json
from scripts.preprocess.buildings import aoi_polys
from scripts.raster.rasterutil import export_web_png
from scripts.shadows.engine import (GRID_M, LOW_SUN_DEG, ground_shadow_union, polygonal, shadow_vector,
                                    shadows_for_buildings)
from scripts.shadows.solar import sun_position

KST = ZoneInfo("Asia/Seoul")
MODEL_VERSION = "shapely-flat-v1"
CFG = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))
EXPO_RES = 2.0
# 도로 중심선 → 반폭(m) 가정. 보행공간 실측 폴리곤이 아니므로 대리지표.
ROAD_HALF_WIDTH = {"primary": 10, "secondary": 8, "tertiary": 6, "trunk": 10, "residential": 3, "unclassified": 3,
                   "service": 2.5, "living_street": 3, "pedestrian": 4, "footway": 1.5, "path": 1.5, "steps": 1.5,
                   "cycleway": 1.5}
EXPO_STOPS = ["#104281", "#256abf", "#5598e7", "#9ec5f4", "#f0efec", "#fdd49e", "#fc8d59", "#d7301f", "#7f0000"]


def times(day: str, w: dict):
    d = datetime.fromisoformat(day).replace(tzinfo=KST)
    h0, m0 = map(int, w["start"].split(":"))
    h1, m1 = map(int, w["end"].split(":"))
    t, end = d.replace(hour=h0, minute=m0), d.replace(hour=h1, minute=m1)
    while t <= end:
        yield t
        t += timedelta(minutes=w["step_min"])


def road_area(aoi_id, aoi, footprints_union):
    r = gpd.read_file(RAW / "osm" / f"{aoi_id}_roads.gpkg").to_crs(WORK_CRS)
    r = r[r["highway"].isin(ROAD_HALF_WIDTH)]
    r = r[r.intersects(aoi)]
    buf = shapely.unary_union([g.buffer(ROAD_HALF_WIDTH[h], cap_style="flat") for g, h in zip(r.geometry, r["highway"])])
    return polygonal(buf.intersection(aoi).difference(footprints_union)), len(r)


def to_wgs(geom):
    g = gpd.GeoSeries([geom], crs=WORK_CRS).to_crs("EPSG:4326").iloc[0]
    g = shapely.set_precision(g, 1e-6)
    return mapping(polygonal(g, 0))


import sys

EXTRA = "--dates" in sys.argv
DATES = sys.argv[sys.argv.index("--dates") + 1].split(",") if EXTRA else CFG["shadow_dates"]
PREV = json.loads((WEB_DATA / "shadows" / "shadow_summary.json").read_text(encoding="utf-8"))     if EXTRA and (WEB_DATA / "shadows" / "shadow_summary.json").exists() else {}


def main() -> None:
    out = WEB_DATA / "shadows"
    out.mkdir(parents=True, exist_ok=True)
    summary = {"model_version": MODEL_VERSION, "kind": "simulation", "aois": [],
               "definitions": __doc__, "low_sun_deg": LOW_SUN_DEG}
    for a in CFG["aois"]:
        aoi, ext = aoi_polys(a)
        b = gpd.read_file(PROCESSED / "buildings" / f"{a['id']}_buildings.gpkg")
        fp_all = shapely.unary_union(b.geometry.values, grid_size=GRID_M)
        hb = b[b["height_m"].notna()]
        basis = polygonal(aoi.difference(fp_all))
        roads, n_roads = road_area(a["id"], aoi, fp_all)
        lon, lat = gpd.GeoSeries([aoi.centroid], crs=WORK_CRS).to_crs("EPSG:4326").iloc[0].coords[0]
        miss = b[b["in_aoi"] & b["height_m"].isna()]
        a_sum = {"id": a["id"], "name": a["name"], "bbox": a["bbox"], "center": [round(lon, 6), round(lat, 6)],
                 "aoi_area_m2": round(aoi.area), "area_basis_m2": round(basis.area),
                 "road_proxy_area_m2": round(roads.area), "n_road_segments": n_roads,
                 "n_buildings_used": int((hb["in_aoi"]).sum()), "n_buildings_used_with_buffer": len(hb),
                 "n_buildings_missing_height": int(len(miss)),
                 "missing_footprint_m2": round(float(miss.area.sum())), "dates": []}
        # 노출시간 격자(EPSG:5179, 2 m)
        minx, miny, maxx, maxy = aoi.bounds
        W, H = int(np.ceil((maxx - minx) / EXPO_RES)), int(np.ceil((maxy - miny) / EXPO_RES))
        tr = from_origin(minx, maxy, EXPO_RES, EXPO_RES)
        ground = rasterize([(basis, 1)], out_shape=(H, W), transform=tr, fill=0, dtype="uint8").astype(bool)

        for day in DATES:
            frames, curve = [], []
            expo_times = {t.strftime("%H:%M") for t in times(day, CFG["exposure_window"])}
            expo_times.discard(CFG["exposure_window"]["end"])  # 표본 = 구간 시작 시각
            lit = np.zeros((H, W), dtype="float32")
            for t in times(day, CFG["time_window"]):
                sp = sun_position(t, lat, lon)
                sv = shadow_vector(sp.elevation_deg, sp.azimuth_deg)
                fr = {"time": t.strftime("%H:%M"), "sun_elevation_deg": round(sp.elevation_deg, 2),
                      "sun_azimuth_deg": round(sp.azimuth_deg, 2), "is_night": sv.is_night, "low_sun": sv.low_sun}
                if sv.is_night:
                    fr.update(shadow_area_m2=None, shadow_fraction_pct=None, road_shadow_pct=None, geometry=None)
                else:
                    sh = shadows_for_buildings(hb.geometry.values, hb["height_m"].values, sv)
                    u = ground_shadow_union(sh, fp_all)
                    u = polygonal(shapely.intersection(u, aoi, grid_size=GRID_M))
                    fr.update(shadow_area_m2=round(u.area, 1),
                              shadow_fraction_pct=round(100 * u.area / basis.area, 2),
                              road_shadow_pct=round(100 * u.intersection(roads).area / roads.area, 2) if roads.area else None,
                              shadow_length_per_m=round(sv.length_per_m, 3),
                              geometry=to_wgs(u.simplify(0.2)))
                    if fr["time"] in expo_times:
                        sh_r = rasterize([(u, 1)], out_shape=(H, W), transform=tr, fill=0, dtype="uint8") if not u.is_empty \
                            else np.zeros((H, W), "uint8")
                        lit += (sh_r == 0) * 0.5
                frames.append(fr)
                curve.append({k: fr[k] for k in ("time", "shadow_fraction_pct", "road_shadow_pct", "sun_elevation_deg")})
            write_json(out / f"{a['id']}_{day}.json", {
                "aoi": a["id"], "date": day, "timezone": "Asia/Seoul", "kind": "simulation",
                "model_version": MODEL_VERSION, "frames": frames})
            lit[~ground] = np.nan
            vals = lit[ground]
            corners = export_web_png(lit, tr, lambda x: _expo_rgba(x), out / f"{a['id']}_{day}_exposure.png",
                                     res_m=EXPO_RES, src_crs=WORK_CRS)
            hist = np.histogram(vals, bins=np.arange(-0.25, 9.5, 0.5))[0].tolist()  # 0,0.5,…,9 h 중심
            a_sum["dates"].append({
                "date": day, "curve": curve, "exposure_png": f"shadows/{a['id']}_{day}_exposure.png",
                "exposure_corners": corners,
                "exposure_stats": {"mean_h": round(float(vals.mean()), 2), "median_h": float(np.median(vals)),
                                   "pct_ge_6h": round(100 * float((vals >= 6).mean()), 1),
                                   "pct_le_3h": round(100 * float((vals <= 3).mean()), 1),
                                   "hist_bins_h": np.arange(0, 9.5, 0.5).tolist(), "hist_counts": hist},
                "max_fraction_pct": max(c["shadow_fraction_pct"] or 0 for c in curve),
            })
            print(a["id"], day, "frames", len(frames), "mean exposure", round(float(vals.mean()), 2))
        if EXTRA:  # 기존 날짜 결과는 유지하고 새 날짜만 덧붙임/교체
            old = next((x for x in PREV.get("aois", []) if x["id"] == a["id"]), None)
            if old:
                keep = [d for d in old["dates"] if d["date"] not in DATES]
                a_sum["dates"] = sorted(keep + a_sum["dates"], key=lambda d: d["date"])
        summary["aois"].append(a_sum)
    summary["exposure_window"] = CFG["exposure_window"]
    summary["time_window"] = CFG["time_window"]
    summary["exposure_legend"] = {"stops": EXPO_STOPS, "range": [0, 9], "unit": "시간(h)"}
    summary["road_half_width_m"] = ROAD_HALF_WIDTH
    q = json.loads((PROCESSED / "buildings" / "building_quality.json").read_text(encoding="utf-8"))
    summary["building_quality"] = q
    write_json(out / "shadow_summary.json", summary)
    register_dataset(
        "S01_building_shadows",
        name="시범 구역 건물 예상 그림자(기하학적 시뮬레이션)",
        provider="본 프로젝트 계산 (NOAA 태양위치 자체 구현 + Shapely)",
        source_url="scripts/shadows/build_aoi_shadows.py",
        license="본 프로젝트 산출물(입력 데이터 라이선스 승계)",
        valid_period=CFG["shadow_dates"],
        crs=f"계산 {WORK_CRS}, 배포 EPSG:4326",
        row_count={s["id"]: len(s["dates"]) for s in summary["aois"]},
        quality_note="평탄 지면·불투명 각기둥 가정. 높이 미확인 건물 제외로 그늘 과소 추정(하한).",
        version=MODEL_VERSION,
        status="ok",
        layer_kind="simulation",
    )


def _expo_rgba(x):
    from scripts.raster import colormaps as cm
    return cm.apply(x, EXPO_STOPS, (0, 9), alpha=200)


if __name__ == "__main__":
    main()
