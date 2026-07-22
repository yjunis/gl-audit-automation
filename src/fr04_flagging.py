# -*- coding: utf-8 -*-
"""
FR-04 · 차이 분석·플래깅 (감사기준서 520.5(d) 대응)
------------------------------------------------------------
목적: FR-03이 만든 '통계적 이상 후보'에 감사 실무의 두 잣대를 적용해
      "감사인이 실제로 봐야 할 항목"만 등급을 매겨 추린다.
        ① 중요성(Materiality) — 금액이 감사상 무시 못 할 크기인가?
        ② 위험도 점수         — 통계 이탈도와 금액 초과 정도를 합쳐 우선순위화

핵심 원칙(중요한 설계):
  중요성은 이상 후보를 '추가'하지 않는다. 통계적 이상(|수정z|>3.5)으로 잡힌 것들을
  '얼마나 급한가'로 줄 세우는 데만 쓴다.  (안 그러면 제품매출 같은 큰 계정은
   매달 생기는 정상 변동도 금액이 커서 전부 걸려버린다 → 잘못된 경보 폭증)

중요성 기준(감사 실무 관행):
  · 전체중요성 OM = 벤치마크(연간 매출) × 0.5%
  · 성과중요성 PM = OM × 75%   (개별 항목 판단선)
  · 명백히 사소 CTT = OM × 5%  (이 밑은 사실상 무시)

입력 : data/fr03_expectations.csv, data/gl_clean.csv
출력 : data/fr04_flags.csv, reports/fr04_플래깅.md, reports/15_위험매트릭스.png, 16_우선순위.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
if os.environ.get("GL_NO_CHARTS"):          # 대시보드 실행 시 차트 저장 생략(속도↑)
    plt.savefig = lambda *a, **k: None
from pathlib import Path

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
exp = pd.read_csv(BASE / "data" / "fr03_expectations.csv", dtype={"계정코드": str})
gl = pd.read_csv(BASE / "data" / "gl_clean.csv",
                 dtype={"계정코드": str}, parse_dates=["전표일자"])
gl["월"] = gl["전표일자"].dt.to_period("M").astype(str)
REP = BASE / "reports"; REP.mkdir(exist_ok=True)
EOK = 100_000_000


def title(t): print("\n" + "=" * 62 + f"\n■ {t}\n" + "=" * 62)


# ========== 1) 중요성(Materiality) 기준 세우기 ==========
def benchmark(gl):
    """벤치마크 = 매출 계정 합계(원가·차감·환입 제외). 없으면 총 차변 발생액 대용."""
    ismae = gl["계정명"].astype(str).str.contains("매출", na=False)
    isexc = gl["계정명"].astype(str).str.contains("원가|차감|환입|할인|에누리", na=False)
    rev = gl.loc[ismae & ~isexc, "대변"].sum() - gl.loc[ismae & ~isexc, "차변"].sum()
    if rev > 0:
        return rev, "매출"
    return gl["차변"].sum(), "차변총계(매출계정 없음)"

rev, bench_kind = benchmark(gl)
OM = rev * 0.005
PM = OM * 0.75
CTT = OM * 0.05

title("1. 중요성(Materiality) 기준")
print(f"벤치마크({bench_kind}) : {rev/EOK:,.1f} 억원")
print(f"전체중요성 OM (매출 0.5%): {OM/EOK:,.2f} 억원")
print(f"성과중요성 PM (OM 75%)   : {PM/EOK:,.2f} 억원  ← 개별 항목 판단선")
print(f"명백히 사소 CTT (OM 5%)  : {CTT/EOK:,.2f} 억원")


# ========== 2) 이상 후보에 중요성·위험도 적용 ==========
cand = exp[exp["이상여부"]].copy()                       # FR-03의 통계적 이상만
cand["편차"] = cand["월값"] - cand["기대중앙값"]
cand["편차_abs"] = cand["편차"].abs()
cand["방향"] = np.where(cand["편차"] >= 0, "급증", "급감")
cand["PM배수"] = cand["편차_abs"] / PM                    # 성과중요성의 몇 배인가

# 등급: 통계이상은 공통, 금액 크기로 높음/중간/낮음
def grade(v):
    if v >= PM:
        return "🔴 높음"
    if v >= CTT:
        return "🟠 중간"
    return "⚪ 낮음"
cand["등급"] = cand["편차_abs"].map(grade)

# 위험 점수(0~100): 금액초과(PM배수)와 통계이탈(|z|)을 반반, 각기 상한 두고 정규화
z = cand["로버스트z"].abs()
score = 50 * np.minimum(cand["PM배수"], 5) / 5 + 50 * np.minimum(z, 10) / 10
cand["위험점수"] = score.round().astype(int)


# ========== 3) 위험요소 태그 + 대표 전표(적요) ==========
def rep_memo(code, month):
    """해당 계정·월에서 금액이 가장 큰 분개 한 줄의 적요·거래처·금액."""
    d = gl[(gl["계정코드"] == code) & (gl["월"] == month)].copy()
    if d.empty:
        return ""
    d["금액"] = (d["차변"] - d["대변"]).abs()
    r = d.loc[d["금액"].idxmax()]
    memo = str(r["적요"])[:28]
    cp = "" if pd.isna(r["거래처명"]) else f"/{r['거래처명']}"
    doc = str(r["전표번호"]).strip() if "전표번호" in d.columns else ""
    docs = f"[{doc}] " if doc and doc.lower() != "nan" else ""
    return f"{docs}{r['금액']/EOK:,.1f}억 {memo}{cp}"


def tags(row):
    t = ["통계이상"]
    if row["편차_abs"] >= PM:
        t.append("중요성초과")
    if row["월"].endswith("-12"):
        t.append("기말(12월)")
    if row["월값"] < 0:
        t.append("음수(역분개의심)")
    return ",".join(t)

cand["위험요소"] = cand.apply(tags, axis=1)
cand["대표전표"] = [rep_memo(c, m) for c, m in zip(cand["계정코드"], cand["월"])]

flags = cand.sort_values("위험점수", ascending=False).reset_index(drop=True)
flags.insert(0, "순위", flags.index + 1)

out = flags[["순위", "계정코드", "계정명", "월", "방향", "월값", "기대중앙값", "편차",
             "로버스트z", "PM배수", "위험점수", "등급", "위험요소", "대표전표"]]
out.to_csv(BASE / "data" / "fr04_flags.csv", index=False, encoding="utf-8-sig")


# ========== 4) 콘솔 요약 ==========
title("2. 감사인 검토 우선순위 (위험점수 순)")
disp = out.copy()
for c in ["월값", "기대중앙값", "편차"]:
    disp[c] = (disp[c] / EOK).round(2)
disp["PM배수"] = disp["PM배수"].round(1)
disp["로버스트z"] = disp["로버스트z"].round(1)
disp = disp.rename(columns={"월값": "실제(억)", "기대중앙값": "기대(억)", "편차": "편차(억)",
                            "로버스트z": "수정z"})
print(disp[["순위", "계정명", "월", "방향", "실제(억)", "기대(억)", "편차(억)",
            "수정z", "PM배수", "위험점수", "등급"]].to_string(index=False))
print("\n[대표 전표(최대 금액 분개)]")
for _, r in out.iterrows():
    print(f"  {r['순위']}. {r['계정명']}({r['월']}) · {r['위험요소']}")
    print(f"       └ {r['대표전표']}")

n_hi = (out["등급"].str.contains("높음")).sum()
n_mid = (out["등급"].str.contains("중간")).sum()
print(f"\n종합: 🔴높음 {n_hi}건 / 🟠중간 {n_mid}건  (감사인 우선 검토 대상)")


# ========== 5) 위험 매트릭스 그래프 ==========
fig, ax = plt.subplots(figsize=(8.5, 6))
colors = {"🔴 높음": "#c44e52", "🟠 중간": "#dd8452", "⚪ 낮음": "#8c8c8c"}
for _, r in out.iterrows():
    ax.scatter(abs(r["로버스트z"]), r["PM배수"], s=60 + r["위험점수"] * 4,
               color=colors.get(r["등급"], "#8c8c8c"), alpha=.7, edgecolor="k", lw=.5)
    ax.annotate(f"{r['계정명']}\n{r['월'][-2:]}월",
                (abs(r["로버스트z"]), r["PM배수"]), fontsize=7.5,
                xytext=(6, 0), textcoords="offset points", va="center")
ax.axhline(1, color="#c44e52", ls="--", lw=1, alpha=.6)   # PM 선(배수=1)
ax.axvline(3.5, color="#4c72b0", ls="--", lw=1, alpha=.6)  # 통계이상 임계
ax.text(3.6, ax.get_ylim()[1] * .96, "|z|=3.5(통계이상)", color="#4c72b0", fontsize=8)
ax.text(ax.get_xlim()[1] * .55, 1.05, "PM(성과중요성)", color="#c44e52", fontsize=8)
ax.set_xlabel("통계 이탈도  |수정 z|  →"); ax.set_ylabel("금액 중요도  (편차 ÷ 성과중요성) →")
ax.set_title("위험 매트릭스: 통계 이탈 × 금액 중요성")
ax.grid(alpha=.3); plt.tight_layout()
plt.savefig(REP / "15_위험매트릭스.png", dpi=110); plt.close()

# 우선순위 막대
fig, ax = plt.subplots(figsize=(8.5, 4.5))
lab = out["계정명"] + "\n" + out["월"].str[-2:] + "월"
bar_c = [colors.get(g, "#8c8c8c") for g in out["등급"]]
ax.barh(lab, out["위험점수"], color=bar_c)
ax.invert_yaxis()
for i, v in enumerate(out["위험점수"]):
    ax.text(v + 1, i, str(v), va="center", fontsize=9)
ax.set_xlabel("위험점수 (0~100)"); ax.set_title("감사 검토 우선순위")
ax.grid(alpha=.3, axis="x"); plt.tight_layout()
plt.savefig(REP / "16_우선순위.png", dpi=110); plt.close()


# ========== 6) 마크다운 리포트 ==========
md = ["# FR-04 차이 분석·플래깅 결과\n",
      "## 중요성 기준",
      f"- 벤치마크({bench_kind}): {rev/EOK:,.1f} 억원",
      f"- 전체중요성 OM(0.5%): {OM/EOK:,.2f} 억 / 성과중요성 PM(75%): {PM/EOK:,.2f} 억 / CTT(5%): {CTT/EOK:,.2f} 억\n",
      f"## 우선순위 (🔴높음 {n_hi} / 🟠중간 {n_mid})\n",
      disp[["순위", "계정명", "월", "방향", "실제(억)", "기대(억)", "편차(억)",
            "수정z", "PM배수", "위험점수", "등급", "위험요소"]].to_markdown(index=False),
      "\n## 대표 전표(각 항목 최대 금액 분개)\n"]
for _, r in out.iterrows():
    md.append(f"- **{r['순위']}. {r['계정명']} ({r['월']})** — {r['대표전표']}")
(REP / "fr04_플래깅.md").write_text("\n".join(md), encoding="utf-8")

print("\n" + "-" * 62)
print("저장:", BASE / "data" / "fr04_flags.csv")
print("저장:", REP / "fr04_플래깅.md")
print("그래프: 15_위험매트릭스.png, 16_우선순위.png")
