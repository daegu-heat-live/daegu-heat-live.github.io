"""LIVE·FORECAST 수집기 — 기상청 단기예보 조회서비스(공공데이터포털 15084084).

  초단기실황 getUltraSrtNcst → LIVE  (구·군 대표 격자 실황값, 관측소 실측 아님)
  초단기예보 getUltraSrtFcst → FORECAST (발표시각 issued_at / 유효시각 valid_at 분리)

인증키는 .env 의 DATA_GO_KR_SERVICE_KEY(일반 인증키, Decoding)에서만 읽고 브라우저로 보내지 않는다.
브라우저는 이 스크립트가 쓴 정적 JSON(web/data/live/*.json)만 읽는다.

  python -m scripts.live.collect            # 1회 수집
  python -m scripts.live.collect --loop 600 # 10분마다 반복(새 발표가 없으면 중복 저장하지 않음)
  python -m scripts.live.collect --backfill 15 # 지난 15시간 실황 채우기(최근 1일 이내만 제공)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import geopandas as gpd
import requests

from scripts.common import PROCESSED, ROOT, USER_AGENT, WEB_DATA, env, register_dataset, write_json
from scripts.live.kma_grid import to_grid, to_latlon
from scripts.live.kma_time import KST, base_candidates, fmt

BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
CATS = {"T1H": ("기온", "°C"), "REH": ("습도", "%"), "WSD": ("풍속", "m/s"), "VEC": ("풍향", "deg"),
        "RN1": ("1시간 강수량", "mm"), "PTY": ("강수형태", "code"), "SKY": ("하늘상태", "code")}
LIVE_WEB = WEB_DATA / "live"
ARCHIVE = ROOT / "data" / "live"
SOURCE_URL = "https://www.data.go.kr/data/15084084/openapi.do"


def rep_grids() -> list[dict]:
    """구·군 대표 격자: 각 구·군 폴리곤 내부 대표점(representative_point)이 속한 격자."""
    gu = gpd.read_file(PROCESSED / "boundaries" / "daegu_gu_5179.gpkg")
    pts = gu.geometry.representative_point().to_crs("EPSG:4326")
    out = []
    for name, code, p in zip(gu["sggnm"], gu["sgg"], pts):
        nx, ny = to_grid(p.y, p.x)
        glat, glon = to_latlon(nx, ny)
        out.append({"gu": name, "sgg": code, "nx": nx, "ny": ny, "grid_lat": round(glat, 5), "grid_lon": round(glon, 5)})
    return out


def call(op: str, key: str, base_dt: datetime, nx: int, ny: int) -> tuple[str, list]:
    d, t = fmt(base_dt)
    params = {"serviceKey": key, "pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
              "base_date": d, "base_time": t, "nx": nx, "ny": ny}
    r = requests.get(f"{BASE}/{op}", params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    try:
        j = r.json()
    except ValueError:
        # 인증 오류 등은 XML 로 오는 경우가 있다
        raise RuntimeError(f"JSON 아님(HTTP {r.status_code}): {r.text[:200]}")
    head = j["response"]["header"]
    code = head.get("resultCode")
    if code == "03":  # NO_DATA — 아직 미발행
        return "NO_DATA", []
    if code != "00":
        raise RuntimeError(f"{op} resultCode={code} {head.get('resultMsg')}")
    return "OK", j["response"]["body"]["items"]["item"]


def fetch(kind: str, key: str, grids: list[dict], now: datetime):
    op = {"ncst": "getUltraSrtNcst", "fcst": "getUltraSrtFcst"}[kind]
    errors = []
    for base_dt in base_candidates(kind, now, n=3):
        rows, ok = [], True
        for g in grids:
            try:
                st, items = call(op, key, base_dt, g["nx"], g["ny"])
            except Exception as e:  # noqa: BLE001 — 오류를 상태 파일에 그대로 남긴다
                errors.append(f"{g['gu']}: {e}")
                ok = False
                break
            if st == "NO_DATA":
                ok = False
                break
            rows.append((g, items))
        if ok:
            # 발표시각은 요청값이 아니라 응답의 baseDate/baseTime 을 기록한다
            # (실측: 초단기예보 15:30 요청 → 응답 baseTime 1500)
            it0 = rows[0][1][0]
            resp_dt = datetime.strptime(it0["baseDate"] + it0["baseTime"], "%Y%m%d%H%M").replace(tzinfo=KST)
            return resp_dt, rows, errors
        if errors:
            break
    return None, [], errors


def parse_ncst(base_dt, rows, received):
    grids = []
    for g, items in rows:
        v = {it["category"]: _num(it["obsrValue"]) for it in items if it["category"] in CATS}
        grids.append({**g, **{k: v.get(k) for k in CATS}})
    return {"kind": "nowcast", "label": "기상청 초단기실황(격자 실황값)", "op": "getUltraSrtNcst",
            "base_at_kst": base_dt.isoformat(), "received_at_utc": received, "grids": grids}


def parse_fcst(base_dt, rows, received):
    valid = sorted({f"{it['fcstDate']}{it['fcstTime']}" for _, items in rows for it in items})
    valid_iso = [datetime.strptime(v, "%Y%m%d%H%M").replace(tzinfo=KST).isoformat() for v in valid]
    grids = []
    for g, items in rows:
        series = {k: [None] * len(valid) for k in CATS}
        for it in items:
            if it["category"] in CATS:
                series[it["category"]][valid.index(f"{it['fcstDate']}{it['fcstTime']}")] = _num(it["fcstValue"])
        grids.append({**g, "series": series})
    return {"kind": "forecast", "label": "기상청 초단기예보", "op": "getUltraSrtFcst",
            "issued_at_kst": base_dt.isoformat(), "received_at_utc": received,
            "valid_at_kst": valid_iso, "grids": grids}


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    # 기상청 결측 표기(-998.9, 900 이상 등)
    return None if x <= -900 or x >= 900 else x


def archive(kind: str, doc: dict, base_key: str) -> bool:
    """같은 발표시각은 한 번만 저장. 새로 저장했으면 True."""
    d = ARCHIVE / kind
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{base_key}.json"
    if p.exists():
        return False
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return True


def build_today():
    """오늘(KST) 수집된 실황을 구·군별 시계열로 묶는다(LIVE 차트용)."""
    today = datetime.now(KST).strftime("%Y%m%d")
    files = sorted((ARCHIVE / "nowcast").glob(f"{today}*.json"))
    series = {}
    times = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        times.append(d["base_at_kst"])
        for g in d["grids"]:
            series.setdefault(g["gu"], []).append(g.get("T1H"))
    write_json(LIVE_WEB / "today.json", {"kind": "nowcast", "date": today, "times_kst": times, "T1H": series})


def run_once() -> dict:
    LIVE_WEB.mkdir(parents=True, exist_ok=True)
    key = env("DATA_GO_KR_SERVICE_KEY")
    now = datetime.now(KST)
    status = {"checked_at_kst": now.isoformat(timespec="seconds"), "key_configured": bool(key),
              "source": "기상청 단기예보 조회서비스(공공데이터포털)", "source_url": SOURCE_URL, "feeds": {}}
    prev = {}
    sp = LIVE_WEB / "status.json"
    if sp.exists():
        prev = json.loads(sp.read_text(encoding="utf-8")).get("feeds", {})
    grids = rep_grids()
    write_json(LIVE_WEB / "grids.json", {"note": "구·군 대표점이 속한 기상청 5 km 격자(격자 중심 좌표)", "grids": grids}, compact=False)
    if not key:
        status["message"] = "인증키 미설정 — .env 에 DATA_GO_KR_SERVICE_KEY 를 넣고 수집기를 실행하세요. 실측·예보 자료 없음."
        write_json(sp, status, compact=False)
        return status
    received = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for kind, parser, out in (("ncst", parse_ncst, "nowcast_latest.json"), ("fcst", parse_fcst, "forecast_latest.json")):
        base_dt, rows, errors = fetch(kind, key, grids, now)
        feed = {"ok": base_dt is not None, "errors": errors[:5]}
        if base_dt is not None:
            doc = parser(base_dt, rows, received)
            write_json(LIVE_WEB / out, doc)
            feed["new"] = archive("nowcast" if kind == "ncst" else "forecast", doc, fmt(base_dt)[0] + fmt(base_dt)[1])
            feed["base_at_kst"] = base_dt.isoformat()
            feed["received_at_utc"] = received
            feed["lag_min"] = round((now - base_dt).total_seconds() / 60)
        else:
            # 실패 시 마지막 정상 자료 시각을 유지해 화면에 표시
            feed["last_ok_base_at_kst"] = prev.get(kind, {}).get("base_at_kst") or prev.get(kind, {}).get("last_ok_base_at_kst")
        status["feeds"][kind] = feed
    build_today()
    # 화면('지금')에 필요한 계산만: 구·군 체감, 시범구역 오늘 체감. 오늘 그림자가 없으면 백그라운드 계산 시작
    try:
        from scripts.live.daily_shadows import start_if_needed
        status["daily_shadows"] = start_if_needed()
    except Exception as e:  # noqa: BLE001
        status["daily_shadows"] = f"error: {e}"
    mods = [("utci", "scripts.comfort.live_utci")]
    if status.get("daily_shadows") == "ready":
        mods.append(("aoi_utci", "scripts.comfort.aoi_utci"))
    for name, mod in mods:
        try:
            __import__(mod, fromlist=["main"]).main()
        except Exception as e:  # noqa: BLE001 — 부가 분석 실패가 수집을 막지 않도록
            status[f"{name}_note"] = str(e)
    write_json(sp, status, compact=False)
    if any(f.get("ok") for f in status["feeds"].values()):
        register_dataset(
            "WX02_WX03_kma_ultrashort", name="기상청 초단기실황(지금 날씨)·초단기예보(구름 상태)",
            provider="기상청 (공공데이터포털 단기예보 조회서비스)", source_url=SOURCE_URL,
            license="공공데이터포털 이용허락범위(출처표시)", crs="기상청 5 km LCC 격자 → 격자중심 위경도",
            observed_at=status["feeds"].get("ncst", {}).get("base_at_kst"),
            fields=list(CATS), row_count={"grids": len(grids), "unique_grids": len({(g['nx'], g['ny']) for g in grids})},
            quality_note="구·군 대표 격자값(관측소 실측 아님). 발표시각은 응답 baseDate/baseTime 기준. 결측(-998.9 등)은 null.",
            status="ok", layer_kind="observed")
    return status


def backfill(hours: int):
    """지난 N시간의 초단기실황을 아카이브에 채운다(서비스는 최근 1일 이내 기준시각만 제공)."""
    from datetime import timedelta
    key = env("DATA_GO_KR_SERVICE_KEY")
    grids = rep_grids()
    uniq = {(g["nx"], g["ny"]): g for g in grids}
    latest = base_candidates("ncst", datetime.now(KST), 1)[0]
    received = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for h in range(1, hours + 1):
        b = latest - timedelta(hours=h)
        if (ARCHIVE / "nowcast" / f"{fmt(b)[0]}{fmt(b)[1]}.json").exists():
            continue
        cache, rows = {}, []
        try:
            for xy, g in uniq.items():
                st, items = call("getUltraSrtNcst", key, b, g["nx"], g["ny"])
                if st != "OK":
                    raise RuntimeError("NO_DATA")
                cache[xy] = items
        except Exception as e:  # noqa: BLE001
            print("skip", b.isoformat(), e)
            continue
        rows = [(g, cache[(g["nx"], g["ny"])]) for g in grids]
        archive("nowcast", parse_ncst(b, rows, received), fmt(b)[0] + fmt(b)[1])
        print("backfilled nowcast", b.isoformat())
    # 같은 기간의 초단기예보 발표분(기상청이 실제 발표한 값)을 다시 받아 오차 분석 표본으로 쓴다
    for h in range(0, hours + 1):
        b = (latest - timedelta(hours=h)).replace(minute=30)
        try:
            cache = {}
            for xy, g in uniq.items():
                st, items = call("getUltraSrtFcst", key, b, g["nx"], g["ny"])
                if st != "OK":
                    raise RuntimeError("NO_DATA")
                cache[xy] = items
        except Exception as e:  # noqa: BLE001
            print("skip fcst", b.isoformat(), e)
            continue
        it0 = next(iter(cache.values()))[0]
        rb = datetime.strptime(it0["baseDate"] + it0["baseTime"], "%Y%m%d%H%M").replace(tzinfo=KST)
        rows = [(g, cache[(g["nx"], g["ny"])]) for g in grids]
        if archive("forecast", parse_fcst(rb, rows, received), fmt(rb)[0] + fmt(rb)[1]):
            print("backfilled forecast", rb.isoformat())
    build_today()
    from scripts.analysis.forecast_error import main as fe
    fe()


def main():
    if "--backfill" in sys.argv:
        backfill(int(sys.argv[sys.argv.index("--backfill") + 1]))
        return
    if "--loop" in sys.argv:
        sec = int(sys.argv[sys.argv.index("--loop") + 1])
        while True:
            print(json.dumps(run_once(), ensure_ascii=False)[:300], flush=True)
            time.sleep(sec)
    else:
        print(json.dumps(run_once(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
