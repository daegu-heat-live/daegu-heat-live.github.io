"""AI 분석 A — 지표면온도 공간패턴 예측·설명 (관측 데이터 기반, 인과 아님).

단위 : 240 m 격자(30 m 픽셀 8×8 평균, 양쪽 유효픽셀 ≥ 50%인 셀만)
목표 : ΔLST = 셀 LST − 해당 장면 대구 중앙값 (°C). 날짜별 절대수준 차이를 제거해 장면 간 비교 가능.
입력 : NDVI, NDBI, MNDWI, 수면비율(MNDWI>0), 1 km 주변 NDVI, 고도, 경사  (S2 2025-07-09, Copernicus DEM)
       ※ 건물밀도·높이: 대구 전역 공식 건물자료 미확보 → 입력에서 제외(OSM 불완전으로 편향 위험)
모델 : 선형회귀(기준선) vs 랜덤포레스트
검증 : ① 공간 블록(3.84 km) GroupKFold 5겹 — 무작위 픽셀 분할의 공간 누출 방지
       ② 시간 이전: 기준 장면으로 학습 → 다른 날짜 장면 전체에 적용
설명 : 블록 교차검증 테스트 폴드의 순열 중요도(통계적 관련성, 인과 아님)
"""
from __future__ import annotations

import json

import numpy as np
import rasterio
from scipy.ndimage import uniform_filter
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from scripts.common import PROCESSED, WEB_DATA, register_dataset, write_json
from scripts.raster import colormaps as cm
from scripts.raster.rasterutil import city_mask, daegu_grid, export_web_png

F = 8                  # 30 m × 8 = 240 m
BLOCK = 16             # 셀 16개 = 3.84 km 공간 블록
PRIMARY = "2025-07-25"
S2 = "20250709"
FEATURES = ["ndvi", "ndbi", "mndwi", "water_frac", "ndvi_1km", "elev_m", "slope_deg"]
LABELS = {"ndvi": "NDVI(식생)", "ndbi": "NDBI(불투수·건물 신호)", "mndwi": "MNDWI(수분)",
          "water_frac": "수면 비율", "ndvi_1km": "주변 1 km NDVI", "elev_m": "고도", "slope_deg": "경사"}


def rd(p):
    with rasterio.open(p) as s:
        return s.read(1).astype("float32")


def block(a, valid_min=0.5):
    h, w = a.shape
    H, W = h // F, w // F
    a = a[:H * F, :W * F].reshape(H, F, W, F)
    n = (~np.isnan(a)).sum((1, 3))
    with np.errstate(invalid="ignore"):
        m = np.nanmean(a, (1, 3))
    m[n < valid_min * F * F] = np.nan
    return m


def build_features(transform):
    ndvi = rd(PROCESSED / "s2" / f"ndvi_{S2}.tif")
    ndbi = rd(PROCESSED / "s2" / f"ndbi_{S2}.tif")
    mndwi = rd(PROCESSED / "s2" / f"mndwi_{S2}.tif")
    dem = rd(PROCESSED / "dem" / "cop_dem_30m.tif")
    gy, gx = np.gradient(np.nan_to_num(dem, nan=np.nanmean(dem)), 30.0)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    slope[np.isnan(dem)] = np.nan
    water = np.where(np.isnan(mndwi), np.nan, (mndwi > 0).astype("float32"))
    nd0 = np.nan_to_num(ndvi)
    w = uniform_filter((~np.isnan(ndvi)).astype("float32"), 33)
    ndvi_1km = np.where(w > 0.3, uniform_filter(nd0, 33) / np.maximum(w, 1e-6), np.nan)
    return {"ndvi": block(ndvi), "ndbi": block(ndbi), "mndwi": block(mndwi), "water_frac": block(water),
            "ndvi_1km": block(ndvi_1km), "elev_m": block(dem), "slope_deg": block(slope)}


def metrics(y, p):
    return {"mae": round(float(mean_absolute_error(y, p)), 3), "rmse": round(float(np.sqrt(mean_squared_error(y, p))), 3),
            "r2": round(float(r2_score(y, p)), 3), "n": int(len(y))}


