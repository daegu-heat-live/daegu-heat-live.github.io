"""공모전 붙임 1~5 작성본(.docx) 생성 — 원 서식(HWP)의 구성을 따라 작성한다.

개인정보(성명·생년월일·연락처·주소·서명)와 동의 체크는 참가자가 직접 기입하도록 비워 둔다.
  python -m scripts.make_submission_docx
"""
from __future__ import annotations

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from scripts.common import ROOT

FONT = "맑은 고딕"
OUT = ROOT / "docs" / "제출서류_붙임1-5_작성본.docx"
BLANK = "　　　　　　"  # 직접 기입 칸


def set_font(run, size=10, bold=False, color=None):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def para(doc_or_cell, text="", size=10, bold=False, align=None, color=None, space_after=2):
    p = doc_or_cell.add_paragraph()
    if text:
        set_font(p.add_run(text), size, bold, color)
    if align:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    return p


def shade(cell, hex_fill="E8EEF7"):
    tcPr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def cell_text(cell, lines, size=10, bold=False, head=False):
    cell.text = ""
    first = True
    for ln in ([lines] if isinstance(lines, str) else lines):
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        p.paragraph_format.space_after = Pt(1)
        if isinstance(ln, tuple):  # (text, bold)
            set_font(p.add_run(ln[0]), size, ln[1])
        else:
            set_font(p.add_run(ln), size, bold or head)
    if head:
        shade(cell)


def table(doc, rows, widths, head_cols=(0,)):
    t = doc.add_table(rows=len(rows), cols=len(widths))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r, row in enumerate(rows):
        c = 0
        for item in row:
            span = 1
            if isinstance(item, dict):
                span, item = item["span"], item["text"]
            cell = t.cell(r, c)
            if span > 1:
                cell = cell.merge(t.cell(r, c + span - 1))
            cell_text(cell, item, head=(c in head_cols and span == 1))
            c += span
    for r in t.rows:
        for i, w in enumerate(widths):
            r.cells[i].width = Cm(w)
    return t


def title(doc, tag, name):
    para(doc, tag, 9, color="666666")
    para(doc, name, 16, True, WD_ALIGN_PARAGRAPH.CENTER, space_after=8)


def receipt(doc):
    table(doc, [["접수번호", "※ 미기재"]], [3, 14])
    para(doc)


def sign_block(doc, kind):
    para(doc)
    para(doc, f"위와 같이 {kind}를 제출합니다.", 10, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "2026.      .      .", 10, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, f"참 가 자 : {BLANK}  (인 또는 서명)", 10, align=WD_ALIGN_PARAGRAPH.RIGHT)
    para(doc, f"법 정 대 리 인 : {BLANK}  (인 또는 서명)", 10, align=WD_ALIGN_PARAGRAPH.RIGHT)
    para(doc, "※만 14세 미만 아동인 경우 법정대리인 동의 포함", 8, color="666666", align=WD_ALIGN_PARAGRAPH.RIGHT)
    para(doc, "대구광역시 탄소중립지원센터장 귀하", 12, True, WD_ALIGN_PARAGRAPH.CENTER)


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------- 내용
WORK_TITLE = "DAEGU HEAT LIVE — 지금 대구, 햇볕 아래와 그늘의 체감 더위 지도"

OVERVIEW = [
    ("[목적] ", True),
    "같은 기온이라도 햇볕 아래와 건물 그늘에서 사람이 느끼는 더위는 크게 다릅니다. 기온 숫자만으로는 알 수 없는 "
    "‘지금, 어디가, 얼마나 덥게(춥게) 느껴지는지’를 시민이 지도 한 장으로 바로 확인하도록 하는 것이 목적입니다.",
    ("[핵심 내용] ", True),
    "① 기상청 초단기실황(기온·습도·바람)을 10분마다 받아 대구 9개 구·군의 지금 날씨를 갱신합니다.",
    "② 국토교통부 GIS건물통합정보의 건물 모양·높이(대구 382,695동)와 태양 위치로 동성로·범어네거리의 건물 그림자를 30분 간격으로 계산합니다.",
    "③ 같은 날씨에서 햇볕을 받는 곳과 그늘을 나눠 국제 체감지표 UTCI를 물리 모델(ASHRAE 55 SolarCal + UTCI)로 산출하고, "
    "위치별로 ‘쾌적·약간 더움·더움(주의)·매우 더움(위험)…’ 단계 색을 지도에 칠합니다.",
    "   예) 2026-11-11 12:00 동성로: 기온 15.1℃ — 햇볕 아래 체감 26.9°(약간 더움), 그늘 17.0°(쾌적), 그늘 효과 9.9°(모델 계산값).",
    ("[주요 특징] ", True),
    "· 실시간: 날씨 10분, 화면 5분 자동 갱신 / 날짜가 바뀌면 그날 그림자 자동 계산",
    "· 위치별 정보: 지도를 누르면 ‘이 위치는 지금 그늘/햇볕, 예상 체감 X°’ 표시, 하루 그림자 재생·해 방향 안내",
    "· 정직한 표시: 관측값과 모델 계산값을 구분하고, 미반영 요소(달궈진 포장 열, 나무 그늘)와 한계를 화면에 공개",
]

