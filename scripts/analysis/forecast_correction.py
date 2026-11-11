"""AI(B안) — 기상청 초단기예보 기온 오차 보정 모델의 학습·검증.

정답(라벨): 같은 유효시각·같은 격자의 기상청 **초단기실황 T1H** (관측소 실측 아님 — 지상관측 미사용 결정)
입력: 예보 T1H, 선행시간(h), 유효시각의 시(sin/cos), 격자 번호, 직전 오차(발표 시점에 알 수 있는 값:
      바로 전 발표의 +1h 예보가 이번 발표 시각에 보인 오차)
모델: RandomForest 회귀로 '오차'를 예측 → 보정 예보 = 예보 − 예측 오차
기준선: ① 원 예보 ② 학습기간 평균 편향 보정
검증: **발표시각 기준 시간 분할**(앞 70% 발표 학습, 뒤 30% 평가) — 미래 정보 누출 방지
적용 기준: 평가 표본 ≥ 300 쌍, 학습 기간 ≥ 3일, 그리고 두 기준선보다 MAE 개선일 때만 'applicable'.
          미충족이면 수치는 공개하되 '실험(적용 안 함)'으로 표시한다.
"""
from __future__ import annotations

import json
import math
from datetime import datetime

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from scripts.common import ROOT, WEB_DATA, write_json

ARCH = ROOT / "data" / "live"
MIN_TEST, MIN_DAYS = 300, 3


def load_pairs():
    nc = {}
    for f in (ARCH / "nowcast").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        nc[d["base_at_kst"]] = {(g["nx"], g["ny"]): g.get("T1H") for g in d["grids"]}
    issues = []
    for f in sorted((ARCH / "forecast").glob("*.json")):
        issues.append(json.loads(f.read_text(encoding="utf-8")))
    issues.sort(key=lambda d: d["issued_at_kst"])
    grid_ids = {}
    rows, prev_err = [], {}
    for d in issues:
        t0 = datetime.fromisoformat(d["issued_at_kst"])
        seen = set()
        for g in d["grids"]:
            xy = (g["nx"], g["ny"])
            if xy in seen:
                continue
            seen.add(xy)
            gid = grid_ids.setdefault(xy, len(grid_ids))
            for k, va in enumerate(d["valid_at_kst"]):
                fc = g["series"]["T1H"][k]
                obs = nc.get(va, {}).get(xy)
                vt = datetime.fromisoformat(va)
                lead = round((vt - t0).total_seconds() / 3600)
                if fc is None:
                    continue
                if lead == 1 and obs is not None:
                    prev_err[(xy, va)] = fc - obs  # 이 발표의 +1h 오차(유효시각에 확인됨)
                rows.append({"issued": d["issued_at_kst"], "valid": va, "xy": xy, "gid": gid, "lead": lead, "fc": fc,
                             "obs": obs, "hs": math.sin(2 * math.pi * vt.hour / 24), "hc": math.cos(2 * math.pi * vt.hour / 24),
                             "last_err": prev_err.get((xy, d["issued_at_kst"]))})
    return [r for r in rows if r["obs"] is not None], issues


def main():
    rows, issues = load_pairs()
    out = {"kind": "ai_experiment", "label": "기상청 초단기실황 T1H(격자)", "doc": __doc__, "n_pairs": len(rows),
           "n_issues": len(issues), "status": "insufficient", "applied": False}
    if len(rows) < 50:
        out["message"] = "대조 가능한 예보-실황 쌍이 50개 미만 — 학습하지 않음"
        write_json(WEB_DATA / "live" / "forecast_correction.json", out, compact=False)
        return out
    iss = sorted({r["issued"] for r in rows})
    cut = iss[int(len(iss) * 0.7)]
    tr = [r for r in rows if r["issued"] < cut]
    te = [r for r in rows if r["issued"] >= cut]
    # 평가 쌍의 유효시각이 학습 발표 이후여야 함(누출 방지: 학습 라벨은 평가 첫 발표 전까지만)
    tr = [r for r in tr if r["valid"] <= cut]
    feat = lambda r: [r["fc"], r["lead"], r["hs"], r["hc"], r["gid"], r["last_err"] if r["last_err"] is not None else 0.0,
                      1.0 if r["last_err"] is not None else 0.0]
    Xtr, ytr = np.array([feat(r) for r in tr]), np.array([r["fc"] - r["obs"] for r in tr])
    Xte, yte_obs, fte = np.array([feat(r) for r in te]), np.array([r["obs"] for r in te]), np.array([r["fc"] for r in te])
    rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=5, random_state=0, n_jobs=-1).fit(Xtr, ytr)
    pred = {"raw": fte, "bias": fte - ytr.mean(), "rf": fte - rf.predict(Xte)}

    def m(p):
        e = p - yte_obs
        return {"mae": round(float(np.abs(e).mean()), 3), "rmse": round(float(np.sqrt((e ** 2).mean())), 3)}
    ev = {k: m(v) for k, v in pred.items()}
    by_lead = {}
    for L in sorted({r["lead"] for r in te}):
        idx = np.array([r["lead"] == L for r in te])
        by_lead[str(L)] = {k: round(float(np.abs(v[idx] - yte_obs[idx]).mean()), 3) for k, v in pred.items()} | {"n": int(idx.sum())}
    days = (datetime.fromisoformat(cut) - datetime.fromisoformat(iss[0])).total_seconds() / 86400
    better = ev["rf"]["mae"] < min(ev["raw"]["mae"], ev["bias"]["mae"])
    ok = len(te) >= MIN_TEST and days >= MIN_DAYS and better
    out.update({
        "train_period": [iss[0], cut], "test_period": [cut, iss[-1]], "train_days": round(days, 2),
        "n_train": len(tr), "n_test": len(te), "eval": ev, "eval_by_lead": by_lead,
        "status": "applicable" if ok else "insufficient", "applied": ok,
        "criteria": {"min_test_pairs": MIN_TEST, "min_train_days": MIN_DAYS, "must_beat_baselines": True},
        "message": ("기준 충족 — 보정 예보를 '실험' 시리즈로 표시 가능" if ok else
                    f"실험 결과(적용 안 함): 평가 {len(te)}쌍·학습 {days:.1f}일 — 기준(평가 ≥{MIN_TEST}쌍, 학습 ≥{MIN_DAYS}일, 기준선보다 개선) "
                    + ("미달" if not better or len(te) < MIN_TEST or days < MIN_DAYS else "")),
    })
    write_json(WEB_DATA / "live" / "forecast_correction.json", out, compact=False)
    return out


if __name__ == "__main__":
    r = main()
    print({k: r.get(k) for k in ("n_pairs", "n_train", "n_test", "train_days", "eval", "status", "message")})