def main() -> None:
    transform, shape = daegu_grid()
    inside = block(np.where(city_mask(transform, shape), 1.0, np.nan), 0.99)
    feats = build_features(transform)
    scenes = json.loads((WEB_DATA / "lst_scenes.json").read_text(encoding="utf-8"))["scenes"]
    dates = [s["date"] for s in scenes]
    H, W = inside.shape
    rows, cols = np.mgrid[0:H, 0:W]
    groups_all = (rows // BLOCK) * 1000 + (cols // BLOCK)
    Xall = np.stack([feats[f] for f in FEATURES], -1)
    fmask = ~np.isnan(Xall).any(-1) & ~np.isnan(inside)

    def target(date):
        lst = block(rd(PROCESSED / "lst" / f"lst_{date.replace('-', '')}.tif"))
        return lst - np.nanmedian(lst[~np.isnan(inside)])

    y_grid = target(PRIMARY)
    m = fmask & ~np.isnan(y_grid)
    X, y, g = Xall[m], y_grid[m], groups_all[m]
    models = {
        "linear": lambda: make_pipeline(StandardScaler(), LinearRegression()),
        "random_forest": lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=5, max_features=0.6,
                                                       n_jobs=-1, random_state=42),
    }
    gkf = GroupKFold(n_splits=5)
    report = {"primary_scene": PRIMARY, "target": "ΔLST(°C) = 셀 LST − 장면 대구 중앙값", "cell_m": 240,
              "block_km": BLOCK * 0.24, "features": [{"id": f, "label": LABELS[f]} for f in FEATURES],
              "n_cells": int(len(y)), "n_blocks": int(len(np.unique(g))), "cv": {}, "kind": "prediction",
              "excluded_features": "건물밀도·평균 건물높이: 대구 전역 공식 건물자료 미확보(OSM 불완전)로 제외"}
    oof = {}
    imp_acc = {f: [] for f in FEATURES}
    for name, mk in models.items():
        pred = np.zeros_like(y)
        for tr, te in gkf.split(X, y, g):
            mdl = mk().fit(X[tr], y[tr])
            pred[te] = mdl.predict(X[te])
            if name == "random_forest":
                pi = permutation_importance(mdl, X[te], y[te], n_repeats=5, random_state=0, n_jobs=-1,
                                            scoring="neg_mean_absolute_error")
                for f, v in zip(FEATURES, pi.importances_mean):
                    imp_acc[f].append(float(v))
        oof[name] = pred
        report["cv"][name] = metrics(y, pred)
        print(name, report["cv"][name])
    # 무작위 분할(누출 위험) 비교용
    rnd = np.random.default_rng(0).integers(0, 5, len(y))
    pr = np.zeros_like(y)
    for k in range(5):
        mdl = models["random_forest"]().fit(X[rnd != k], y[rnd != k])
        pr[rnd == k] = mdl.predict(X[rnd == k])
    report["cv"]["random_forest_random_split_for_reference"] = metrics(y, pr)
    report["importance"] = sorted([{"id": f, "label": LABELS[f], "mae_increase": round(float(np.mean(v)), 3)}
                                   for f, v in imp_acc.items()], key=lambda d: -d["mae_increase"])
    lin = models["linear"]().fit(X, y)
    coefs = lin[-1].coef_
    report["linear_std_coef"] = [{"id": f, "label": LABELS[f], "coef_per_sd": round(float(c), 3)} for f, c in zip(FEATURES, coefs)]

    # 전체 학습 → 시간 이전 검증
    rf = models["random_forest"]().fit(X, y)
    transfer = []
    for d in dates:
        if d == PRIMARY:
            continue
        yt = target(d)
        mt = fmask & ~np.isnan(yt)
        p = rf.predict(Xall[mt])
        transfer.append({"date": d, **metrics(yt[mt], p),
                         "baseline_mae_zero": round(float(np.mean(np.abs(yt[mt]))), 3)})
    report["temporal_transfer"] = transfer

    # 지도: 예측·잔차(OOF, 공간 블록 CV)
    t240 = rasterio.Affine(transform.a * F, 0, transform.c, 0, transform.e * F, transform.f)
    pred_g = np.full((H, W), np.nan, "float32"); pred_g[m] = oof["random_forest"]
    obs_g = np.full((H, W), np.nan, "float32"); obs_g[m] = y
    res_g = obs_g - pred_g
    div = ["#1c5cab", "#5598e7", "#9ec5f4", "#f0efec", "#f4a3a2", "#e66767", "#b8302f"]
    out = WEB_DATA / "ai"
    report["maps"] = {
        "observed": {"png": "ai/obs_anom.png", "corners": export_web_png(obs_g, t240, lambda a: cm.apply(a, div, (-8, 8)), out / "obs_anom.png", 240), "range": [-8, 8]},
        "predicted": {"png": "ai/pred_anom.png", "corners": export_web_png(pred_g, t240, lambda a: cm.apply(a, div, (-8, 8)), out / "pred_anom.png", 240), "range": [-8, 8]},
        "residual": {"png": "ai/resid.png", "corners": export_web_png(res_g, t240, lambda a: cm.apply(a, div, (-4, 4)), out / "resid.png", 240), "range": [-4, 4]},
        "stops": div,
    }
    # 산점도용 표본(관측 vs 예측)
    idx = np.random.default_rng(1).choice(len(y), min(1500, len(y)), replace=False)
    report["scatter"] = [[round(float(y[i]), 2), round(float(oof["random_forest"][i]), 2)] for i in idx]
    # NDVI 구간별 ΔLST (설명용 기술통계)
    bins = np.arange(-0.1, 0.95, 0.1)
    report["ndvi_bins"] = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        s = (X[:, 0] >= lo) & (X[:, 0] < hi)
        if s.sum() >= 10:
            report["ndvi_bins"].append({"lo": round(float(lo), 1), "hi": round(float(hi), 1), "n": int(s.sum()),
                                        "median": round(float(np.median(y[s])), 2),
                                        "q25": round(float(np.percentile(y[s], 25)), 2),
                                        "q75": round(float(np.percentile(y[s], 75)), 2)})
    write_json(out / "model_report.json", report, compact=False)
    register_dataset(
        "A01_lst_model", name="ΔLST 공간패턴 예측 모델(랜덤포레스트, 공간 블록 CV)",
        provider="본 프로젝트 분석", source_url="scripts/analysis/lst_model.py",
        license="본 프로젝트 산출물", observed_at=PRIMARY, crs="UTM 52N 240 m 격자",
        row_count={"cells": int(len(y))}, quality_note="예측(관측 아님). 상관 기반 설명이며 인과 해석 금지.",
        version="rf-v1", status="ok", layer_kind="prediction")
    print(json.dumps({k: report[k] for k in ("cv", "importance")}, ensure_ascii=False, indent=1))
    print("transfer", [(t["date"], t["mae"], t["baseline_mae_zero"]) for t in transfer])


if __name__ == "__main__":
    main()
