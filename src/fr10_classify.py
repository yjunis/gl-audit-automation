# -*- coding: utf-8 -*-
"""
FR-10 · 계정과목 자동 분류기 (5층 정확도 + 인적 검토·수정)
------------------------------------------------------------
GL 계정명을 '재무제표 표준항목'으로 매핑한다. FR-11(분식위험 점수 M·Z)의 전제 기능.
감사기준서 315(왜곡표시 위험 계정 식별)·표시·분류 적정성 관점.

정확도 5층 (RFP FR-10):
  1층 표준사전(account_dict.json) — 이름 키워드 매칭. '가장 긴 키워드'가 이김
        (외상매출금 → '외상매출금'(매출채권)이 '매출'(매출)을 이긴다). 차감계정 별도.
  2층 계정코드 교차검증 — 코드 앞자리가 대분류와 맞는지 확인(회사마다 코드체계 달라 '참고용' 신호).
  3층 차변/대변 성격 교차검증 — 자산·비용=차변, 부채·자본·수익=대변. 실제 잔액성격과 모순 포착.
  4층 회계 항등식 검산 — 자산순 = 부채+자본+당기순이익. 미분류 계정 net 만큼 어긋난다.
  5층 퍼지 추정(difflib) — 미매칭 계정을 문자 유사도로 추정('낮은 확신'으로 표기).

인적 검토(FR-10 핵심): fr10_overrides.json 의 사용자 수정을 최우선 반영(=학습). 검토 화면은 fr10_review_app.py.

입력 : data/gl_clean.csv     (GL_BASE 로 회사 폴더 지정 가능)
출력 : data/fr10_account_map.csv, reports/fr10_계정분류.md
"""
import os
import re
import json
import difflib
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
SRC = Path(__file__).resolve().parent
REP = BASE / "reports"; REP.mkdir(exist_ok=True)
EOK = 100_000_000

# ===== 사전 로드 =====
DICT = json.loads((SRC / "account_dict.json").read_text(encoding="utf-8"))
CATS = DICT["categories"]

# 코드 앞자리 → 대분류(참고용, 회사별 상이). 한국 관행의 느슨한 기대치.
CODE_HINT = {"1": "자산", "2": "부채", "3": "자본", "4": "매출", "5": "매출원가",
             "6": "판관비", "7": "매출원가", "8": "판관비", "9": "영업외"}


def norm(s):
    """정규화: 공백·괄호·기호 제거."""
    return re.sub(r"[\s()\[\]（）·・,./\-_]", "", str(s))


# 키워드 인덱스: (정규화키워드, 카테고리index, 원본키워드)
KW = []
for i, c in enumerate(CATS):
    for kw in c["키워드"]:
        KW.append((norm(kw), i, kw))
ALL_NORMKW = [k[0] for k in KW]


def classify_name(name):
    """1층+5층: 이름으로 표준항목 결정 → (cat_idx, 확신도, 근거)."""
    nn = norm(name)
    # 1층: 부분일치 후보 중 '가장 긴 키워드' 승 (동률이면 사전 우선순위=앞 index)
    hits = [(len(nk), -ci, ci, ok) for nk, ci, ok in KW if nk and nk in nn]
    if hits:
        hits.sort(reverse=True)
        _, _, ci, ok = hits[0]
        conf = "정확일치" if nn == norm(ok) else "키워드"
        return ci, conf, ok
    # 5층: 퍼지 추정
    m = difflib.get_close_matches(nn, ALL_NORMKW, n=1, cutoff=0.6)
    if m:
        ci = next(c for nk, c, _ in KW if nk == m[0])
        return ci, "추정", CATS[ci]["키워드"][0]
    return None, "미분류", ""


