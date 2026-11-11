# 데이터 출처 (2026-11-11 수집)

기계 판독용 전체 메타데이터(필드·건수·결측률·CRS·수집시각)는 `data/catalog.json`.

| ID | 데이터 | 실제 사용 원본 / 접근 경로 | 라이선스·표시 | 상태 |
|---|---|---|---|---|
| WX-02/03 | 기상청 초단기예보·초단기실황 | 공공데이터포털 단기예보 조회서비스 15084084 (`getUltraSrtFcst`, `getUltraSrtNcst`) | 공공데이터포털 이용허락(출처표시) | 확보(2026-11-11 실제 응답 확인) |
| WX-01 | 기상청 AWS·ASOS 지상관측(API허브) | https://apihub.kma.go.kr | — | 제외(프로젝트 결정) |
| D06 | 대구 행정경계 | 통계청 SGIS 행정동 경계, 시점 정리본 vuski/admdongkor `ver20261001` — https://github.com/vuski/admdongkor | 원본 통계청(공공누리), 정리본 저장소 조건 | 확보 |
| D05 | Landsat 8/9 C2 L2 지표면온도(ST_B10, QA_PIXEL) | USGS 원본, Microsoft Planetary Computer `landsat-c2-l2` 미러 — https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2 | USGS 공개자료 | 확보(9개 장면) |
| D04 | 기상 관측(기온·이슬점·풍향풍속) | 기상청 대구(47143=ASOS 143) SYNOP, 대구공항(47142) METAR — NOAA NCEI ISD `noaa-global-hourly-pds` | NOAA 공개자료, 원 관측 기상청 | 확보(2023-01~2025-08-25) |
| D11 | Sentinel-2 L2A (B03·B04·B08·B11·SCL) | ESA Copernicus, Planetary Computer `sentinel-2-l2a` | Copernicus 무료·개방, “Contains modified Copernicus Sentinel data 2025” | 확보(2025-07-09) |
| D12 | DEM | Copernicus DEM GLO-30, Planetary Computer `cop-dem-glo-30` | Copernicus DEM 라이선스(출처표시) | 확보(대체) |
| D13 | OSM 건물윤곽·도로·수목·공원 | Overpass API — https://www.openstreetmap.org/ | ODbL 1.0, © OpenStreetMap contributors | 확보(참조·임시) |
| D01 | 국토부 GIS건물통합정보 SHP `AL_D010_27_20261109` | https://www.data.go.kr/data/15083092/fileData.do → V-World dsId=18 (사용자 로그인 후 수동 다운로드) | 공공누리 제1유형 | 확보(2026-11-06 기준, 382,695동) |
| D02 | GIS건물통합정보 WMS/WFS | https://www.data.go.kr/data/15123970/openapi.do | 공공누리 | 미사용(인증키 필요) |
| D03 | 건축HUB 건축물대장 | https://www.data.go.kr/data/15134735/openapi.do | 공공누리 | 미사용(인증키 필요) |
| D07 | 산림청 가로수 현황 | https://www.data.go.kr/data/15120900/fileData.do | 공공누리 | **미확보: 로그인 필요** → OSM 수목점 임시 |
| D08 | 수성구 가로수 현황 | https://www.data.go.kr/data/15104567/fileData.do | 공공누리 | 미확보 |
| D09 | 대구 도시공원 | https://www.data.go.kr/data/15117091/fileData.do | 공공누리 | 미확보 → OSM 공원 임시 |
| D10 | 토지피복지도 | https://egis.me.go.kr/ | 환경부 | 미확보(인증 필요) |
| D14 | V-World 배경지도 | https://www.vworld.kr/ | 표시의무 | 미사용 → OpenFreeMap |
| — | 배경지도 | OpenFreeMap (OpenMapTiles, OSM 데이터) — https://openfreemap.org/ | OSM ODbL, OpenMapTiles 표시 | 사용 |
| — | UTCI·SolarCal | pythermalcomfort 4.8.1 (`utci`, `solar_gain`) — https://pythermalcomfort.readthedocs.io/ | MIT | 사용 |
| — | 일사 모델 | pvlib (Haurwitz, Erbs) + Kasten–Czeplak 운량식 | BSD-3 | 사용 |
| — | 참고 서비스 | 대구 3D지도 http://3d.daegu.go.kr/ · 도시생태현황지도 https://gis.go.kr/bc/ | 재사용 권한 미확인 | **참고만(데이터 미사용)** |
| — | 태양 위치 | NOAA Solar Calculator 알고리즘(Meeus) 자체 구현, pvlib(NREL SPA)로 검증 | 알고리즘(데이터 아님) | 사용 |

## 획득 실패 기록

| 원본 | 실패 원인 | 대체 |
|---|---|---|
| GIS건물통합정보 SHP | V-World 로그인 후 다운로드(자동 수집 불가) | 사용자가 수동 다운로드해 적용(2026-11-11) |
| Overture Maps 건물(2026-10-21) | 동성로 2,177동 중 높이 0동, 층수 77동 → 높이 원본으로 부적합 | 미사용 |
| 기상청 ASOS OpenAPI | 인증키 필요 | NOAA ISD(같은 관측소) |
| 산림청 가로수 | 공공데이터포털 로그인 필요 | OSM 수목점 279개(수고·수관 0건) |
| CARTO 배경지도 | 2026년 현재 API 키 요구(워터마크) | OpenFreeMap |
| Sentinel-2 2025-07-10(R003 궤도) | 대구의 21%만 촬영 범위 | 2025-07-09(R103 궤도, 99.9%) |

## 참고 서비스(자료 유형 참고만)

- 그늘로: 뚜벅의 여름길 — https://ttubeok.com/support/
- 그늘나침반 — https://apps.apple.com/kr/app/id6799209656 (서버·API 호출, 결과 재사용 없음)
- pybdshadow — https://github.com/ni1o1/pybdshadow (검토 후보, 미채택)
