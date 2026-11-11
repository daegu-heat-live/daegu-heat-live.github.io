"""웹 래스터 오버레이용 색상표(웹 범례와 동일 값 사용: web/js/legend.js)."""
from __future__ import annotations

import numpy as np

# 지표면온도: 단일 난색 계열 순차(밝음→어두움). ColorBrewer OrRd 9단계.
LST_STOPS = ["#fff7ec", "#fee8c8", "#fdd49e", "#fdbb84", "#fc8d59", "#ef6548", "#d7301f", "#b30000", "#7f0000"]
LST_RANGE = (25.0, 55.0)  # °C, 범례 고정

# NDVI: 녹색 순차 (ColorBrewer Greens), 0~0.8
NDVI_STOPS = ["#f7fcf5", "#e5f5e0", "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#006d2c", "#00441b"]
NDVI_RANGE = (0.0, 0.8)

# 잔차(관측-예측): 발산 파랑↔빨강, 중앙 회색
RESID_STOPS = ["#1c5cab", "#5598e7", "#9ec5f4", "#f0efec", "#f4a3a2", "#e66767", "#b8302f"]
RESID_RANGE = (-4.0, 4.0)


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def apply(arr: np.ndarray, stops: list[str], vrange: tuple[float, float], alpha: int = 230) -> np.ndarray:
    """float 배열(NaN=투명) → RGBA uint8."""
    lo, hi = vrange
    cols = np.array([_hex(s) for s in stops], dtype=float)
    t = np.clip((arr - lo) / (hi - lo), 0, 1) * (len(stops) - 1)
    t = np.nan_to_num(t, nan=0)
    i0 = np.floor(t).astype(int).clip(0, len(stops) - 2)
    f = (t - i0)[..., None]
    rgb = cols[i0] * (1 - f) + cols[i0 + 1] * f
    out = np.zeros(arr.shape + (4,), dtype=np.uint8)
    out[..., :3] = rgb.round().astype(np.uint8)
    out[..., 3] = np.where(np.isnan(arr), 0, alpha)
    return out