AI_MAIN = "Claude Opus 5.5 (Anthropic) — Claude Code 데스크톱 앱(코딩 에이전트)으로 사용"

CASES = [
    {
        "purpose": "공공데이터 확보 가능성 조사, 데이터 수집·전처리 및 건물 그림자 계산 코드 작성",
        "prompt": "(개발 지시서 파일 첨부) “개발 ㄱㄱ 대구시 공공데이터 분석 공모전 제출용이야”",
        "result": [
            "AI가 각 공공데이터의 실제 접근 경로를 호출해 확인한 결과, 건물 높이 원본(GIS건물통합정보)은 V-World 로그인 후에만 받을 수 있어 "
            "자동 수집이 불가능하다고 보고 → 참가자가 V-World에서 대구 SHP(AL_D010_27_20261109)를 직접 내려받아 적용함.",
            "AI가 작성한 그림자 계산 코드는 태양 위치를 표준 라이브러리(pvlib)와 비교(오차 0.05° 이내)하는 등 자동 테스트로 검증함.",
            "원본 데이터에서 ‘1층인데 높이 5,035 m’ 같은 입력 오류 156동을 발견해, 층당 높이가 비정상인 건물을 계산에서 제외하는 규칙을 추가함.",
        ],
    },
    {
        "purpose": "기상청 실시간 API 연동 및 체감 더위(UTCI) 계산 모델 구현",
        "prompt": "(열쾌적성 수정 지시서 v1.4 첨부) “파일 잘못올림 이거대로 다시해줘”, “지상관측은 스킵하자 굳이싶다”",
        "result": [
            "기상청 단기예보 API의 실제 응답을 확인하던 중 ‘15:30 발표 요청 → 응답 발표시각 15:00’ 차이를 발견해, 요청값이 아닌 응답값으로 기록하도록 수정함.",
            "현장 실측 자료가 없어 UTCI를 ‘모델 추정값’으로만 표시하기로 판정함. ‘그늘이면 −N℃’ 같은 임의 공식은 쓰지 않고, 검증된 공개 모델"
            "(ASHRAE 55 SolarCal, pythermalcomfort UTCI)만 사용함.",
            "AI 기반 예보 오차 보정 모델도 시험했으나, 시간 분할 평가에서 기존 예보보다 오차가 커서(2026-11-11 평가, 평균 오차 약 1.7℃ vs 1.1~1.2℃, 학습 자료 1일 미만) 작품에 적용하지 않음.",
        ],
    },
    {
        "purpose": "시민 눈높이에 맞춘 화면 단순화와 표현 개선",
        "prompt": "“스스로 피드백 해봐 … 열쾌적성이 먼말인지 모르겠어 … 최대한 쉬운 방향으로 풀어내는게좋을거같아”, "
                  "“과거 데이터가 너무 많은데 현재의 데이터만을 중점으로 만들어줘 … 실시간 그늘+실시간 그림자로 위치별 예상 더운추운정도를 나타내주는 페이지 이렇게 딱 구성해줘”",
        "result": [
            "AI가 스스로 화면을 점검해 7가지 문제(전문용어, 그래프 읽는 법 부재, 핵심 메시지 묻힘 등)를 정리하고, ‘열쾌적성·UTCI’를 ‘체감 더위’로 바꾸는 등 문구를 고침.",
            "참가자 판단으로 예보·과거 비교 화면을 삭제하고 ‘지금’ 한 화면(실시간 그림자 + 위치별 체감 더위)으로 재구성함.",
            "참가자 요청으로 그림자를 더 잘 보이게(어두운 덧칠·테두리), 하루 재생 버튼과 해·그림자 방향 안내를 추가함. 모든 화면은 브라우저에서 직접 확인함.",
        ],
    },
]

