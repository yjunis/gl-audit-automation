# -*- coding: utf-8 -*-
"""
프로그램 소개 PDF 생성 — 신입 회계사 눈높이로 '목적 + 결과의 의미'를 요약.
바탕화면에 GL_분석프로그램_소개.pdf 로 저장.
실행: PYTHONUTF8=1 python src/make_overview_pdf.py
"""
import os
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.backends.backend_pdf import PdfPages

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

SRC = Path(__file__).resolve().parent
PROJ = SRC.parent
REP = PROJ / "reports"
DESK = Path.home() / "OneDrive" / "Desktop"
if not DESK.exists():
    DESK = Path.home() / "Desktop"
OUT = DESK / "GL_분석프로그램_소개.pdf"

# 색상 팔레트
NAVY, BLUE, LBLUE = "#0b3d66", "#2b6cb0", "#dbe9f6"
RED, ORANGE, GREEN, GRAY = "#c0392b", "#e67e22", "#27ae60", "#5f6b7a"
INK = "#1c2833"

A4 = (8.27, 11.69)


def new_page():
    fig = plt.figure(figsize=A4)
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    return fig, ax


def header(ax, kicker, title, y=0.90):
    ax.text(0.09, y + 0.062, kicker, transform=ax.transAxes, color=BLUE,
            fontsize=10.5, fontweight="bold", va="center")
    ax.add_patch(FancyBboxPatch((0.06, y), 0.88, 0.052, boxstyle="round,pad=0.005,rounding_size=0.01",
                                fc=NAVY, ec="none", transform=ax.transAxes))
    ax.text(0.09, y + 0.026, title, transform=ax.transAxes, color="white",
            fontsize=18, fontweight="bold", va="center")


def box(ax, x, y, w, h, fc, ec="none", rad=0.012):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.004,rounding_size={rad}",
                                fc=fc, ec=ec, lw=1.2, transform=ax.transAxes))


def bullets(ax, x, y, lines, dy=0.032, fs=11, mark="●", mcol=BLUE, tcol=INK, gap=0.022):
    for head, body in lines:
        ax.text(x, y, mark, transform=ax.transAxes, color=mcol, fontsize=fs - 1, va="top")
        if head:
            ax.text(x + gap, y, head, transform=ax.transAxes, color=tcol, fontsize=fs,
                    fontweight="bold", va="top")
            ax.text(x + gap, y - 0.026, body, transform=ax.transAxes, color=GRAY, fontsize=fs - 1.5,
                    va="top")
            y -= dy + 0.024
        else:
            ax.text(x + gap, y, body, transform=ax.transAxes, color=tcol, fontsize=fs, va="top")
            y -= dy
    return y


def put_image(fig, path, rect, title=None, cap=None):
    """rect=[x,y,w,h] (figure fraction). 이미지 비율 유지해 박스 안에 맞춤."""
    if not Path(path).exists():
        return
    img = mpimg.imread(path)
    ih, iw = img.shape[0], img.shape[1]
    x, y, w, h = rect
    if title:
        fig.text(x, y + h + 0.005, title, fontsize=10.5, fontweight="bold", color=NAVY)
    ar_img = iw / ih
    ar_box = (w * A4[0]) / (h * A4[1])
    if ar_img > ar_box:      # 이미지가 더 넓다 → 폭 기준
        nw = w; nh = w * A4[0] / ar_img / A4[1]
    else:
        nh = h; nw = h * A4[1] * ar_img / A4[0]
    nx = x + (w - nw) / 2; ny = y + (h - nh) / 2
    a = fig.add_axes([nx, ny, nw, nh]); a.axis("off"); a.imshow(img)
    if cap:
        fig.text(x, y - 0.012, cap, fontsize=8.6, color=GRAY, style="italic")


pdf = PdfPages(OUT)
_PNGDIR = os.environ.get("GL_PDF_PNG")
_pageno = [0]


def emit(fig):
    pdf.savefig(fig)
    if _PNGDIR:
        _pageno[0] += 1
        fig.savefig(Path(_PNGDIR) / f"p{_pageno[0]}.png", dpi=90)
    plt.close(fig)

