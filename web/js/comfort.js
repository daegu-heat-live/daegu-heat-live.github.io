// 체감 더위·추위(UTCI) 단계와 색 — 쉬운 말로. 값은 모두 물리 모델 추정치.
export const UTCI_CATS = [
  { lo: -Infinity, hi: -13, label: '매우 추움', color: '#1c5cab' },
  { lo: -13, hi: 0, label: '추움', color: '#5598e7' },
  { lo: 0, hi: 9, label: '쌀쌀함', color: '#9ec5f4' },
  { lo: 9, hi: 26, label: '쾌적', color: '#d9d7cf' },
  { lo: 26, hi: 32, label: '약간 더움', color: '#fdbb84' },
  { lo: 32, hi: 38, label: '더움(주의)', color: '#fc8d59' },
  { lo: 38, hi: 46, label: '매우 더움(위험)', color: '#d7301f' },
  { lo: 46, hi: Infinity, label: '극한 더위', color: '#7f0000' },
];
const catOf = (u) => UTCI_CATS.find((c) => u > c.lo && u <= c.hi);
export const utciColor = (u) => (u === null || u === undefined ? '#898781' : catOf(u)?.color ?? '#898781');
export const plainCat = (u) => (u === null || u === undefined ? '계산 불가' : catOf(u)?.label ?? '—');

export function utciLegendHtml() {
  return `<div class="ttl">예상 더위·추위 정도 <span class="tag sim">모델</span></div>
    <div class="lg-items">${UTCI_CATS.map((c) => `<span><span class="sw" style="background:${c.color}"></span>${c.label}</span>`).join('')}</div>
    <div class="meta">지도에서 <b>점선 네모 안 밝은 색 = 햇볕 드는 곳</b>, <b>어둡게 테두리 친 부분 = 건물 그림자(그늘)</b>입니다. 그림자 속 색이 그늘의 체감 단계. 갈색 덩어리는 건물.</div>`;
}
