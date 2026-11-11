// 공통 유틸: 데이터 로딩, 테마 토큰, 지도 배경

const cache = new Map();
export async function getJSON(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(`data/${path}`).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path);
}

export function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
export const isDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches
  && document.documentElement.dataset.theme !== 'light';

export function toast(msg, ms = 3500) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => { t.hidden = true; }, ms);
}

export const fmt = (v, d = 1, unit = '') => (v === null || v === undefined || Number.isNaN(v)) ? '—' : `${Number(v).toFixed(d)}${unit}`;
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---- 지도 배경: OpenFreeMap 벡터 타일(OpenMapTiles 스키마, OSM 데이터, 키 불필요) ----
// 배포 시 V-World 등 공식 배경으로 교체 가능(키·표시의무 확인 후). 저작자 표시는 스타일에 포함.
export function baseStyle() {
  return `https://tiles.openfreemap.org/styles/${isDark() ? 'dark' : 'positron'}`;
}
// 주제 레이어를 추가한 뒤 호출: 배경 지명 라벨을 맨 위로 올리고 한글 이름을 우선 표시
export function raiseLabels(map) {
  for (const l of map.getStyle().layers) {
    if (l.type !== 'symbol' || !l.source || l.source !== 'openmaptiles') continue;
    map.moveLayer(l.id);
    const tf = map.getLayoutProperty(l.id, 'text-field');
    if (tf) map.setLayoutProperty(l.id, 'text-field', ['coalesce', ['get', 'name:ko'], ['get', 'name']]);
  }
}
