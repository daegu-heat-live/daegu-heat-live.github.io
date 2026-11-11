"""시범 구역 건물 형상 + 높이 결합 및 품질 리포트.

우선순위
 1) 공식: 국토부 GIS건물통합정보 SHP (data/raw/buildings/ 에 V-World에서 받은 대구 파일을 둔다)
    - 높이 필드 값 → height_status = "registry"  (건축물대장 기반 높이)
    - 높이 결측 & 지상층수 있음 → "estimated" (층수×가정 층고)
 2) 임시: OpenStreetMap 건물 윤곽
    - height 태그 → "observed_osm" (기여자 입력값)
    - building:levels → "estimated"
 그 외 → "missing" : 그림자 계산에서 **제외**하고 지도에 ‘높이 미확인’으로 표시.
 0·음수·600 m 초과 → "invalid" (제외).
"""
from __future__ import annotations

import glob
import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from scripts.common import PROCESSED, RAW, ROOT, WEB_DATA, WORK_CRS, register_dataset, write_json
from scripts.shadows.engine import MAX_VALID_HEIGHT_M

SCHEMA = json.loads((ROOT / "config" / "buildings_schema.json").read_text(encoding="utf-8"))
AOIS = json.loads((ROOT / "config" / "aoi.json").read_text(encoding="utf-8"))
FLOOR_H = SCHEMA["assumed_floor_height_m"]


def _num(v):
    if v is None:
        return np.nan
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", str(v).replace(",", "."))
    return float(m.group(1)) if m else np.nan


def _pick(cols, cands):
    for c in cands:
        if c in cols:
            return c
    return None


def aoi_polys(a):
    w, s, e, n = a["bbox"]
    aoi = gpd.GeoSeries([box(w, s, e, n)], crs="EPSG:4326").to_crs(WORK_CRS).iloc[0]
    return aoi, aoi.buffer(AOIS["shadow_buffer_m"])


def load_official(ext_poly):
    files = glob.glob(str(ROOT / SCHEMA["official_shp_glob"]), recursive=True)
    if not files:
        return None, None
    parts = []
    for f in files:
        # bbox 로 필요한 구역만 읽는다(대구 전체 dbf 약 700 MB)
        g = gpd.read_file(f, encoding=SCHEMA["official_encoding"],
                          bbox=gpd.GeoSeries([ext_poly], crs=WORK_CRS))
        if g.crs is None:
            raise ValueError(f"{f}: .prj 없음 — 좌표계를 추측해 지정하지 않는다. 원본 .prj 확인 필요")
        g = g.to_crs(WORK_CRS)
        parts.append(g[g.intersects(ext_poly)])
    g = pd.concat(parts, ignore_index=True)
    cols = list(g.columns)
    f_id, f_h, f_fl = (_pick(cols, SCHEMA[k]) for k in ("id_fields", "height_fields", "floors_fields"))
    f_nm, f_use, f_dt = (_pick(cols, SCHEMA[k]) for k in ("name_fields", "use_fields", "date_fields"))
    if f_h is None:
        raise ValueError(f"높이 필드를 찾지 못함. 컬럼: {cols} → config/buildings_schema.json 수정")
    out = gpd.GeoDataFrame({
        "building_id": g[f_id].astype(str) if f_id else g.index.astype(str),
        "name": g[f_nm] if f_nm else None,
        "use": g[f_use] if f_use else None,
        "source_date": g[f_dt].astype(str) if f_dt else None,
        "raw_height": g[f_h].map(_num),
        "raw_levels": g[f_fl].map(_num) if f_fl else np.nan,
    }, geometry=g.geometry, crs=WORK_CRS)
    out["footprint_source"] = "국토부 GIS건물통합정보"
    out["primary_status"] = "registry"
    return out, {"files": files, "fields": {"id": f_id, "height": f_h, "floors": f_fl}}


def load_osm(aoi_id):
    g = gpd.read_file(RAW / "osm" / f"{aoi_id}_buildings.gpkg").to_crs(WORK_CRS)
    out = gpd.GeoDataFrame({
        "building_id": g["osm_id"], "name": g.get("name"), "use": g.get("building"), "source_date": None,
        "raw_height": g["height"].map(_num) if "height" in g else np.nan,
        "raw_levels": g["building:levels"].map(_num) if "building:levels" in g else np.nan,
    }, geometry=g.geometry, crs=WORK_CRS)
    out["footprint_source"] = "OpenStreetMap"
    out["primary_status"] = "observed_osm"
    return out


