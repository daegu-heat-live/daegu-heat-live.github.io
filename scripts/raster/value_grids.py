"""지도 클릭 조회용 값 격자(PNG 인코딩) 생성.

각 LST 장면/합성·NDVI GeoTIFF를 EPSG:3857 60 m 격자로 재투영 후
  v = round((값 + OFFSET) × 100)  → R = v >> 8, G = v & 255, A = 255(유효)/0(결측)
으로 RGBA PNG에 무손실 저장한다. 브라우저는 canvas로 읽어 픽셀을 역산한다.
(표시용 PNG와 별개. 값 해상도 60 m — 클릭 정보에 명시)
"""
from __future__ import annotations

import json

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
from pyproj import Transformer

from scripts.common import PROCESSED, WEB_DATA, write_json

RES = 60.0 * 1.234


def encode(tif, out_png, offset):
    with rasterio.open(tif) as s:
        a = s.read(1).astype("float32")
        dt, dw, dh = calculate_default_transform(s.crs, "EPSG:3857", s.width, s.height, *s.bounds, resolution=RES)
        dst = np.full((dh, dw), np.nan, "float32")
        reproject(a, dst, src_transform=s.transform, src_crs=s.crs, dst_transform=dt, dst_crs="EPSG:3857",
                  resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    v = np.clip(np.round((np.nan_to_num(dst) + offset) * 100), 0, 65535).astype(np.uint32)
    rgba = np.zeros((dh, dw, 4), np.uint8)
    rgba[..., 0] = v >> 8
    rgba[..., 1] = v & 255
    rgba[..., 2] = 0
    rgba[..., 3] = np.where(np.isnan(dst), 0, 255)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(out_png, optimize=True)
    tr = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    return {"png": str(out_png.relative_to(WEB_DATA)).replace("\\", "/"), "offset": offset, "scale": 100,
            "width": dw, "height": dh,
            "merc_bounds": [dt.c, dt.f + dh * dt.e, dt.c + dw * dt.a, dt.f], "res_m": 60}


def main():
    idx = {}
    for tif in sorted((PROCESSED / "lst").glob("lst_*.tif")):
        key = tif.stem.replace("lst_", "")
        idx[key] = encode(tif, WEB_DATA / "values" / f"lst_{key}.png", 50.0)
    nd = sorted((PROCESSED / "s2").glob("ndvi_*.tif"))
    if nd:
        idx["ndvi"] = encode(nd[0], WEB_DATA / "values" / "ndvi.png", 1.0)
    write_json(WEB_DATA / "values" / "index.json", idx, compact=False)
    print(list(idx))


if __name__ == "__main__":
    main()
