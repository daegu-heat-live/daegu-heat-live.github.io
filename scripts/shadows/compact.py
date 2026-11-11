"""그림자 프레임 GeoJSON → 정수 차분 인코딩(웹 용량 절감, 정밀도 1e-6° ≈ 0.1 m).

frame["geometry"] (GeoJSON) 를 frame["q"] = [polygon, ...] 로 바꾼다.
  polygon = [ring, ...],  ring = [x0, y0, dx1, dy1, ...]  (정수, 단위 1e-6°, 파일 헤더 origin 기준)
브라우저 복원: web/js/app.js decodeQ()
"""
from __future__ import annotations

import json

from scripts.common import WEB_DATA, write_json

SCALE = 1_000_000


def encode(geom: dict, ox: float, oy: float) -> list:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    out = []
    for poly in polys:
        rings = []
        for ring in poly:
            flat, px, py = [], 0, 0
            for i, (x, y) in enumerate(ring):
                ix, iy = round((x - ox) * SCALE), round((y - oy) * SCALE)
                if i == 0:
                    flat += [ix, iy]
                else:
                    if ix == px and iy == py:
                        continue
                    flat += [ix - px, iy - py]
                px, py = ix, iy
            if len(flat) >= 8:
                rings.append(flat)
        if rings:
            out.append(rings)
    return out


def main() -> None:
    for p in sorted((WEB_DATA / "shadows").glob("*_20??-??-??.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("encoding") == "q1e6":
            continue
        ox = oy = None
        for fr in d["frames"]:
            g = fr.pop("geometry", None)
            if g is None:
                fr["q"] = None
                continue
            if ox is None:
                first = g["coordinates"][0][0][0] if g["type"] == "MultiPolygon" else g["coordinates"][0][0]
                ox, oy = round(first[0], 3), round(first[1], 3)
            fr["q"] = encode(g, ox, oy)
        d["encoding"] = "q1e6"
        d["origin"] = [ox, oy]
        before = p.stat().st_size
        write_json(p, d)
        print(p.name, f"{before / 1e6:.1f} MB → {p.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
