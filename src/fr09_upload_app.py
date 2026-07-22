# -*- coding: utf-8 -*-
"""
드래그-드롭 업로드 대시보드 (Streamlit)
------------------------------------------------------------
브라우저에 계정별원장 엑셀을 끌어다 놓으면:
  1) 적응형 로더가 형식을 자동 인식해 표준화
  2) FR-02~05 분석 파이프라인을 백그라운드로 실행(실패 격리)
  3) 검증·기대치·플래깅·이상탐지 결과를 대시보드로 즉시 표시

실행:  streamlit run src/fr09_upload_app.py
       → 브라우저 http://localhost:8501 에서 파일을 끌어다 놓기
"""
import os
import re
import gc
import sys
import json
import shutil
import tempfile
import subprocess
import hashlib
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
from adaptive_loader import load_ledger
from explain_backend import _cause, _procedure, driver_txns

DICT = json.loads((SRC / "account_dict.json").read_text(encoding="utf-8"))
ITEMS = [c["표준항목"] for c in DICT["categories"]] + ["미분류"]

# 부정 스크리닝 신호 사전 — 전문 태그를 '아이콘·쉬운이름·왜 떴나·왜 보나·권고'로 번역(FR-09 이해 지원)
FLAG_GUIDE = {
    "상대계정조합": {"icon": "🔗", "name": "드문 계정 조합",
                 "why": "평소 잘 엮이지 않는 계정끼리 묶인 분개입니다",
                 "reason": "비정상적인 회계처리의 신호일 수 있습니다",
                 "act": "이 계정 조합이 왜 필요했는지 회계처리 근거를 확인하세요"},
    "결산수정키워드": {"icon": "✏️", "name": "결산조정 단어",
                  "why": "적요에 '수정·조정·대체' 등 결산조정 단어가 있습니다",
                  "reason": "경영진이 개입한 임의 조정일 여지가 있습니다(기준서 240)",
                  "act": "결산조정 사유와 승인(품의) 여부를 확인하세요"},
    "거래처없는대형": {"icon": "❓", "name": "거래처 없는 큰 금액",
                  "why": "거래처 없이 금액이 큰 전표입니다",
                  "reason": "거래 상대방이 불명확합니다",
                  "act": "거래 상대방과 증빙(계약서·세금계산서)을 확인하세요"},
    "중복전표": {"icon": "👯", "name": "중복 의심",
              "why": "같은 날·거래처·금액이 반복됩니다",
              "reason": "같은 거래가 이중으로 기록됐을 수 있습니다",
              "act": "이중 계상(같은 거래 두 번 기록) 여부를 대조하세요"},
    "라운드금액": {"icon": "🎯", "name": "딱 떨어지는 금액",
               "why": "금액 끝자리가 000으로 딱 떨어집니다",
               "reason": "실제 거래가 아니라 임의로 산정했을 가능성이 있습니다",
               "act": "실제 거래금액인지 산정 근거를 확인하세요"},
    "기말": {"icon": "📅", "name": "기말 집중",
           "why": "분기말·연말에 몰린 전표입니다",
           "reason": "실적을 맞추기 위한 조정일 여지가 있습니다",
           "act": "기말에 집중된 사유(실적 조정 여부)를 확인하세요"},
    "주말": {"icon": "🌙", "name": "주말 입력",
           "why": "주말·휴일에 입력된 전표입니다",
           "reason": "정규 결재 프로세스 밖일 수 있습니다",
           "act": "주말 입력 사유와 결재 절차를 확인하세요"},
    "적요모호": {"icon": "🌫️", "name": "모호한 적요",
              "why": "적요가 비었거나 너무 짧습니다",
              "reason": "거래 근거가 불명확합니다",
              "act": "적요를 보완하고 실제 거래 내용을 확인하세요"},
    "수기전표": {"icon": "🖐️", "name": "수기 전표",
              "why": "시스템 자동이 아닌 수기(수동)로 입력된 전표입니다",
              "reason": "자동 통제 밖에서 입력됐습니다",
              "act": "수기 입력 사유와 승인 여부를 확인하세요"},
    "소급입력": {"icon": "⏪", "name": "소급 입력",
              "why": "회계일보다 한참 늦게 입력된(소급) 전표입니다",
              "reason": "사후에 조정했을 여지가 있습니다",
              "act": "회계일과 입력일 차이(소급)의 사유를 확인하세요"},
    "작성자이상": {"icon": "👤", "name": "이례적 작성자",
               "why": "드물게 등장하는 작성자가 큰 금액을 처리했습니다",
               "reason": "권한 밖 처리일 가능성이 있습니다",
               "act": "작성자의 권한과 처리 적정성을 확인하세요"},
}


def parse_reason(s):
    """'주말(10), 라운드금액(15)' → [('라운드금액',15),('주말',10)] (점수 내림차순)."""
    if not isinstance(s, str):
        return []
    pairs = [(n, int(v)) for n, v in re.findall(r"([가-힣]+)\((\d+)\)", s)]
    return sorted(pairs, key=lambda x: -x[1])


EOK = 100_000_000
MAX_MB = 100
# 업로드 화면은 저사양 PC 대비 핵심 단계만(FR-05 보조탐지는 메모리 커서 배치에서만 실행)
STEPS = [("검증(FR-02)", "fr02_validate.py"), ("기대치(FR-03)", "fr03_expectation.py"),
         ("플래깅(FR-04)", "fr04_flagging.py"), ("부정스크리닝(FR-09)", "fraud_screen.py"),
         ("계정분류(FR-10)", "fr10_classify.py")]

