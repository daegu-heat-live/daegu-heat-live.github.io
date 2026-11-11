"""D11 Sentinel-2 L2A 분광지수(NDVI·NDBI·MNDWI) + D12 대체 Copernicus DEM GLO-30 고도.

- Sentinel-2: 동일 날짜(2025-07-09, 상대궤도 R103) 같은 궤도 타일 T52SDE/T52SDF 모자이크. SCL로 구름·그림자·결측 제거.
  NDVI=(B08−B04)/(B08+B04), NDBI=(B11−B08)/(B11+B08), MNDWI=(B03−B11)/(B03+B11)
  **열적외선이 없으므로 온도 아님.** 30 m 대구 격자로 평균 재표본.
- DEM: Copernicus GLO-30(ESA, 무료·출처표시). 국토정보플랫폼 DEM은 인증 필요해 대체.
"""
from __future__ import annotations

import numpy as np
import planetary_computer as pc
import pystac_client
from rasterio.enums import Resampling

from scripts.common import PROCESSED, WEB_DATA, register_dataset, write_json
from scripts.raster import colormaps as cm
from scripts.raster.rasterutil import city_mask, daegu_grid, export_web_png, read_to_grid, save_tif

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BBOX = [128.35, 35.6, 128.78, 36.33]
S2_DATE = "2025-07-09"  # R103 궤도: 대구 100% 커버, Landsat 관측일과 동일
SCL_BAD = {0, 1, 3, 8, 9, 10, 11}


def main() -> None:
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    transform, shape = daegu_grid()
    inside = city_mask(transform, shape)
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=BBOX, datetime=S2_DATE).items())
    print("S2 items", [i.id for i in items])
    bands = {k: np.full(shape, np.nan, "float32") for k in ("B03", "B04", "B08", "B11")}
    for it in items:
        scl = read_to_grid(it.assets["SCL"].href, transform, shape, dtype="uint8", src_nodata=0)
        bad = np.isin(scl, list(SCL_BAD))
        for k in bands:
            v = read_to_grid(it.assets[k].href, transform, shape, resampling=Resampling.average,
                             dtype="float32", src_nodata=0)
            # 처리기준 04.00 이후 BOA_ADD_OFFSET = -1000
            off = float(it.properties.get("s2:boa_add_offset", -1000) if "s2:processing_baseline" in it.properties
                        and float(it.properties["s2:processing_baseline"]) >= 4 else 0)
            v = (v + off) / 10000.0
            v[bad] = np.nan
            fill = np.isnan(bands[k]) & ~np.isnan(v)
            bands[k][fill] = v[fill]
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (bands["B08"] - bands["B04"]) / (bands["B08"] + bands["B04"])
        ndbi = (bands["B11"] - bands["B08"]) / (bands["B11"] + bands["B08"])
        mndwi = (bands["B03"] - bands["B11"]) / (bands["B03"] + bands["B11"])
    for a in (ndvi, ndbi, mndwi):
        a[~inside] = np.nan
        a[(a < -1) | (a > 1)] = np.nan
    out = PROCESSED / "s2"
    for name, a in (("ndvi", ndvi), ("ndbi", ndbi), ("mndwi", mndwi)):
        save_tif(out / f"{name}_{S2_DATE.replace('-', '')}.tif", a.astype("float32"), transform)
    cov = float((~np.isnan(ndvi[inside])).mean())
    corners = export_web_png(ndvi, transform, lambda x: cm.apply(x, cm.NDVI_STOPS, cm.NDVI_RANGE, alpha=220),
                             WEB_DATA / "ndvi" / "ndvi.png")
    write_json(WEB_DATA / "ndvi" / "ndvi.json", {
        "kind": "observed", "date": S2_DATE, "scene_ids": [i.id for i in items], "png": "ndvi/ndvi.png",
        "corners": corners, "legend": {"stops": cm.NDVI_STOPS, "range": cm.NDVI_RANGE},
        "coverage_pct": round(cov * 100, 1), "pixel_size_m": 30, "native_m": 10})
    print("NDVI coverage", cov)

    # ---- DEM ----
    dem_items = list(cat.search(collections=["cop-dem-glo-30"], bbox=BBOX).items())
    dem = np.full(shape, np.nan, "float32")
    for it in dem_items:
        v = read_to_grid(it.assets["data"].href, transform, shape, resampling=Resampling.bilinear, dtype="float32")
        fill = np.isnan(dem) & ~np.isnan(v)
        dem[fill] = v[fill]
    dem[~inside] = np.nan
    save_tif(PROCESSED / "dem" / "cop_dem_30m.tif", dem, transform)
    print("DEM tiles", len(dem_items), "range", np.nanmin(dem), np.nanmax(dem))

    register_dataset(
        "D11_sentinel2",
        name="Sentinel-2 L2A 분광지수(NDVI·NDBI·MNDWI)",
        provider="ESA Copernicus (Microsoft Planetary Computer 미러)",
        source_url="https://browser.dataspace.copernicus.eu/",
        access_url="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a",
        license="Copernicus Sentinel data — 무료·개방, 출처표시 ‘Contains modified Copernicus Sentinel data 2025’",
        observed_at=S2_DATE, crs="UTM 52N 30 m 격자(10 m 평균 재표본)",
        fields=["B03", "B04", "B08", "B11", "SCL"], row_count={"scenes": len(items)},
        null_rate=round(1 - cov, 4), quality_note="SCL 0,1,3,8,9,10,11 제거. 열적외 없음(온도 아님).",
        version="L2A", status="ok", layer_kind="observed")
    register_dataset(
        "D12_dem",
        name="Copernicus DEM GLO-30 (국토정보플랫폼 DEM 대체)",
        provider="ESA / Airbus (Microsoft Planetary Computer 미러)",
        source_url="https://planetarycomputer.microsoft.com/dataset/cop-dem-glo-30",
        license="Copernicus DEM GLO-30 라이선스(무료, 출처표시)",
        crs="UTM 52N 30 m 격자", row_count={"tiles": len(dem_items)},
        quality_note="그림자 엔진에는 미사용(평탄 지면 가정). AI 모델 공변량(고도)으로만 사용.",
        version="GLO-30", status="ok", layer_kind="reference")


if __name__ == "__main__":
    main()
