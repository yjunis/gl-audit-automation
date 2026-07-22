# -*- coding: utf-8 -*-
"""
정적 웹사이트 빌더 (Vercel 배포용 · 합성데이터 전용)
------------------------------------------------------------
목적: fr09 대시보드(Streamlit)를 '서버 없이 도는 단일 index.html'로 굽는다.
      → Vercel 같은 정적 호스팅에 그대로 올릴 수 있고, 링크가 절대 깨지지 않는다.
      → 입력은 오직 demo_data/ 의 가상제조(주) 원장뿐 → 비밀유지 문제 원천 차단.

흐름:
  1) demo_data 두 해(2024·2025) 엑셀을 앱과 동일한 파이프라인으로 분석
     (load_ledger → FR-02~04·09·10 → 2년 YoY 재계산 → FR-11 분식위험)
  2) 결과 CSV로 앱과 동일한 Plotly 그래프를 재현
     (리스크 히트맵 · 계정별 상세[Plotly 드롭다운] · 부정 게이지 · 전표 스크리닝 표)
  3) EY 테마 HTML로 조립 → web/index.html 저장

실행:  python src/build_static_site.py
출력:  web/index.html  (+ web/vercel.json, web/README.md 는 별도)
"""
import os
import sys
import gc
import json
import shutil
import subprocess
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
sys.path.insert(0, str(SRC))
from adaptive_loader import load_ledger

DEMO = ROOT / "demo_data"
BUILD = ROOT / "web" / "_build"          # 중간 산출물(배포 제외)
OUT = ROOT / "web"                        # 배포 폴더
EOK = 100_000_000

PIPE_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
            "MPLBACKEND": "Agg", "GL_NO_CHARTS": "1"}
STEPS = ["fr02_validate.py", "fr03_expectation.py", "fr04_flagging.py",
         "fraud_screen.py", "fr10_classify.py"]

# ── 통일 Plotly 테마(앱과 동일) ──
pio.templates["gl"] = go.layout.Template(layout=dict(
    font=dict(family="Malgun Gothic, Segoe UI, sans-serif", color="#2E2E38", size=12),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=["#2E2E38", "#747480", "#B9B9C0", "#E4002B", "#9CA3AF", "#4A4A55"],
    xaxis=dict(gridcolor="#F1F1F4", linecolor="#ECECF0", zerolinecolor="#ECECF0"),
    yaxis=dict(gridcolor="#F1F1F4", linecolor="#ECECF0", zerolinecolor="#ECECF0"),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
))
pio.templates.default = "gl"

PLOTLY_CFG = {"displayModeBar": False, "responsive": True}


def eok2(x):
    return f"{x / EOK:,.2f}"


def kmon(m, multi):
    y, mm = str(m).split("-")[:2]
    return f"{y[2:]}년 {int(mm)}월" if multi else f"{int(mm)}월"


# ============================================================
# 1) 파이프라인 실행 (앱 흐름 재현)
# ============================================================
def standardize(xlsx):
    """엑셀 → 표준 폴더(gl_clean·trial_balance). base 경로 반환."""
    r = load_ledger(xlsx)
    meta = r["meta"]
    base = BUILD / ("std_" + hashlib.md5(str(xlsx).encode()).hexdigest()[:10])
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "reports").mkdir(exist_ok=True)
    r["gl"].to_csv(base / "data" / "gl_clean.csv", index=False, encoding="utf-8-sig")
    r["tb"].to_csv(base / "data" / "trial_balance.csv", index=False, encoding="utf-8-sig")
    yr = int(pd.to_datetime(r["gl"]["전표일자"]).dt.year.max())
    del r
    gc.collect()
    return str(base), meta, yr