st.set_page_config(page_title="GL 원장 분석", layout="wide", page_icon="📊")
st.markdown("""<style>
:root{ --ink:#33333D; --accent:#FFE600; --muted:#8A8A94; --line:#ECECF0; --surface:#F8F8FA; }
html, body, [class*="css"]{ font-family:'Pretendard','Malgun Gothic','Segoe UI',system-ui,sans-serif; }
.block-container{ padding-top:1.5rem; padding-bottom:3rem; max-width:1180px; }
h1,h2,h3{ letter-spacing:-.4px; color:var(--ink); }

/* ── 사이드바 ── */
[data-testid="stSidebar"]{ border-right:1px solid var(--line); }
.brand{ display:flex; gap:11px; align-items:center; margin:.1rem 0 .3rem; }
.brand-mark{ font-size:1.25rem; width:42px; height:42px; display:flex; align-items:center;
  justify-content:center; border-radius:10px; color:#33333D;
  background:#FFE600; box-shadow:0 4px 12px rgba(46,46,56,.16); }
.brand-name{ font-weight:800; font-size:1.02rem; color:var(--ink); line-height:1.1; }
.brand-sub{ font-size:.6rem; color:var(--muted); letter-spacing:1px; font-weight:700; }
.side-mode{ margin-top:.7rem; padding:.55rem .7rem; background:var(--surface); border:1px solid var(--line);
  border-left:4px solid #C7C7CF; border-radius:8px; font-size:.8rem; color:var(--ink); font-weight:600; }

/* ── 히어로 (EY: 다크 그레이 + 옐로우 악센트) ── */
.hero{ background:linear-gradient(120deg,#3A3A46 0%,#26262F 100%);
  border-left:6px solid #FFE600; border-radius:14px; padding:16px 26px; margin:.1rem 0 .7rem; color:#fff;
  box-shadow:0 10px 26px rgba(46,46,56,.16); }
.hero-eyebrow{ font-size:.64rem; letter-spacing:2px; color:#FFE600; font-weight:800; }
.hero-title{ font-size:1.4rem; font-weight:800; margin-top:2px; letter-spacing:-.5px; color:#fff; }
.hero-sub{ font-size:.86rem; color:#C7C7CF; margin-top:4px; }
.hero-empty{ padding:48px 32px; text-align:center; }
.hero-empty .hero-title{ font-size:2.05rem; }
.hero-cta{ margin-top:16px; display:inline-block; font-size:.9rem; color:#fff; font-weight:600;
  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.22);
  padding:9px 18px; border-radius:999px; }

/* ── KPI 카드 (옐로우 상단 악센트) ── */
.kpi-row{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:.5rem; }
.kpi{ background:#fff; border:1px solid var(--line); border-top:3px solid var(--accent);
  border-radius:12px; padding:15px 18px; box-shadow:0 1px 3px rgba(46,46,56,.05); transition:.15s; }
.kpi:hover{ box-shadow:0 6px 18px rgba(46,46,56,.10); transform:translateY(-1px); }
.kpi-label{ font-size:.74rem; color:var(--muted); font-weight:700; letter-spacing:.2px; }
.kpi-val{ font-size:1.5rem; font-weight:800; color:var(--ink); margin-top:4px; line-height:1.1; }
.kpi-sub{ font-size:.72rem; color:var(--muted); margin-top:3px; }

/* ── 탭 (옐로우 언더라인) ── */
[data-testid="stTabs"] [data-baseweb="tab-list"]{ gap:2px; border-bottom:1px solid var(--line); }
button[data-baseweb="tab"]{ font-size:.92rem; font-weight:600; color:var(--muted); padding:.5rem .9rem; }
button[data-baseweb="tab"][aria-selected="true"]{ color:var(--ink); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"]{ background:var(--accent); height:3px; border-radius:3px; }
button[data-baseweb="tab"][aria-selected="true"]{ color:#33333D; }

/* ── 카드류·기타 ── */
[data-testid="stExpander"]{ border:1px solid var(--line); border-radius:12px;
  box-shadow:0 1px 2px rgba(46,46,56,.03); }
[data-testid="stExpander"] summary{ font-weight:600; }
[data-testid="stAlert"]{ border-radius:12px; border:1px solid rgba(0,0,0,.04); }
[data-testid="stDataFrame"]{ border:1px solid var(--line); border-radius:10px; }
[data-testid="stMetricValue"]{ font-size:1.5rem; font-weight:800; color:var(--ink); }
hr{ margin:1.1rem 0; border:none; border-top:1px solid var(--line); }
.stButton>button, [data-testid="stFileUploader"] button{ border-radius:9px; font-weight:700;
  padding:.4rem 1rem; background:#454550; color:#fff; border:1px solid #454550; }
.stButton>button:hover, [data-testid="stFileUploader"] button:hover{ background:#5A5A66;
  color:#fff; border-color:#5A5A66; }

/* 공통 표(html_table) — 회사·내용과 무관하게 형식 고정 */
.gltbl{ table-layout:fixed; width:100%; border-collapse:collapse; font-size:.85rem; margin:.2rem 0 .4rem; }
.gltbl th{ text-align:center; background:#F7F7F9; color:#33333D; font-weight:700;
  padding:6px 8px; border-bottom:2px solid #E4E4E9; }
.gltbl td{ text-align:center; padding:5px 8px; border-bottom:1px solid #F0F0F3;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
</style>""", unsafe_allow_html=True)

# 모든 plotly 차트에 통일 테마 적용(투명 배경·은은한 그리드·일관 색상)
pio.templates["gl"] = go.layout.Template(layout=dict(
    font=dict(family="Malgun Gothic, Segoe UI, sans-serif", color="#2E2E38", size=12),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=["#2E2E38", "#747480", "#B9B9C0", "#E4002B", "#9CA3AF", "#4A4A55"],
    xaxis=dict(gridcolor="#F1F1F4", linecolor="#ECECF0", zerolinecolor="#ECECF0"),
    yaxis=dict(gridcolor="#F1F1F4", linecolor="#ECECF0", zerolinecolor="#ECECF0"),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
))
pio.templates.default = "gl"


# 서브프로세스 공통 env: 차트 생략(GL_NO_CHARTS)으로 대시보드 실행 가속(대시보드는 plotly 사용)
PIPE_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
            "MPLBACKEND": "Agg", "GL_NO_CHARTS": "1"}