MPF_MAX, MPF_MIN = 15.0, 1.5  # 층당 높이(m) 일관성 범위


def suspect(h, lv):
    """높이·층수가 모두 있을 때 층당 높이가 비현실적인 경우(대장 입력 오류 의심)."""
    mpf = h / lv.where(lv >= 1)
    return ((mpf > MPF_MAX) & (h > 30)) | ((mpf < MPF_MIN) & (lv >= 3))


def classify(b: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if SCHEMA.get("zero_height_is_missing"):
        # GIS건물통합정보: 높이·층수 0 = 대장 미기재(무허가·부속건물 등) → 결측
        b["raw_height"] = b["raw_height"].where(b["raw_height"] != 0)
        b["raw_levels"] = b["raw_levels"].where(b["raw_levels"] != 0)
    h, lv = b["raw_height"], b["raw_levels"]
    ok_h = h.notna() & (h > 0) & (h <= MAX_VALID_HEIGHT_M)
    ok_lv = lv.notna() & (lv >= 1) & (lv <= 150)
    sus = suspect(h, lv) & ok_h
    b["height_m"] = np.where(ok_h & ~sus, h, np.where(~ok_h & ok_lv, lv * FLOOR_H, np.nan))
    b["height_status"] = np.select(
        [sus, ok_h, ~ok_h & ok_lv, h.notna() & ~ok_h & ~ok_lv],
        ["invalid", b["primary_status"], "estimated", "invalid"], "missing")
    b["height_imputed"] = b["height_status"] == "estimated"
    b["height_source"] = np.select(
        [b["height_status"] == "registry", b["height_status"] == "observed_osm", b["height_status"] == "estimated"],
        ["GIS건물통합정보 높이(건축물대장 기반)", "OSM height 태그", f"층수×{FLOOR_H} m 가정"], "없음")
    b["height_confidence"] = b["height_status"].map(
        {"registry": "high", "observed_osm": "medium", "estimated": "low"}).fillna("none")
    return b.drop(columns=["primary_status"])


def citywide_report():
    """대구 전체 건물의 높이 보유율(명세 4.2-6). 공식 SHP가 있을 때만."""
    import pyogrio
    files = glob.glob(str(ROOT / SCHEMA["official_shp_glob"]), recursive=True)
    if not files:
        return None
    df = pd.concat([pyogrio.read_dataframe(f, columns=[SCHEMA["height_fields"][0], SCHEMA["floors_fields"][0]],
                                           read_geometry=False) for f in files])
    h = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    lv = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    n = len(df)
    bad = (h < 0) | (h > MAX_VALID_HEIGHT_M) | (suspect(h, lv) & (h > 0))
    ok_h = (h > 0) & (h <= MAX_VALID_HEIGHT_M) & ~bad
    ok_lv = ~ok_h & ~bad & (lv >= 1) & (lv <= 150)
    return {"n_buildings": int(n),
            "pct_registry_height": round(100 * ok_h.mean(), 1),
            "pct_floors_only_estimated": round(100 * ok_lv.mean(), 1),
            "pct_invalid": round(100 * bad.mean(), 2), "n_invalid": int(bad.sum()),
            "invalid_rule": f"0 초과·{MAX_VALID_HEIGHT_M:.0f} m 이하, 층당 {MPF_MIN}~{MPF_MAX} m(층수 있을 때) 벗어나면 비정상",
            "pct_missing": round(100 * (~ok_h & ~ok_lv & ~bad).mean(), 1),
            "height_p50_m": round(float(h[ok_h].median()), 1), "height_p99_m": round(float(h[ok_h].quantile(.99)), 1),
            "height_max_m": round(float(h[ok_h].max()), 1)}


def main() -> None:
    reports = {}
    for a in AOIS["aois"]:
        aoi, ext = aoi_polys(a)
        official, meta = load_official(ext)
        b = official if official is not None else load_osm(a["id"])
        mode = "official" if official is not None else "osm_interim"
        b = b[b.geometry.notna() & ~b.geometry.is_empty].copy()
        b["geometry"] = b.geometry.make_valid()
        b = b[b.intersects(ext)]
        n0 = len(b)
        b = b[b.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        b = b[b.area >= 4]  # 4 m² 미만 조각 제외
        # 중복(같은 형상) 제거
        b["_wkb"] = b.geometry.normalize().to_wkb()
        n_dup = int(b.duplicated("_wkb").sum())
        b = b.drop_duplicates("_wkb").drop(columns="_wkb")
        b = classify(b)
        b["in_aoi"] = b.intersects(aoi)
        b["footprint_m2"] = b.area.round(1)
        out = PROCESSED / "buildings"
        out.mkdir(parents=True, exist_ok=True)
        b.to_file(out / f"{a['id']}_buildings.gpkg", driver="GPKG")

        inside = b[b["in_aoi"]]
        vc = inside["height_status"].value_counts()
        n = len(inside)
        rep = {
            "aoi": a["id"], "mode": mode, "n_buildings_in_aoi": int(n), "n_buildings_with_buffer": int(len(b)),
            "dropped_invalid_or_tiny": int(n0 - len(b) - n_dup), "dropped_duplicates": n_dup,
            "status_counts": {k: int(v) for k, v in vc.items()},
            "pct": {k: round(100 * v / n, 1) for k, v in vc.items()},
            "footprint_area_pct_with_height": round(100 * inside.loc[inside.height_m.notna(), "footprint_m2"].sum()
                                                    / inside["footprint_m2"].sum(), 1),
            "assumed_floor_height_m": FLOOR_H,
            "official_meta": meta,
        }
        reports[a["id"]] = rep
        print(json.dumps(rep, ensure_ascii=False))

        w = b.to_crs("EPSG:4326")
        w["geometry"] = w.geometry.simplify(0.000003)
        cols = ["building_id", "name", "use", "height_m", "height_status", "height_source", "footprint_source",
                "footprint_m2", "in_aoi", "geometry"]
        w["height_m"] = w["height_m"].round(1)
        (WEB_DATA / "shadows").mkdir(parents=True, exist_ok=True)
        w[cols].to_file(WEB_DATA / "shadows" / f"{a['id']}_buildings.geojson", driver="GeoJSON",
                        COORDINATE_PRECISION=6)

    city = citywide_report()
    if city:
        reports["_daegu_all"] = city
        print("daegu all:", city)
    write_json(WEB_DATA / "building_quality.json", reports, compact=False)
    write_json(PROCESSED / "buildings" / "building_quality.json", reports, compact=False)
    mode = {r["mode"] for k, r in reports.items() if not k.startswith("_")}
    register_dataset(
        "D01_buildings",
        name="시범 구역 건물 형상·높이",
        provider="국토부 GIS건물통합정보" if mode == {"official"} else "OpenStreetMap(임시) — 국토부 GIS건물통합정보 적용 대기",
        source_url="https://www.data.go.kr/data/15083092/fileData.do",
        download_url="https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=18",
        license="GIS건물통합정보: 공공누리 제1유형(출처표시) / OSM: ODbL 1.0",
        crs=WORK_CRS,
        fields=["building_id", "height_m", "height_status", "height_source", "height_confidence", "height_imputed"],
        row_count={**{k: v["n_buildings_in_aoi"] for k, v in reports.items() if not k.startswith("_")},
                   **({"daegu_all": city["n_buildings"]} if city else {})},
        null_rate={**{k: round(v["pct"].get("missing", 0) / 100, 3) for k, v in reports.items() if not k.startswith("_")},
                   **({"daegu_all_no_height_no_floors": round(city["pct_missing"] / 100, 3)} if city else {})},
        valid_period="2026-11-06 (A22 데이터기준일자)" if city else None,
        quality_note=("공식 SHP는 V-World 로그인 후 다운로드 필요(자동 수집 불가). 미확보 시 OSM 윤곽+층수 추정으로 임시 계산하며 "
                      "UI에 ‘임시·추정’으로 표기. 높이 미확인 건물은 그림자 계산 제외."),
        status="official" if mode == {"official"} else "interim_osm",
        layer_kind="reference",
    )


if __name__ == "__main__":
    main()
