# -*- coding: utf-8 -*-
"""
FR-08 · 대시보드 (Streamlit + Plotly)
------------------------------------------------------------
탐색용 대화형 화면. 마우스로 이상 플래그를 고르면 그 계정의 월별 그래프,
원인 설명, 근거 전표가 함께 뜬다. (엑셀 조서=제출용 / 대시보드=탐색용)

실행:  streamlit run src/fr08_dashboard.py
그러면 브라우저에서 http://localhost:8501 로 열린다.
"""
import os
import sys
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from explain_backend import _cause, _procedure, driver_txns

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
DATA = BASE / "data"
EOK = 100_000_000

st.set_page_config(page_title="GL 분석적 절차 자동화", layout="wide", page_icon="📊")


@st.cache_data
def load():
    gl = pd.read_csv(DATA / "gl_clean.csv", dtype={"계정코드": str}, parse_dates=["전표일자"])
    gl["월"] = gl["전표일자"].dt.to_period("M").astype(str)
    d = dict(
        gl=gl,
        vres=pd.read_csv(DATA / "fr02_results.csv"),
        tb=pd.read_csv(DATA / "trial_balance.csv", dtype={"계정코드": str}),
        exp=pd.read_csv(DATA / "fr03_expectations.csv", dtype={"계정코드": str}),
        flags=pd.read_csv(DATA / "fr04_flags.csv", dtype={"계정코드": str}),
        expl=pd.read_csv(DATA / "fr06_explanations.csv"),
        anom=pd.read_csv(DATA / "fr05_anomalies.csv", parse_dates=["전표일자"]),
        benf=pd.read_csv(DATA / "fr05_benford.csv"),
    )
    return d


D = load()
gl, flags, exp, expl = D["gl"], D["flags"], D["exp"], D["expl"]
_mae = gl["계정명"].astype(str).str.contains("매출", na=False) & ~gl["계정명"].astype(str).str.contains("원가|차감|환입|할인|에누리", na=False)
rev = gl.loc[_mae, "대변"].sum() - gl.loc[_mae, "차변"].sum()
rev = rev if rev > 0 else gl["차변"].sum()
PM = rev * 0.00375

st.title("📊 GL 분석적 절차 자동화 대시보드")
st.caption("가상제조(주) · FY2025 · 감사기준서 520 분석적 절차 — 탐지부터 원인설명까지 자동화")

# ===== 상단 KPI =====
n_hi = int(flags["등급"].str.contains("높음").sum())
n_mid = int(flags["등급"].str.contains("중간").sum())
n_fail = int((D["vres"]["결과"] == "실패").sum())
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("원장 규모", f"{len(gl):,} 줄", f"계정 {gl['계정명'].nunique()}개")
c2.metric("무결성 판정", "✅ 통과" if n_fail == 0 else "❌ 보류", f"실패 {n_fail}건")
c3.metric("🔴 높음 플래그", f"{n_hi} 건")
c4.metric("🟠 중간 플래그", f"{n_mid} 건")
c5.metric("성과중요성 PM", f"{PM/EOK:,.2f} 억", f"매출 {rev/EOK:,.0f}억 기준")

tab1, tab2, tab3, tab4 = st.tabs(["🚩 이상 플래그 & 원인", "📈 위험 매트릭스", "📒 시산표 · 검증", "🔍 보조탐지"])

# ===== 탭 1: 플래그 상세 =====
with tab1:
    left, right = st.columns([1, 2])
    with left:
        st.subheader("검토 대상 플래그")
        labels = [f"{r['순위']}. {r['계정명']} {r['월']} ({r['등급']})" for _, r in flags.iterrows()]
        pick = st.radio("항목 선택", labels, label_visibility="collapsed")
        idx = labels.index(pick)
        fg = flags.iloc[idx]

    with right:
        acct, month = fg["계정명"], fg["월"]
        st.subheader(f"{acct} · {month}")
        m1, m2, m3 = st.columns(3)
        m1.metric("실제", f"{fg['월값']/EOK:,.1f} 억")
        m2.metric("기대(중앙값)", f"{fg['기대중앙값']/EOK:,.1f} 억")
        m3.metric("편차", f"{fg['편차']/EOK:+,.1f} 억", f"수정z {fg['로버스트z']:.1f}")

        # 월별 실제 vs 기대구간 (plotly)
        d = exp[exp["계정명"] == acct].sort_values("월")
        d["이상여부"] = d["이상여부"].astype(str).str.lower().isin(["true", "1"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=d["월"], y=d["상한"] / EOK, line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=d["월"], y=d["하한"] / EOK, fill="tonexty",
                                 fillcolor="rgba(158,202,225,0.35)", line=dict(width=0),
                                 name="기대구간", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=d["월"], y=d["월값"] / EOK, mode="lines+markers",
                                 name="실제", line=dict(color="#08519c")))
        od = d[d["이상여부"]]
        fig.add_trace(go.Scatter(x=od["월"], y=od["월값"] / EOK, mode="markers",
                                 name="이상", marker=dict(color="#c00000", size=13, symbol="x")))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                          yaxis_title="억원", legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig, use_container_width=True)

    # 원인 설명 + 근거전표
    st.markdown("---")
    nat = "차변성격"
    _n = exp.loc[exp["계정명"] == acct, "자연방향"]
    if len(_n):
        nat = _n.iloc[0]
    t = driver_txns(gl[(gl["계정명"] == acct) & (gl["월"] == month)], nat, fg["편차"] >= 0)
    t["금액(억)"] = (t["기여"] / EOK).round(2)
    t["전표일자"] = pd.to_datetime(t["전표일자"]).dt.strftime("%Y-%m-%d")
    txns = [{"적요": r["적요"], "전표번호": r.get("전표번호", ""),
             "거래처": (None if pd.isna(r["거래처명"]) else r["거래처명"]),
             "금액": r["기여"]} for _, r in t.iterrows()]
    cc1, cc2 = st.columns([3, 2])
    with cc1:
        st.subheader("🤖 자동 원인 설명")
        row = expl[(expl["계정명"] == acct) & (expl["월"] == month)]
        if len(row):
            st.markdown(row.iloc[0]["설명초안"])
        else:
            st.markdown(f"**🔎 추정 원인:** {_cause(txns)}")
            st.caption(f"권고 절차: {_procedure(fg, txns)}")
    with cc2:
        st.subheader("근거 전표 (상위 5건)")
        cols = ["전표일자"] + (["전표번호"] if "전표번호" in t.columns else []) + ["적요", "거래처명", "금액(억)"]
        st.dataframe(t[cols], hide_index=True, use_container_width=True)