# ===================== 1. 표지 =====================
fig, ax = new_page()
ax.add_patch(FancyBboxPatch((0, 0.72), 1, 0.28, boxstyle="square,pad=0", fc=NAVY, ec="none",
                            transform=ax.transAxes))
ax.text(0.5, 0.90, "GL 분석적 절차 자동화 프로그램", transform=ax.transAxes, color="white",
        fontsize=25, fontweight="bold", ha="center")
ax.text(0.5, 0.855, "General Ledger  ·  Analytical Procedures & Fraud Screening",
        transform=ax.transAxes, color="#a9c7e8", fontsize=12, ha="center")
ax.text(0.5, 0.78, "계정별원장(엑셀)을 넣으면,  '어디를 먼저 봐야 하는지'를\n자동으로 짚어주는 감사 보조 도구",
        transform=ax.transAxes, color="white", fontsize=13.5, ha="center", va="center", linespacing=1.5)

# 3 기둥
pills = [("분석적 절차", "기대치를 벗어난\n계정·월 선별", "감사기준서 520", BLUE),
         ("부정 스크리닝", "위험 신호 가진\n전표 추출", "감사기준서 240", ORANGE),
         ("분식위험 점수", "재무제표 수준\n조작·부실 신호", "감사기준서 315", GREEN)]
for i, (t, d, s, c) in enumerate(pills):
    x = 0.09 + i * 0.30
    box(ax, x, 0.46, 0.26, 0.19, LBLUE)
    ax.add_patch(FancyBboxPatch((x, 0.605), 0.26, 0.045, boxstyle="round,pad=0.002,rounding_size=0.008",
                                fc=c, ec="none", transform=ax.transAxes))
    ax.text(x + 0.13, 0.627, t, transform=ax.transAxes, color="white", fontsize=12.5,
            fontweight="bold", ha="center", va="center")
    ax.text(x + 0.13, 0.545, d, transform=ax.transAxes, color=INK, fontsize=10.5,
            ha="center", va="center", linespacing=1.4)
    ax.text(x + 0.13, 0.478, s, transform=ax.transAxes, color=GRAY, fontsize=9, ha="center")

ax.text(0.5, 0.36, "이 문서는 프로그램의 목적과 결과의 의미를\n신입 회계사 눈높이에서 요약합니다.",
        transform=ax.transAxes, color=INK, fontsize=12, ha="center", va="center", linespacing=1.5)
ax.plot([0.09, 0.91], [0.09, 0.09], color="#cbd5e0", lw=1, transform=ax.transAxes)
ax.text(0.09, 0.06, "기반 기준서  감사기준서 520 · 240 · 315 · 320 · 200", transform=ax.transAxes,
        color=GRAY, fontsize=9.5)
ax.text(0.91, 0.06, "포트폴리오 · 2026", transform=ax.transAxes, color=GRAY, fontsize=9.5, ha="right")
emit(fig)

# ===================== 2. 왜 만들었나 =====================
fig, ax = new_page()
header(ax, "PURPOSE · 이 도구는 무엇을 위한 것인가", "1.  왜 만들었나 — 감사인의 고민")
y = bullets(ax, 0.09, 0.86, [
    ("수만~수십만 줄의 원장, 전수 확인은 불가능", "그래서 감사는 '위험이 높은 곳'을 골라 집중한다."),
    ("감사기준서 520 · 분석적 절차", "정상이라면 이 정도일 것 (기대치)을 세우고, 크게 벗어난 곳을 찾는다."),
    ("감사기준서 240 · 부정 위험", "주말 입력·라운드 금액·결산조정 등 '부정의 신호'를 가진 전표를 추린다."),
])
# 비유 박스
box(ax, 0.09, 0.545, 0.82, 0.11, "#fdf3e6")
ax.text(0.115, 0.63, "비유 — 건강검진과 같다", transform=ax.transAxes, color=ORANGE,
        fontsize=12, fontweight="bold", va="top")
ax.text(0.115, 0.60, "여러 수치를 재서 '정상 범위 밖'을 표시할 뿐, 그 자체가 '병 확진'이 아니다.\n"
        "정밀검사를 먼저 받아볼 대상을 골라주는 것 — 이 프로그램의 표시도 똑같다.",
        transform=ax.transAxes, color=INK, fontsize=10.5, va="top", linespacing=1.5)