def run_scripts(base, scripts):
    env = {**PIPE_ENV, "GL_BASE": str(base)}
    for script in scripts:
        p = subprocess.run([sys.executable, str(SRC / script)], env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
        ok = "OK" if p.returncode == 0 else "FAIL"
        tail = "" if p.returncode == 0 else (p.stderr.strip().splitlines() or [""])[-1][:90]
        print(f"    [{ok}] {script} {tail}", flush=True)


def build_two_year(cur_base, prior_base):
    cur = pd.read_csv(Path(cur_base) / "data" / "gl_clean.csv",
                      dtype={"계정코드": str}, parse_dates=["전표일자"])
    pri = pd.read_csv(Path(prior_base) / "data" / "gl_clean.csv",
                      dtype={"계정코드": str}, parse_dates=["전표일자"])
    combo = pd.concat([pri, cur], ignore_index=True)
    yb = Path(cur_base).parent / ("yoy_" + Path(cur_base).name)
    (yb / "data").mkdir(parents=True, exist_ok=True)
    (yb / "reports").mkdir(exist_ok=True)
    combo.to_csv(yb / "data" / "gl_clean.csv", index=False, encoding="utf-8-sig")
    shutil.copy(Path(cur_base) / "data" / "trial_balance.csv",
                yb / "data" / "trial_balance.csv")
    del cur, pri, combo
    gc.collect()
    run_scripts(yb, ["fr03_expectation.py", "fr04_flagging.py"])
    return str(yb)


def run_fraud_scores(cur_base, prior_base):
    args = [sys.executable, str(SRC / "fr11_fraud_scores.py"), str(prior_base), str(cur_base)]
    p = subprocess.run(args, env=PIPE_ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    if p.returncode != 0:
        print("    [FAIL] fr11 " + (p.stderr.strip().splitlines() or [""])[-1][:200], flush=True)


def read_csv(base, name, **kw):
    p = Path(base) / "data" / name
    return pd.read_csv(p, **kw) if p.exists() else None


def run_pipeline():
    if BUILD.exists():
        shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    files = sorted(DEMO.glob("*.xls*"))
    print(f"[1/3] 표준화 · 대상 {len(files)}개", flush=True)
    peeked = []
    for f in files:
        b, m, y = standardize(f)
        peeked.append({"base": b, "meta": m, "year": y})
        print(f"    {f.name} → {y} · 계정 {m['n_accounts']} · 행 {m['n_rows']:,}", flush=True)
    peeked.sort(key=lambda p: p["year"])
    cur, prior = peeked[-1], peeked[-2]
    print("[2/3] 당기 파이프라인(FR-02~04·09·10)", flush=True)
    run_scripts(cur["base"], STEPS)
    print("[2/3] 2년 YoY 재계산(FR-03·04)", flush=True)
    yoy_base = build_two_year(cur["base"], prior["base"])
    print("[2/3] 분식위험(FR-11 · Beneish M / Altman Z')", flush=True)
    run_fraud_scores(cur["base"], prior["base"])   # (당기, 전기) 순서 — 앱과 동일
    return cur, prior, yoy_base


# ============================================================
# 2) 그래프 생성
# ============================================================
def fig_heatmap(exp, order, method):
    acc_list = list(order.index[:18])
    ex = exp[exp["계정명"].isin(acc_list)].copy()
    cy = exp["월"].str[:4].max()
    ex = ex[ex["월"].str[:4] == cy]
    ex["absz"] = ex["로버스트z"].abs()
    hm = (ex.pivot_table(index="계정명", columns="월", values="absz", aggfunc="max")
          .reindex(acc_list).fillna(0))
    fig = go.Figure(go.Heatmap(
        z=hm.values, x=[kmon(c, False) for c in hm.columns], y=list(hm.index),
        colorscale=[[0, "#F8F8FA"], [0.5, "#B4B4BC"], [1, "#33333D"]],
        zmin=0, zmax=6, xgap=2, ygap=2,
        hovertemplate="%{y} · %{x}<br>이탈 |z| %{z:.1f}<extra></extra>",
        colorbar=dict(title="|z|", thickness=10)))
    fig.update_layout(height=min(560, 80 + 27 * len(hm.index)),
                      margin=dict(l=10, r=10, t=6, b=6),
                      yaxis=dict(autorange="reversed"))
    return fig


def fig_detail(flags, exp, order, yoy_on):
    """계정별 상세 — Plotly 내장 드롭다운으로 계정 전환(정적 페이지에서 작동)."""
    accts = (flags.groupby("계정명", sort=False)
             .agg(건수=("월", "size"), 최고등급=("등급", "first")).reset_index())
    _GR = {"높음": 0, "중간": 1, "낮음": 2}
    accts = (accts.assign(_g=accts["최고등급"].map(lambda g: _GR.get(g, 3)))
             .sort_values(["_g", "계정명"]).reset_index(drop=True))
    _DOT = {"높음": "🔴", "중간": "🟠", "낮음": "🟡"}

    fig = go.Figure()
    spans = []          # 계정별 (시작 trace idx, trace 개수)
    for _, ar in accts.iterrows():
        acct = ar["계정명"]
        d = exp[exp["계정명"] == acct].sort_values("월").copy()
        d["이상여부"] = d["이상여부"].astype(str).str.lower().isin(["true", "1"])
        d["연"] = d["월"].str[:4]
        d["월num"] = d["월"].str[5:7].astype(int)
        d["월표"] = d["월num"].astype(str) + "월"
        start = len(fig.data)
        if yoy_on and d["연"].nunique() >= 2:
            cy, py = d["연"].max(), d["연"].min()
            cd = d[d["연"] == cy].sort_values("월num")
            pr = d[d["연"] == py].sort_values("월num")
            fig.add_trace(go.Scatter(x=cd["월표"], y=cd["상한"] / EOK, line=dict(width=0),
                                     showlegend=False, hoverinfo="skip", visible=False))
            fig.add_trace(go.Scatter(x=cd["월표"], y=cd["하한"] / EOK, fill="tonexty",
                                     fillcolor="rgba(255,214,0,0.16)", line=dict(width=0),
                                     name="기대구간", hoverinfo="skip", visible=False))
            fig.add_trace(go.Scatter(x=pr["월표"], y=pr["월값"] / EOK, mode="lines+markers",
                                     name=f"전기 {py}",
                                     line=dict(color="#C79A00", dash="dot", width=2.2),
                                     marker=dict(size=7, symbol="diamond"), visible=False))
            fig.add_trace(go.Scatter(x=cd["월표"], y=cd["월값"] / EOK, mode="lines+markers",
                                     name=f"당기 {cy}", line=dict(color="#2E2E38", width=2.5),
                                     visible=False))
            od = cd[cd["이상여부"]]
            fig.add_trace(go.Scatter(x=od["월표"], y=od["월값"] / EOK, mode="markers",
                                     name="이상", marker=dict(color="#E4002B", size=12, symbol="x"),
                                     visible=False))
        else:
            dd = d.sort_values("월num")
            fig.add_trace(go.Scatter(x=dd["월표"], y=dd["상한"] / EOK, line=dict(width=0),
                                     showlegend=False, hoverinfo="skip", visible=False))
            fig.add_trace(go.Scatter(x=dd["월표"], y=dd["하한"] / EOK, fill="tonexty",
                                     fillcolor="rgba(255,214,0,0.16)", line=dict(width=0),
                                     name="기대구간", hoverinfo="skip", visible=False))
            fig.add_trace(go.Scatter(x=dd["월표"], y=dd["월값"] / EOK, mode="lines+markers",
                                     name="실제", line=dict(color="#2E2E38", width=2.5),
                                     visible=False))
            od = dd[dd["이상여부"]]
            fig.add_trace(go.Scatter(x=od["월표"], y=od["월값"] / EOK, mode="markers",
                                     name="이상", marker=dict(color="#E4002B", size=12, symbol="x"),
                                     visible=False))
        spans.append((start, len(fig.data) - start))

    ntr = len(fig.data)
    # 첫 계정만 보이게
    for i in range(spans[0][1]):
        fig.data[spans[0][0] + i].visible = True

    buttons = []
    for k, (_, ar) in enumerate(accts.iterrows()):
        vis = [False] * ntr
        s, cnt = spans[k]
        for i in range(cnt):
            vis[s + i] = True
        label = f"{_DOT.get(ar['최고등급'], '⚪')}  {ar['계정명']}   ·   이상 {ar['건수']}개월"
        buttons.append(dict(label=label, method="update", args=[{"visible": vis}]))

    fig.update_layout(
        height=300, margin=dict(l=10, r=10, t=64, b=10),
        yaxis_title="억원", legend=dict(orientation="h", y=1.32),
        xaxis=dict(categoryorder="array", categoryarray=[f"{m}월" for m in range(1, 13)]),
        updatemenus=[dict(active=0, buttons=buttons, x=0, xanchor="left", y=1.6,
                          yanchor="top", bgcolor="#fff", bordercolor="#ECECF0",
                          borderwidth=1, font=dict(size=12))])
    return fig, accts


def fig_gauge(value, rng, steps, thr):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        number={"font": {"size": 30, "color": "#2E2E38"}},
        gauge={"axis": {"range": rng, "tickcolor": "#B9B9C0", "tickfont": {"size": 10}},
               "bar": {"color": "#2E2E38", "thickness": 0.28}, "borderwidth": 0,
               "steps": steps,
               "threshold": {"line": {"color": "#E4002B", "width": 3}, "value": thr}}))
    fig.update_layout(height=200, margin=dict(l=24, r=24, t=10, b=0))
    return fig


