"""기상청 격자 변환·발표시각 로직 테스트 (네트워크 없음)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.live.kma_grid import to_grid, to_latlon
from scripts.live.kma_time import base_candidates, fmt

KST = ZoneInfo("Asia/Seoul")


def test_grid_seoul_reference():
    # 서울시청 — 활용가이드 예시 격자(60,127)
    assert to_grid(37.5665, 126.9780) == (60, 127)


def test_grid_daegu_in_expected_range():
    # 대구 도심은 기상청 격자표상 nx 88~90, ny 89~92 부근(실제 API 응답으로 재확인)
    nx, ny = to_grid(35.8714, 128.6014)
    assert 88 <= nx <= 90 and 89 <= ny <= 92


def test_grid_roundtrip():
    for nx, ny in [(89, 90), (88, 91), (60, 127)]:
        lat, lon = to_latlon(nx, ny)
        assert to_grid(lat, lon) == (nx, ny)


def test_fcst_before_45_uses_previous_hour():
    c = base_candidates("fcst", datetime(2026, 11, 11, 14, 40, tzinfo=KST))
    assert fmt(c[0]) == ("20261111", "1330")
    assert fmt(c[1]) == ("20261111", "1230")


def test_fcst_after_45_uses_this_hour():
    assert fmt(base_candidates("fcst", datetime(2026, 11, 11, 14, 50, tzinfo=KST))[0]) == ("20261111", "1430")


def test_ncst_boundary_and_midnight():
    assert fmt(base_candidates("ncst", datetime(2026, 11, 11, 14, 39, tzinfo=KST))[0]) == ("20261111", "1300")
    assert fmt(base_candidates("ncst", datetime(2026, 11, 11, 14, 41, tzinfo=KST))[0]) == ("20261111", "1400")
    assert fmt(base_candidates("ncst", datetime(2026, 11, 12, 0, 10, tzinfo=KST))[0]) == ("20261111", "2300")


def test_utc_input_converted_to_kst():
    utc = datetime(2026, 11, 11, 5, 50, tzinfo=ZoneInfo("UTC"))  # = 14:50 KST
    assert fmt(base_candidates("fcst", utc)[0]) == ("20261111", "1430")


def test_naive_rejected():
    with pytest.raises(ValueError):
        base_candidates("fcst", datetime(2026, 11, 11, 14, 50))


# ---- 파서: 실황/예보 구분·결측 처리 (TEST DATA: 응답 형식만 모방한 가상 값) ----
from scripts.live.collect import parse_fcst, parse_ncst  # noqa: E402

G = {"gu": "중구", "sgg": "27110", "nx": 89, "ny": 90, "grid_lat": 35.85, "grid_lon": 128.61}


def test_forecast_is_labeled_forecast_with_valid_times():
    items = [{"category": "T1H", "fcstDate": "20261111", "fcstTime": t, "fcstValue": v, "baseDate": "20261111", "baseTime": "1500"}
             for t, v in (("1600", "16"), ("1700", "14"))]
    d = parse_fcst(datetime(2026, 11, 11, 15, tzinfo=KST), [(G, items)], "x")
    assert d["kind"] == "forecast" and "예보" in d["label"]
    assert d["issued_at_kst"].startswith("2026-11-11T15:00")
    assert [v[11:16] for v in d["valid_at_kst"]] == ["16:00", "17:00"]
    assert d["grids"][0]["series"]["T1H"] == [16.0, 14.0]
    assert d["grids"][0]["series"]["REH"] == [None, None]  # 응답에 없으면 null, 값을 만들지 않음


def test_nowcast_is_not_labeled_station_observation_and_missing_is_null():
    items = [{"category": "T1H", "obsrValue": "16.3"}, {"category": "REH", "obsrValue": "-998.9"}]
    d = parse_ncst(datetime(2026, 11, 11, 15, tzinfo=KST), [(G, items)], "x")
    assert d["kind"] == "nowcast" and "격자" in d["label"]
    assert d["grids"][0]["T1H"] == 16.3
    assert d["grids"][0]["REH"] is None
