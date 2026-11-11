"""태양 위치: 자체 NOAA 구현 vs pvlib(NREL SPA) 비교 + 기본 물리 검증."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pvlib
import pytest

from scripts.shadows.solar import sun_position

KST = ZoneInfo("Asia/Seoul")
DONGSEONGRO = (35.8693, 128.5960)


def _spa(dt, lat, lon):
    r = pvlib.solarposition.spa_python(pd.DatetimeIndex([dt]), lat, lon)
    return float(r["apparent_elevation"].iloc[0]), float(r["azimuth"].iloc[0])


@pytest.mark.parametrize("date", ["2025-03-20", "2025-06-21", "2025-08-02", "2025-12-21"])
def test_matches_pvlib_spa_over_day(date):
    lat, lon = DONGSEONGRO
    base = datetime.fromisoformat(date).replace(tzinfo=KST)
    worst_el = worst_az = 0.0
    for m in range(6 * 60, 20 * 60 + 1, 30):
        dt = base + timedelta(minutes=m)
        ours = sun_position(dt, lat, lon)
        el, az = _spa(dt, lat, lon)
        if el > 1:  # 지평선 근처는 굴절 모델 차이로 제외
            worst_el = max(worst_el, abs(ours.elevation_deg - el))
            worst_az = max(worst_az, abs((ours.azimuth_deg - az + 180) % 360 - 180))
    assert worst_el < 0.05, worst_el
    assert worst_az < 0.1, worst_az


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        sun_position(datetime(2025, 8, 2, 12), *DONGSEONGRO)


def test_kst_vs_utc_same_instant():
    a = sun_position(datetime(2025, 8, 2, 12, tzinfo=KST), *DONGSEONGRO)
    b = sun_position(datetime(2025, 8, 2, 3, tzinfo=ZoneInfo("UTC")), *DONGSEONGRO)
    assert abs(a.elevation_deg - b.elevation_deg) < 1e-9


def test_solar_noon_south_and_high_in_summer():
    # 대구 경도 128.6° → 태양 남중 ≈ 12:25~12:35 KST
    p = sun_position(datetime(2025, 6, 21, 12, 30, tzinfo=KST), *DONGSEONGRO)
    assert 170 < p.azimuth_deg < 190
    assert 76 < p.elevation_deg < 78  # 90 - 35.87 + 23.44 ≈ 77.6


def test_morning_east_afternoon_west_night_below():
    am = sun_position(datetime(2025, 8, 2, 8, tzinfo=KST), *DONGSEONGRO)
    pm = sun_position(datetime(2025, 8, 2, 17, tzinfo=KST), *DONGSEONGRO)
    night = sun_position(datetime(2025, 8, 2, 21, tzinfo=KST), *DONGSEONGRO)
    assert 60 < am.azimuth_deg < 120
    assert 240 < pm.azimuth_deg < 300
    assert night.elevation_deg < 0