# ============================================================
# 3) HTML 조립
# ============================================================
def esc(v):
    return ("" if v is None or (isinstance(v, float) and pd.isna(v)) else
            str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def html_table(df, wide=("적요",)):
    w = [3.0 if c in wide else 1.0 for c in df.columns]
    tot = sum(w) or 1
    cols = "".join(f'<col style="width:{x/tot*100:.1f}%">' for x in w)
    th = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    body = ""
    for _, r in df.iterrows():
        body += "<tr>" + "".join(f'<td title="{esc(v)}">{esc(v)}</td>' for v in r) + "</tr>"
    return (f'<table class="gltbl"><colgroup>{cols}</colgroup>'
            f'<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>')


def fig_div(fig, div_id, include_js=False):
    return pio.to_html(fig, include_plotlyjs=("cdn" if include_js else False),
                       full_html=False, div_id=div_id, config=PLOTLY_CFG)


FLAG_NAME = {
    "상대계정조합": "드문 계정 조합", "결산수정키워드": "결산조정 단어",
    "거래처없는대형": "거래처 없는 큰 금액", "중복전표": "중복 의심",
    "라운드금액": "딱 떨어지는 금액", "기말": "기말 집중", "주말": "주말 입력",
    "적요모호": "모호한 적요", "수기전표": "수기 전표", "소급입력": "소급 입력",
    "작성자이상": "이례적 작성자",
}
import re as _re


def easy_reasons(s, n=3):
    if not isinstance(s, str):
        return ""
    pairs = [(nm, int(v)) for nm, v in _re.findall(r"([가-힣]+)\((\d+)\)", s)]
    pairs.sort(key=lambda x: -x[1])
    head = " · ".join(FLAG_NAME.get(nm, nm) for nm, _ in pairs[:n])
    return head + ("" if len(pairs) <= n else f" 외 {len(pairs) - n}")


def build_html(cur, prior, yoy_base):
    meta = cur["meta"]
    company = "가상제조(주)"
    mode = f"2년치 · 전년 동월 대비  ·  당기 {cur['year']} / 전기 {prior['year']}"
    yoy_on = True
    method = "전년 동월 대비"

    flags = read_csv(yoy_base, "fr04_flags.csv", dtype={"계정코드": str})
    exp = read_csv(yoy_base, "fr03_expectations.csv", dtype={"계정코드": str})
    fraud = read_csv(cur["base"], "fr09_fraud_flags.csv")
    fscore = read_csv(cur["base"], "fr11_fraud_scores.csv")

    _EMO = r"[🔴🟠🟡🟢⚪]\s*"
    for _df in (flags, fraud):
        if _df is not None and "등급" in _df.columns:
            _df["등급"] = _df["등급"].astype(str).str.replace(_EMO, "", regex=True)

    # 지표
    rev = exp is not None
    n_acc = meta["n_accounts"]
    n_rows = meta["n_rows"]
    diff = abs(meta["debit"] - meta["credit"])
    ratio = diff / max(meta["debit"], 1)
    grade = ("완벽" if diff < 1 else "사실상 일치" if ratio < 0.001
             else "근접" if ratio < 0.01 else "검토 필요")

    order = flags.groupby("계정명", sort=False)["위험점수"].max().sort_values(ascending=False)
    n_facct = flags["계정명"].nunique()
    n_high = int((flags["등급"] == "높음").sum())
    t0 = flags.iloc[0]
    lvl = "#E4002B" if n_high > 0 else "#B9B9C0"
    summary = (f"<b>{n_acc}개 계정</b> 중 <b>{n_facct}개</b>에서 이상 <b>{len(flags)}건</b> · "
               f"대차 {grade} · 기준 {method} · 최우선 <b>{esc(t0['계정명'])}</b> "
               f"({kmon(t0['월'], yoy_on)} {esc(t0['방향'])}, 편차 {t0['편차']/EOK:+,.2f}억)")

    # ── 그래프들 ──
    heat = fig_heatmap(exp, order, method)
    detail, accts = fig_detail(flags, exp, order, yoy_on)

    # 부정 게이지
    gauges_html = ""
    if fscore is not None and not fscore.empty:
        zrow = fscore[fscore["모형"] == "Altman Z'"]
        mrow = fscore[fscore["모형"] == "Beneish M"]
        gcols = []
        if len(zrow) and pd.notna(zrow.iloc[0]["점수"]):
            z = float(zrow.iloc[0]["점수"])
            zone = "🟢 안전" if z > 2.9 else ("🟠 회색(관찰)" if z > 1.23 else "🔴 위험")
            gz = fig_gauge(z, [0, 6],
                           [{"range": [0, 1.23], "color": "#F3C7CD"},
                            {"range": [1.23, 2.9], "color": "#E6E6EA"},
                            {"range": [2.9, 6], "color": "#CFE3D6"}], 1.23)
            gcols.append(("Altman Z′ · 도산위험", fig_div(gz, "gz"),
                          f"판정 <b>{zone}</b> · 안전&gt;2.9 / 회색 1.23~2.9 / 위험&lt;1.23",
                          "재무곤경·도산 가능성 · 높을수록 안전"))
        if len(mrow) and pd.notna(mrow.iloc[0]["점수"]):
            m = float(mrow.iloc[0]["점수"])
            note = "🟢 정상권" if m < -2.22 else ("🟠 관찰 구간" if m < -1.78 else "🔴 주의 신호")
            gm = fig_gauge(m, [-4, 1],
                           [{"range": [-4, -2.22], "color": "#CFE3D6"},
                            {"range": [-2.22, -1.78], "color": "#F5E7C2"},
                            {"range": [-1.78, 1], "color": "#F3C7CD"}], -1.78)
            gcols.append(("Beneish M · 분식주의 신호", fig_div(gm, "gm"),
                          f"판정 <b>{note}</b> · 표준선 -1.78 / 보수선 -2.22",
                          "이익조작 가능성 신호 · 낮을수록 정상 · 확정 아님(참고용)"))
        cells = ""
        for title, div, judge, cap in gcols:
            cells += (f'<div class="gauge-card"><div class="gauge-title">{title}</div>{div}'
                      f'<div class="gauge-judge">{judge}</div>'
                      f'<div class="cap">{cap}</div></div>')
        gauges_html = (
            '<div class="sec-head">재무제표 수준 위험 점수 · 도산위험 · 분식주의 '
            '<span class="tag">학술 계량모형 · 참고용</span></div>'
            '<p class="cap">개별 전표가 아니라 재무제표 &#39;전체 수준&#39;의 위험을 확립된 계량모형으로 본 참고 '
            '지표입니다. 확정이 아니라 추가 절차의 단서로만 씁니다 (감사기준서 200·240).</p>'
            f'<div class="gauge-row">{cells}</div>')

    # 전표 스크리닝 표
    fraud_html = ""
    if fraud is not None and not fraud.empty:
        n_hi = int(fraud["등급"].str.contains("높음").sum())
        n_mid = int(fraud["등급"].str.contains("중간").sum())
        show = fraud.copy()
        show["금액(억)"] = show["금액"].map(eok2)
        show["사유"] = show["걸린이유"].map(easy_reasons)
        cols = [c for c in ["순위", "전표일자", "계정명", "적요", "거래처명",
                            "금액(억)", "부정위험점수", "등급", "사유"] if c in show.columns]
        n = min(50, len(show))
        fraud_html = (
            '<div class="sec-head">전표 수준 부정 스크리닝 <span class="tag">JET · 감사기준서 240</span></div>'
            f'<p class="cap">수기입력·소급입력·비정상시간·이상 작성자 등 위험 신호로 전 분개를 훑어 '
            f'<b>높음 {n_hi} · 중간 {n_mid}건</b>을 우선순위화. 부정 확정이 아니라 감사인이 '
            f'&#39;먼저 볼 순서&#39;를 제시하는 실험적 부가 기능입니다.</p>'
            f'<details class="exp"><summary>전표 스크리닝 상위 {n}건 보기</summary>'
            f'<div class="tbl-scroll">{html_table(show[cols].head(50))}</div></details>')

    # 이상 표시 월 표(첫 계정)
    first_acct = accts.iloc[0]["계정명"]
    sub = flags[flags["계정명"] == first_acct].sort_values("월").reset_index(drop=True)
    tv = sub[["월", "방향", "월값", "기대중앙값", "편차", "로버스트z", "등급"]].copy()
    tv["월"] = tv["월"].map(lambda mm: kmon(mm, yoy_on))
    for c in ["월값", "기대중앙값", "편차"]:
        tv[c] = tv[c].map(eok2)
    tv["로버스트z"] = tv["로버스트z"].round(1)
    tv.columns = ["월", "방향", "실제(억)", "기대(억)", "편차(억)", "수정z", "등급"]
    detail_tbl = html_table(tv, wide=())

    # KPI
    PM = (exp is not None) and 0
    kpi = "".join(
        f'<div class="kpi"><div class="kpi-label">{lb}</div>'
        f'<div class="kpi-val">{vl}</div>{f"<div class=\'kpi-sub\'>{sb}</div>" if sb else ""}</div>'
        for lb, vl, sb in [
            ("계정 수", f"{n_acc:,}", ""),
            ("분개 줄 수", f"{n_rows:,}", ""),
            ("대차 품질", grade, f"오차율 {ratio:.2%}"),
            ("분석 기법", "전년 동월 대비", "2개 연도 · YoY"),
        ])

    heat_div = fig_div(heat, "heat", include_js=True)   # plotly.js는 여기서 1회 로드
    detail_div = fig_div(detail, "detail")

    page = TEMPLATE.format(
        company=esc(company), mode=esc(mode), kpi=kpi, lvl=lvl, summary=summary,
        method=esc(method), heat_div=heat_div, detail_div=detail_div,
        detail_tbl=detail_tbl, first_acct=esc(first_acct),
        gauges=gauges_html, fraud=fraud_html)
    return page


TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GL 원장 분석 · 분석적 절차 자동화</title>
<style>
:root{{ --ink:#33333D; --accent:#FFE600; --muted:#8A8A94; --line:#ECECF0; --surface:#F8F8FA; }}
*{{ box-sizing:border-box; }}
body{{ margin:0; background:#fff; color:var(--ink);
  font-family:'Pretendard','Malgun Gothic','Segoe UI',system-ui,sans-serif; }}
.wrap{{ max-width:1180px; margin:0 auto; padding:26px 20px 70px; }}
h1,h2,h3{{ letter-spacing:-.4px; color:var(--ink); }}
.demo-note{{ background:#FFF9CC; border:1px solid #F2E48A; border-radius:9px;
  padding:8px 14px; font-size:.82rem; color:#6b6400; margin-bottom:14px; }}
.hero{{ background:linear-gradient(120deg,#3A3A46 0%,#26262F 100%);
  border-left:6px solid #FFE600; border-radius:14px; padding:18px 26px; margin:.1rem 0 1rem;
  color:#fff; box-shadow:0 10px 26px rgba(46,46,56,.16); }}
.hero-eyebrow{{ font-size:.64rem; letter-spacing:2px; color:#FFE600; font-weight:800; }}
.hero-title{{ font-size:1.5rem; font-weight:800; margin-top:2px; letter-spacing:-.5px; color:#fff; }}
.hero-sub{{ font-size:.86rem; color:#C7C7CF; margin-top:4px; }}
.kpi-row{{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:1rem; }}
.kpi{{ background:#fff; border:1px solid var(--line); border-top:3px solid var(--accent);
  border-radius:12px; padding:15px 18px; box-shadow:0 1px 3px rgba(46,46,56,.05); }}
.kpi-label{{ font-size:.74rem; color:var(--muted); font-weight:700; }}
.kpi-val{{ font-size:1.5rem; font-weight:800; color:var(--ink); margin-top:4px; line-height:1.1; }}
.kpi-sub{{ font-size:.72rem; color:var(--muted); margin-top:3px; }}
.summary{{ border:1px solid #ECECF0; border-left:5px solid {lvl};
  background:#F8F8FA; border-radius:10px; padding:11px 16px; margin:.1rem 0 1.4rem;
  font-size:1.0rem; color:#33333D; }}
.card{{ background:#fff; border:1px solid var(--line); border-radius:14px;
  padding:18px 20px; margin-bottom:22px; box-shadow:0 1px 3px rgba(46,46,56,.04); }}
.sec-head{{ font-size:1.06rem; font-weight:800; margin:0 0 4px; }}
.sec-head .tag, .tag{{ display:inline-block; font-size:.64rem; font-weight:800; letter-spacing:.5px;
  color:#6b6400; background:#FFF3B0; border-radius:999px; padding:2px 9px; margin-left:6px;
  vertical-align:middle; }}
.cap{{ font-size:.76rem; color:var(--muted); margin:4px 0 12px; line-height:1.5; }}
.zcap{{ font-size:.72rem; color:#9aa4b2; margin:-2px 0 8px; }}
.rightcap{{ font-size:.7rem; color:#9aa4b2; text-align:right; margin:-2px 0 2px; }}
.gauge-row{{ display:grid; grid-template-columns:repeat(2,1fr); gap:18px; }}
.gauge-card{{ border:1px solid var(--line); border-radius:12px; padding:12px 14px; background:#fff; }}
.gauge-title{{ font-weight:800; font-size:.92rem; margin-bottom:2px; }}
.gauge-judge{{ font-size:.82rem; margin-top:4px; }}
.gltbl{{ table-layout:fixed; width:100%; border-collapse:collapse; font-size:.85rem; margin:.2rem 0 .4rem; }}
.gltbl th{{ text-align:center; background:#F7F7F9; color:#33333D; font-weight:700;
  padding:6px 8px; border-bottom:2px solid #E4E4E9; }}
.gltbl td{{ text-align:center; padding:5px 8px; border-bottom:1px solid #F0F0F3;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.tbl-scroll{{ overflow-x:auto; }}
details.exp{{ border:1px solid var(--line); border-radius:12px; padding:6px 14px; margin-top:8px; }}
details.exp summary{{ font-weight:700; cursor:pointer; padding:6px 0; }}
.foot{{ font-size:.74rem; color:var(--muted); margin-top:24px; line-height:1.6; }}
@media (max-width:760px){{
  .kpi-row{{ grid-template-columns:repeat(2,1fr); }}
  .gauge-row{{ grid-template-columns:1fr; }}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="demo-note">📌 이 페이지는 <b>가상제조(주) 합성 데이터</b>로 만든 <b>포트폴리오 데모</b>입니다.
    실제 감사자료가 아니며, 분석적 절차(감사기준서 520)·부정 스크리닝(240)의 결과 화면을 보여줍니다.</div>

  <div class="hero">
    <div class="hero-eyebrow">GL 감사 대시보드</div>
    <div class="hero-title">{company}</div>
    <div class="hero-sub">{mode}</div>
  </div>

  <div class="kpi-row">{kpi}</div>

  <div class="summary">{summary}</div>

  <div class="card">
    <div class="sec-head">리스크 히트맵</div>
    <p class="cap">계정 × 월 · 색이 진할수록 검토 우선 · 당기 기준 (기법 {method})</p>
    <div class="zcap">z = 이탈도(로버스트 z) · 그 달 실제값이 기대치에서 <b>평소 변동폭의 몇 배</b>만큼
      벗어났는지 · |z|가 클수록 이례적 (통상 |z|&gt;3.5면 이상 후보)</div>
    {heat_div}
  </div>

  <div class="card">
    <div class="sec-head">계정별 상세</div>
    <div class="rightcap">🔴 높음 · 🟠 중간 · 🟡 낮음 위험 · 위 드롭다운에서 계정 선택</div>
    {detail_div}
    <div style="height:10px"></div>
    <div class="sec-head" style="font-size:.95rem">이상 표시 월 — {first_acct}
      <span class="tag">드롭다운 첫 계정 기준</span></div>
    {detail_tbl}
  </div>

  <div class="card">{gauges}</div>

  <div class="card">{fraud}</div>

  <div class="foot">
    적응형 로더 + FR-02~04·09·10 파이프라인 · FR-11 분식위험 · 감사기준서 520·240·315·330 기반<br>
    합성데이터 기반 정적 데모 · 실제 배포판은 엑셀 원장을 드래그&amp;드롭하면 동일 분석을 즉시 수행합니다.
  </div>
</div>
</body>
</html>
"""


def main():
    cur, prior, yoy_base = run_pipeline()
    print("[3/3] HTML 조립", flush=True)
    html = build_html(cur, prior, yoy_base)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    kb = len((OUT / "index.html").read_bytes()) / 1024
    print(f"    저장: {OUT / 'index.html'}  ({kb:,.0f} KB)", flush=True)
    print("완료.", flush=True)


if __name__ == "__main__":
    main()