@st.cache_data(show_spinner=False)
def standardize(file_bytes, filename):
    """엑셀 → 표준화(gl_clean·trial_balance). 무거운 엑셀 파싱은 파일당 여기서 딱 한 번.
       반환: (base, meta, year).  (파일 내용 기준 캐시 → 같은 파일 재사용 무료)"""
    work = Path(tempfile.gettempdir()) / "gl_upload"
    work.mkdir(parents=True, exist_ok=True)
    src = work / filename
    src.write_bytes(file_bytes)
    r = load_ledger(src)                                   # 적응형 로드(형식 자동 인식)
    meta = r["meta"]
    base = work / ("std_" + hashlib.md5(file_bytes).hexdigest()[:10])
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "reports").mkdir(exist_ok=True)
    r["gl"].to_csv(base / "data" / "gl_clean.csv", index=False, encoding="utf-8-sig")
    r["tb"].to_csv(base / "data" / "trial_balance.csv", index=False, encoding="utf-8-sig")
    yr = (int(pd.to_datetime(r["gl"]["전표일자"]).dt.year.max())
          if len(r["gl"]) else None)
    del r, src
    gc.collect()
    return str(base), meta, yr


@st.cache_data(show_spinner=False)
def run_pipeline(base):
    """표준화된 폴더에 FR-02~10 분석 실행(차트 생략). (base 기준 캐시)"""
    env = {**PIPE_ENV, "GL_BASE": str(base)}
    logs = []
    for label, script in STEPS:
        try:
            p = subprocess.run([sys.executable, str(SRC / script)], env=env,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            logs.append((label, p.returncode == 0,
                         "" if p.returncode == 0 else
                         (p.stderr.strip().splitlines() or [""])[-1][:80]))
        except Exception as e:
            logs.append((label, False, f"{type(e).__name__}: {str(e)[:60]}"))
    return logs


@st.cache_data(show_spinner=False)
def build_two_year(cur_base, prior_base):
    """당기+전기 원장을 병합해 2년치 폴더를 만들고 FR-03·FR-04를 재실행한다.
       → FR-03이 데이터 2년을 감지해 '전년 동월 대비(YoY)' 기대치로 자동 전환.
       반환: (yoy_base, n_year, method)  n_year<2면 YoY 미적용(연도 안 겹치는지 확인용)."""
    cur = pd.read_csv(Path(cur_base) / "data" / "gl_clean.csv",
                      dtype={"계정코드": str}, parse_dates=["전표일자"])
    pri = pd.read_csv(Path(prior_base) / "data" / "gl_clean.csv",
                      dtype={"계정코드": str}, parse_dates=["전표일자"])
    combo = pd.concat([pri, cur], ignore_index=True)
    n_year = combo["전표일자"].dt.year.nunique()
    yb = Path(cur_base).parent / ("yoy_" + Path(cur_base).name)
    (yb / "data").mkdir(parents=True, exist_ok=True)
    (yb / "reports").mkdir(exist_ok=True)
    combo.to_csv(yb / "data" / "gl_clean.csv", index=False, encoding="utf-8-sig")
    shutil.copy(Path(cur_base) / "data" / "trial_balance.csv",   # 잔액 판정용(당기 기준)
                yb / "data" / "trial_balance.csv")
    del cur, pri, combo
    gc.collect()
    env = {**PIPE_ENV, "GL_BASE": str(yb)}
    for script in ("fr03_expectation.py", "fr04_flagging.py"):
        subprocess.run([sys.executable, str(SRC / script)], env=env,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    method = "전년 동월 대비(YoY)" if n_year >= 2 else "로버스트 통계밴드(단일연도)"
    return str(yb), int(n_year), method


@st.cache_data(show_spinner=False)
def run_fraud_scores(cur_base, prior_base):
    """FR-11 재무제표 분식위험 점수(Beneish M · Altman Z') 산출.
       2년치면 (전기, 당기)로 M-Score까지, 단일연도면 당기만 → Altman Z'만."""
    args = [sys.executable, str(SRC / "fr11_fraud_scores.py")]
    args += ([str(prior_base), str(cur_base)] if prior_base else [str(cur_base)])
    subprocess.run(args, env=PIPE_ENV, capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=600)
    return str(Path(cur_base) / "data" / "fr11_fraud_scores.csv")


def read_csv(base, name, **kw):
    p = Path(base) / "data" / name
    return pd.read_csv(p, **kw) if p.exists() else None


def _esc(v):
    return ("" if v is None or (isinstance(v, float) and pd.isna(v)) else
            str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def html_table(df, wide=("적요",)):
    """헤더·셀 가운데 정렬 + 고정 레이아웃 표(회사·내용과 무관하게 형식 동일).
       wide 열은 넓게, 나머지는 균등. 긴 텍스트는 …로 잘라 표 크기가 변하지 않음."""
    w = [3.0 if c in wide else 1.0 for c in df.columns]
    tot = sum(w) or 1
    cols = "".join(f'<col style="width:{x/tot*100:.1f}%">' for x in w)
    th = "".join(f"<th>{_esc(c)}</th>" for c in df.columns)
    body = ""
    for _, r in df.iterrows():
        body += "<tr>" + "".join(f'<td title="{_esc(v)}">{_esc(v)}</td>' for v in r) + "</tr>"
    st.markdown(f'<table class="gltbl"><colgroup>{cols}</colgroup>'
                f'<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>',
                unsafe_allow_html=True)


def kmon(m, multi):
    """'2025-01' → 단일연도 '1월' / 다연도 '25년 1월' (월 표시를 한글로 통일)."""
    y, mm = str(m).split("-")[:2]
    return f"{y[2:]}년 {int(mm)}월" if multi else f"{int(mm)}월"


def eok2(x):
    """금액을 억단위·소수점 둘째자리 문자열로 통일('5.00')."""
    return f"{x / EOK:,.2f}"


def benchmark_rev(gl):
    mae = gl["계정명"].astype(str).str.contains("매출", na=False) & \
        ~gl["계정명"].astype(str).str.contains("원가|차감|환입|할인|에누리", na=False)
    rev = gl.loc[mae, "대변"].sum() - gl.loc[mae, "차변"].sum()
    return rev if rev > 0 else gl["차변"].sum()


def audit_response(name, std, cat, direction):
    """발견(계정·방향)을 감사 대응으로 번역: (의심 주장 리스트, 권고 절차 리스트).
       감사기준서 315(위험평가)·330(대응) 흐름. 계정 유형별 휴리스틱."""
    n = f"{name} {std}"
    up = (direction == "급증")

    def has(*ks):
        return any(k in n for k in ks)

    if has("매출채권", "외상매출", "받을어음", "미수"):
        a = ["실재성(존재)", "기간귀속(cut-off)"] if up else ["완전성"]
        p = ["매출채권 조회서 발송·회수 대사", "기말 전후 매출 cut-off 테스트(선적·인도 증빙 확인)",
             "기말 후 회수(subsequent receipt) 확인"]
    elif has("매출") and not has("원가"):
        a = ["발생사실(occurrence)", "기간귀속(cut-off)"]
        p = ["기말 매출 cut-off 테스트", "수익인식 기준·계약 조건 검토", "반품·에누리 후속 확인"]
    elif has("현금", "예금", "당좌"):
        a = ["실재성(존재)"]
        p = ["은행 조회서 발송", "은행잔액조정표 대사", "기말 입출금 증빙 확인"]
    elif has("재고", "상품", "제품", "원재료", "재공품", "저장품"):
        a = ["실재성(존재)", "평가(순실현가치)"]
        p = ["재고 실사 입회·수량 대사", "저가법(NRV) 평가 검토", "기말 재고 cut-off"]
    elif has("유형자산", "건물", "기계", "비품", "토지", "건설중", "차량"):
        a = ["실재성(존재)", "평가"]
        p = ["취득 증빙 대사(계약서·세금계산서)", "자본적지출/수선비 구분 검토", "감가상각 재계산"]
    elif has("매입채무", "외상매입", "지급어음", "미지급"):
        a = ["완전성(누락 여부)"]
        p = ["채무 조회·구매처 확인", "기말 후 지급(subsequent payment) 검토", "미계상 부채 탐색"]
    elif has("차입", "사채", "리스부채"):
        a = ["완전성", "평가"]
        p = ["금융기관 조회서", "약정서·상환일정 대사", "이자비용 재계산"]
    elif (cat and "비용" in str(cat)) or has("판관", "원가", "관리비", "급여", "수수료"):
        a = ["발생사실(occurrence)", "기간귀속(cut-off)"]
        p = ["증빙 대사(vouching)", "기간귀속 테스트", "이례적 거래처·금액 확인"]
    else:
        a = ["실재성(존재)", "평가"]
        p = ["대표 전표 증빙 대사", "담당자 문의·거래 배경 확인"]
    if not up and "실재성(존재)" in a:
        a = a + ["완전성(누락 여부)"]
    return a, p


# ============ 사이드바: 브랜드 + 업로드 ============
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">📊</div><div>'
        '<div class="brand-name">GL 원장 분석</div>'
        '<div class="brand-sub">분석적 절차 · 부정 스크리닝</div>'
        '</div></div>', unsafe_allow_html=True)
    ups = st.file_uploader(
        "계정별원장 (.xlsx / .xls)", type=["xlsx", "xls"], accept_multiple_files=True,
        help="여러 해를 함께 올리면 '전년 동월 대비'로 자동 전환됩니다")

if not ups:
    st.markdown(
        '<div class="hero hero-empty">'
        '<div class="hero-eyebrow">GL 감사 대시보드</div>'
        '<div class="hero-title">계정별원장 분석 자동화</div>'
        '<div class="hero-sub">감사기준서 520 · 240 기반 — 분석적 절차와 부정 스크리닝을 한 화면에서</div>'
        '<div class="hero-cta">← 왼쪽 사이드바에 엑셀 원장을 올리면 분석이 시작됩니다</div>'
        '</div>', unsafe_allow_html=True)
    st.stop()

for u in ups:
    if len(u.getvalue()) > MAX_MB * 1e6:
        st.error(f"‘{u.name}’이(가) {len(u.getvalue())/1e6:.0f}MB로 너무 큽니다(한계 {MAX_MB}MB).")
        st.stop()

# 표준화(엑셀 1회 로드) + 연도 판별 → 당기(최신)·전기(그 직전)
try:
    with st.spinner("파일 인식 중..."):
        peeked = []
        for u in ups:
            sb, sm, yr = standardize(u.getvalue(), u.name)
            peeked.append({"name": u.name, "base": sb, "meta": sm, "year": yr})
    peeked.sort(key=lambda p: (p["year"] or 0))
except Exception as e:
    st.error(f"파일을 읽지 못했습니다: {type(e).__name__}: {e}")
    st.stop()

cur = peeked[-1]                                  # 최신 연도 = 당기
prior = peeked[-2] if len(peeked) >= 2 else None  # 그 직전 = 전기
base, meta = cur["base"], cur["meta"]

try:
    with st.spinner("분석 실행 중... (파일이 크면 시간이 걸립니다)"):
        logs = run_pipeline(base)
except Exception as e:
    st.error(f"분석 실행 실패: {type(e).__name__}: {e}")
    st.stop()

# 품질·중요성 계산
gl = read_csv(base, "gl_clean.csv", dtype={"계정코드": str}, parse_dates=["전표일자"])
gl["월"] = gl["전표일자"].dt.to_period("M").astype(str)
rev = benchmark_rev(gl)
PM = rev * 0.00375
diff = abs(meta["debit"] - meta["credit"])
ratio = diff / max(meta["debit"], 1)
grade = ("완벽" if diff < 1 else "사실상 일치" if ratio < 0.001
         else "근접" if ratio < 0.01 else "검토 필요")

# 파일 개수 → 단일연도 / 2년치(YoY·M-Score) 자동
analysis_base = base
prior_base = prior_meta = None
yoy_on = False
if prior is not None:
    try:
        with st.spinner("2년치 기대치(전년 동월 대비) 재계산 중..."):
            prior_base, prior_meta = prior["base"], prior["meta"]
            yoy_base, ny, _ = build_two_year(base, prior_base)
        if ny >= 2:
            analysis_base, yoy_on = yoy_base, True
    except Exception as e:
        st.error(f"2년치 분석 실패: {type(e).__name__}: {e}")

if len(peeked) == 1:
    mode = f"단일연도 · {cur['year']}"
elif yoy_on:
    mode = f"2년치 · 전년 동월 대비  ·  당기 {cur['year']} / 전기 {prior['year']}"
else:
    mode = "단일연도 (연도 중복으로 2년치 미적용)"

# 재무제표 수준 위험 점수(FR-11) 산출 — 2년치면 M-Score까지, 단일연도면 Altman Z'만
try:
    run_fraud_scores(base, prior_base if yoy_on else None)
except Exception:
    pass

# ============ 사이드바: 회사명 + 상태 ============
with st.sidebar:
    company = st.text_input("회사명", value=meta["company"], help="자동 감지값 · 필요하면 수정")
    st.markdown(f'<div class="side-mode">{mode}</div>', unsafe_allow_html=True)
    st.caption(f"인식 형식 · {meta['layout']}")

# ============ 메인: 히어로 + KPI 카드 ============
st.markdown(
    f'<div class="hero"><div class="hero-eyebrow">GL 감사 대시보드</div>'
    f'<div class="hero-title">{company}</div>'
    f'<div class="hero-sub">{mode}</div></div>', unsafe_allow_html=True)


def _kpi(label, val, sub=""):
    s = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-val">{val}</div>{s}</div>')


st.markdown(
    '<div class="kpi-row">'
    + _kpi("계정 수", f"{meta['n_accounts']:,}")
    + _kpi("분개 줄 수", f"{meta['n_rows']:,}")
    + _kpi("대차 품질", grade, f"오차율 {ratio:.2%}")
    + _kpi("성과중요성", f"{PM / EOK:,.2f}억")
    + '</div>', unsafe_allow_html=True)

if sum(ok for _, ok, _ in logs) < len(logs):
    st.caption("⚠️ 일부 분석 단계 실패: " + ", ".join(lbl for lbl, ok, _ in logs if not ok))
if grade == "검토 필요":
    st.warning("대차가 크게 어긋납니다(형식 특수 가능성). 수치는 재확인이 필요합니다.")

flags = read_csv(analysis_base, "fr04_flags.csv", dtype={"계정코드": str})
exp = read_csv(analysis_base, "fr03_expectations.csv", dtype={"계정코드": str})
vres = read_csv(base, "fr02_results.csv")
fraud = read_csv(base, "fr09_fraud_flags.csv")
fscore = read_csv(base, "fr11_fraud_scores.csv")
amap = read_csv(base, "fr10_account_map.csv", dtype={"계정코드": str})

# 등급 문자열의 색 이모지 제거(높음/중간/낮음 텍스트만) — 필터는 단어 기반이라 그대로 동작
_EMO = r"[🔴🟠🟡🟢⚪]\s*"
for _df in (flags, fraud):
    if _df is not None and "등급" in _df.columns:
        _df["등급"] = _df["등급"].astype(str).str.replace(_EMO, "", regex=True)

# ============ 3초 요약 (탭 위, 항상 표시) ============
_order = None
if flags is None or flags.empty:
    st.success(f"이상 없음 — 분석적 절차에서 검토 우선 항목이 발견되지 않았습니다. (대차 {grade})")
    _method = "전년 동월 대비" if yoy_on else "통계밴드(단일연도)"
else:
    n_facct = flags["계정명"].nunique()
    n_high = int((flags["등급"] == "높음").sum())
    _t0 = flags.iloc[0]
    _lvl = "#E4002B" if n_high > 0 else "#B9B9C0"
    _method = "전년 동월 대비" if yoy_on else "통계밴드(단일연도)"
    _sent = (f"<b>{meta['n_accounts']}개 계정</b> 중 <b>{n_facct}개</b>에서 이상 <b>{len(flags)}건</b> · "
             f"대차 {grade} · 기준 {_method} · 최우선 <b>{_t0['계정명']}</b> "
             f"({kmon(_t0['월'], yoy_on)} {_t0['방향']}, 편차 {_t0['편차']/EOK:+,.2f}억)")
    st.markdown(f'<div style="border:1px solid #ECECF0;border-left:5px solid {_lvl};'
                f'background:#F8F8FA;border-radius:10px;padding:10px 16px;margin:.1rem 0 .7rem;'
                f'font-size:1.0rem;color:#33333D;">{_sent}</div>', unsafe_allow_html=True)
    _order = flags.groupby("계정명", sort=False)["위험점수"].max().sort_values(ascending=False)

_ZMEAN = {"X1": "운전자본/총자산", "X2": "이익잉여금/총자산", "X3": "EBIT/총자산",
          "X4": "자기자본/총부채", "X5": "매출/총자산"}
_MMEAN = {"DSRI": "매출채권/매출 증가", "GMI": "매출총이익률 악화", "AQI": "자산 부실화",
          "SGI": "매출성장", "DEPI": "감가상각률 둔화", "SGAI": "판관비율 증가",
          "LVGI": "레버리지 증가", "TATA": "발생액/총자산"}


def _gauge(value, rng, steps, thr):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        number={"font": {"size": 30, "color": "#2E2E38"}},
        gauge={"axis": {"range": rng, "tickcolor": "#B9B9C0", "tickfont": {"size": 10}},
               "bar": {"color": "#2E2E38", "thickness": 0.28}, "borderwidth": 0,
               "steps": steps,
               "threshold": {"line": {"color": "#E4002B", "width": 3}, "value": thr}}))
    fig.update_layout(height=190, margin=dict(l=24, r=24, t=8, b=0))
    return fig


