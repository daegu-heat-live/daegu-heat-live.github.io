# DAEGU HEAT LIVE

**지금 대구, 햇볕 아래와 그늘은 얼마나 다르게 느껴질까?**
기상청 실시간 날씨와 건물 그림자를 합쳐, 시범 구역(동성로·범어네거리)의 **위치별 예상 더위·추위 정도**를 지도 한 장으로 보여줍니다.
2026 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회 부문 2(공공데이터 분석·시각화) 출품용.

## 화면 (한 화면)
- **지도**: 지금 시각의 건물 그림자. 햇볕 드는 곳과 그늘을 체감 단계 색으로 칠함(쌀쌀함 · 쾌적 · 약간 더움 · 더움 · 매우 더움…)
- **한 줄 요약 + 카드**: 기온, 그늘 비율, 햇볕 아래 체감, 그늘 체감
- **지도 클릭**: “이 위치는 지금 그늘/햇볕, 예상 체감 X°”
- **오늘 시간 이동**: 06~20시 30분 단위, ‘지금으로’ 버튼. 5분마다 자동 갱신
- **출처**: 쓰인 공공데이터·계산 방법·한계

체감 값은 국제 지표 **UTCI**를 물리 모델로 계산한 **참고값**입니다(현장 실측 아님).

## 데이터
| 자료 | 제공 | 쓰임 |
|---|---|---|
| 단기예보 조회서비스(초단기실황·초단기예보) | 기상청 · 공공데이터포털 15084084 | 지금 기온·습도·바람(실황), 구름 상태(예보) |
| GIS건물통합정보 | 국토교통부 · V-World | 건물 모양·높이 → 그림자 |
| 행정동 경계 | 통계청 SGIS | 구·군 대표 격자 |
| OpenStreetMap | OSM 기여자 | 배경지도, 도로 |

## 실행
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
# .env 에 DATA_GO_KR_SERVICE_KEY=공공데이터포털 일반 인증키(Decoding)
# data/raw/buildings/ 에 V-World에서 받은 대구 GIS건물통합정보 SHP
.venv/Scripts/python -m scripts.run_all                 # 경계·건물 처리 + 첫 수집(오늘 그림자 계산 시작, 약 30분)
.venv/Scripts/python -m scripts.live.collect --loop 600  # 계속 실행: 10분마다 날씨, 날짜 바뀌면 그림자 자동 계산
.venv/Scripts/python scripts/serve.py 8765               # http://localhost:8765
.venv/Scripts/python -m pytest                           # 39개 테스트
```
`web/` 폴더가 그대로 정적 사이트입니다(약 13 MB). 수집기가 `web/data/live`, `web/data/comfort`, `web/data/shadows`를 갱신합니다.

## 계산 순서
1. 기상청 초단기실황(기온·습도·바람) + 같은 시각 초단기예보 구름 상태 — `scripts/live/collect.py`
2. 오늘 06~20시 30분마다 건물 그림자 — NOAA 태양 위치 + Shapely (`scripts/shadows/`)
3. 햇볕 세기 = 맑은 하늘 일사 × 구름 보정(Haurwitz, Kasten–Czeplak, Erbs)
4. 햇볕/그늘 체감 = SolarCal(ASHRAE 55) 복사열 + UTCI(pythermalcomfort) — `scripts/comfort/utci_model.py`

## 한계
- 달궈진 아스팔트·벽의 열 미반영 → 햇볕 아래 값이 낮게 나올 수 있음 · 나무 그늘 미반영
- 날씨는 5 km 칸 값을 구역 전체에 적용 · 높이 자료 없는 건물(동성로 19.9 %)은 그림자 제외
- 현장 측정 비교 없음(참고용 모델 값)

자세히: [docs/thermal_comfort.md](docs/thermal_comfort.md) · [docs/realtime.md](docs/realtime.md) · [docs/shadow_validation.md](docs/shadow_validation.md) · [docs/sources.md](docs/sources.md)

## 변경 이력
- 2026-11-11: 화면을 ‘지금’ 한 화면으로 정리. 예보(몇 시간 후)·과거 비교(위성 지표면온도·폭염일·AI 분석) 화면 삭제.
  해당 처리 스크립트(`scripts/raster`, `scripts/analysis`)는 저장소에 남아 있으나 화면·실행 순서에서 제외.
