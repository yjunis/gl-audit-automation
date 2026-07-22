# -*- coding: utf-8 -*-
"""
FR-11 · 재무제표 분식위험 점수 (Beneish M-Score · Altman Z') — 감사기준서 240·315
------------------------------------------------------------
재무제표 '수준'의 분식·재무곤경 위험을 확립된 계량모형으로 산출한다.
계수는 학술연구로 확정된 '고정값'이라 회사를 가리지 않는다(회사별 재훈련 불필요).
FR-10 자동분류로 회사별 계정명을 표준항목에 매핑한 뒤 재무제표 항목을 집계한다.

  · Beneish M-Score : 8개 지표, M > -1.78 이면 분식(이익조작) 의심.  ← 2개 연도 필요
  · Altman Z'-Score : 비상장기업용 5개 비율, 안전/회색/위험 구역.   ← 1개 연도로 가능
  · 각 점수는 '지표별 기여도'로 분해(블랙박스 금지, NFR-06).

실행:
  python src/fr11_fraud_scores.py <전기연도폴더> <당기연도폴더>
  (예)  python src/fr11_fraud_scores.py output/DEMO_2024 output/DEMO_2025
  당기 폴더 하나만 주면 Altman Z' 만 산출(M-Score 생략).

출력 : <당기폴더>/data/fr11_fraud_scores.csv, <당기폴더>/reports/fr11_분식위험.md
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
from fr10_classify import classify_name, CATS   # 표준사전 분류 재사용
EOK = 100_000_000

ITEM_META = {c["표준항목"]: c for c in CATS}


def account_nets(folder):
    """한 연도 폴더 → 계정별 부호있는 기말잔액(net). 회사 형식에 따라 자동 전환.
       ① 시산표 시스템누계가 채워졌으면(시스템누계형): net = 시스템누계차변 - 대변 (가장 정확)
       ② 비었으면(잔액추정형): net = FR-10 성격(차변/대변) × |gl 마지막 running 잔액|
          (running 잔액은 전기이월을 이미 반영 → 거래합보다 정확)"""
    folder = Path(folder)
    gl = pd.read_csv(folder / "data" / "gl_clean.csv", dtype={"계정코드": str})
    acc = gl[["계정코드", "계정명"]].drop_duplicates()

    tb_net = None
    tbf = folder / "data" / "trial_balance.csv"
    if tbf.exists():
        tb = pd.read_csv(tbf, dtype={"계정코드": str})
        if {"시스템누계차변", "시스템누계대변"} <= set(tb.columns):
            v = tb["시스템누계차변"].fillna(0) - tb["시스템누계대변"].fillna(0)
            if v.abs().sum() > 0:               # 실제 값이 있을 때만 채택
                tb_net = dict(zip(tb["계정코드"].astype(str), v))

    # gl 마지막 running 잔액(계정별), 부호 없는 크기
    lastbal = (gl.drop_duplicates("계정코드", keep="last")
               .set_index("계정코드")["잔액"].abs().to_dict()) if "잔액" in gl.columns else {}

    recs = []
    for _, r in acc.iterrows():
        code, name = str(r["계정코드"]), str(r["계정명"])
        ci, _, _ = classify_name(name)
        if ci is None:
            item, grp, stmt, side = "미분류", "미분류", "-", "차변"
        else:
            c = CATS[ci]; item, grp, stmt, side = c["표준항목"], c["대분류"], c["재무제표"], c["성격"]
        if tb_net is not None and code in tb_net:
            net = tb_net[code]
        else:
            sign = 1 if side == "차변" else -1
            net = sign * lastbal.get(code, 0.0)
        recs.append((item, grp, stmt, net))
    return pd.DataFrame(recs, columns=["표준항목", "대분류", "재무제표", "net"])


def fs_aggregate(folder):
    """한 연도 폴더 → 재무제표 항목 집계 dict."""
    m = account_nets(folder)

    it = m.groupby("표준항목")["net"].sum()
    gp = m.groupby("대분류")["net"].sum()
    st = m.groupby("재무제표")["net"].sum()

    def I(k): return float(it.get(k, 0.0))
    def G(k): return float(gp.get(k, 0.0))
    def S(k): return float(st.get(k, 0.0))

    d = {}
    d["총자산"] = S("자산")
    d["유동자산"] = G("유동자산")
    d["순매출채권"] = I("매출채권") + I("대손충당금")
    d["순재고"] = I("재고자산") + I("재고평가충당금")
    d["순유형자산"] = I("유형자산") + I("감가상각누계액")     # 근사(무형·사용권 상각 일부 포함)
    d["현금"] = I("현금성자산")
    d["매출"] = -G("매출")                                  # 수익은 대변 net(-) → 부호전환
    d["매출원가"] = G("매출원가")
    d["판관비"] = G("판관비")
    d["감가상각비"] = I("감가상각비")
    d["총부채"] = -S("부채")
    d["유동부채"] = -G("유동부채")
    d["이익잉여금"] = -I("이익잉여금")
    ni = (-S("수익")) - S("비용")                           # 당기순이익 = 수익-비용
    d["당기순이익"] = ni
    d["자본총계"] = -S("자본") + ni                         # 미마감 손익 포함
    d["영업이익"] = d["매출"] - d["매출원가"] - d["판관비"]   # EBIT 근사
    d["미분류net"] = I("미분류")
    return d


def safe_div(a, b):
    return a / b if b not in (0, 0.0) and not pd.isna(b) else np.nan


def beneish_m(p, c):
    """전기 p, 당기 c 집계로 Beneish 8지표 + M-Score. 각 지표·기여도 반환."""
    DSRI = safe_div(safe_div(c["순매출채권"], c["매출"]),
                    safe_div(p["순매출채권"], p["매출"]))
    gm_c = safe_div(c["매출"] - c["매출원가"], c["매출"])
    gm_p = safe_div(p["매출"] - p["매출원가"], p["매출"])
    GMI = safe_div(gm_p, gm_c)
    aqi_c = 1 - safe_div(c["유동자산"] + c["순유형자산"], c["총자산"])
    aqi_p = 1 - safe_div(p["유동자산"] + p["순유형자산"], p["총자산"])
    AQI = safe_div(aqi_c, aqi_p)
    SGI = safe_div(c["매출"], p["매출"])
    dr_c = safe_div(c["감가상각비"], c["감가상각비"] + c["순유형자산"])
    dr_p = safe_div(p["감가상각비"], p["감가상각비"] + p["순유형자산"])
    DEPI = safe_div(dr_p, dr_c)
    SGAI = safe_div(safe_div(c["판관비"], c["매출"]), safe_div(p["판관비"], p["매출"]))
    LVGI = safe_div(safe_div(c["총부채"], c["총자산"]), safe_div(p["총부채"], p["총자산"]))
    # TATA(발생액) 근사: (Δ유동자산-Δ현금-Δ유동부채-감가상각비)/총자산
    tata = ((c["유동자산"] - p["유동자산"]) - (c["현금"] - p["현금"])
            - (c["유동부채"] - p["유동부채"]) - c["감가상각비"])
    TATA = safe_div(tata, c["총자산"])

    idx = dict(DSRI=DSRI, GMI=GMI, AQI=AQI, SGI=SGI, DEPI=DEPI,
               SGAI=SGAI, LVGI=LVGI, TATA=TATA)
    coef = dict(_const=-4.84, DSRI=0.920, GMI=0.528, AQI=0.404, SGI=0.892,
                DEPI=0.115, SGAI=-0.172, TATA=4.679, LVGI=-0.327)
    contrib = {k: coef[k] * (idx[k] if not pd.isna(idx[k]) else 0) for k in idx}
    M = coef["_const"] + sum(contrib.values())
    return M, idx, contrib


def altman_zprime(c):
    """비상장기업용 Altman Z'(당기만 필요). 5비율 + 기여도."""
    TA = c["총자산"]
    X1 = safe_div(c["유동자산"] - c["유동부채"], TA)     # 운전자본/총자산
    X2 = safe_div(c["이익잉여금"], TA)                   # 이익잉여금/총자산
    X3 = safe_div(c["영업이익"], TA)                     # EBIT/총자산
    X4 = safe_div(c["자본총계"], c["총부채"])            # 자기자본(장부)/총부채
    X5 = safe_div(c["매출"], TA)                         # 매출/총자산
    coef = dict(X1=0.717, X2=0.847, X3=3.107, X4=0.420, X5=0.998)
    idx = dict(X1=X1, X2=X2, X3=X3, X4=X4, X5=X5)
    contrib = {k: coef[k] * (idx[k] if not pd.isna(idx[k]) else 0) for k in idx}
    Z = sum(contrib.values())
    return Z, idx, contrib


