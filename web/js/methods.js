// 출처 화면 — 지금 화면에 쓰인 자료와 계산 방법만 간단히
import { getJSON, esc } from './util.js';

const USED = ['WX02_WX03_kma_ultrashort', 'D01_buildings', 'D06_boundaries', 'S01_building_shadows', 'M01_utci'];

export async function initMethods() {
  const [cat, q] = await Promise.all([getJSON('catalog.json'), getJSON('building_quality.json')]);
  const rows = USED.map((id) => [id, cat.datasets[id]]).filter(([, d]) => d).map(([, d]) => `<tr>
    <td><b>${esc(d.name)}</b></td><td>${esc(d.provider)}</td>
    <td>${d.source_url && /^https?:/.test(d.source_url) ? `<a href="${esc(d.source_url)}" target="_blank" rel="noopener">원본 링크</a>` : esc(d.source_url || '')}</td>
    <td>${esc(d.license || '')}</td></tr>`).join('');
  const city = q._daegu_all;
  const aoi = Object.entries(q).filter(([k]) => !k.startsWith('_')).map(([, r]) =>
    `<li>${esc(r.aoi === 'dongseongro' ? '동성로' : '범어')}: 건물 ${r.n_buildings_in_aoi.toLocaleString()}동 — 대장 높이 ${r.pct.registry ?? 0}% · 층수로 추정 ${r.pct.estimated ?? 0}% · 높이 없음 ${r.pct.missing ?? 0}%(그림자 계산 제외)</li>`).join('');
  document.getElementById('methods').innerHTML = `<div class="methods">
    <h2>쓰인 공공데이터</h2>
    <div class="card tablewrap"><table><thead><tr><th>자료</th><th>제공</th><th>출처</th><th>이용 조건</th></tr></thead><tbody>${rows}</tbody></table></div>

    <h2>어떻게 계산하나요?</h2>
    <div class="card"><ol>
      <li><b>지금 날씨</b>: 기상청 초단기실황(기온·습도·바람, 5 km 칸)을 10분마다 받습니다. 구름 상태는 같은 시각의 초단기예보 값을 씁니다.</li>
      <li><b>그림자</b>: 건물 바닥 모양과 높이(국토부 GIS건물통합정보), 해의 높이·방향(NOAA 계산식)으로 30분마다 그림자 모양을 계산합니다.</li>
      <li><b>햇볕의 세기</b>: 해 높이와 구름양으로 추정합니다(Haurwitz 맑은 하늘 일사 × Kasten–Czeplak 구름 보정, Erbs 직달·산란 분리).</li>
      <li><b>체감 더위·추위</b>: 같은 날씨에서 직사광선을 받는 곳(햇볕)과 막힌 곳(그늘)을 따로 계산합니다. 햇볕에 의한 복사열은 ASHRAE 55 SolarCal, 체감 지표는 국제 UTCI(pythermalcomfort).</li>
      <li>지도 색: 점선 네모 안 = 햇볕 드는 곳의 체감, 그림자 = 그늘의 체감.</li>
    </ol></div>

    <h2>알아둘 점</h2>
    <div class="card"><ul>
      <li>체감 숫자는 <b>모델로 계산한 참고값</b>입니다. 현장에서 직접 잰 값이 아닙니다.</li>
      <li>달궈진 아스팔트·벽에서 나오는 열을 넣지 못해 <b>햇볕 아래 값이 실제보다 낮을 수</b> 있습니다.</li>
      <li>나무 그늘·차양은 계산하지 않았습니다. 건물 그림자만 반영합니다.</li>
      <li>날씨는 구역 전체에 같은 값(5 km 칸)을 씁니다.</li>
      ${city ? `<li>대구 전체 건물 ${city.n_buildings.toLocaleString()}동 중 높이 자료 ${city.pct_registry_height}% · 층수만 ${city.pct_floors_only_estimated}% · 둘 다 없음 ${city.pct_missing}%.</li>` : ''}
      ${aoi}
    </ul></div>

    <h2>자세한 문서</h2>
    <div class="card"><p class="meta">저장소 docs/thermal_comfort.md(계산식·가정), docs/realtime.md(기상청 수집), docs/shadow_validation.md(그림자 검증),
      docs/data_usage_log.md·ai_prompt_log.md(공모전 제출용 사용 내역).</p></div>
  </div>`;
}
