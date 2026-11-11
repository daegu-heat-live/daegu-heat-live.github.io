"""래스터 공통: 대구 기준 격자, 원격 COG 재투영 읽기, 웹 PNG 내보내기."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject

from scripts.common import PROCESSED

GRID_CRS = "EPSG:32652"  # Landsat/Sentinel-2 원본 UTM 52N
RES = 30.0


def daegu_city(crs: str = GRID_CRS) -> gpd.GeoDataFrame:
    return gpd.read_file(PROCESSED / "boundaries" / "daegu_city_5179.gpkg").to_crs(crs)


def daegu_grid(res: float = RES, pad: float = 600.0):
    """대구 외곽 경계 + 여유폭을 덮는 고정 격자(transform, shape)."""
    city = daegu_city()
    minx, miny, maxx, maxy = city.total_bounds
    minx = np.floor((minx - pad) / res) * res
    maxy = np.ceil((maxy + pad) / res) * res
    w = int(np.ceil((maxx + pad - minx) / res))
    h = int(np.ceil((maxy - (miny - pad)) / res))
    return from_origin(minx, maxy, res, res), (h, w)


def city_mask(transform, shape) -> np.ndarray:
    """True = 대구 내부."""
    city = daegu_city()
    return ~geometry_mask(city.geometry, out_shape=shape, transform=transform)


def read_to_grid(href: str, transform, shape, resampling=Resampling.nearest, dtype="float32",
                 src_nodata=None) -> np.ndarray:
    dst = np.full(shape, np.nan if "float" in dtype else 0, dtype=dtype)
    with rasterio.open(href) as src:
        reproject(source=rasterio.band(src, 1), destination=dst, dst_transform=transform,
                  dst_crs=GRID_CRS, resampling=resampling,
                  src_nodata=src_nodata if src_nodata is not None else src.nodata,
                  dst_nodata=np.nan if "float" in dtype else 0)
    return dst


def save_tif(path: Path, arr: np.ndarray, transform, nodata=np.nan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=arr.dtype, crs=GRID_CRS, transform=transform, nodata=nodata,
                       compress="deflate", tiled=True) as dst:
        dst.write(arr, 1)


def export_web_png(arr: np.ndarray, transform, rgba_fn, out_png: Path, res_m: float = 30.0,
                   src_crs: str = GRID_CRS) -> list:
    """UTM 배열 → EPSG:3857 재투영 → RGBA PNG. MapLibre image source용 4개 모서리(lon,lat) 반환."""
    h, w = arr.shape
    left, top = transform.c, transform.f
    right, bottom = left + w * transform.a, top + h * transform.e
    dt, dw, dh = calculate_default_transform(src_crs, "EPSG:3857", w, h, left, bottom, right, top,
                                             resolution=res_m * 1.234)  # 위도 35.9° 메르카토르 축척(1/cos φ)
    dst = np.full((dh, dw), np.nan, dtype="float32")
    reproject(arr.astype("float32"), dst, src_transform=transform, src_crs=src_crs, dst_transform=dt,
              dst_crs="EPSG:3857", resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
    rgba = rgba_fn(dst)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(out_png, optimize=True)
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    l, t = dt.c, dt.f
    r, b = l + dw * dt.a, t + dh * dt.e
    corners = [tr.transform(l, t), tr.transform(r, t), tr.transform(r, b), tr.transform(l, b)]
    return [[round(x, 6), round(y, 6)] for x, y in corners]
