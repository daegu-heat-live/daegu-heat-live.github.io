"""NOAA 태양 위치 알고리즘(NOAA Global Monitoring Laboratory Solar Calculator,
Meeus "Astronomical Algorithms" 기반) 자체 구현.

- 입력 시각은 timezone-aware datetime 이어야 한다(KST 오해 방지). naive 입력은 거부.
- 반환: 고도각(겉보기, 대기굴절 보정 포함) / 방위각(북=0°, 시계방향) [도].
- 검증: tests/test_solar.py 에서 pvlib(NREL SPA)과 비교.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SunPosition:
    elevation_deg: float        # 굴절 보정된 겉보기 고도
    azimuth_deg: float          # 북=0, 동=90
    zenith_deg: float
    declination_deg: float
    equation_of_time_min: float


def _julian_day(dt_utc: datetime) -> float:
    y, m = dt_utc.year, dt_utc.month
    d = dt_utc.day + (dt_utc.hour + (dt_utc.minute + (dt_utc.second + dt_utc.microsecond / 1e6) / 60) / 60) / 24
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def sun_position(when: datetime, lat: float, lon: float) -> SunPosition:
    if when.tzinfo is None:
        raise ValueError("timezone-aware datetime 필요 (예: ZoneInfo('Asia/Seoul'))")
    dt = when.astimezone(timezone.utc)
    jd = _julian_day(dt)
    t = (jd - 2451545.0) / 36525.0  # Julian century

    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(2 * mr) * (0.019993 - 0.000101 * t) + math.sin(3 * mr) * 0.000289)
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(app_long))))

    yv = math.tan(math.radians(eps / 2)) ** 2
    l0r = math.radians(l0)
    eot = 4 * math.degrees(
        yv * math.sin(2 * l0r) - 2 * e * math.sin(mr) + 4 * e * yv * math.sin(mr) * math.cos(2 * l0r)
        - 0.5 * yv * yv * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))

    minutes_utc = dt.hour * 60 + dt.minute + (dt.second + dt.microsecond / 1e6) / 60
    true_solar_time = (minutes_utc + eot + 4 * lon) % 1440
    hour_angle = true_solar_time / 4 - 180 if true_solar_time / 4 >= 0 else true_solar_time / 4 + 180

    latr, declr, har = math.radians(lat), math.radians(decl), math.radians(hour_angle)
    cos_z = math.sin(latr) * math.sin(declr) + math.cos(latr) * math.cos(declr) * math.cos(har)
    cos_z = max(-1.0, min(1.0, cos_z))
    zen = math.degrees(math.acos(cos_z))
    elev = 90 - zen

    # 대기 굴절 보정 (NOAA)
    if elev > 85:
        refr = 0.0
    else:
        te = math.tan(math.radians(elev))
        if elev > 5:
            refr = 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5
        elif elev > -0.575:
            refr = 1735 + elev * (-518.2 + elev * (103.4 + elev * (-12.79 + elev * 0.711)))
        else:
            refr = -20.772 / te
        refr /= 3600
    elev_app = elev + refr

    sz = math.sin(math.radians(zen))
    if abs(sz) < 1e-12:
        az = 180.0
    else:
        az_cos = (math.sin(latr) * cos_z - math.sin(declr)) / (math.cos(latr) * sz)
        az_cos = max(-1.0, min(1.0, az_cos))
        a = math.degrees(math.acos(az_cos))
        az = (a + 180) % 360 if hour_angle > 0 else (540 - a) % 360
    return SunPosition(elev_app, az, 90 - elev_app, decl, eot)