DATASETS = [
    ("기상청_단기예보 ((구)_동네예보) 조회서비스\n(초단기실황·초단기예보)", "기상청", "https://www.data.go.kr/data/15084084/openapi.do"),
    ("국토교통부_GIS건물통합정보\n(대구광역시, 2026-11-06 기준)", "국토교통부", "https://www.data.go.kr/data/15083092/fileData.do"),
    ("행정구역(행정동) 경계", "통계청(통계지리정보서비스 SGIS)",
     "https://sgis.kostat.go.kr\n(시점별 정리본: https://github.com/vuski/admdongkor)"),
]


def build():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, Cm(2))
    sec.top_margin = sec.bottom_margin = Cm(1.8)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    st.font.size = Pt(10)

    # ---------------- 붙임 1
    title(doc, "붙임 1  참가신청서(서식)", "2026 대구광역시 기후·환경·탄소중립\n공공데이터 AI 활용대회 참가 신청서")
    table(doc, [
        ["접수번호", {"span": 3, "text": "※ 미기재"}],
        ["성  명", BLANK, "생년월일", "　　년　　월　　일(　　세)"],
        ["연 락 처", BLANK, "성 별", "□ 남　　□ 여"],
        ["이 메 일", {"span": 3, "text": BLANK}],
        ["주  소", {"span": 3, "text": "※ 도로명주소 기재"}],
        ["출품작", {"span": 3, "text": "□ (부문1)아이디어 기획 제안　　■ (부문2)데이터 분석·시각화"}],
        ["작품명", {"span": 3, "text": [(WORK_TITLE, True)]}],
        ["활용 데이터 및 AI", {"span": 3, "text": [
            "· 사용 공공데이터 : 기상청 단기예보 조회서비스(초단기실황·초단기예보), 국토교통부 GIS건물통합정보, 통계청 행정동 경계",
            "· 사용 AI 도구 : ㅍㅋ"]}],
        ["작품 개요", {"span": 3, "text": OVERVIEW}],
        ["제출", {"span": 3, "text": "붙임 1,2,3,4,5 작성 후 출품작과 제출 (smeeheo@dpi.re.kr)"}],
    ], [3, 5.5, 2.5, 6], head_cols=(0, 2))
    sign_block(doc, "참가 신청서")
    page_break(doc)

    # ---------------- 붙임 2
    title(doc, "붙임 2  개인정보 수집 이용 동의서(서식)", "개인정보 수집 이용 동의서")
    receipt(doc)
    for ln in [
        ("【개인정보 수집 및 초상권 이용 동의 안내】", True),
        ("가. 개인정보 수집･이용 목적", True),
        "◦ ｢2026 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회｣에서 수집되는 개인정보는 정보주체의 동의를 얻어 ‘수상작 선정평가 및 상금 지급 및 대회 운영·관리’를 목적으로 이용됩니다.",
        ("나. 개인정보 수집·이용 항목", True), "◦ 성명, 생년월일, 연락처, 성별, 이메일, 주소",
        ("다. 개인정보 보유･이용 기간", True),
        "◦ ｢제1회 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회｣ 공고일로부터 3년간 보관(※ 관련 법령에 따른 보존 의무 이행 및 사후 관리 목적)",
        ("라. 개인정보 수집･이용에 동의하지 않을 권리 및 동의하지 않을 경우 불이익", True),
        "◦ 정보주체는 ｢2026 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회｣에 개인정보 수집 이용 동의를 거부할 권리가 있습니다.",
        "◦ 개인정보 수집 이용에 동의하지 않을 경우 본 대회에 참가 신청 및 심사 대상 제외 등의 불이익이 발생할 수 있습니다.",
    ]:
        para(doc, ln[0] if isinstance(ln, tuple) else ln, 10, isinstance(ln, tuple))
    para(doc)
    para(doc, "본인은 ｢제1회 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회｣에서 개인정보를 수집･이용하는 것에 동의합니다.", 10, True, WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "(동의함 □   동의하지 않음 □)", 10, align=WD_ALIGN_PARAGRAPH.CENTER)
    sign_block(doc, "개인정보 수집 이용 동의서")
    page_break(doc)

    # ---------------- 붙임 3
    title(doc, "붙임 3  서약서(서식)", "서  약  서")
    receipt(doc)
    para(doc, "본인은 대구광역시 탄소중립지원센터가 주최하는 ｢2026 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회｣에 작품을 출품함에 있어 다음과 같이 서약합니다.", 10)
    for ln in [
        "◦ 본인은 제출한 작품 및 서류의 모든 내용이 사실임을 확인함.",
        "◦ 타 공모전에서 제출하였거나, 시상 또는 수상 경력이 있는 작품이 아님을 확인함.",
        "◦ 응모작과 관련한 문제가 발생할 경우 모든 법적․도의적 책임은 본인에게 있음.",
        "◦ 응모작과 관련된 서류는 일체 반환하지 않음.",
        "◦ 수상작에 대한 저작권은 참가자에게 귀속되나, 주최·주관기관(대구광역시 및 대구광역시 탄소중립지원센터)이 공익 목적(홍보, 교육, 정책 반영 등)으로 복제, 배포, 2차 저작물 작성 및 활용하는 것에 동의함.",
        "◦ 생성형 AI 및 공공데이터 활용 시 출처를 명확히 기재하며, 존재하지 않는 데이터나 분석 결과를 위조·조작하지 않았음.",
        "◦ 수상 후 창작이 아닌 모방 혹은 표절 등으로 밝혀진 경우 수상은 취소되며, 상금 환수에 동의하여 이의를 제기하지 않겠음.",
        "◦ 위 모든 사항 및 참가 신청서, 개인정보 수집 이용 동의서 등 미기재 및 오기재로 인해 발생한 불이익에 대한 책임은 본인에게 있음.",
    ]:
        para(doc, ln, 10)
    para(doc, "(동의함 □   동의하지 않음 □)", 10, align=WD_ALIGN_PARAGRAPH.CENTER)
    sign_block(doc, "서약서")
    page_break(doc)

    # ---------------- 붙임 4
    title(doc, "붙임 4  AI 프롬프트 활용 내역서(서식)", "AI 프롬프트 활용 내역서")
    rows = [
        ["접수번호", "※ 미기재"],
        ["주요 사용 AI", AI_MAIN],
        ["활용 목적", ["[V] 데이터 수집·전처리 및 분석 코드 작성　[  ] 아이디어 구상 및 기획서 작성",
                     "[V] 시각화 그래픽 및 이미지 생성(지도·그래프 코드 작성)　[V] 기타 (웹 대시보드 개발, 화면 문구 개선, 검증 테스트 작성)"]],
        [{"span": 2, "text": [("AI 활용 내역 및 프롬프트 상세내용", True)]}],
    ]
    for i, c in enumerate(CASES, 1):
        rows.append([f"사례{i}", [("[활용 목적] ", True), c["purpose"], ("[입력 프롬프트] ", True), c["prompt"],
                                  ("[활용 및 보완 내용] ", True), *[f"· {r}" for r in c["result"]]]])
    t = table(doc, rows, [3, 14])
    shade(t.cell(3, 0))
    para(doc, "※ 입력 프롬프트는 참가자가 실제로 입력한 문장을 그대로 옮김. 전체 대화 중 핵심 요청만 발췌.", 8, color="666666")
    page_break(doc)

    # ---------------- 붙임 5
    title(doc, "붙임 5  공공데이터 사용 내역서(서식)", "공공데이터 사용 내역서")
    table(doc, [
        ["접수번호", {"span": 3, "text": "※ 미기재"}],
        ["활용 데이터 수", {"span": 3, "text": f"총 ( {len(DATASETS)} )개 데이터셋 활용"}],
        ["주요 제공기관", {"span": 3, "text": "기상청, 국토교통부, 통계청"}],
        ["연번", "공공데이터명", "제공기관", "데이터 출처 URL"],
        *[[str(i), n.split("\n"), o, u.split("\n")] for i, (n, o, u) in enumerate(DATASETS, 1)],
    ], [1.5, 5.5, 3.5, 6.5], head_cols=(0,))
    para(doc, "(※ 본 출품작에 활용된 공공데이터의 명칭, 제공 기관, 정확한 접속 URL을 기재해 주시기 바랍니다.)", 8, color="666666")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
