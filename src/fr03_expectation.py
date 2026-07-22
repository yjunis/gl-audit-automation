# -*- coding: utf-8 -*-
"""
FR-03 · 기대치 생성 엔진 (감사기준서 520.5(c) 대응)
------------------------------------------------------------
목적: 각 '계정 × 월' 실제값에 대해 "이 정도면 정상"이라는 기대 구간을 만든다.
      실제값이 기대 구간을 벗어나면 다음 단계(FR-04)에서 '차이'로 플래깅한다.

적응형 기법 선택(3단계) — 보유한 이력 길이에 따라 자동 선택:
  · 24개월+ & 계절성 있음   → 시계열 분해(STL)로 계절·추세 제거 후 잔차 판정
  · 12~24개월              → 추세 회귀(시간에 대한 회귀)
  · 12개월 이하 / 단일 연도 → 계정별 '월 로버스트 통계밴드'(중앙값 ± MAD)
  ─ 현재 데이터: 2025년 12개월(단일 연도, 직전연도 없음)
    → 자동 선택 = '로버스트 통계밴드'  (전년동월대비·계절분해는 이력 부족으로 불가)
    → 추가로 계정 간 회귀 시연: 제품매출원가 ~ 제품매출 (OLS + 95% 예측구간)

로버스트 통계밴드 원리(왜 평균이 아니라 중앙값/MAD인가):
  평균·표준편차는 '이상치 한 방'에 크게 흔들린다. 우리는 이상치를 '찾는' 게
  목적이므로, 이상치에 둔감한 중앙값(median)과 MAD(중앙값 절대편차)를 쓴다.
  수정 z점수 = 0.6745 × (값 − 중앙값) / MAD,  |z| > 3.5 이면 이상(Iglewicz–Hoaglin 기준).

입력 : data/gl_clean.csv
출력 : data/fr03_expectations.csv  (계정×월 기대구간·이상여부)
       reports/fr03_기대치.md, reports/11~14_*.png (그래프)
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
if os.environ.get("GL_NO_CHARTS"):          # 대시보드 실행 시 차트 저장 생략(속도↑)
    plt.savefig = lambda *a, **k: None
import statsmodels.api as sm
from pathlib import Path

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
gl = pd.read_csv(BASE / "data" / "gl_clean.csv",
                 dtype={"계정코드": str}, parse_dates=["전표일자"])
REP = BASE / "reports"; REP.mkdir(exist_ok=True)
EOK = 100_000_000  # 억원

K = 3.5              # 이상 판정 임계 (|수정 z| > 3.5)
SCALE = 0.6745       # 정규분포 하 MAD→표준편차 환산 상수
MIN_ACTIVE_M = 9     # 밴드 판정 대상: 12개월 중 활동한 달이 이 이상(정기 계정)
SIZE_FLOOR = 0.5 * 100_000_000   # 월 활동 중앙값이 이 미만이면 소액 → 판정 제외
REL_FLOOR = 0.15     # MAD가 0에 가까울 때 대비, 산포 하한 = 중앙값의 15%


def title(t): print("\n" + "=" * 62 + f"\n■ {t}\n" + "=" * 62)


# ========== 0) 적응형 기법 선택 (이력 진단) ==========
gl["월"] = gl["전표일자"].dt.to_period("M").astype(str)
months = sorted(gl["월"].unique())
n_month = len(months)
n_year = gl["전표일자"].dt.year.nunique()

# 적응형 선택: 직전연도가 있으면 '전년 동월 대비'(계절성 자동 반영), 없으면 단일연도 통계밴드.
# (3개 연도 이상이면 시계열 분해(STL)가 이상적이나 데이터 확보 시 확장 — 현재는 YoY까지 구현)
prior_year_mode = n_year >= 2
if n_year >= 3 and n_month >= 36:
    method = "전년 동월 대비(YoY)  ※3년+ 시계열분해는 향후 확장"
elif prior_year_mode:
    method = "전년 동월 대비(YoY)"
else:
    method = "로버스트 통계밴드(중앙값 ± MAD)"

title("0. 적응형 기법 선택 (보유 이력 진단)")
print(f"관측 기간   : {months[0]} ~ {months[-1]}  ({n_month}개월, {n_year}개 연도)")
print(f"직전연도    : {'있음 → 전년동월대비 가능' if prior_year_mode else '없음 → 전년동월대비 불가'}")
print(f"계절분해    : {'가능(3년+ 확보 시)' if n_month >= 36 else '불가(36개월 미만)'}")
print(f"→ 자동 선택 기법 : {method}")
print("  + 계정 간 회귀 시연 : 매출원가 ~ 매출 (OLS, 95% 예측구간)")


# ========== 1) 계정별 월 시계열 만들기 (자연 방향으로 정렬) ==========
# 계정마다 활동이 주로 실리는 쪽(차변/대변)이 다르다.
# 연간 총액이 큰 쪽을 '자연 방향'으로 보고, 월값 = (자연쪽 − 반대쪽) 으로 양수 지향 시계열 생성.
tot = gl.groupby("계정코드").agg(D=("차변", "sum"), C=("대변", "sum"))
natural = np.where(tot["D"] >= tot["C"], "차변성격", "대변성격")
natural = pd.Series(natural, index=tot.index, name="자연방향")

mon = (gl.groupby(["계정코드", "계정명", "월"])
         .agg(차=("차변", "sum"), 대=("대변", "sum")).reset_index()
         .merge(natural, on="계정코드"))
mon["월값"] = np.where(mon["자연방향"] == "차변성격",
                       mon["차"] - mon["대"], mon["대"] - mon["차"])


# ========== 2) 기대구간 계산 (적응형: 단일연도=밴드 / 2년+=전년동월대비) ==========
# 판정 대상 = '정기(매달) 활동 + 유의미한 규모' 계정만(비정기·소액은 밴드 불안정 → 제외).
g = mon.groupby("계정코드")["월값"]
mon["관측월수"] = g.transform("size")
mon["활동월수"] = g.transform(lambda s: int((s.abs() > 0).sum()))
mon["규모중앙값"] = g.transform(lambda s: np.median(np.abs(s)))   # 규모 게이트(월값 절대 중앙값)

if not prior_year_mode:
    # --- (A) 단일 연도: 로버스트 통계밴드(중앙값 ± MAD) ---
    #     "이 계정의 평소 월값 분포"에서 벗어난 달을 이상으로 본다.
    mon["기대중앙값"] = g.transform("median")
    mad = g.transform(lambda s: np.median(np.abs(s - np.median(s))))
    mon["sigma"] = np.maximum(mad / SCALE, REL_FLOOR * mon["기대중앙값"].abs())
    mon["판정대상"] = (mon["활동월수"] >= MIN_ACTIVE_M) & (mon["규모중앙값"] >= SIZE_FLOOR)
    mon["평가월"] = True
else:
    # --- (B) 적응형: '흐름 계정'만 전년동월대비, 순증감 계정은 로버스트 밴드로 자동 전환 ---
    #     매출·원가처럼 한 방향으로 꾸준히 누적되는 계정은 '전년 동월 × 성장률'이 잘 맞지만,
    #     외상매출금 등 매달 순증감(±)이 부호를 바꾸며 0 근처를 오가는 재무상태표 계정은
    #     성장률(=연간합÷연간합)이 폭주해 허위경보를 낸다. → 계정별로 판별해 밴드로 전환.
    mon["연"] = mon["월"].str[:4].astype(int)
    mon["월번호"] = mon["월"].str[5:7].astype(int)
    yrs = sorted(mon["연"].unique()); y_base, y_cur = yrs[0], yrs[-1]
    prev = mon[mon["연"] == y_base].set_index(["계정코드", "월번호"])["월값"]
    s_base = mon[mon["연"] == y_base].groupby("계정코드")["월값"].sum()
    s_cur = mon[mon["연"] == y_cur].groupby("계정코드")["월값"].sum()
    growth = (s_cur / s_base.replace(0, np.nan)).clip(0.2, 5).fillna(1.0)  # 극단 성장률 제한

    # 계정별 'YoY 적용 가능' 판별:
    #   연간합이 두 해 모두 같은 부호 & 월 규모(월값 절대 중앙값)의 3배 이상
    #   → 한 방향으로 꾸준히 누적되는 '흐름 계정'으로 간주. 아니면 순증감 계정 → 밴드.
    _scale = mon.groupby("계정코드")["규모중앙값"].first()

    def _yoy_ok(code):
        b, c, sc = s_base.get(code, 0.0), s_cur.get(code, 0.0), _scale.get(code, 0.0)
        return bool(sc > 0 and b != 0 and c != 0 and np.sign(b) == np.sign(c)
                    and abs(b) >= 3 * sc and abs(c) >= 3 * sc)
    yoy_ok = {code: _yoy_ok(code) for code in _scale.index}
    mon["YoY적용"] = mon["계정코드"].map(yoy_ok).fillna(False)

    # 순증감 계정용 '계절 반영' 밴드: 분기말월(3·6·9·12)과 그 외를 따로 묶어 평소값·산포 계산.
    #   (부가세·법인세 등 분기 신고월의 규칙적 급변을 '정상'으로 처리 → 오탐 완화)
    mon["계절군"] = np.where(mon["월번호"].isin([3, 6, 9, 12]), "분기말", "일반")
    band_med = mon.groupby(["계정코드", "계절군"])["월값"].transform("median")
    band_mad = mon.groupby(["계정코드", "계절군"])["월값"].transform(
        lambda s: np.median(np.abs(s - np.median(s))) / SCALE)

    def _expect(r):
        code = r["계정코드"]
        if yoy_ok.get(code, False):                # 흐름 계정 → 전년 동월 × 성장률
            if r["연"] == y_cur:
                return prev.get((code, r["월번호"]), np.nan) * growth.get(code, 1.0)
            return r["월값"]                        # 기준연도는 자기값(편차 0)
        return band_med.loc[r.name]                # 순증감 계정 → 계절군별 평소값(밴드)
    mon["기대중앙값"] = mon.apply(_expect, axis=1)
    dev = mon["월값"] - mon["기대중앙값"]

    # 산포(sigma): YoY 계정=당기 편차 MAD / 밴드 계정=계절군별 월값 MAD, 규모의 15% 하한
    sig_yoy = (mon[mon["연"] == y_cur].assign(_d=dev[mon["연"] == y_cur])
               .groupby("계정코드")["_d"].apply(lambda s: np.median(np.abs(s - np.median(s))) / SCALE))
    mon["sigma"] = np.maximum(
        np.where(mon["YoY적용"], mon["계정코드"].map(sig_yoy).fillna(0.0), band_mad),
        REL_FLOOR * mon["규모중앙값"])

    both = set(s_base[s_base.abs() > 0].index) & set(s_cur[s_cur.abs() > 0].index)
    base_ok = (mon["활동월수"] >= 12) & (mon["규모중앙값"] >= SIZE_FLOOR)
    #   YoY 계정은 두 해 모두 값이 있어야, 밴드 계정은 자기 분포만으로 판정
    mon["판정대상"] = base_ok & ((~mon["YoY적용"]) | mon["계정코드"].isin(both))
    mon["평가월"] = mon["연"] == y_cur              # 이상 판정은 당기 월에만(전년은 기준선)

mon["로버스트z"] = np.where(mon["sigma"] > 0,
                            (mon["월값"] - mon["기대중앙값"]) / mon["sigma"], 0.0)
mon["하한"] = mon["기대중앙값"] - K * mon["sigma"]
mon["상한"] = mon["기대중앙값"] + K * mon["sigma"]
mon["이상여부"] = mon["판정대상"] & mon["평가월"] & (mon["로버스트z"].abs() > K)
if prior_year_mode:
    mon["적용기법"] = np.where(~mon["판정대상"], "판정제외(비정기·소액)",
                       np.where(mon["YoY적용"], "전년 동월 대비(YoY)",
                                "로버스트 계절밴드(분기말/일반 구분·순증감 계정)"))
else:
    mon["적용기법"] = np.where(mon["판정대상"], method.split("  ")[0], "판정제외(비정기·소액)")

out = mon[["계정코드", "계정명", "자연방향", "월", "월값", "활동월수", "판정대상",
           "기대중앙값", "하한", "상한", "로버스트z", "이상여부", "적용기법"]]
out.to_csv(BASE / "data" / "fr03_expectations.csv", index=False, encoding="utf-8-sig")

n_target = mon.loc[mon["판정대상"], "계정코드"].nunique()

# 이상 요약
flag = out[out["이상여부"]].copy()
flag["편차_억"] = (flag["월값"] - flag["기대중앙값"]) / EOK
flag = flag.reindex(flag["로버스트z"].abs().sort_values(ascending=False).index)

title(f"2. {method.split('  ')[0]} — 기대구간 이탈(이상) 월 Top 15")
show = flag.head(15)[["계정명", "월", "월값", "기대중앙값", "로버스트z", "편차_억"]].copy()
show["월값"] = (show["월값"] / EOK).round(2)
show["기대중앙값"] = (show["기대중앙값"] / EOK).round(2)
show["로버스트z"] = show["로버스트z"].round(1)
show["편차_억"] = show["편차_억"].round(2)
show.columns = ["계정명", "월", "실제(억)", "기대중앙값(억)", "수정z", "편차(억)"]
print(show.to_string(index=False))
print(f"\n전체 {mon['계정코드'].nunique()}개 계정 중 판정대상(정기·유의미) {n_target}개 → 이상 표시 월 {len(flag)}건 "
      f"(활동 {MIN_ACTIVE_M}개월↑ & 월중앙값 {SIZE_FLOOR/EOK:.1f}억↑ 계정만)")


# ========== 3) 계정 간 회귀 시연: 제품매출원가 ~ 제품매출 ==========
title("3. 회귀 기대치 시연 — 매출원가 ~ 매출 (월 단위)")
piv = mon.pivot_table(index="월", columns="계정명", values="월값", aggfunc="sum")
# 회사마다 계정명이 달라도 되도록 이름 기반으로 매출·매출원가 계정을 모아 합산
sales_cols = [c for c in piv.columns if "매출" in str(c)
              and not any(e in str(c) for e in ["원가", "채권", "할인", "환입", "에누리", "선수", "미수"])]
cogs_cols = [c for c in piv.columns if "매출원가" in str(c)]
reg = None
if sales_cols and cogs_cols:
    sub = pd.DataFrame({"매출": piv[sales_cols].sum(axis=1),
                        "매출원가": piv[cogs_cols].sum(axis=1)}).dropna()
else:
    sub = pd.DataFrame()
if len(sub) >= 3 and sub["매출"].nunique() > 1:
    try:
        X = sm.add_constant(sub["매출"], has_constant="add")       # const 항상 추가
        model = sm.OLS(sub["매출원가"], X).fit()
        sf = model.get_prediction(X).summary_frame(alpha=0.05)
        reg = sub.copy()
        reg["기대원가"] = sf["mean"].values
        reg["예측하한"] = sf["obs_ci_lower"].values
        reg["예측상한"] = sf["obs_ci_upper"].values
        reg["구간이탈"] = (reg["매출원가"] < reg["예측하한"]) | (reg["매출원가"] > reg["예측상한"])
        print(f"대상 계정: 매출 {len(sales_cols)}개·매출원가 {len(cogs_cols)}개 합산, 월 {len(sub)}포인트")
        print(f"회귀식 : 매출원가 = {model.params['const']/EOK:,.2f}억 "
              f"+ {model.params['매출']:.3f} × 매출")
        print(f"설명력 R² = {model.rsquared:.3f}  (1에 가까울수록 매출로 원가가 잘 설명됨)")
        disp = reg.copy()
        for c in ["매출", "매출원가", "기대원가", "예측하한", "예측상한"]:
            disp[c] = (disp[c] / EOK).round(2)
        disp.columns = ["매출(억)", "원가(억)", "기대원가(억)", "예측하한(억)", "예측상한(억)", "구간이탈"]
        print(disp.to_string())
        print("→ '구간이탈=True'인 달은 매출 규모로 설명되지 않는 원가 → 검토 대상")
    except Exception as e:                          # 회귀는 '시연'이므로 실패해도 전체는 진행
        reg = None
        print("회귀 시연 생략(계산 불가):", str(e)[:60])
else:
    print("회귀 시연 생략 — 매출/매출원가 계정 없음 또는 월 데이터 부족")


# ========== 4) 그래프 ==========
def band_chart(acct, fname, idx):
    d = mon[mon["계정명"] == acct].sort_values("월")
    if d.empty:
        return
    x = d["월"].values
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.fill_between(x, d["하한"] / EOK, d["상한"] / EOK, color="#9ecae1",
                    alpha=.35, label="기대구간")
    ax.plot(x, d["기대중앙값"] / EOK, color="#3182bd", ls="--", lw=1, label="기대")
    ax.plot(x, d["월값"] / EOK, marker="o", color="#08519c", label="실제")
    out_pt = d[d["이상여부"]]
    ax.scatter(out_pt["월"], out_pt["월값"] / EOK, color="#c44e52", s=90,
               zorder=5, label="이상(구간 이탈)")
    ax.set_title(f"[{acct}] 월별 실제 vs 기대구간 (억원)")
    ax.set_ylabel("억원"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    plt.xticks(rotation=45); plt.tight_layout()
    plt.savefig(REP / fname, dpi=110); plt.close()


# 그래프 대상: 이 회사에서 '판정대상 & 활동 큰' 계정 상위 3개 자동 선택
chart_accts = (mon[mon["판정대상"]].assign(절대=mon["월값"].abs())
               .groupby("계정명")["절대"].median()
               .sort_values(ascending=False).head(3).index.tolist())
for i, acct in enumerate(chart_accts, start=11):
    band_chart(acct, f"{i}_기대_{acct}.png", i)

if reg is not None:
    fig, ax = plt.subplots(figsize=(7, 5))
    order = reg.sort_values("매출")
    ax.plot(order["매출"] / EOK, order["기대원가"] / EOK, color="#3182bd", label="회귀 기대선")
    ax.fill_between(order["매출"] / EOK, order["예측하한"] / EOK, order["예측상한"] / EOK,
                    color="#9ecae1", alpha=.35, label="95% 예측구간")
    normal = reg[~reg["구간이탈"]]; odd = reg[reg["구간이탈"]]
    ax.scatter(normal["매출"] / EOK, normal["매출원가"] / EOK, color="#08519c", label="정상 월")
    ax.scatter(odd["매출"] / EOK, odd["매출원가"] / EOK, color="#c44e52", s=90, zorder=5, label="구간이탈 월")
    for _, r in reg.iterrows():
        ax.annotate(str(r.name)[-2:], (r["매출"] / EOK, r["매출원가"] / EOK), fontsize=7,
                    xytext=(3, 3), textcoords="offset points")
    ax.set_title("회귀 기대치: 매출 → 매출원가")
    ax.set_xlabel("매출(억)"); ax.set_ylabel("매출원가(억)")
    ax.grid(alpha=.3); ax.legend(fontsize=8)
    plt.tight_layout(); plt.savefig(REP / "14_회귀_원가대매출.png", dpi=110); plt.close()


# ========== 5) 마크다운 리포트 ==========
md = ["# FR-03 기대치 생성 엔진 결과\n",
      f"- 입력: `gl_clean.csv`  ({len(gl):,}줄)",
      f"- 관측 기간: {months[0]} ~ {months[-1]} ({n_month}개월, {n_year}개 연도)",
      f"- 자동 선택 기법: **{method}**"
      + ("  (2개 연도 → 전년 동월 대비: 계절성 자동 반영, 성장률 보정)" if prior_year_mode
         else "  (직전연도 없음 → 전년동월대비·계절분해 불가)"),
      f"- 판정대상 계정: {n_target}개 (활동 {MIN_ACTIVE_M}개월↑ & 월중앙값 {SIZE_FLOOR/EOK:.1f}억↑) / 전체 {mon['계정코드'].nunique()}개",
      f"- 이상 표시 월: **{len(flag)}건**\n",
      "## 기대구간 이탈(이상) Top 15\n",
      show.to_markdown(index=False)]
if reg is not None:
    md += ["\n## 회귀 시연 (매출원가 ~ 매출)\n",
           f"- 회귀식: 매출원가 = {model.params['const']/EOK:,.2f}억 + {model.params['매출']:.3f} × 매출",
           f"- R² = {model.rsquared:.3f}",
           f"- 예측구간 이탈 월: {int(reg['구간이탈'].sum())}개\n",
           disp.to_markdown()]
(REP / "fr03_기대치.md").write_text("\n".join(md), encoding="utf-8")

print("\n" + "-" * 62)
print("저장:", BASE / "data" / "fr03_expectations.csv")
print("저장:", REP / "fr03_기대치.md")
print("그래프:", ", ".join(f"{i}_기대_{a}.png" for i, a in enumerate(chart_accts, 11))
      + (", 14_회귀_원가대매출.png" if reg is not None else ""))