def fs_gauges(fscore, yoy_on):
    """재무제표 수준 위험 점수(FR-11)를 게이지로 도식화 — 도산(Altman Z')·분식주의(Beneish M)."""
    if fscore is None or fscore.empty:
        return False
    st.markdown("**재무제표 수준 위험 점수** · 도산위험 · 분식주의 (학술 계량모형 · 참고용)")
    st.caption("개별 전표가 아니라 재무제표 '전체 수준'의 위험을 확립된 계량모형으로 본 참고 지표입니다. "
               "확정이 아니라 추가 절차의 단서로만 씁니다 (감사기준서 200·240).")
    zrow = fscore[fscore["모형"] == "Altman Z'"]
    mrow = fscore[fscore["모형"] == "Beneish M"]
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Altman Z′ · 도산위험**")
        if len(zrow) and pd.notna(zrow.iloc[0]["점수"]):
            z = float(zrow.iloc[0]["점수"])
            zone = "🟢 안전" if z > 2.9 else ("🟠 회색(관찰)" if z > 1.23 else "🔴 위험")
            st.plotly_chart(_gauge(z, [0, 6],
                [{"range": [0, 1.23], "color": "#F3C7CD"},
                 {"range": [1.23, 2.9], "color": "#E6E6EA"},
                 {"range": [2.9, 6], "color": "#CFE3D6"}], 1.23),
                use_container_width=True, config={"displayModeBar": False})
            st.markdown(f"판정 **{zone}** · 안전&gt;2.9 / 회색 1.23~2.9 / 위험&lt;1.23")
            st.caption("재무곤경·도산 가능성 · 높을수록 안전")
        else:
            st.info("산출 불가(데이터 부족).")
    with g2:
        st.markdown("**Beneish M · 분식주의 신호**")
        if len(mrow) and pd.notna(mrow.iloc[0]["점수"]):
            m = float(mrow.iloc[0]["점수"])
            note = "🟢 정상권" if m < -2.22 else ("🟠 관찰 구간" if m < -1.78 else "🔴 주의 신호")
            st.plotly_chart(_gauge(m, [-4, 1],
                [{"range": [-4, -2.22], "color": "#CFE3D6"},
                 {"range": [-2.22, -1.78], "color": "#F5E7C2"},
                 {"range": [-1.78, 1], "color": "#F3C7CD"}], -1.78),
                use_container_width=True, config={"displayModeBar": False})
            st.markdown(f"판정 **{note}** · 표준선 -1.78 / 보수선 -2.22")
            st.caption("이익조작 가능성 신호 · 낮을수록 정상 · 확정 아님(참고용)")
        elif not yoy_on:
            st.info("2개 연도가 있어야 산출됩니다(당기·전기 비교 필요).")
        else:
            st.info("산출 불가(데이터 부족).")
    with st.expander("지표 분해 — 각 모형이 무엇을 보는가"):
        cc = st.columns(2)
        for col, row, mean in ((cc[0], zrow, _ZMEAN), (cc[1], mrow, _MMEAN)):
            if not len(row):
                continue
            try:
                idx = json.loads(row.iloc[0]["지표"])
            except Exception:
                idx = {}
            recs = [{"지표": k, "의미": mean.get(k, ""),
                     "값": (round(v, 3) if isinstance(v, (int, float)) else "n/a")}
                    for k, v in idx.items()]
            if recs:
                col.markdown(f"**{row.iloc[0]['모형']}**")
                col.dataframe(pd.DataFrame(recs), hide_index=True, use_container_width=True)
    return True