def main():
    gl = pd.read_csv(BASE / "data" / "gl_clean.csv", dtype={"계정코드": str})
    g = (gl.groupby(["계정코드", "계정명"], as_index=False)
         .agg(차변합=("차변", "sum"), 대변합=("대변", "sum"), 건수=("차변", "size")))

    # net = 기말잔액. 시산표(시스템누계차변-대변)이 정확한 잔액(=기초+기중).
    #   · 재무상태표 계정 → 기말잔액 레벨,  손익 계정 → 기간 총액 (FR-11이 원하는 값)
    #   · 시산표 없으면 gl 기간흐름(차변합-대변합)으로 대체
    tb_path = BASE / "data" / "trial_balance.csv"
    if tb_path.exists():
        tb = pd.read_csv(tb_path, dtype={"계정코드": str})
        tb["net"] = tb["시스템누계차변"].fillna(0) - tb["시스템누계대변"].fillna(0)
        g = g.merge(tb[["계정코드", "net"]], on="계정코드", how="left")
        g["net"] = g["net"].fillna(g["차변합"] - g["대변합"])
    else:
        g["net"] = g["차변합"] - g["대변합"]
    g["잔액성격"] = np.where(g["net"] >= 0, "차변", "대변")   # +면 차변, -면 대변

    # 사용자 확정(override) 로드
    ov_path = BASE / "data" / "fr10_overrides.json"
    if not ov_path.exists():
        ov_path = SRC / "fr10_overrides.json"      # 없으면 src 기본값 참조
    overrides = {}
    if ov_path.exists():
        try:
            overrides = json.loads(ov_path.read_text(encoding="utf-8"))
        except Exception:
            overrides = {}
    valid_items = {c["표준항목"]: i for i, c in enumerate(CATS)}

    rows = []
    for _, r in g.iterrows():
        code, name = str(r["계정코드"]), str(r["계정명"])
        # 사용자 확정 우선 (계정코드 또는 계정명 키)
        forced = overrides.get(code) or overrides.get(name)
        if forced and forced in valid_items:
            ci, conf, basis = valid_items[forced], "사용자확정", "수동지정"
        else:
            ci, conf, basis = classify_name(name)

        if ci is None:
            item, ggrp, side_exp, stmt, contra = "미분류", "미분류", "-", "-", False
        else:
            c = CATS[ci]
            item, ggrp = c["표준항목"], c["대분류"]
            side_exp, stmt, contra = c["성격"], c["재무제표"], c["차감"]

        # 2층: 코드 앞자리 참고 신호
        code_hint = CODE_HINT.get(code[:1], "?") if code[:1].isdigit() else "합성"
        # 3층: 성격 교차검증 (차감계정은 대변 잔액이 정상)
        actual = r["잔액성격"]
        if item == "미분류":
            sidechk = "-"
        elif abs(r["net"]) < 1:
            sidechk = "잔액0"
        elif actual == side_exp:
            sidechk = "✅일치"
        else:
            sidechk = "⚠️불일치"

        rows.append(dict(계정코드=code, 계정명=name, 표준항목=item, 대분류=ggrp,
                         재무제표=stmt, 차감=contra, 기대성격=side_exp, 잔액성격=actual,
                         확신도=conf, 근거키워드=basis, 코드힌트=code_hint,
                         성격점검=sidechk, net=r["net"], 건수=int(r["건수"])))

    m = pd.DataFrame(rows)

    # ===== 4층: 회계 항등식 검산 =====
    def ssum(stmt):
        return m.loc[m["재무제표"] == stmt, "net"].sum()
    asset = ssum("자산")                      # 자산순(차감 포함, +)
    liab = -ssum("부채")                       # 부채(대변→부호전환, +)
    equity = -ssum("자본")                     # 자본(+)
    rev = -m.loc[m["재무제표"] == "수익", "net"].sum()   # 수익(+)
    exp = m.loc[m["재무제표"] == "비용", "net"].sum()     # 비용(+)
    ni = rev - exp                            # 당기순이익
    unclass = m.loc[m["표준항목"] == "미분류", "net"].sum()
    tb_diff = m["net"].sum()                  # 시산표 자체 대차차이(원장 기초 특성, 분류 무관)
    # 분류 잔차 = 자산순 − (부채+자본+당기순이익) = 시산표대차차이 − 미분류net
    resid = asset - (liab + equity + ni)
    # 분류 품질 판정: '미분류 net'이 0에 가까우면 커버리지 양호(시산표 대차차이와 무관)
    ident_ok = abs(unclass) < max(abs(asset) * 0.005, 1)

    # ===== 저장 =====
    save = m.copy()
    save["net(억)"] = (save["net"] / EOK).round(2)
    cols = ["계정코드", "계정명", "표준항목", "대분류", "재무제표", "차감",
            "기대성격", "잔액성격", "성격점검", "확신도", "근거키워드", "코드힌트",
            "net(억)", "건수"]
    save[cols].to_csv(BASE / "data" / "fr10_account_map.csv",
                      index=False, encoding="utf-8-sig")

    # ===== 콘솔 요약 =====
    n = len(m)
    conf_cnt = m["확신도"].value_counts()
    unmatched = m[m["표준항목"] == "미분류"]
    lowconf = m[m["확신도"].isin(["추정"])]
    mismatch = m[m["성격점검"] == "⚠️불일치"]

    print("=" * 64)
    print("FR-10 계정과목 자동 분류 (감사기준서 315)")
    print("=" * 64)
    print(f"대상 계정: {n}개")
    print("확신도 분포:", " / ".join(f"{k} {v}" for k, v in conf_cnt.items()))
    print("-" * 64)
    print("표준항목별 계정 수:")
    for item, cnt in m["표준항목"].value_counts().items():
        print(f"  {item:12s} {cnt:>3}개")
    print("-" * 64)
    print("[4층] 회계 항등식 검산  (자산순 = 부채+자본+당기순이익)")
    print(f"  자산순 {asset/EOK:>10,.1f}억  =  부채 {liab/EOK:,.1f}억 + "
          f"자본 {equity/EOK:,.1f}억 + 당기순이익 {ni/EOK:,.1f}억 + 잔차 {resid/EOK:,.1f}억")
    print(f"  · 미분류 net(분류 품질): {unclass/EOK:,.2f}억  → "
          f"{'✅ 커버리지 정합' if ident_ok else '⚠️ 미분류 점검 필요'}")
    print(f"  · 시산표 자체 대차차이(원장 기초 특성, 분류 무관): {tb_diff/EOK:,.2f}억")
    if len(unmatched):
        print("-" * 64)
        print(f"⚠️ 미분류 {len(unmatched)}개 (검토 필요):",
              ", ".join(unmatched["계정명"].head(15)))
    if len(mismatch):
        print(f"⚠️ 성격 불일치 {len(mismatch)}개:",
              ", ".join(mismatch["계정명"].head(10)))

    # ===== 리포트 =====
    md = ["# FR-10 계정과목 자동 분류 결과 (감사기준서 315)\n",
          f"- 대상 계정: **{n}개**",
          "- 확신도: " + " / ".join(f"{k} {v}" for k, v in conf_cnt.items()),
          f"- 회계 항등식 검산: 자산순 {asset/EOK:,.1f}억 = 부채 {liab/EOK:,.1f}억 + "
          f"자본 {equity/EOK:,.1f}억 + 당기순이익 {ni/EOK:,.1f}억 + 잔차 {resid/EOK:,.1f}억",
          f"- 미분류 net(분류 품질): {unclass/EOK:,.2f}억 "
          f"({'✅ 커버리지 정합' if ident_ok else '⚠️ 점검 필요'}) · "
          f"시산표 자체 대차차이(원장 기초 특성): {tb_diff/EOK:,.2f}억\n",
          "## 표준항목별 분포\n", "| 표준항목 | 대분류 | 계정 수 | net(억) |", "|---|---|---:|---:|"]
    grp = (m.groupby(["표준항목", "대분류"], as_index=False)
           .agg(계정수=("계정명", "size"), net=("net", "sum")))
    for _, r in grp.sort_values("net", key=abs, ascending=False).iterrows():
        md.append(f"| {r['표준항목']} | {r['대분류']} | {r['계정수']} | {r['net']/EOK:,.1f} |")

    if len(unmatched) or len(lowconf) or len(mismatch):
        md += ["\n## ⚠️ 검토 필요 계정 (검토 화면에서 수정 권장)\n",
               "| 계정코드 | 계정명 | 자동분류 | 확신도 | 성격점검 |", "|---|---|---|---|---|"]
        for _, r in pd.concat([unmatched, lowconf, mismatch]).drop_duplicates("계정코드").iterrows():
            md.append(f"| {r['계정코드']} | {r['계정명']} | {r['표준항목']} | "
                      f"{r['확신도']} | {r['성격점검']} |")
    md += ["\n> 자동 분류는 초안입니다. `streamlit run src/fr10_review_app.py` 로 검토·수정하면 "
           "다음 실행부터 자동 반영됩니다(인적 최종통제, 감사기준서 200·240)."]
    (REP / "fr10_계정분류.md").write_text("\n".join(md), encoding="utf-8")

    print("-" * 64)
    print("저장:", BASE / "data" / "fr10_account_map.csv")
    print("저장:", REP / "fr10_계정분류.md")


if __name__ == "__main__":
    main()
