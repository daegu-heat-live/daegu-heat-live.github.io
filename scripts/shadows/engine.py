"""건물 그림자 기하 엔진 (Shapely 직접 구현, 평탄 지면 가정).

L = H / tan(α),  dx = -L·sin(A),  dy = -L·cos(A)     (A: 북=0 시계방향, x=동, y=북)

그림자 = 바닥 다각형을 (dx,dy) 방향으로 쓸고 지나간 영역(Minkowski sum with segment)
       = union(바닥, 이동된 상단, 각 모서리의 평행사변형 띠)
지면 그림자 = 위 영역 − 건물 바닥 자체.

입력 좌표계는 반드시 미터 단위 투영(동=+x, 북=+y)이어야 한다(EPSG:5179 등).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import shapely
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, Polygon
from shapely import unary_union  # shapely 2: grid_size 지원

LOW_SUN_DEG = 5.0          # 이 아래는 그림자 길이 폭증 → low_sun 경고 플래그
MAX_VALID_HEIGHT_M = 600.  # 이보다 크면 비현실값으로 제외
GRID_M = 0.001             # 1 mm 정밀도 격자: 부동소수 잔여 조각(sliver) 제거


@dataclass(frozen=True)
class ShadowVector:
    dx: float
    dy: float
    length_per_m: float  # 높이 1 m 당 그림자 길이 = 1/tan(α)
    is_night: bool
    low_sun: bool


def shadow_vector(elevation_deg: float, azimuth_deg: float) -> ShadowVector:
    if elevation_deg <= 0:
        return ShadowVector(0.0, 0.0, math.inf, True, False)
    k = 1.0 / math.tan(math.radians(elevation_deg))
    a = math.radians(azimuth_deg)
    return ShadowVector(-k * math.sin(a), -k * math.cos(a), k, False, elevation_deg < LOW_SUN_DEG)


def valid_height(h) -> bool:
    try:
        h = float(h)
    except (TypeError, ValueError):
        return False
    return math.isfinite(h) and 0 < h <= MAX_VALID_HEIGHT_M


def _polygons(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def building_shadow(footprint, height_m: float, sv: ShadowVector, include_footprint: bool = False):
    """한 건물의 지면 그림자 다각형. 무효 높이·야간이면 빈 도형."""
    if sv.is_night or not valid_height(height_m):
        return Polygon()
    if not footprint.is_valid:
        footprint = shapely.make_valid(footprint)
    dx, dy = sv.dx * height_m, sv.dy * height_m
    parts = []
    for poly in _polygons(footprint):
        parts.append(poly)
        parts.append(translate(poly, dx, dy))
        for ring in [poly.exterior, *poly.interiors]:
            cs = list(ring.coords)
            for (x1, y1), (x2, y2) in zip(cs[:-1], cs[1:]):
                q = Polygon([(x1, y1), (x2, y2), (x2 + dx, y2 + dy), (x1 + dx, y1 + dy)])
                if q.area > 1e-9:
                    parts.append(q)
    swept = unary_union(parts, grid_size=GRID_M)
    if not include_footprint:
        swept = shapely.difference(swept, footprint, grid_size=GRID_M)
    return polygonal(swept)


def polygonal(geom, min_area: float = 1e-6):
    """도형에서 면적 있는 Polygon 성분만 남긴다(차집합 후 선분·점 잔여물 제거)."""
    if geom is None or geom.is_empty:
        return Polygon()
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    polys = []
    stack = [geom]
    while stack:
        g = stack.pop()
        if isinstance(g, Polygon):
            if g.area > min_area:
                polys.append(g)
        elif hasattr(g, "geoms"):
            stack.extend(g.geoms)
    if not polys:
        return Polygon()
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def shadows_for_buildings(footprints, heights, sv: ShadowVector):
    """각 건물 그림자 리스트(입력 순서 유지)."""
    return [building_shadow(f, h, sv) for f, h in zip(footprints, heights)]


def ground_shadow_union(shadows, all_footprints):
    """여러 건물 그림자의 합집합에서 (모든) 건물 바닥을 뺀 지면 그림자. 중복 면적 1회만 집계."""
    u = unary_union([s for s in shadows if s is not None and not s.is_empty], grid_size=GRID_M)
    if u.is_empty:
        return u
    if hasattr(all_footprints, "geom_type"):  # 미리 합친 바닥 도형(프레임마다 재계산 방지)
        fp = all_footprints
    else:
        fp = unary_union([shapely.make_valid(f) for f in all_footprints], grid_size=GRID_M)
    return polygonal(shapely.difference(u, fp, grid_size=GRID_M))