# ===== 탭 2: 위험 매트릭스 =====
with tab2:
    st.subheader("위험 매트릭스 — 통계 이탈 × 금액 중요성")
    fig = go.Figure()
    cmap = {"🔴 높음": "#c00000", "🟠 중간": "#ed7d31", "⚪ 낮음": "#a6a6a6"}
    for g, sub in flags.groupby("등급"):
        fig.add_trace(go.Scatter(
            x=sub["로버스트z"].abs(), y=sub["PM배수"], mode="markers+text",
            text=sub["계정명"] + " " + sub["월"].str[-2:] + "월",
            textposition="top center", name=g,
            marker=dict(size=sub["위험점수"] / 2 + 10, color=cmap.get(g, "#888"),
                        line=dict(width=1, color="black"), opacity=0.8)))
    fig.add_hline(y=1, line_dash="dash", line_color="#c00000",
                  annotation_text="PM(성과중요성)")
    fig.add_vline(x=3.5, line_dash="dash", line_color="#4c72b0",
                  annotation_text="|z|=3.5 통계이상")
    fig.update_layout(height=520, xaxis_title="통계 이탈도 |수정 z|",
                      yaxis_title="금액 중요도 (편차 ÷ PM)")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        flags[["순위", "계정명", "월", "방향", "위험점수", "등급", "위험요소"]],
        hide_index=True, use_container_width=True)

# ===== 탭 3: 시산표 · 검증 =====
with tab3:
    st.subheader("① 데이터 무결성 검증 (FR-02)")

    def color_res(v):
        return {"통과": "background-color:#C6EFCE", "경고": "background-color:#FFEB9C",
                "실패": "background-color:#FFC7CE"}.get(v, "")
    st.dataframe(D["vres"].style.map(color_res, subset=["결과"]),
                 hide_index=True, use_container_width=True)

    st.subheader("② 시산표 (계정별 기초·누계)")
    kw = st.text_input("계정명 검색", "")
    tb = D["tb"].copy()
    if kw:
        tb = tb[tb["계정명"].str.contains(kw, na=False)]
    st.dataframe(tb, hide_index=True, use_container_width=True, height=360)

# ===== 탭 4: 보조탐지 =====
with tab4:
    st.subheader("① 벤포드 법칙 — 금액 첫자리 분포")
    b = D["benf"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=b.iloc[:, 0].astype(int), y=b["Found"] * 100, name="실제%",
                         marker_color="#4c72b0"))
    fig.add_trace(go.Scatter(x=b.iloc[:, 0].astype(int), y=b["Expected"] * 100,
                             name="벤포드 기대%", line=dict(color="#c00000")))
    fig.update_layout(height=340, xaxis_title="첫자리", yaxis_title="%",
                      margin=dict(t=20), xaxis=dict(dtick=1))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("② Isolation Forest — 개별 분개 이상 Top 20")
    a = D["anom"].head(20).copy()
    a["전표일자"] = a["전표일자"].dt.strftime("%Y-%m-%d")
    a["금액(억)"] = (a["금액"] / EOK).round(2)
    st.dataframe(a[["순위", "전표일자", "요일", "계정명", "적요", "금액(억)", "이상점수"]],
                 hide_index=True, use_container_width=True, height=420)

st.caption("생성: 적재(FR-01) → 검증(FR-02) → 기대치(FR-03) → 플래깅(FR-04) → 보조탐지(FR-05) → 원인설명 MCP(FR-06) → 대시보드(FR-08) 자동 파이프라인")
