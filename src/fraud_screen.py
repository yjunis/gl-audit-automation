# -*- coding: utf-8 -*-
"""
FR-09 · 전표 부정위험 스크리닝 (Journal Entry Testing / 감사기준서 240)
------------------------------------------------------------
총계정원장 분개를 훑어 '부정 징후(레드플래그)'를 점수화한다.
감사기준서 240 문단 32(a)(경영진 통제 무력화 대응 위한 분개 적정성 테스트)의 직접 구현.

핵심 원칙:
  · 판정이 아니라 '먼저 볼 순서' (우선순위)
  · 모든 점수는 '걸린 이유(배점 분해)'로 설명 가능 (블랙박스 금지)
  · 가중치는 fraud_weights.json 으로 조정 가능 (코드 수정 불필요)
  · 사용 불가한 테스트(예: 전표번호 없는 회사의 상대계정 조합)는 자동 생략

레드플래그(240 A41~A44):
  [고정형]  기말 · 주말 · 라운드금액 · 결산/수정 키워드 · 적요 모호 · 거래처 없는 대형
  [데이터형] 이례적 상대계정 조합(희소도) · 중복 전표

입력 : data/gl_clean.csv        (GL_BASE 로 회사 폴더 지정 가능)
출력 : data/fr09_fraud_flags.csv, reports/fr09_부정스크리닝.md
"""
import os
import json
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
SRC = Path(__file__).resolve().parent
REP = BASE / "reports"; REP.mkdir(exist_ok=True)
EOK = 100_000_000

# ===== 가중치 설정 (외부 JSON, 없으면 기본값) =====
DEFAULT_W = {"상대계정조합": 30, "결산수정키워드": 25, "거래처없는대형": 20,
             "중복전표": 15, "라운드금액": 15, "기말": 10, "주말": 10, "적요모호": 10,
             "수기전표": 20, "소급입력": 20, "작성자이상": 10}  # 뒤 3개 = FR-13 메타(있을 때만 활성)
try:
    _cfg = json.loads((SRC / "fraud_weights.json").read_text(encoding="utf-8"))
    WALL = {k: _cfg.get(k, v) for k, v in DEFAULT_W.items()}
    HI = _cfg.get("_임계_등급_높음", 45)
    MID = _cfg.get("_임계_등급_중간", 25)
except Exception:
    WALL, HI, MID = dict(DEFAULT_W), 45, 25
# W·MAXPOSS는 실제 활성화된 플래그가 정해진 뒤(아래) 확정한다.

gl = pd.read_csv(BASE / "data" / "gl_clean.csv",
                 dtype={"계정코드": str}, parse_dates=["전표일자"])
if "전표번호" in gl.columns:
    gl["전표번호"] = gl["전표번호"].fillna("").astype(str).str.strip()
else:
    gl["전표번호"] = ""

gl["금액"] = gl["차변"] - gl["대변"]
gl["절대금액"] = gl["금액"].abs()

# 수행중요성 PM (거래처없는 대형 임계 + 금액 축)
_mae = gl["계정명"].astype(str).str.contains("매출", na=False) & \
    ~gl["계정명"].astype(str).str.contains("원가|차감|환입|할인|에누리", na=False)
rev = gl.loc[_mae, "대변"].sum() - gl.loc[_mae, "차변"].sum()
rev = rev if rev > 0 else gl["차변"].sum()
PM = rev * 0.00375

# ===== 레드플래그 판정 =====
dow = gl["전표일자"].dt.dayofweek
day = gl["전표일자"].dt.day
mon = gl["전표일자"].dt.month
amt_int = gl["절대금액"].round().astype("int64")
memo = gl["적요"].fillna("").astype(str)
memo_n = memo.str.replace(r"\s+", "", regex=True)

f = {}
f["주말"] = dow >= 5
# 기말: 분기말(3·6·9·12월) 말일 + 연말 마감 임박 (단순 월말은 너무 흔해 제외)
f["기말"] = (mon.isin([3, 6, 9, 12]) & (day >= 28)) | ((mon == 12) & (day >= 20))
f["라운드금액"] = (amt_int > 0) & (amt_int % 1_000_000 == 0)  # 백만 단위 딱 떨어짐
f["결산수정키워드"] = memo_n.str.contains(
    "수정|취소|역분개|재분류|조정|임시|가공|대체|정정|결산", na=False)
