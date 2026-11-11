"""기상청 동네예보 격자(DFS, Lambert Conformal Conic) ↔ 위경도 변환.

기상청 단기예보 조회서비스 활용가이드의 격자 정의를 따른다:
  Re=6371.00877 km, grid=5 km, slat1=30°, slat2=60°, olon=126°, olat=38°, xo=43, yo=136
"""
from __future__ import annotations

import math

RE, GRID = 6371.00877, 5.0
SLAT1, SLAT2, OLON, OLAT = 30.0, 60.0, 126.0, 38.0
XO, YO = 43, 136

_DEG = math.pi / 180.0
_re = RE / GRID
_s1, _s2, _olon, _olat = SLAT1 * _DEG, SLAT2 * _DEG, OLON * _DEG, OLAT * _DEG
_sn = math.log(math.cos(_s1) / math.cos(_s2)) / math.log(math.tan(math.pi * 0.25 + _s2 * 0.5) / math.tan(math.pi * 0.25 + _s1 * 0.5))
_sf = math.tan(math.pi * 0.25 + _s1 * 0.5) ** _sn * math.cos(_s1) / _sn
_ro = _re * _sf / math.tan(math.pi * 0.25 + _olat * 0.5) ** _sn


def to_grid(lat: float, lon: float) -> tuple[int, int]:
    ra = _re * _sf / math.tan(math.pi * 0.25 + lat * _DEG * 0.5) ** _sn
    theta = lon * _DEG - _olon
    if theta > math.pi:
        theta -= 2 * math.pi
    if theta < -math.pi:
        theta += 2 * math.pi
    theta *= _sn
    x = math.floor(ra * math.sin(theta) + XO + 0.5)
    y = math.floor(_ro - ra * math.cos(theta) + YO + 0.5)
    return int(x), int(y)


def to_latlon(nx: int, ny: int) -> tuple[float, float]:
    xn, yn = nx - XO, _ro - ny + YO
    ra = math.copysign(math.hypot(xn, yn), _sn)
    alat = 2 * math.atan((_re * _sf / ra) ** (1 / _sn)) - math.pi * 0.5
    if abs(xn) <= 0:
        theta = 0.0
    elif abs(yn) <= 0:
        theta = math.copysign(math.pi * 0.5, xn)
    else:
        theta = math.atan2(xn, yn)
    alon = theta / _sn + _olon
    return alat / _DEG, alon / _DEG