t_heat, t_detail, t3, t5, t7 = st.tabs(
    ["리스크 히트맵", "계정별 상세", "검증·시산표", "부정·이상 탐지 (실험)", "계정 분류"])

# ---- 탭: 리스크 히트맵 ----
with t_heat:
    if _order is None or exp is None:
        st.info("표시할 이상 항목이 없습니다.")
    else:
        st.caption(f"계정 × 월 · 색이 진할수록 검토 우선 · 당기 기준 (기법 {_method})")
        st.markdown('<div style="font-size:.72rem;color:#9aa4b2;margin:-2px 0 4px">'
                    'z = 이탈도(로버스트 z) · 그 달 실제값이 기대치에서 <b>평소 변동폭의 몇 배</b>만큼 '
                    '벗어났는지 · |z|가 클수록 이례적 (통상 |z|&gt;3.5면 이상 후보)</div>',
                    unsafe_allow_html=True)
        _acc_list = list(_order.index[:18])
        _ex = exp[exp["계정명"].isin(_acc_list)].copy()
        _cy = exp["월"].str[:4].max()                 # 당기(최신 연도)
        _ex = _ex[_ex["월"].str[:4] == _cy]           # 판정 대상은 당기뿐 → 히트맵도 당기만
        _ex["absz"] = _ex["로버스트z"].abs()
        hm = (_ex.pivot_table(index="계정명", columns="월", values="absz", aggfunc="max")
              .reindex(_acc_list).fillna(0))
        heat = go.Figure(go.Heatmap(
            z=hm.values, x=[kmon(c, False) for c in hm.columns], y=list(hm.index),
            colorscale=[[0, "#F8F8FA"], [0.5, "#B4B4BC"], [1, "#33333D"]],
            zmin=0, zmax=6, xgap=2, ygap=2,
            hovertemplate="%{y} · %{x}<br>이탈 |z| %{z:.1f}<extra></extra>",
            colorbar=dict(title="|z|", thickness=10)))
        heat.update_layout(height=min(560, 80 + 27 * len(hm.index)),
                           margin=dict(l=10, r=10, t=6, b=6),
                           yaxis=dict(autorange="reversed"))
        st.plotly_chart(heat, use_container_width=True, config={"displayModeBar": False})