ax.text(0.09, 0.49, "이 프로그램이 실제로 하는 일", transform=ax.transAxes, color=NAVY,
        fontsize=13, fontweight="bold")
bullets(ax, 0.09, 0.455, [
    ("", "엑셀 원장의 형식(더존·유니ERP 등)을 자동 인식해 표준화하고, 대차(차변=대변) 무결성을 검증"),
    ("", "계정 × 월 '기대구간'을 만들어, 벗어난 달을 검토 대상으로 표시"),
    ("", "전표 하나하나의 부정 위험신호를 점수화 (근거를 문장으로 분해)"),
    ("", "2년치가 있으면 재무제표 수준 분식위험(Beneish M · Altman Z')까지 산출"),
    ("", "모든 결과를 브라우저 대시보드로 즉시 확인"),
], dy=0.036, mark="▶", mcol=GREEN)
emit(fig)

# ===================== 3. 전체 흐름 =====================
fig, ax = new_page()
header(ax, "PIPELINE · 무엇을 어떤 순서로", "2.  전체 흐름 한눈에")

steps = ["원장 업로드\n(엑셀)", "형식 자동인식\n· 표준화", "무결성 검증\n(대차 대사)", "기대치 ·\n차이 분석"]
for i, s in enumerate(steps):
    x = 0.07 + i * 0.225
    box(ax, x, 0.79, 0.19, 0.075, LBLUE, ec=BLUE)
    ax.text(x + 0.095, 0.827, s, transform=ax.transAxes, ha="center", va="center",
            fontsize=10, color=INK, linespacing=1.3)
    if i < 3:
        ax.annotate("", xy=(x + 0.222, 0.827), xytext=(x + 0.19, 0.827), transform=ax.transAxes,
                    arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.6))

# 세 갈래 결과
ax.annotate("", xy=(0.5, 0.75), xytext=(0.5, 0.788), transform=ax.transAxes,
            arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.6))
outs = [("이상 플래그", "기대구간 밖 계정·월", BLUE),
        ("부정 스크리닝", "위험신호 전표 점수화", ORANGE),
        ("분식위험 점수", "재무제표 수준 위험", GREEN)]
for i, (t, d, c) in enumerate(outs):
    x = 0.09 + i * 0.29
    box(ax, x, 0.64, 0.25, 0.09, "white", ec=c)
    ax.add_patch(FancyBboxPatch((x, 0.695), 0.25, 0.035, boxstyle="round,pad=0.002,rounding_size=0.006",
                                fc=c, ec="none", transform=ax.transAxes))
    ax.text(x + 0.125, 0.712, t, transform=ax.transAxes, color="white", fontsize=11,
            fontweight="bold", ha="center", va="center")
    ax.text(x + 0.125, 0.663, d, transform=ax.transAxes, color=INK, fontsize=9.5, ha="center")

# 두 축 설명
ax.text(0.09, 0.57, "두 개의 축으로 본다", transform=ax.transAxes, color=NAVY, fontsize=13,
        fontweight="bold")
box(ax, 0.09, 0.40, 0.40, 0.14, "#eaf3ff")
ax.text(0.11, 0.515, "축 A · 전표 단위", transform=ax.transAxes, color=BLUE, fontsize=12,
        fontweight="bold", va="top")
ax.text(0.11, 0.485, "1년치 데이터로 가능", transform=ax.transAxes, color=GRAY, fontsize=9.5, va="top")
ax.text(0.11, 0.455, "개별 전표의 부정 신호를 본다.\n\"이 전표를 왜 이렇게 처리했지?\"",
        transform=ax.transAxes, color=INK, fontsize=10.5, va="top", linespacing=1.5)
box(ax, 0.51, 0.40, 0.40, 0.14, "#eafaf1")
ax.text(0.53, 0.515, "축 B · 회사 단위", transform=ax.transAxes, color=GREEN, fontsize=12,
        fontweight="bold", va="top")
ax.text(0.53, 0.485, "2년치 데이터 필요", transform=ax.transAxes, color=GRAY, fontsize=9.5, va="top")
ax.text(0.53, 0.455, "재무비율로 도산·이익조작 위험을 본다.\n\"이 회사 재무제표를 믿을 수 있나?\"",
        transform=ax.transAxes, color=INK, fontsize=10.5, va="top", linespacing=1.5)

