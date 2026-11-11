# v1.3 실시간 기능 적용 기록 (2026-11-11)

## 결정
| v1.3 항목 | 적용 | 비고 |
|---|---|---|
| WX-01 AWS·ASOS 지상관측(API허브) | **제외(사용자 결정)** | 관측소 실측 최신값 없음. HISTORY는 기존 NOAA ISD 관측 장기 시계열 유지 |
| WX-02 초단기예보 `getUltraSrtFcst` | ✅ FORECAST | 실제 응답 수신 확인 |
| WX-03 초단기실황 `getUltraSrtNcst` | ✅ LIVE(대체 실황) | 실제 응답 수신 확인. 화면 라벨 “기상청 초단기실황(격자 실황값)” |
| WX-04 천리안 2A LST | 미구현(P2) | 과거 Landsat LST는 HISTORY에 유지 |
| WX-05 민간 API | 미사용 | |

## Phase 0 게이트 — 실제 응답 확인
- 2026-11-11 16:06 KST, 격자 89,90(중구·남구) 외 8개 격자
- `getUltraSrtNcst` base 2026-11-11 15:00 → resultCode 00, T1H 16.3 °C, REH 42 %, WSD 1.1 m/s
- `getUltraSrtFcst` 요청 base_time 1530 → **응답 baseTime 1500**, 유효시각 16:00~21:00 6개
  → 발표시각은 요청값이 아닌 응답 `baseDate/baseTime`으로 기록하도록 수집기 수정
- 백필: 2026-11-10 23:00 ~ 11-11 14:00 실황 16회 수신(서비스는 최근 1일 이내 기준시각만 제공)

## 구조
```
scripts/live/kma_grid.py   기상청 LCC 5 km 격자 ↔ 위경도 (서울시청 60,127 검증)
scripts/live/kma_time.py   발표시각 후보(실황 HH00·40분 이후, 예보 HH30·45분 이후) → 실패 시 과거로
scripts/live/collect.py    수집기: 9개 구·군 대표 격자(고유 8개) → web/data/live/*.json, data/live/ 아카이브
web/js/live.js             LIVE·FORECAST 화면, 상단 상태바(1분마다 재조회)
```
- 인증키는 `.env`(`DATA_GO_KR_SERVICE_KEY`)에서 수집기만 읽는다. 브라우저 번들·정적 JSON에 키 없음.
- 같은 발표시각은 한 번만 아카이브(`data/live/nowcast|forecast/YYYYMMDDHHMM.json`).
- 실패 시 `status.json`에 오류와 마지막 정상 기준시각을 남기고, 화면은 “자료 없음/수신 오류”를 표시한다. 임의 값 없음.
- 기상청 결측 표기(-998.9, ±900 이상)는 null.

## 실행
```bash
python -m scripts.live.collect --backfill 24   # 최근 1일 실황 채우기
python -m scripts.live.collect --loop 600      # 10분마다 수집(실행 중인 동안만 LIVE가 갱신됨)
python scripts/serve.py 8765
```
정적 배포 시에는 수집기를 주기 실행(예: 서버 cron, GitHub Actions)해 `web/data/live/`를 갱신해야 한다. 그렇지 않으면 상태바가 “지연”을 표시한다.

## HISTORY 추가
- 연도별 폭염일(일 최고 ≥ 33 °C)·열대야(19~09시 최저 ≥ 25 °C), 여름 일 최고기온 연도 비교 — `scripts/analysis/heat_days.py`
- 정시 관측 기반 근사(공식 통계와 다를 수 있음), 결측 많은 날 제외, 2025년은 8/25까지.
- 대구(ASOS 143): 폭염일 2023 22 · 2024 51 · 2025* 38일, 열대야 12 · 37 · 22일.

## 아직 안 한 것 (v1.3 선택·후속)
- 예보 오차(MAE) 분석·AI 보정: 과거 예보 아카이브가 없어 **오늘부터 수집 중**. 수일~수주 누적 후 같은 유효시각의 실황과 비교 가능(실황도 격자값이라 ‘관측소 대비 오차’가 아닌 ‘실황 대비 오차’).
- 관측값 공간 보간(추정 기온): 관측소 실측을 쓰지 않기로 해 미구현.
- SHADOW `현재 그늘` 버튼(오늘 날짜 즉시 계산): 현재는 사전 계산 4개 날짜만 제공.
- `현재 vs 지난 7일/30일` 비교: 실황 아카이브가 쌓인 뒤 가능.