# ---- 탭: 계정별 상세 (라디오 선택) ----
with t_detail:
    if _order is None:
        st.info("이상 항목이 없습니다.")
    else:
        accts = (flags.groupby("계정명", sort=False)
                 .agg(건수=("월", "size"), 최고등급=("등급", "first"))
                 .reset_index())
        _GR = {"높음": 0, "중간": 1, "낮음": 2}          # 위험 높은 순 → 가나다순
        accts = (accts.assign(_g=accts["최고등급"].map(lambda g: _GR.get(g, 3)))
                 .sort_values(["_g", "계정명"]).reset_index(drop=True))
        _DOT = {"높음": "🔴", "중간": "🟠", "낮음": "🟡"}
        st.markdown('<div style="font-size:.7rem;color:#9aa4b2;text-align:right;margin:-4px 0 2px">'
                    '🔴 높음 · 🟠 중간 · 🟡 낮음 위험 · 높은 순 → 가나다순</div>',
                    unsafe_allow_html=True)
        labels = [f"{_DOT.get(r['최고등급'], '⚪')}  {r['계정명']}   ·   이상 {r['건수']}개월"
                  for _, r in accts.iterrows()]
        pick = st.selectbox("계정 선택", labels, label_visibility="collapsed")
        acct = accts.iloc[labels.index(pick)]["계정명"]
        sub = flags[flags["계정명"] == acct].sort_values("월").reset_index(drop=True)
        nat = "차변성격"
        if exp is not None:
            _n = exp.loc[exp["계정명"] == acct, "자연방향"]
            if len(_n):
                nat = _n.iloc[0]
        if exp is not None:
            d = exp[exp["계정명"] == acct].sort_values("월").copy()
            d["이상여부"] = d["이상여부"].astype(str).str.lower().isin(["true", "1"])
            d["연"] = d["월"].str[:4]
            d["월num"] = d["월"].str[5:7].astype(int)
            d["월표"] = d["월num"].astype(str) + "월"
            fig = go.Figure()
            if yoy_on and d["연"].nunique() >= 2:
                cy, py = d["연"].max(), d["연"].min()      # 당기·전기 연도
                cd = d[d["연"] == cy].sort_values("월num")
                pr = d[d["연"] == py].sort_values("월num")
                # 기대구간(당기 기준)
                fig.add_trace(go.Scatter(x=cd["월표"], y=cd["상한"] / EOK, line=dict(width=0),
                                         showlegend=False, hoverinfo="skip"))
                fig.add_trace(go.Scatter(x=cd["월표"], y=cd["하한"] / EOK, fill="tonexty",
                                         fillcolor="rgba(255,214,0,0.16)", line=dict(width=0),
                                         name="기대구간", hoverinfo="skip"))
                # 전기(골드 점선 · 눈에 잘 들어오도록)
                fig.add_trace(go.Scatter(x=pr["월표"], y=pr["월값"] / EOK, mode="lines+markers",
                                         name=f"전기 {py}",
                                         line=dict(color="#C79A00", dash="dot", width=2.2),
                                         marker=dict(size=7, symbol="diamond")))
                # 당기
                fig.add_trace(go.Scatter(x=cd["월표"], y=cd["월값"] / EOK, mode="lines+markers",
                                         name=f"당기 {cy}", line=dict(color="#2E2E38", width=2.5)))
                od = cd[cd["이상여부"]]
                fig.add_trace(go.Scatter(x=od["월표"], y=od["월값"] / EOK, mode="markers",
                                         name="이상", marker=dict(color="#E4002B", size=12, symbol="x")))
                fig.update_xaxes(categoryorder="array",
                                 categoryarray=[f"{m}월" for m in range(1, 13)])
            else:
                dd = d.sort_values("월num")
                fig.add_trace(go.Scatter(x=dd["월표"], y=dd["상한"] / EOK, line=dict(width=0),
                                         showlegend=False, hoverinfo="skip"))
                fig.add_trace(go.Scatter(x=dd["월표"], y=dd["하한"] / EOK, fill="tonexty",
                                         fillcolor="rgba(255,214,0,0.16)", line=dict(width=0),
                                         name="기대구간", hoverinfo="skip"))
                fig.add_trace(go.Scatter(x=dd["월표"], y=dd["월값"] / EOK, mode="lines+markers",
                                         name="실제", line=dict(color="#2E2E38", width=2.5)))
                od = dd[dd["이상여부"]]
                fig.add_trace(go.Scatter(x=od["월표"], y=od["월값"] / EOK, mode="markers",
                                         name="이상", marker=dict(color="#E4002B", size=12, symbol="x")))
            fig.update_layout(height=240, margin=dict(l=10, r=10, t=20, b=10),
                              yaxis_title="억원", legend=dict(orientation="h", y=1.28))
            st.plotly_chart(fig, use_container_width=True)

        # ── 라디오 아래: 전체 폭으로 (전표 깨짐 방지) ──
        st.markdown(f"**이상 표시 월 — {acct}**")
        tv = sub[["월", "방향", "월값", "기대중앙값", "편차", "로버스트z", "등급"]].copy()
        tv["월"] = tv["월"].map(lambda m: kmon(m, yoy_on))
        for c in ["월값", "기대중앙값", "편차"]:
            tv[c] = tv[c].map(eok2)
        tv["로버스트z"] = tv["로버스트z"].round(1)
        tv.columns = ["월", "방향", "실제(억)", "기대(억)", "편차(억)", "수정z", "등급"]
        html_table(tv, wide=())

        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
        st.markdown("**월별 상세 — 추정 원인 · 근거 전표**")
        sub_z = sub.reindex(sub["로버스트z"].abs().sort_values(ascending=False).index)
        for i, (_, fg) in enumerate(sub_z.iterrows()):
            month = fg["월"]
            head = (f"{kmon(month, yoy_on)} · {fg['등급']} · 실제 {fg['월값']/EOK:,.2f}억 "
                    f"vs 기대 {fg['기대중앙값']/EOK:,.2f}억 (편차 {fg['편차']/EOK:+,.2f}억, 수정z {fg['로버스트z']:.1f})")
            with st.expander(head, expanded=(i == 0)):
                t = driver_txns(gl[(gl["계정명"] == acct) & (gl["월"] == month)],
                                nat, fg["편차"] >= 0).head(6).copy()
                t["전표일자"] = pd.to_datetime(t["전표일자"]).dt.strftime("%Y-%m-%d")
                txns = [{"적요": r["적요"], "전표번호": r.get("전표번호", ""),
                         "거래처": (None if pd.isna(r["거래처명"]) else r["거래처명"]),
                         "금액": r["기여"]} for _, r in t.iterrows()]
                st.markdown(f"**추정 원인:** {_cause(txns)}")
                t["금액(억)"] = t["기여"].map(eok2)
                tcols = ["전표일자"] + (["전표번호"] if "전표번호" in t.columns else []) + \
                        ["적요", "거래처명", "금액(억)"]
                html_table(t[tcols])