box(ax, 0.09, 0.30, 0.82, 0.07, "#fdf3e6")
ax.text(0.115, 0.35, "데이터 양에 따라 분석법이 자동으로 바뀐다", transform=ax.transAxes,
        color=ORANGE, fontsize=11.5, fontweight="bold", va="top")
ax.text(0.115, 0.323, "1년치 → 통계밴드(평소 분포)   ·   2년치 → 전년 동월 대비(계절성 반영)   ·   3년+ → 시계열 분해(확장 예정)",
        transform=ax.transAxes, color=INK, fontsize=9.8, va="top")
emit(fig)

# ===================== 4. 결과 읽기 (1) =====================
fig, ax = new_page()
header(ax, "HOW TO READ · 화면별 결과의 의미 (1/2)", "3.  결과를 어떻게 읽나")

ax.text(0.09, 0.86, "① 이상 플래그 — 계정이 '평소 범위'를 벗어난 달", transform=ax.transAxes,
        color=NAVY, fontsize=13, fontweight="bold")
ax.text(0.09, 0.835, "파란 띠 = 이 계정의 정상 기대구간.  빨간 점 = 구간을 벗어난 달 = 먼저 확인할 대상.",
        transform=ax.transAxes, color=GRAY, fontsize=10)
put_image(fig, REP / "13_기대_외상매출금.png", [0.12, 0.60, 0.76, 0.20])

ax.text(0.09, 0.55, "② 위험 매트릭스 — '먼저 볼 순서'를 좌표로", transform=ax.transAxes,
        color=NAVY, fontsize=13, fontweight="bold")
ax.text(0.09, 0.525, "오른쪽일수록 통계적으로 많이 벗어남 · 위일수록 금액이 큼.  오른쪽 위 = 최우선 검토.",
        transform=ax.transAxes, color=GRAY, fontsize=10)
put_image(fig, REP / "15_위험매트릭스.png", [0.15, 0.20, 0.70, 0.29])
emit(fig)

# ===================== 5. 결과 읽기 (2) =====================
fig, ax = new_page()
header(ax, "HOW TO READ · 화면별 결과의 의미 (2/2)", "3.  결과를 어떻게 읽나 (계속)")

ax.text(0.09, 0.86, "③ 부정 의심 전표 — 점수는 '먼저 볼 순서'", transform=ax.transAxes,
        color=NAVY, fontsize=13, fontweight="bold")
bullets(ax, 0.09, 0.825, [
    ("", "각 전표의 위험 신호(주말·라운드금액·결산조정 등)를 배점 합산해 0~100점"),
    ("", "점수가 '왜 높은지'를 신호별로 분해해서 보여준다 (블랙박스 아님)"),
    ("", "'높음' 등급은 상세 카드로,  '중간' 등급은 전표 목록 표로 전부 확인"),
], dy=0.03, mark="·", mcol=ORANGE, fs=10.5)

ax.text(0.09, 0.70, "④ 분식위험 점수 — 재무제표 수준의 신호 (2년치)", transform=ax.transAxes,
        color=NAVY, fontsize=13, fontweight="bold")
box(ax, 0.09, 0.58, 0.40, 0.10, "#eafaf1")
ax.text(0.11, 0.66, "Altman Z' (도산위험)", transform=ax.transAxes, color=GREEN, fontsize=11.5,
        fontweight="bold", va="top")
ax.text(0.11, 0.633, "5개 재무비율로 재무곤경 가능성.\n안전 > 2.9 / 회색 / 위험 < 1.23",
        transform=ax.transAxes, color=INK, fontsize=10, va="top", linespacing=1.5)
box(ax, 0.51, 0.58, 0.40, 0.10, "#fdeeee")
ax.text(0.53, 0.66, "Beneish M (이익조작)", transform=ax.transAxes, color=RED, fontsize=11.5,
        fontweight="bold", va="top")
ax.text(0.53, 0.633, "8개 지표로 이익 부풀리기 신호.\nM > -1.78 이면 분식 의심",
        transform=ax.transAxes, color=INK, fontsize=10, va="top", linespacing=1.5)

