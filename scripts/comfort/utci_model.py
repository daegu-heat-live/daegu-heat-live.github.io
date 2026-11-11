"""야외 열쾌적성(UTCI) 물리 모델 — 일조/그늘 두 조건을 **같은 기상 입력**으로 계산한다.

계산 사슬 (모두 공개 문헌 모델, 학습 없음):
  1) 태양 위치 : scripts.shadows.solar (NOAA 알고리즘, pvlib SPA 대비 검증)
  2) 맑은 하늘 전천일사 GHI_clear : Haurwitz (1945)              — pvlib.clearsky.haurwitz
  3) 운량 보정 GHI = GHI_clear·(1 − 0.75·(N/8)^3.4) : Kasten & Czeplak (1980), N=운량(oktas)
  4) 직달(DNI)·산란 분리 : Erbs et al. (1982)                       — pvlib.irradiance.erbs
  5) 일사에 의한 평균복사온도 증가 ΔMRT : SolarCal (Arens et al. 2015; ASHRAE 55 부록)
        — pythermalcomfort.models.solar_gain, 서 있는 사람, 흡수율 0.7, 지면 반사율 0.2
        일조: f_bes=1(직달 받음), 그늘: f_bes=0(직달 차단, 산란·반사만)
  6) MRT = T_air + ΔMRT   ← **가정**: 주변 표면 장파복사 온도 = 기온
        (햇볕에 달궈진 포장면·벽면의 추가 장파복사를 반영하지 못해 일조 UTCI를 과소 추정할 수 있음)
  7) UTCI = f(T_air, MRT, v10, RH) : Bröde et al. (2012) 다항식     — pythermalcomfort.models.utci

모든 결과는 **모의(simulated) 추정값**이며 실측 체감온도가 아니다. 현장 흑구온도·복사 측정이 없어 MRT/UTCI 검증 불가.
입력이 없으면 숫자를 만들지 않고 None + quality_flag='insufficient_data' 를 반환한다.
"""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd
import pvlib
from pythermalcomfort.models import solar_gain, utci

from scripts.shadows.solar import sun_position

MODEL_VERSION = "utci-solarcal-v1"
ASW, FLOOR_REFL, POSTURE = 0.7, 0.2, "standing"
# 기상청 하늘상태(SKY) → 운량(oktas). 기상청 기준: 맑음 0~5/10, 구름많음 6~8/10, 흐림 9~10/10 의 구간 중앙값
SKY_TO_OKTA = {1: 2.0, 3: 5.6, 4: 7.6}
ASSUMPTIONS = [
    "장파복사: 주변 표면 온도 = 기온 가정(달궈진 포장·벽면 미반영 → 일조 UTCI 과소 가능)",
    "일사: Haurwitz 맑은하늘 × Kasten–Czeplak 운량 보정, Erbs 직달·산란 분리(일사 실측 아님)",
    "ΔMRT: SolarCal(서 있는 사람, 흡수율 0.7, 지면 반사율 0.2(그늘은 0), 하늘 시야 100%, 보행 방향 5방향 평균)",
    "SolarCal은 산란일사를 직달일사로부터 추정하므로 흐린 날 산란일사 효과를 과소 반영할 수 있음",
    "풍속: 기상청 10 m 풍속을 UTCI 기준 높이(10 m) 그대로 사용, 0.5~17 m/s 범위로 제한",
    "그늘: 건물 그림자 기하 모의(수목·차양 미반영)",
]


def cloud_okta(sky: int | None = None, pty: int | None = None, okta: float | None = None) -> float | None:
    if okta is not None:
        return float(okta)
    if pty not in (None, 0):
        return 8.0  # 강수 중: 흐림 처리
    return SKY_TO_OKTA.get(int(sky)) if sky is not None else None


def irradiance(when: datetime, lat: float, lon: float, okta: float | None):
    sp = sun_position(when, lat, lon)
    if sp.elevation_deg <= 0:
        return sp, 0.0, 0.0, 0.0
    if okta is None:
        return sp, None, None, None
    zen = pd.Series([90 - sp.elevation_deg])
    ghi_clear = float(pvlib.clearsky.haurwitz(zen)["ghi"].iloc[0])
    ghi = ghi_clear * (1 - 0.75 * (min(max(okta, 0), 8) / 8) ** 3.4)
    doy = pd.DatetimeIndex([pd.Timestamp(when)]).dayofyear
    e = pvlib.irradiance.erbs(pd.Series([ghi]), zen, doy)
    dni, dhi = (float(pd.Series(e[k]).iloc[0]) for k in ("dni", "dhi"))
    return sp, ghi, dni, dhi