# ---- 탭: 검증·시산표 ----
with t3:
    if vres is not None:
        st.subheader("데이터 무결성 검증")

        def color_res(v):
            return {"통과": "background-color:#C6EFCE", "경고": "background-color:#FFEB9C",
                    "실패": "background-color:#FFC7CE"}.get(v, "")
        st.dataframe(vres.style.map(color_res, subset=["결과"]),
                     hide_index=True, use_container_width=True)
    st.subheader("시산표 (계정별)")
    tb = read_csv(base, "trial_balance.csv", dtype={"계정코드": str})
    if tb is not None:
        kw = st.text_input("계정명 검색", "")
        if kw:
            tb = tb[tb["계정명"].astype(str).str.contains(kw, na=False)]
        st.dataframe(tb, hide_index=True, use_container_width=True, height=340)

# ---- 탭5: 부정·이상 탐지 (실험) · FR-09 감사기준서 240 ----
with t5:
    _has_scores = fs_gauges(fscore, yoy_on)
    if _has_scores:
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        st.divider()
    if fraud is None or fraud.empty:
        st.caption("전표 수준 부정 스크리닝(JET) 결과가 없습니다.")
    else:
        n_hi = int(fraud["등급"].str.contains("높음").sum())
        n_mid = int(fraud["등급"].str.contains("중간").sum())
        # ── 첫 화면: 한 줄 요약(전표 스크리닝은 접어둠) ──
        st.markdown(
            "**전표 수준 부정 스크리닝 (JET · 감사기준서 240)** — "
            "수기입력·소급입력·비정상시간·이상 작성자 등 위험 신호로 전 분개를 훑어 "
            f"**높음 {n_hi} · 중간 {n_mid}건**을 우선순위화. "
            "부정 확정이 아니라 감사인이 '먼저 볼 순서'를 제시하는 실험적 부가 기능입니다.")

        def easy_reasons(s, n=3):
            rs = parse_reason(s)
            head = " · ".join(FLAG_GUIDE.get(nm, {}).get("name", nm) for nm, _ in rs[:n])
            return head + ("" if len(rs) <= n else f" 외 {len(rs) - n}")

        show = fraud.copy()
        show["금액(억)"] = show["금액"].map(eok2)
        show["사유"] = show["걸린이유"].map(easy_reasons)
        cols = [c for c in ["순위", "전표일자", "계정명", "적요", "거래처명",
                            "금액(억)", "부정위험점수", "등급", "사유"] if c in show.columns]
        _n = min(50, len(show))
        with st.expander(f"전표 스크리닝 상위 {_n}건 보기", expanded=False):
            st.dataframe(show[cols].head(50), hide_index=True,
                         use_container_width=True, height=420)

        with st.expander("신호 사전 — 각 사유의 뜻"):
            rows = [{"신호": v["name"], "무슨 뜻": v["why"], "왜 보나": v["reason"]}
                    for v in FLAG_GUIDE.values()]
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                         use_container_width=True, height=380)

        st.caption("한계 — 규칙·통계 기반의 실험적 부가 기능 · 일부 지표는 근사 계산 · "
                   "부정 확정이 아니며 감사인의 추가 절차·전문가적 판단으로 확정합니다 (기준서 200·240).")

