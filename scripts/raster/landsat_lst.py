"""D05 Landsat Collection 2 Level-2 지표면온도(ST_B10) 처리.

- 접근: Microsoft Planetary Computer STAC(`landsat-c2-l2`, USGS 원본 미러, 익명 SAS 서명).
- 대상: Landsat 8/9, WRS path 114 (대구 상공 통과 약 10:58 KST), 2023~2025년 6~8월.
- 같은 날짜·같은 궤도의 row 035/036 은 동일 촬영 스트립이므로 모자이크를 허용한다.
  **서로 다른 날짜를 섞은 단일 시각 지도는 만들지 않는다.** 여름 합성은 별도 레이어로 표기.
- 품질: QA_PIXEL 비트 0(fill),1(dilated cloud),2(cirrus),3(cloud),4(cloud shadow),5(snow) 제거.
- 보정: LST_K = DN * 0.00341802 + 149.0, LST_C = LST_K - 273.15 (USGS L2 스케일 계수).
- 대구 경계 내 유효픽셀 비율 ≥ MIN_COVERAGE 인 장면만 채택.
"""
from __future__ import annotations

import json
from datetime import datetime

import geopandas as gpd
import numpy as np
import planetary_computer as pc
import pystac_client
from rasterio.enums import Resampling
from rasterio.features import rasterize

from scripts.common import PROCESSED, WEB_DATA, register_dataset, write_json
from scripts.raster import colormaps as cm
from scripts.raster.rasterutil import (GRID_CRS, city_mask, daegu_grid, export_web_png, read_to_grid,
                                       save_tif)

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BBOX = [128.35, 35.6, 128.78, 36.33]
YEARS = [2023, 2024, 2025]
MIN_COVERAGE = 0.80
QA_BAD_BITS = (0, 1, 2, 3, 4, 5)
SCALE, OFFSET = 0.00341802, 149.0


def search_items():
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    items = []
    for y in YEARS:
        s = cat.search(collections=["landsat-c2-l2"], bbox=BBOX, datetime=f"{y}-06-01/{y}-08-31",
                       query={"eo:cloud_cover": {"lt": 60}, "platform": {"in": ["landsat-8", "landsat-9"]},
                              "landsat:wrs_path": {"eq": "114"}})
        items += list(s.items())
    by_date: dict[str, list] = {}
    for it in items:
        by_date.setdefault(it.datetime.strftime("%Y-%m-%d"), []).append(it)
    return dict(sorted(by_date.items()))


def zones(transform, shape):
    gu = gpd.read_file(PROCESSED / "boundaries" / "daegu_gu_5179.gpkg").to_crs(GRID_CRS)
    dong = gpd.read_file(PROCESSED / "boundaries" / "daegu_dong_5179.gpkg").to_crs(GRID_CRS)
    gz = rasterize(((g, i + 1) for i, g in enumerate(gu.geometry)), out_shape=shape, transform=transform,
                   fill=0, dtype="int32")
    dz = rasterize(((g, i + 1) for i, g in enumerate(dong.geometry)), out_shape=shape, transform=transform,
                   fill=0, dtype="int32")
    return gu, gz, dong, dz


def zone_stats(lst, zone_arr, n, hot_thr):
    res = []
    for i in range(1, n + 1):
        m = zone_arr == i
        total = int(m.sum())
        v = lst[m]
        v = v[~np.isnan(v)]
        if total == 0 or v.size < max(30, 0.3 * total):
            res.append(None)
            continue
        res.append({"mean": round(float(v.mean()), 2), "median": round(float(np.median(v)), 2),
                    "p90": round(float(np.percentile(v, 90)), 2),
                    "hot_frac": round(float((v >= hot_thr).mean()), 4),
                    "valid_frac": round(v.size / total, 4), "n_px": int(v.size)})
    return res


