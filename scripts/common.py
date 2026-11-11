"""공통 경로·좌표계·데이터 카탈로그 유틸리티.

모든 스크립트는 프로젝트 루트에서 `python -m scripts.<pkg>.<module>` 로 실행한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
CATALOG = ROOT / "data" / "catalog.json"
WEB_DATA = ROOT / "web" / "data"

# 작업 좌표계: 미터 단위 투영 (Korea 2000 / Unified CS)
WORK_CRS = "EPSG:5179"
WEB_CRS = "EPSG:4326"

USER_AGENT = "daegu-heat-atlas/0.1 (public-data contest prototype)"

for p in (RAW, PROCESSED, WEB_DATA):
    p.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_catalog() -> dict:
    if CATALOG.exists():
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    return {"generated_by": "scripts/common.py", "datasets": {}}


def register_dataset(dataset_id: str, **meta) -> None:
    """data/catalog.json 에 데이터셋 메타데이터를 기록(덮어쓰기)한다.

    필수 권장 키: name, provider, source_url, license, retrieved_at,
    observed_at|valid_period, crs, fields, row_count, null_rate, quality_note, version, status
    """
    cat = load_catalog()
    entry = cat["datasets"].get(dataset_id, {})
    entry.update(meta)
    entry.setdefault("retrieved_at", now_iso())
    entry["updated_at"] = now_iso()
    cat["datasets"][dataset_id] = entry
    CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")
    # 웹에서도 같은 카탈로그를 읽는다
    (WEB_DATA / "catalog.json").write_text(
        json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_json(path: Path, obj, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def env(name: str, default: str | None = None) -> str | None:
    """.env 파일(있으면)과 환경변수에서 값을 읽는다. 키는 저장소에 커밋하지 않는다."""
    envfile = ROOT / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    return os.environ.get(name, default)