# ---- 탭7: 계정 분류 (설정 · FR-10) ----
with t7:
    st.caption("내부 설정 — 자동 분류 초안을 검토·수정합니다. 틀린 항목을 드롭다운으로 고치고 '저장 & 재분류'를 누르세요.")
    if amap is None or amap.empty:
        st.info("계정 분류 결과가 없습니다(FR-10 단계 미완).")
    else:
        u = int((amap["표준항목"] == "미분류").sum())
        e = int((amap["확신도"] == "추정").sum())
        mm = int((amap["성격점검"] == "⚠️불일치").sum()) if "성격점검" in amap.columns else 0
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("전체 계정", f"{len(amap)}개")
        k2.metric("미분류", f"{u}개")
        k3.metric("추정(저확신)", f"{e}개")
        k4.metric("성격 불일치", f"{mm}개")

        only = st.checkbox("검토 권장(미분류·추정·불일치)만 보기", value=(u + e + mm > 0))
        view = amap
        if only:
            cond = (amap["표준항목"] == "미분류") | (amap["확신도"] == "추정")
            if "성격점검" in amap.columns:
                cond = cond | (amap["성격점검"] == "⚠️불일치")
            view = amap[cond]
        show_cols = [c for c in ["계정코드", "계정명", "표준항목", "대분류", "확신도",
                                 "성격점검", "net(억)", "건수"] if c in view.columns]
        edited = st.data_editor(
            view[show_cols], hide_index=True, use_container_width=True, height=460,
            disabled=[c for c in show_cols if c != "표준항목"],
            column_config={"표준항목": st.column_config.SelectboxColumn(
                "표준항목(수정)", options=ITEMS, required=True)}, key="amap_editor")

        if st.button("저장 & 재분류", type="primary"):
            cur_map = amap.set_index("계정코드")["표준항목"].to_dict()
            ovp = Path(base) / "data" / "fr10_overrides.json"
            ov = json.loads(ovp.read_text(encoding="utf-8")) if ovp.exists() else {}
            changed = 0
            for _, r in edited.iterrows():
                code, new = str(r["계정코드"]), r["표준항목"]
                if new != cur_map.get(code):
                    ov[code] = new
                    changed += 1
            if changed == 0:
                st.info("변경된 항목이 없습니다.")
            else:
                ovp.write_text(json.dumps(ov, ensure_ascii=False, indent=2), encoding="utf-8")
                env = {**os.environ, "GL_BASE": str(base), "PYTHONIOENCODING": "utf-8",
                       "PYTHONUTF8": "1"}
                with st.spinner(f"{changed}건 저장 후 재분류 중..."):
                    rr = subprocess.run([sys.executable, str(SRC / "fr10_classify.py")],
                                        env=env, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace")
                if rr.returncode == 0:
                    st.success(f"{changed}건 반영 완료. 분식위험 점수도 갱신됩니다.")
                    st.rerun()
                else:
                    st.error("재분류 실패:\n" + (rr.stderr or "")[-600:])

st.caption("적응형 로더 + FR-02~04·09·10 파이프라인 · FR-11 분식위험 · 다른 파일을 올리면 새로 분석합니다.")
