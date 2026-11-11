"""FORECAST — 초단기예보 기온 오차(실황 대비) 집계.

수집기가 저장한 예보 아카이브(data/live/forecast/{발표}.json)의 각 유효시각 값을,
같은 시각을 기준으로 하는 초단기실황(data/live/nowcast/{기준}.json)의 같은 격자 값과 대조한다.
  오차 = 예보 T1H − 실황 T1H,  선행시간(lead) = 유효시각 − 발표시각(시간)
※ 비교 기준은 관측소 실측이 아니라 기상청 **격자 실황**이다(지상관측 미사용 결정).
※ 과거 예보를 사후에 만들지 않는다. 수집기가 실제로 받은 발표만 사용하며, 표본 수(n)를 함께 공개한다.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from scripts.common import ROOT, WEB_DATA, write_json

ARCH = ROOT / "data" / "live"


def main() -> dict:
    nc = {}
    for f in (ARCH / "nowcast").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        nc[d["base_at_kst"]] = {(g["nx"], g["ny"]): g.get("T1H") for g in d["grids"]}
    by_lead = defaultdict(list)
    by_gu = defaultdict(list)
    pairs = []
    issued_n = 0
    for f in sorted((ARCH / "forecast").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        issued_n += 1
        t0 = datetime.fromisoformat(d["issued_at_kst"])
        seen = set()
        for g in d["grids"]:
            if (g["nx"], g["ny"]) in seen:  # 같은 격자(중구·남구) 중복 집계 방지
                continue
            seen.add((g["nx"], g["ny"]))
            for k, va in enumerate(d["valid_at_kst"]):
                obs = nc.get(va, {}).get((g["nx"], g["ny"]))
                fc = g["series"]["T1H"][k]
                if obs is None or fc is None:
                    continue
                lead = round((datetime.fromisoformat(va) - t0).total_seconds() / 3600)
                e = fc - obs
                by_lead[lead].append(e)
                by_gu[g["gu"]].append(e)
                pairs.append({"issued": d["issued_at_kst"], "valid": va, "gu": g["gu"], "fcst": fc, "nowcast": obs})

    def stat(v):
        n = len(v)
        return {"n": n, "mae": round(sum(abs(x) for x in v) / n, 2), "bias": round(sum(v) / n, 2),
                "rmse": round((sum(x * x for x in v) / n) ** 0.5, 2)} if n else {"n": 0}

    out = {"kind": "analysis", "reference": "기상청 초단기실황(격자) — 관측소 실측 아님",
           "variable": "T1H 기온(°C)", "issued_count": issued_n, "pairs_total": len(pairs),
           "by_lead_h": {str(k): stat(v) for k, v in sorted(by_lead.items())},
           "by_gu": {k: stat(v) for k, v in sorted(by_gu.items())},
           "overall": stat([x for v in by_lead.values() for x in v]),
           "recent_pairs": pairs[-60:], "doc": __doc__}
    write_json(WEB_DATA / "live" / "forecast_error.json", out)
    return out


if __name__ == "__main__":
    r = main()
    print({k: r[k] for k in ("issued_count", "pairs_total", "overall", "by_lead_h")})