ax.text(0.09, 0.545, "⑤ 보조 탐지 — 벤포드 법칙 (금액 첫자리 분포)", transform=ax.transAxes,
        color=NAVY, fontsize=13, fontweight="bold")
ax.text(0.09, 0.52, "자연스러운 금액은 첫자리가 1일 확률이 가장 높다(벤포드). 분포가 크게 어긋나면 인위적 조작 신호.",
        transform=ax.transAxes, color=GRAY, fontsize=10)
put_image(fig, REP / "04_벤포드.png", [0.17, 0.20, 0.66, 0.28])
emit(fig)

# ===================== 6. 해석 원칙 + 신호 사전 =====================
fig, ax = new_page()
header(ax, "PRINCIPLES · 결과를 오해하지 않으려면", "4.  해석의 3대 원칙")
principles = [
    ("표시 = '확정'이 아니라 '확인 순서'", "빨간 표시가 오류·부정을 확정하는 게 아니다.\n표시가 많아도 원장이 부실한 게 아니라, 스크리닝이 넓게 훑기 때문이다."),
    ("점수는 블랙박스가 아니다", "어떤 신호가 몇 점 기여했는지 항상 분해되어 보인다.\n감사인이 배점·임계값을 직접 조정할 수 있다."),
    ("최종 판단은 사람의 몫 (감사기준서 200)", "도구는 '먼저 볼 순서'를 제안할 뿐이다.\n정당한 결산분개도 걸릴 수 있어, 감사인의 직업적 회의로 확정한다."),
]
y = 0.85
for i, (h, b) in enumerate(principles, 1):
    box(ax, 0.09, y - 0.082, 0.82, 0.092, LBLUE if i % 2 else "#eef4fb")
    ax.text(0.115, y, f"{i}.  {h}", transform=ax.transAxes, color=NAVY, fontsize=12.5,
            fontweight="bold", va="top")
    ax.text(0.115, y - 0.032, b, transform=ax.transAxes, color=INK, fontsize=10, va="top",
            linespacing=1.5)
    y -= 0.115

ax.text(0.09, 0.42, "부정 신호 사전 (자주 나오는 것)", transform=ax.transAxes, color=NAVY,
        fontsize=13, fontweight="bold")
sig = [("주말 입력", "주말·휴일에 입력됨", "정규 결재 프로세스 밖일 수 있음"),
       ("딱 떨어지는 금액", "끝자리가 000", "실제 거래가 아닌 임의 산정 가능성"),
       ("결산조정 단어", "적요에 '수정·조정·대체'", "경영진의 임의 조정 여지"),
       ("거래처 없는 큰 금액", "상대방 없이 금액 큼", "거래 상대방이 불명확"),
       ("드문 계정 조합", "평소 안 엮이는 계정끼리", "비정상적 회계처리 신호"),
       ("중복 의심", "같은 날·거래처·금액 반복", "이중 계상 가능성")]
yy = 0.375
ax.text(0.10, yy, "신호", transform=ax.transAxes, color=GRAY, fontsize=9.5, fontweight="bold")
ax.text(0.28, yy, "무슨 뜻", transform=ax.transAxes, color=GRAY, fontsize=9.5, fontweight="bold")
ax.text(0.55, yy, "왜 보나", transform=ax.transAxes, color=GRAY, fontsize=9.5, fontweight="bold")
ax.plot([0.09, 0.91], [yy - 0.008, yy - 0.008], color="#cbd5e0", lw=1, transform=ax.transAxes)
yy -= 0.032
for n, m, w in sig:
    ax.text(0.10, yy, n, transform=ax.transAxes, color=INK, fontsize=10, fontweight="bold", va="top")
    ax.text(0.28, yy, m, transform=ax.transAxes, color=INK, fontsize=9.8, va="top")
    ax.text(0.55, yy, w, transform=ax.transAxes, color=GRAY, fontsize=9.8, va="top")
    yy -= 0.035

box(ax, 0.09, 0.055, 0.82, 0.06, NAVY)
ax.text(0.5, 0.085, "핵심 —  이 도구는 '답'이 아니라, 감사인이 '어디를 먼저 볼지'를 빠르게 정하도록 돕는다.",
        transform=ax.transAxes, color="white", fontsize=10, ha="center", va="center")
emit(fig)

pdf.close()
print("저장 완료:", OUT)