def compute(t_air, rh, wind10, when: datetime, lat: float, lon: float,
            sky=None, pty=None, okta=None) -> dict:
    """같은 기상 입력에 대해 일조/그늘 UTCI를 계산."""
    out = {"model_version": MODEL_VERSION, "provenance": "simulated", "valid_at_kst": when.isoformat(),
           "inputs": {"air_temp_c": t_air, "rh_pct": rh, "wind10_ms": wind10, "sky": sky, "pty": pty},
           "sun": None, "shade": None, "delta_utci": None, "flags": []}
    if any(v is None for v in (t_air, rh, wind10)):
        out["quality_flag"] = "insufficient_data"
        out["flags"].append("기온·습도·풍속 중 결측")
        return out
    ok = cloud_okta(sky, pty, okta)
    sp, ghi, dni, dhi = irradiance(when, lat, lon, ok)
    out["inputs"].update({"cloud_okta": ok, "sun_elevation_deg": round(sp.elevation_deg, 2),
                          "ghi_wm2": None if ghi is None else round(ghi, 1),
                          "dni_wm2": None if dni is None else round(dni, 1)})
    v = float(wind10)
    if v < 0.5:
        out["flags"].append("풍속 0.5 m/s 미만 → 0.5로 제한(UTCI 적용범위)")
    if v > 17:
        out["flags"].append("풍속 17 m/s 초과 → 17로 제한")
    v = min(max(v, 0.5), 17)
    if sp.elevation_deg <= 0:
        out["flags"].append("야간: 일사 없음, 일조/그늘 동일")
    elif dni is None:
        out["quality_flag"] = "insufficient_data"
        out["flags"].append("운량(하늘상태) 없음 → 일사 추정 불가")
        return out

    def one(f_bes):
        d_mrt = 0.0
        if sp.elevation_deg > 0 and dni > 0:
            # 보행자 방향을 알 수 없으므로 태양 대비 상대방위 0~180° 다섯 방향 평균
            # 그늘(f_bes=0)에서는 주변 지면도 그늘로 보고 지면 반사 일사 제외
            vals = [float(solar_gain(sol_altitude=sp.elevation_deg, sharp=sh, sol_radiation_dir=dni, sol_transmittance=1,
                                     f_svv=1, f_bes=f_bes, asw=ASW, posture=POSTURE,
                                     floor_reflectance=FLOOR_REFL if f_bes > 0 else 0.0).delta_mrt)
                    for sh in (0, 45, 90, 135, 180)]
            d_mrt = sum(vals) / len(vals)
        mrt = t_air + d_mrt
        r = utci(tdb=t_air, tr=mrt, v=v, rh=rh, limit_inputs=True)
        u = float(r.utci)
        if math.isnan(u):
            return {"mrt_c": round(mrt, 1), "delta_mrt": round(d_mrt, 1), "utci_c": None, "category": "적용범위 밖"}
        return {"mrt_c": round(mrt, 1), "delta_mrt": round(d_mrt, 1), "utci_c": round(u, 1),
                "category": category_ko(u)}

    out["sun"], out["shade"] = one(1.0), one(0.0)
    if out["sun"]["utci_c"] is not None and out["shade"]["utci_c"] is not None:
        out["delta_utci"] = round(out["sun"]["utci_c"] - out["shade"]["utci_c"], 1)
    out["quality_flag"] = "estimated"
    return out


# UTCI 열스트레스 범주(Bröde et al. 2012)
_CATS = [(46, "극한 더위 스트레스"), (38, "매우 강한 더위 스트레스"), (32, "강한 더위 스트레스"),
         (26, "보통 더위 스트레스"), (9, "열 스트레스 없음"), (0, "약한 추위 스트레스"),
         (-13, "보통 추위 스트레스"), (-27, "강한 추위 스트레스"), (-40, "매우 강한 추위 스트레스")]


def category_ko(u: float) -> str:
    for lo, name in _CATS:
        if u > lo:
            return name
    return "극한 추위 스트레스"