f["적요모호"] = memo.str.strip().str.len() < 4
f["거래처없는대형"] = gl["거래처명"].isna() & (gl["절대금액"] >= PM)

# 중복 전표: 같은 날·같은 거래처·같은 금액 (전형적 이중지급 징후 — same/same/same)
dup_key = (gl["전표일자"].dt.strftime("%Y%m%d") + "|" + gl["거래처명"].astype(str)
           + "|" + amt_int.astype(str))
f["중복전표"] = ((dup_key.map(dup_key.value_counts()) > 1)
                & (gl["절대금액"] > 0) & gl["거래처명"].notna())

# 이례적 상대계정 조합 (전표번호 있을 때만 — 없으면 자동 생략)
gl["상대계정조합"] = ""
f["상대계정조합"] = pd.Series(False, index=gl.index)
doc_ratio = (gl["전표번호"] != "").mean()
combo_used = doc_ratio > 0.5
if combo_used:
    gl["_vk"] = gl["전표일자"].dt.strftime("%Y%m%d") + "|" + gl["전표번호"]
    dr = (gl[gl["차변"] > 0].sort_values("차변").groupby("_vk").tail(1)
          [["_vk", "계정명"]].rename(columns={"계정명": "차변계정"}))
    cr = (gl[gl["대변"] > 0].sort_values("대변").groupby("_vk").tail(1)
          [["_vk", "계정명"]].rename(columns={"계정명": "대변계정"}))
    pair = dr.merge(cr, on="_vk", how="inner")
    if len(pair):                                    # 대차 짝이 맞는 전표가 있을 때만
        pair["조합"] = pair["차변계정"] + " → " + pair["대변계정"]
        freq = pair["조합"].value_counts()
        pair["빈도"] = pair["조합"].map(freq)
        thr = max(2, int(freq.quantile(0.05)))       # 하위 5% 이하 = 희소
        rare_vk = set(pair.loc[pair["빈도"] <= thr, "_vk"])
        combo_map = pair.set_index("_vk")["조합"]
        f["상대계정조합"] = gl["_vk"].isin(rare_vk)
        gl["상대계정조합"] = gl["_vk"].map(combo_map).fillna("")
    else:                                            # 전표당 1줄 등 → 조합분석 불가
        combo_used = False

# ===== FR-13 메타필드 레드플래그 (해당 열이 있을 때만 활성, 없으면 자동 생략) =====
meta_active = []
if "전표유형" in gl.columns and gl["전표유형"].notna().any():
    jt = gl["전표유형"].fillna("").astype(str)
    f["수기전표"] = (jt.str.contains("수기|수동|직접|일반전표", na=False)
                   & ~jt.str.contains("자동|이관|결산자동|자동이체", na=False))
    meta_active.append("수기전표")
if "입력일" in gl.columns and pd.to_datetime(gl["입력일"], errors="coerce").notna().any():
    gap = (pd.to_datetime(gl["입력일"], errors="coerce") - gl["전표일자"]).dt.days
    f["소급입력"] = gap.fillna(0) >= 7            # 회계일보다 7일 이상 늦게 입력(소급/지연기표)
    meta_active.append("소급입력")
if "작성자" in gl.columns and gl["작성자"].notna().any():
    au = gl["작성자"].fillna("").astype(str)
    freq_au = au.map(au.value_counts())
    thr_au = max(1, int(freq_au.quantile(0.05)))
    f["작성자이상"] = (freq_au <= thr_au) & (au.str.len() > 0) & (gl["절대금액"] >= PM)
    meta_active.append("작성자이상")

# 활성 플래그만으로 가중치·만점 구성 (메타필드 없으면 기존 8개 그대로)
W = {k: WALL[k] for k in f}
MAXPOSS = sum(W.values())

# ===== 점수 산정 =====
comp = pd.DataFrame({k: f[k].astype(int) * W[k] for k in W})   # 이유별 배점
raw = comp.sum(axis=1)
score = (raw / MAXPOSS * 100).round().astype(int)
gl["부정위험점수"] = score
gl["금액중요도"] = (gl["절대금액"] / PM).round(2)


def grade(s):
    return "🔴 높음" if s >= HI else ("🟠 중간" if s >= MID else "⚪ 낮음")