def main():
    args = sys.argv[1:]
    if len(args) >= 2:
        prior_dir, cur_dir = args[0], args[1]
    elif len(args) == 1:
        prior_dir, cur_dir = None, args[0]
    else:
        prior_dir, cur_dir = "output/DEMO_2024", "output/DEMO_2025"

    cur = fs_aggregate(cur_dir)
    prior = fs_aggregate(prior_dir) if prior_dir else None
    curP = Path(cur_dir)
    (curP / "reports").mkdir(exist_ok=True)

    print("=" * 64)
    print("FR-11 재무제표 분식위험 점수 (감사기준서 240·315)")
    print("=" * 64)
    print(f"당기: {cur_dir}" + (f" | 전기: {prior_dir}" if prior_dir else " | (전기 없음 → Altman Z'만)"))
    # 신뢰도: 미분류 net이 총자산 대비 크면 분류 보완 필요(검토화면 권장)
    unc_ratio = abs(cur["미분류net"]) / max(abs(cur["총자산"]), 1)
    reliab = ("✅ 양호" if unc_ratio < 0.02 else
              "🟠 보통(분류 보완 권장)" if unc_ratio < 0.05 else "🔴 낮음(검토화면서 분류 후 재실행 권장)")
    print(f"분류 신뢰도: {reliab}  (미분류 net {cur['미분류net']/EOK:,.1f}억 = 총자산의 {unc_ratio:.1%})")
    print("-" * 64)
    print("재무제표 집계(억):")
    for k in ["총자산", "유동자산", "순매출채권", "순재고", "순유형자산", "매출", "매출원가",
              "판관비", "감가상각비", "총부채", "유동부채", "이익잉여금", "영업이익", "당기순이익"]:
        line = f"  {k:10s} 당기 {cur[k]/EOK:>10,.1f}"
        if prior:
            line += f"   전기 {prior[k]/EOK:>10,.1f}"
        print(line)

    rows = []

    # ── Altman Z'
    Z, zi, zc = altman_zprime(cur)
    zone = "🟢 안전" if Z > 2.9 else ("🟠 회색" if Z > 1.23 else "🔴 위험")
    print("-" * 64)
    print(f"[Altman Z'] Z' = {Z:,.2f}  → {zone}  (안전>2.9 / 회색 1.23~2.9 / 위험<1.23)")
    for k in ["X1", "X2", "X3", "X4", "X5"]:
        print(f"    {k}={zi[k]:>7,.3f}  기여 {zc[k]:>7,.3f}")
    rows.append(dict(모형="Altman Z'", 점수=round(Z, 2), 판정=zone,
                     지표=json.dumps({k: round(float(zi[k]), 3) for k in zi}, ensure_ascii=False)))

    # ── Beneish M
    if prior:
        M, mi, mc = beneish_m(prior, cur)
        verdict = "🔴 분식의심(M>-1.78)" if M > -1.78 else "🟢 정상권(M<-1.78)"
        print("-" * 64)
        print(f"[Beneish M] M = {M:,.2f}  → {verdict}")
        for k in ["DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI", "TATA"]:
            v = mi[k]; vs = f"{v:>7,.3f}" if not pd.isna(v) else "   n/a "
            print(f"    {k:5s}={vs}  기여 {mc[k]:>7,.3f}")
        rows.append(dict(모형="Beneish M", 점수=round(M, 2), 판정=verdict,
                         지표=json.dumps({k: (round(float(mi[k]), 3) if not pd.isna(mi[k]) else None)
                                          for k in mi}, ensure_ascii=False)))
    else:
        print("-" * 64)
        print("[Beneish M] 전기 데이터 없음 → 생략 (2개 연도 필요)")

    out = pd.DataFrame(rows)
    out.to_csv(curP / "data" / "fr11_fraud_scores.csv", index=False, encoding="utf-8-sig")

    # ── 리포트
    md = ["# FR-11 재무제표 분식위험 점수 (감사기준서 240·315)\n",
          f"- 당기: `{cur_dir}`" + (f" · 전기: `{prior_dir}`" if prior_dir else " · (전기 없음)"),
          f"- 계수는 학술 고정값 → 회사 무관. 미분류 net 당기 {cur['미분류net']/EOK:,.2f}억"
          + (f" · 전기 {prior['미분류net']/EOK:,.2f}억" if prior else ""),
          f"- **분류 신뢰도: {reliab}** (미분류 net = 총자산의 {unc_ratio:.1%}). "
          "내부거래(본지점)는 상계 제외. 미분류가 크면 `fr10_review_app.py`에서 분류 후 재실행 권장.",
          "\n## Altman Z' (비상장기업)\n",
          f"**Z' = {Z:,.2f} → {zone}**  (안전>2.9 / 회색 1.23~2.9 / 위험<1.23)\n",
          "| 지표 | 의미 | 값 | 기여 |", "|---|---|---:|---:|"]
    zmean = {"X1": "운전자본/총자산", "X2": "이익잉여금/총자산", "X3": "EBIT/총자산",
             "X4": "자기자본/총부채", "X5": "매출/총자산"}
    for k in ["X1", "X2", "X3", "X4", "X5"]:
        md.append(f"| {k} | {zmean[k]} | {zi[k]:,.3f} | {zc[k]:,.3f} |")
    if prior:
        md += ["\n## Beneish M-Score\n", f"**M = {M:,.2f} → {verdict}**  (M > -1.78 이면 이익조작 의심)\n",
               "| 지표 | 의미 | 값 | 기여 |", "|---|---|---:|---:|"]
        mmean = {"DSRI": "매출채권/매출 증가", "GMI": "매출총이익률 악화", "AQI": "자산부실화",
                 "SGI": "매출성장", "DEPI": "감가상각률 둔화", "SGAI": "판관비율 증가",
                 "LVGI": "레버리지 증가", "TATA": "발생액/총자산"}
        for k in ["DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI", "TATA"]:
            vv = f"{mi[k]:,.3f}" if not pd.isna(mi[k]) else "n/a"
            md.append(f"| {k} | {mmean[k]} | {vv} | {mc[k]:,.3f} |")
    md += ["\n> 점수는 '위험 신호'이지 분식 확정이 아니다. 감사인의 추가 절차·전문가적 회의로 확정한다(감사기준서 200·240).",
           "> TATA·순유형자산은 현금흐름표·자산명세 부재로 근사 계산했다."]
    (curP / "reports" / "fr11_분식위험.md").write_text("\n".join(md), encoding="utf-8")

    print("-" * 64)
    print("저장:", curP / "data" / "fr11_fraud_scores.csv")
    print("저장:", curP / "reports" / "fr11_분식위험.md")


if __name__ == "__main__":
    main()
