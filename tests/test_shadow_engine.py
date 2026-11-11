"""그림자 기하 검증 — 모든 입력은 TEST DATA(가상 도형)이며 실제 건물이 아님."""
import math

import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from scripts.shadows.engine import (building_shadow, ground_shadow_union, shadow_vector, valid_height)


def test_length_10m_at_45deg_sun_south():
    # TEST DATA: 10×10 m 정사각형, 높이 10 m, 태양 고도 45°, 방위 180°(남) → 그림자는 북쪽 10 m
    sv = shadow_vector(45, 180)
    assert sv.dx == pytest.approx(0, abs=1e-9)
    assert sv.dy == pytest.approx(1.0)
    s = building_shadow(box(0, 0, 10, 10), 10, sv)
    assert s.area == pytest.approx(100, rel=1e-6)
    minx, miny, maxx, maxy = s.bounds
    assert (miny, maxy) == pytest.approx((10, 20))


def test_direction_east_sun_casts_west():
    sv = shadow_vector(30, 90)  # 동쪽 태양
    s = building_shadow(box(0, 0, 10, 10), 10, sv)
    L = 10 / math.tan(math.radians(30))
    assert s.bounds[0] == pytest.approx(-L, abs=1e-3)  # 1 mm 정밀도 격자
    assert s.area == pytest.approx(10 * L, abs=0.05)


def test_diagonal_area_matches_minkowski():
    sv = shadow_vector(45, 225)  # 남서 태양 → 북동 그림자
    s = building_shadow(box(0, 0, 10, 10), 10, sv)
    dx = dy = 10 * math.sin(math.radians(45))
    # 정사각형을 (dx,dy)로 쓸면 넓이 = 100 + 10*|dx| + 10*|dy|, 건물 제외 → -100
    assert s.area == pytest.approx(10 * dx + 10 * dy, abs=0.05)


def test_l_shape_concave():
    L = Polygon([(0, 0), (20, 0), (20, 5), (5, 5), (5, 20), (0, 20)])
    s = building_shadow(L, 6, shadow_vector(45, 180))
    assert s.is_valid and s.area > 0
    assert not s.intersects(L.buffer(-0.01))  # 바닥 내부와 겹치지 않음


def test_multipolygon_and_union_no_double_count():
    a, b = box(0, 0, 10, 10), box(12, 0, 22, 10)
    sv = shadow_vector(45, 180)
    sa, sb = building_shadow(a, 10, sv), building_shadow(b, 10, sv)
    u = ground_shadow_union([sa, sb], [a, b])
    assert u.area == pytest.approx(sa.area + sb.area)
    mp = building_shadow(MultiPolygon([a, b]), 10, sv)
    assert mp.area == pytest.approx(u.area, rel=1e-6)
    # 겹치는 그림자: 같은 건물 두 번 → 합집합 면적은 한 번만
    u2 = ground_shadow_union([sa, sa], [a])
    assert u2.area == pytest.approx(sa.area)


def test_noon_shorter_than_morning():
    s_noon = building_shadow(box(0, 0, 10, 10), 20, shadow_vector(75, 180))
    s_morn = building_shadow(box(0, 0, 10, 10), 20, shadow_vector(20, 100))
    assert s_noon.area < s_morn.area


@pytest.mark.parametrize("h", [None, 0, -3, float("nan"), 1000, "abc"])
def test_invalid_heights_excluded(h):
    assert not valid_height(h)
    assert building_shadow(box(0, 0, 10, 10), h, shadow_vector(45, 180)).is_empty


def test_night_and_low_sun_flags():
    assert shadow_vector(-2, 280).is_night
    assert building_shadow(box(0, 0, 1, 1), 10, shadow_vector(-2, 280)).is_empty
    sv = shadow_vector(3, 280)
    assert sv.low_sun and not sv.is_night
    assert sv.length_per_m == pytest.approx(1 / math.tan(math.radians(3)))


def test_invalid_footprint_is_repaired():
    bow = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])  # 자기교차
    s = building_shadow(bow, 5, shadow_vector(45, 180))
    assert s.is_valid