# 걸린 것만(점수>0) 추려 이유 분해
hit = comp[raw > 0].copy()
out = gl.loc[hit.index].copy()
out["등급"] = out["부정위험점수"].map(grade)
# 설명가능성(NFR-06): 정규화 점수를 재현·검증할 수 있도록 원배점합·만점 동봉
# 부정위험점수 = round(원배점합 / 최대배점 * 100)
out["원배점합"] = raw.loc[hit.index].astype(int)
out["최대배점"] = int(MAXPOSS)


def mk_reason(row):
    return ", ".join(f"{c}({int(row[c])})" for c in comp.columns if row[c] > 0)


out["걸린이유"] = hit.apply(mk_reason, axis=1)
out = out.sort_values(["부정위험점수", "절대금액"], ascending=False).reset_index(drop=True)
out.insert(0, "순위", out.index + 1)

cols = ["순위", "전표일자", "전표번호", "계정명", "적요", "거래처명",
        "금액", "금액중요도", "상대계정조합", "부정위험점수", "원배점합", "최대배점", "등급", "걸린이유"]
save = out[cols].head(500).copy()
save["전표일자"] = save["전표일자"].dt.strftime("%Y-%m-%d")
save.to_csv(BASE / "data" / "fr09_fraud_flags.csv", index=False, encoding="utf-8-sig")

# ===== 콘솔 요약 =====
n_hi = (out["등급"].str.contains("높음")).sum()
n_mid = (out["등급"].str.contains("중간")).sum()
print("=" * 64)
print("FR-09 전표 부정위험 스크리닝 (감사기준서 240)")
print("=" * 64)
print(f"대상: {len(gl):,} 분개 | 수행중요성 PM {PM/EOK:,.2f}억")
print(f"상대계정 조합 분석: {'적용' if combo_used else '생략(전표번호 부족)'}")
print(f"FR-13 메타 레드플래그: {', '.join(meta_active) if meta_active else '없음(작성자·입력일·전표유형 열 미존재 → 자동 생략)'}")
print(f"플래그된 분개: {len(out):,}건  (🔴높음 {n_hi} / 🟠중간 {n_mid})")
print("-" * 64)
print("레드플래그별 적발 건수:")
for k in W:
    print(f"  {k:12s} {int(f[k].sum()):>7,}건  (배점 {W[k]})")
print("-" * 64)
print("부정위험 Top 12:")
with pd.option_context("display.unicode.east_asian_width", True, "display.width", 200):
    top = out.head(12).copy()
    top["금액(억)"] = (top["금액"] / EOK).round(2)
    top["일자"] = top["전표일자"].dt.strftime("%m-%d")
    print(top[["순위", "일자", "계정명", "금액(억)", "부정위험점수", "등급", "걸린이유"]].to_string(index=False))

# ===== 리포트 =====
md = ["# FR-09 전표 부정위험 스크리닝 결과 (감사기준서 240)\n",
      f"- 대상: {len(gl):,} 분개 · 수행중요성(PM) {PM/EOK:,.2f}억",
      f"- 상대계정 조합 분석: {'적용' if combo_used else '생략(전표번호 부족)'}",
      f"- FR-13 메타 레드플래그: {', '.join(meta_active) if meta_active else '없음(관련 열 미존재 → 자동 생략)'}",
      f"- 플래그: **{len(out):,}건** (🔴높음 {n_hi} / 🟠중간 {n_mid})\n",
      "## 레드플래그별 적발 건수\n",
      "| 레드플래그 | 적발 | 배점 |", "|---|---:|---:|"]
for k in W:
    md.append(f"| {k} | {int(f[k].sum()):,} | {W[k]} |")
md += ["\n## 부정위험 Top 15\n"]
t15 = out.head(15).copy()
t15["금액(억)"] = (t15["금액"] / EOK).round(2)
t15["전표일자"] = t15["전표일자"].dt.strftime("%Y-%m-%d")
md.append(t15[["순위", "전표일자", "계정명", "금액(억)", "부정위험점수", "등급", "걸린이유"]]
          .to_markdown(index=False))
md += ["\n> 주의: 점수는 '먼저 볼 순서'이며 부정 확정이 아니다. 정당한 결산분개 등도 걸릴 수 있으므로 감사인이 최종 검토한다."]
(REP / "fr09_부정스크리닝.md").write_text("\n".join(md), encoding="utf-8")

print("-" * 64)
print("저장:", BASE / "data" / "fr09_fraud_flags.csv")
print("저장:", REP / "fr09_부정스크리닝.md")
