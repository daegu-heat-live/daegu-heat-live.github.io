"""UTCI 물리 모델 동작 검증 — 입력값은 TEST DATA(가상 기상 조건)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.comfort.utci_model import category_ko, cloud_okta, compute

KST = ZoneInfo("Asia/Seoul")
LAT, LON = 35.8693, 128.596
NOON = datetime(2025, 7, 25, 13, tzinfo=KST)


def test_missing_input_returns_insufficient_not_number():
    r = compute(None, 50, 1, NOON, LAT, LON, sky=1)
    assert r["quality_flag"] == "insufficient_data" and r["sun"] is None and r["delta_utci"] is None


def test_unknown_cloud_daytime_is_insufficient():
    r = compute(30, 50, 1, NOON, LAT, LON)  # 운량 없음
    assert r["quality_flag"] == "insufficient_data"


def test_night_sun_equals_shade():
    r = compute(26, 80, 1, datetime(2025, 7, 25, 23, tzinfo=KST), LAT, LON, sky=1)
    assert r["sun"]["utci_c"] == r["shade"]["utci_c"] and r["delta_utci"] == 0
    assert r["sun"]["mrt_c"] == 26  # 야간 MRT = 기온(가정)


def test_clear_day_sun_hotter_than_shade_and_shade_not_below_air_mrt():
    r = compute(30, 50, 1.5, NOON, LAT, LON, sky=1)
    assert r["sun"]["utci_c"] > r["shade"]["utci_c"]
    assert r["shade"]["mrt_c"] >= 30
    assert r["provenance"] == "simulated"


def test_overcast_reduces_sun_shade_difference():
    clear = compute(30, 50, 1.5, NOON, LAT, LON, sky=1)["delta_utci"]
    cloudy = compute(30, 50, 1.5, NOON, LAT, LON, sky=4)["delta_utci"]
    rain = compute(30, 50, 1.5, NOON, LAT, LON, sky=1, pty=1)["delta_utci"]
    assert cloudy < clear and rain <= cloudy


def test_wind_clamped_and_flagged():
    r = compute(30, 50, 0.0, NOON, LAT, LON, sky=1)
    assert any("0.5" in f for f in r["flags"])


def test_categories_and_cloud_mapping():
    assert category_ko(40) == "매우 강한 더위 스트레스"
    assert category_ko(20) == "열 스트레스 없음"
    assert category_ko(-20) == "강한 추위 스트레스"
    assert cloud_okta(sky=1) < cloud_okta(sky=3) < cloud_okta(sky=4)
    assert cloud_okta(sky=1, pty=1) == 8.0
