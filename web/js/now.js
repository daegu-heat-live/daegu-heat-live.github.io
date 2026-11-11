// DAEGU HEAT LIVE — "지금" 한 화면: 실시간 그림자 + 위치별 예상 더위·추위(모델)
import { css, fmt, esc, baseStyle, raiseLabels, toast } from './util.js';
import { utciColor, plainCat, utciLegendHtml } from './comfort.js';
import { initMethods } from './methods.js';

const $ = (id) => document.getElementById(id);
const S = { aois: [], aoi: null, today: null, frames: {}, comfort: {}, idx: 0, followNow: true, live: null };
let map;

const todayKst = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' });
const hmKst = (d = new Date()) => d.toLocaleTimeString('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false });
const DIRS = ['북', '북동', '동', '남동', '남', '남서', '서', '북서'];
const dirKo = (az) => DIRS[Math.round(((az % 360) + 360) % 360 / 45) % 8];
const mins = (hm) => +hm.slice(0, 2) * 60 + +hm.slice(3, 5);

async function fresh(path) {
  try {
    const r = await fetch(`data/${path}?t=${Date.now()}`, { cache: 'no-store' });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

function decodeQ(q, ox, oy) {
  return {
    type: 'MultiPolygon',
    coordinates: q.map((poly) => poly.map((r) => {
      let x = r[0], y = r[1];
      const pts = [[ox + x / 1e6, oy + y / 1e6]];
      for (let i = 2; i < r.length; i += 2) { x += r[i]; y += r[i + 1]; pts.push([ox + x / 1e6, oy + y / 1e6]); }
      return pts;
    })),
  };
}

// ---------------- 상태바 ----------------
async function refreshStatus() {
  const st = await fresh('live/status.json');
  const n = st?.feeds?.ncst;
  const el = $('statusbar');
  if (!st || !st.key_configured) { el.innerHTML = '<span class="dot" style="background:#898781"></span>실시간 날씨 자료 없음'; return; }
  const base = n?.base_at_kst || n?.last_ok_base_at_kst;
  const lagMin = base ? Math.round((Date.now() - new Date(base)) / 60000) : null;
  const ok = n?.ok && lagMin !== null && lagMin < 120;
  el.innerHTML = `<span class="dot" style="background:${ok ? '#0ca30c' : '#d03b3b'}"></span>기상청 실황 <b>${base ? hmKst(new Date(base)) : '—'}</b> 기준 · ${ok ? '정상' : '<b>지연</b>'}`;
}

// ---------------- 데이터 ----------------
async function loadDay() {
  S.today = todayKst();
  const summ = await fresh('shadows/shadow_summary.json');
  S.aois = summ?.aois || [];
  S.hasToday = S.aois.length && S.aois.every((a) => a.dates.some((d) => d.date === S.today));
  if (!S.hasToday) return;
  await Promise.all(S.aois.map(async (a) => {
    const d = await fresh(`shadows/${a.id}_${S.today}.json`);
    if (d?.encoding === 'q1e6') { const [ox, oy] = d.origin; d.frames.forEach((f) => { f.geometry = f.q ? decodeQ(f.q, ox, oy) : null; }); }
    S.frames[a.id] = d?.frames || [];
  }));
  await loadComfort();
}
async function loadComfort() {
  await Promise.all(S.aois.map(async (a) => { S.comfort[a.id] = await fresh(`comfort/${a.id}_${S.today}.json`); }));
  S.live = await fresh('comfort/live_utci.json');
}
function nowIdx() {
  const fr = S.frames[S.aoi] || [];
  if (!fr.length) return 0;
  const m = mins(hmKst());
  let best = 0;
  fr.forEach((f, i) => { if (Math.abs(mins(f.time) - m) < Math.abs(mins(fr[best].time) - m)) best = i; });
  return best;
}

// ---------------- 지도 ----------------
async function initMap() {
  map = new maplibregl.Map({ container: 'map', style: baseStyle(), center: [128.6, 35.869], zoom: 15, attributionControl: { compact: true }, maxZoom: 18.5 });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
  await new Promise((r) => (map.isStyleLoaded() ? r() : map.once('style.load', r)));
  const aoiGeo = await fresh('aois.geojson');
  S.aoiGeo = aoiGeo;
  map.addSource('sun', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({ id: 'sun', type: 'fill', source: 'sun', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.4 } });
  map.addSource('shadow', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  // 그림자: 그늘 체감 색 위에 어두운 덧칠 + 테두리 → 모양과 움직임이 또렷하게
  map.addLayer({ id: 'shadow', type: 'fill', source: 'shadow', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.95 } });
  map.addLayer({ id: 'shadow-dark', type: 'fill', source: 'shadow', paint: { 'fill-color': '#1b2a40', 'fill-opacity': 0.38 } });
  map.addLayer({ id: 'shadow-line', type: 'line', source: 'shadow', paint: { 'line-color': '#1b2a40', 'line-width': 0.8, 'line-opacity': 0.8 } });
  const bfc = { type: 'FeatureCollection', features: [] };
  for (const a of S.aois) {
    const g = await fresh(`shadows/${a.id}_buildings.geojson`);
    (g?.features || []).forEach((f) => bfc.features.push(f));
  }
  map.addSource('buildings', { type: 'geojson', data: bfc });
  map.addLayer({ id: 'buildings', type: 'fill', source: 'buildings', minzoom: 13,
    paint: { 'fill-color': '#8c7b65', 'fill-opacity': ['case', ['in', ['get', 'height_status'], ['literal', ['missing', 'invalid']]], 0.45, 0.95] } });
  map.addSource('aois', { type: 'geojson', data: aoiGeo });
  map.addLayer({ id: 'aois', type: 'line', source: 'aois', paint: { 'line-color': css('--ink'), 'line-width': 2, 'line-dasharray': [2, 1.5] } });
  raiseLabels(map);
  map.on('click', onClick);
}

function fitAoi() {
  const a = S.aois.find((x) => x.id === S.aoi);
  if (a) { const [w, s, e, n] = a.bbox; map.fitBounds([[w, s], [e, n]], { padding: 20, duration: 600 }); }
}

// ---------------- 그리기 ----------------
function render() {
  const fr = S.frames[S.aoi]?.[S.idx];
  const cf = S.comfort[S.aoi]?.frames?.[S.idx];
  $('time-slider').value = S.idx;
  const isNowFrame = S.idx === nowIdx() && mins(hmKst()) >= 6 * 60 && mins(hmKst()) <= 20 * 60 + 15;
  $('time-big').innerHTML = fr ? `${fr.time} ${isNowFrame ? '<span class="tag obs">지금</span>' : '<span class="meta">(오늘)</span>'}` : '--:--';
  $('sun-dir').innerHTML = !fr ? '' : fr.is_night ? '🌙 해가 진 시간 — 그림자 없음'
    : `<span class="arrow" title="해 방향" style="transform:rotate(${fr.sun_azimuth_deg}deg)">☀</span>
       해: <b>${dirKo(fr.sun_azimuth_deg)}</b>쪽 하늘 ${fmt(fr.sun_elevation_deg, 0)}° 높이
       → 그림자는 <span class="arrow sh" style="transform:rotate(${(fr.sun_azimuth_deg + 180) % 360}deg)">↑</span><b>${dirKo((fr.sun_azimuth_deg + 180) % 360)}</b>쪽,
       길이 = 건물 높이의 <b>${fmt(fr.shadow_length_per_m, 1)}배</b>${fr.low_sun ? ' (해가 매우 낮음)' : ''}`;

  // 지도: 구역별 햇볕(네모)·그늘(그림자) 색
  const feats = [], suns = [];
  for (const a of S.aois) {
    const f = S.frames[a.id]?.[S.idx];
    const c = S.comfort[a.id]?.frames?.[S.idx];
    if (f?.geometry) feats.push({ type: 'Feature', properties: { color: utciColor(c?.shade?.utci_c) }, geometry: f.geometry });
    const g = S.aoiGeo.features.find((x) => x.properties.id === a.id);
    if (g) suns.push({ type: 'Feature', properties: { color: utciColor(c?.sun?.utci_c) }, geometry: g.geometry });
  }
  map.getSource('shadow').setData({ type: 'FeatureCollection', features: feats });
  map.getSource('sun').setData({ type: 'FeatureCollection', features: suns });

  // 카드
  const a = S.aois.find((x) => x.id === S.aoi);
  const t = (k, v, s, u) => `<div class="tile big"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${u !== undefined ? `<span class="sw" style="background:${utciColor(u)}"></span>` : ''}${s}</div></div>`;
  if (!cf || cf.delta_utci === null) {
    $('cards').innerHTML = '';
    $('cards-note').textContent = cf ? `이 시각은 계산할 수 없습니다: ${(cf.flags || []).join(' · ') || '날씨 자료 부족'}` : '';
    $('headline').textContent = '이 시각의 날씨 자료가 없어 체감 정도를 계산하지 못했습니다.';
    return;
  }
  const night = (cf.inputs.sun_elevation_deg ?? 0) <= 0;
  $('cards').innerHTML = [
    t('기온', fmt(cf.inputs.air_temp_c, 1, '°C'), cf.provenance_weather === 'forecast' ? '기상청 예보' : '기상청 실황'),
    t('그늘 비율', fmt(fr?.shadow_fraction_pct, 0, '%'), '구역 땅 중 그림자'),
    t('햇볕 아래', fmt(cf.sun.utci_c, 1, '°'), plainCat(cf.sun.utci_c), cf.sun.utci_c),
    t('그늘', fmt(cf.shade.utci_c, 1, '°'), plainCat(cf.shade.utci_c), cf.shade.utci_c),
  ].join('');
  $('cards-note').textContent = '햇볕 아래·그늘 숫자는 몸이 느끼는 더위·추위를 온도로 나타낸 모델 값(UTCI)입니다.';
  const name = a?.name.split(' ')[0] ?? '';
  $('headline').innerHTML = night
    ? `<b>${esc(fr.time)} ${esc(name)}</b> — 해가 져서 그림자가 없습니다. 어디서나 체감은 <b>${fmt(cf.sun.utci_c, 1)}°</b>(${plainCat(cf.sun.utci_c)})로 같습니다.`
    : cf.delta_utci < 0.5
      ? `<b>${esc(fr.time)} ${esc(name)}</b> — 해가 낮거나 구름이 많아 햇볕과 그늘의 차이가 거의 없습니다. 체감 <b>${fmt(cf.sun.utci_c, 1)}°</b>(${plainCat(cf.sun.utci_c)}).`
      : `<b>${esc(fr.time)} ${esc(name)}</b> — 햇볕 아래는 <b>${fmt(cf.sun.utci_c, 1)}°</b>(${plainCat(cf.sun.utci_c)}), 그늘은 <b>${fmt(cf.shade.utci_c, 1)}°</b>(${plainCat(cf.shade.utci_c)}).
         그늘이 <b>${fmt(cf.delta_utci, 1)}° 덜 덥게</b> 느껴집니다.`;
}

// ---------------- 위치 클릭 ----------------
function onClick(e) {
  const inShadow = map.queryRenderedFeatures(e.point, { layers: ['shadow'] }).length > 0;
  const onBuilding = map.queryRenderedFeatures(e.point, { layers: ['buildings'] }).length > 0;
  const inAoi = map.queryRenderedFeatures(e.point, { layers: ['sun'] }).length > 0;
  const cf = S.comfort[S.aoi]?.frames?.[S.idx];
  let html;
  if (!inAoi) html = '<b>계산 구역 밖입니다</b><br><span class="meta">점선 네모(시범 구역) 안을 눌러 주세요.</span>';
  else if (onBuilding && !inShadow) html = '<b>건물 위입니다</b><br><span class="meta">건물 옆 길·광장을 눌러 보세요.</span>';
  else if (!cf || cf.delta_utci === null) html = '<b>이 시각은 계산할 수 없습니다</b>';
  else {
    const c = inShadow ? cf.shade : cf.sun, o = inShadow ? cf.sun : cf.shade;
    html = `<span class="sw" style="background:${utciColor(c.utci_c)}"></span><b>이 위치는 ${S.idx === nowIdx() ? '지금' : esc(S.frames[S.aoi][S.idx].time) + '에'} ${inShadow ? '그늘' : '햇볕 아래'}</b><br>
      예상 체감 <b style="font-size:20px">${fmt(c.utci_c, 1)}°</b> · ${plainCat(c.utci_c)}<br>
      <span class="meta">${inShadow ? '햇볕이 들었다면' : '그늘이었다면'} ${fmt(o.utci_c, 1)}° · 기온 ${fmt(cf.inputs.air_temp_c, 1)}°C · 모델 값</span>`;
  }
  $('spot').innerHTML = html;
  if (S.marker) S.marker.remove();
  S.marker = new maplibregl.Marker({ color: '#0b0b0b', scale: 0.7 }).setLngLat(e.lngLat).addTo(map);
}

// ---------------- 구·군 표 ----------------
function renderGu() {
  const d = S.live;
  if (!d) { $('gu-table').innerHTML = '<p class="meta">자료 없음</p>'; return; }
  $('gu-table').innerHTML = `<p class="meta">${esc(d.weather_base_at_kst.slice(11, 16))} 기상청 실황 · 체감은 모델 값</p>
    <table><thead><tr><th>구·군</th><th class="num">기온</th><th class="num">햇볕</th><th class="num">그늘</th></tr></thead><tbody>
    ${d.grids.map((r) => `<tr><td>${esc(r.gu)}</td><td class="num">${fmt(r.inputs.air_temp_c, 1)}°</td>
      <td class="num">${r.sun ? `<span class="sw" style="background:${utciColor(r.sun.utci_c)}"></span>${fmt(r.sun.utci_c, 1)}°` : '—'}</td>
      <td class="num">${r.shade ? `<span class="sw" style="background:${utciColor(r.shade.utci_c)}"></span>${fmt(r.shade.utci_c, 1)}°` : '—'}</td></tr>`).join('')}
    </tbody></table>`;
}

function stopPlay() {
  if (S.playing) clearInterval(S.playing);
  S.playing = null;
  $('btn-play').textContent = '▶ 하루 재생';
}

// ---------------- 시작 ----------------
async function main() {
  $('legend').innerHTML = utciLegendHtml();
  refreshStatus();
  await loadDay();
  if (!S.hasToday) {
    $('headline').innerHTML = '<b>오늘 그림자를 계산하는 중입니다.</b> 수집기가 하루 한 번 자동으로 계산합니다(약 30분).';
  }
  S.aoi = S.aois[0]?.id;
  $('sel-aoi').innerHTML = S.aois.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join('');
  await initMap();
  fitAoi();
  renderGu();
  if (S.hasToday) {
    $('time-slider').max = String((S.frames[S.aoi]?.length || 1) - 1);
    S.idx = nowIdx();
    render();
  }
  $('sel-aoi').onchange = (e) => { S.aoi = e.target.value; fitAoi(); render(); $('spot').innerHTML = '<b>지도를 눌러 보세요</b>'; };
  $('time-slider').oninput = (e) => { stopPlay(); S.idx = +e.target.value; S.followNow = S.idx === nowIdx(); render(); };
  $('btn-play').onclick = () => {
    if (S.playing) { stopPlay(); return; }
    S.followNow = false;
    const n = S.frames[S.aoi]?.length || 1;
    if (S.idx >= n - 1) S.idx = 0;
    $('btn-play').textContent = '❚❚ 멈춤';
    S.playing = setInterval(() => {
      S.idx += 1;
      if (S.idx >= n - 1) { S.idx = n - 1; stopPlay(); }
      render();
    }, 700);
  };
  $('btn-now').onclick = () => {
    stopPlay();
    S.followNow = true; S.idx = nowIdx(); render();
    const m = mins(hmKst());
    if (m < 6 * 60 || m > 20 * 60 + 15) toast('지금은 계산 시간(06~20시) 밖이라 가장 가까운 시각을 보여줍니다.');
  };
  // 5분마다 새 실황 반영, '지금' 모드면 시각도 따라감
  setInterval(async () => {
    refreshStatus();
    if (todayKst() !== S.today) { location.reload(); return; }
    await loadComfort();
    renderGu();
    if (S.hasToday) { if (S.followNow) S.idx = nowIdx(); render(); }
  }, 5 * 60 * 1000);
  document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => {
    const v = b.dataset.view;
    document.querySelectorAll('.tabs button').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
    $('view-now').hidden = v !== 'now';
    $('view-methods').hidden = v !== 'methods';
    if (v === 'methods' && !S.methods) { S.methods = true; initMethods(); }
    if (v === 'now') map.resize();
  }));
}

main().catch((e) => { console.error(e); toast(`오류: ${e.message}`); });