def main() -> None:
    transform, shape = daegu_grid()
    inside = city_mask(transform, shape)
    gu, gz, dong, dz = zones(transform, shape)
    out_dir = PROCESSED / "lst"
    web_dir = WEB_DATA / "lst"
    out_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)

    scenes, rejected, kept_arrays = [], [], {}
    for date, its in search_items().items():
        lst = np.full(shape, np.nan, dtype="float32")
        ids, times = [], []
        for it in sorted(its, key=lambda x: x.properties["landsat:wrs_row"]):
            st = read_to_grid(it.assets["lwir11"].href, transform, shape, dtype="float32", src_nodata=0)
            qa = read_to_grid(it.assets["qa_pixel"].href, transform, shape, dtype="uint16", src_nodata=1)
            bad = np.zeros(shape, bool)
            for b in QA_BAD_BITS:
                bad |= (qa >> b) & 1 == 1
            bad |= qa == 0
            v = st * SCALE + OFFSET - 273.15
            v[bad | np.isnan(st)] = np.nan
            fill = np.isnan(lst) & ~np.isnan(v)
            lst[fill] = v[fill]
            ids.append(it.id)
            times.append(it.datetime)
        lst[~inside] = np.nan
        coverage = float((~np.isnan(lst[inside])).mean())
        t_utc = min(times)
        meta = {"date": date, "scene_ids": ids, "platform": ids[0][:4].replace("LC08", "Landsat 8").replace("LC09", "Landsat 9"),
                "observed_at_utc": t_utc.isoformat(),
                "observed_at_kst": t_utc.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Seoul")).isoformat(timespec="minutes"),
                "coverage_pct": round(coverage * 100, 1),
                "stac_cloud_cover": [round(i.properties["eo:cloud_cover"], 1) for i in its]}
        if coverage < MIN_COVERAGE:
            rejected.append(meta)
            print("reject", date, f"{coverage:.2%}")
            continue
        v = lst[inside & ~np.isnan(lst)]
        hot_thr = float(np.percentile(v, 90))
        meta.update({
            "city": {"mean": round(float(v.mean()), 2), "median": round(float(np.median(v)), 2),
                     "p10": round(float(np.percentile(v, 10)), 2), "p90": round(hot_thr, 2),
                     "min": round(float(v.min()), 2), "max": round(float(v.max()), 2)},
            "hot_threshold_c": round(hot_thr, 2),
            "gu": zone_stats(lst, gz, len(gu), hot_thr),
            "dong": [s["mean"] if s else None for s in zone_stats(lst, dz, len(dong), hot_thr)],
        })
        sid = date.replace("-", "")
        save_tif(out_dir / f"lst_{sid}.tif", lst, transform)
        meta["png"] = f"lst/lst_{sid}.png"
        meta["corners"] = export_web_png(lst, transform, lambda a: cm.apply(a, cm.LST_STOPS, cm.LST_RANGE), web_dir / f"lst_{sid}.png")
        hist, edges = np.histogram(v, bins=np.arange(15, 66, 1))
        meta["hist"] = {"start": 15, "step": 1, "counts": hist.tolist()}
        scenes.append(meta)
        kept_arrays[date] = lst
        print("keep", date, f"{coverage:.2%}", meta["city"])

    # ---- 여름 합성(연도별 유효관측 중앙값) — 단일 시각 실측 아님 ----
    composites = []
    for y in YEARS:
        arrs = [a for d, a in kept_arrays.items() if d.startswith(str(y))]
        if not arrs:
            continue
        stack = np.stack(arrs)
        med = np.nanmedian(stack, axis=0).astype("float32")
        nobs = (~np.isnan(stack)).sum(0)
        med[nobs < 1] = np.nan
        save_tif(out_dir / f"lst_composite_{y}.tif", med, transform)
        v = med[inside & ~np.isnan(med)]
        hot_thr = float(np.percentile(v, 90))
        composites.append({
            "id": f"composite_{y}", "year": y, "n_scenes": len(arrs),
            "dates": [d for d in kept_arrays if d.startswith(str(y))],
            "label": f"{y}년 6~8월 유효관측 중앙값(합성 지도)",
            "png": f"lst/lst_composite_{y}.png",
            "corners": export_web_png(med, transform, lambda a: cm.apply(a, cm.LST_STOPS, cm.LST_RANGE), web_dir / f"lst_composite_{y}.png"),
            "city": {"mean": round(float(v.mean()), 2), "median": round(float(np.median(v)), 2),
                     "p90": round(hot_thr, 2)},
            "gu": zone_stats(med, gz, len(gu), hot_thr),
            "dong": [s["mean"] if s else None for s in zone_stats(med, dz, len(dong), hot_thr)],
        })

    write_json(WEB_DATA / "lst_scenes.json", {
        "kind": "observed",
        "product": "Landsat Collection 2 Level-2 Surface Temperature (ST_B10)",
        "unit": "지표면온도 °C",
        "legend": {"stops": cm.LST_STOPS, "range": cm.LST_RANGE},
        "grid": {"crs": GRID_CRS, "pixel_size_m": 30, "thermal_native_m": 100},
        "gu_names": gu["sggnm"].tolist(), "gu_codes": gu["sgg"].tolist(),
        "dong_codes": dong["adm_cd2"].tolist(), "dong_names": dong["adm_nm"].tolist(),
        "hot_definition": "해당 장면 대구 전체 유효픽셀 상위 10% 임계값 이상",
        "min_coverage_pct": MIN_COVERAGE * 100,
        "scenes": scenes, "composites": composites, "rejected": rejected,
    })
    register_dataset(
        "D05_landsat_lst",
        name="Landsat 8/9 Collection 2 Level-2 지표면온도",
        provider="USGS (Microsoft Planetary Computer 미러 경유)",
        source_url="https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature",
        access_url="https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2",
        license="USGS Landsat 자료: 공개(public domain), 출처 표기 권장",
        observed_at=[s["observed_at_kst"] for s in scenes],
        crs=f"원본 UTM 52N → {GRID_CRS} 30m 격자(대구 고정 격자)",
        fields=["ST_B10(lwir11)", "QA_PIXEL"],
        row_count={"scenes_kept": len(scenes), "scenes_rejected": len(rejected)},
        null_rate={s["date"]: round(1 - s["coverage_pct"] / 100, 3) for s in scenes},
        quality_note=(f"QA 비트 {QA_BAD_BITS} 제거, 대구 내 유효픽셀 {MIN_COVERAGE:.0%} 미만 장면 제외. "
                      "열적외 원 해상도 100m(30m로 재표본 제공). 지표면온도이며 기온 아님."),
        version="Collection 2 Level-2",
        status="ok",
        layer_kind="observed",
    )
    print(f"kept {len(scenes)} rejected {len(rejected)}")


if __name__ == "__main__":
    main()
