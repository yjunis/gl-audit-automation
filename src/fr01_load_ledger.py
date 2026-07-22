# -*- coding: utf-8 -*-
"""
FR-01 (실데이터 버전 2) · 계정별원장 로더 & 표준화기
------------------------------------------------------------
목적: 계정별원장 엑셀(계정마다 시트 1개)을 읽어 '표준 GL'로 합친다.
      분개장과 달리 '적요(메모)·거래처명'이 있어 분석에 더 유리.

입력 : data/계정별원장_FY2025.4Q_20260204.xlsx  (계정별 시트 139개)
출력 : data/gl_clean.csv  (이후 모든 단계가 읽는 표준 원장)

각 시트 8개 열:
  0 날짜 | 1 적요 | 2 거래처코드 | 3 거래처명 |
  4 사업자번호 | 5 차변 | 6 대변 | 7 잔액
  - 계정코드/계정명은 시트 이름에서 추출 (예: '0_현금(1010000)')
  - [전기이월]/[월계]/[누계] 행은 날짜가 비어 있어 자동 제외
"""

import re
import pandas as pd
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "data" / "계정별원장_FY2025.4Q_20260204.xlsx"
OUT = Path(__file__).resolve().parent.parent / "data" / "gl_clean.csv"
TB_OUT = Path(__file__).resolve().parent.parent / "data" / "trial_balance.csv"

COLS = ["날짜", "적요", "거래처코드", "거래처명", "사업자번호", "차변", "대변", "잔액"]
CODE_RE = re.compile(r"\((\d{6,7})\)\s*$")   # 시트명 끝의 (계정코드)


def nospace(x):
    return re.sub(r"\s+", "", str(x))         # '[ 전 기 이 월 ]' → '[전기이월]'


xl = pd.ExcelFile(SRC)
frames, skipped, tb_rows = [], [], []

for s in xl.sheet_names:
    m = CODE_RE.search(s)
    if not m:                       # 'Sheet1' 등 계정시트가 아닌 것은 건너뜀
        skipped.append(s)
        continue
    code = m.group(1)
    name = re.sub(r"\(\d{6,7}\)\s*$", "", re.sub(r"^\d+_", "", s)).strip()

    raw = xl.parse(s, header=None).iloc[:, :8]
    raw.columns = COLS
    memo = raw["적요"].map(nospace)
    rawD = pd.to_numeric(raw["차변"], errors="coerce")
    rawC = pd.to_numeric(raw["대변"], errors="coerce")

    # --- 시산표(역산 대사)용 값: 기초잔액(전기이월) + 시스템 누계 ---
    op = memo.str.contains("전기이월")
    openD = float(rawD[op].fillna(0).iloc[0]) if op.any() else 0.0
    openC = float(rawC[op].fillna(0).iloc[0]) if op.any() else 0.0
    nj = memo.str.contains("누계")            # [누계] = 시스템이 찍어준 누적 차/대 합계
    sysD = float(rawD[nj].fillna(0).iloc[-1]) if nj.any() else float("nan")
    sysC = float(rawC[nj].fillna(0).iloc[-1]) if nj.any() else float("nan")

    df = raw[raw["날짜"].astype(str).str.match(r"\d{4}/\d{2}/\d{2}")].copy()  # 날짜행만

    tb_rows.append({
        "계정코드": code, "계정명": name,
        "기초차변": openD, "기초대변": openC,
        "거래건수": len(df),
        "시스템누계차변": sysD, "시스템누계대변": sysC,
    })
    if df.empty:                     # 거래 없는 계정(기초잔액만) → 상세는 없지만 시산표엔 남김
        continue

    frames.append(pd.DataFrame({
        "계정코드": code,
        "계정명": name,
        "전표일자": pd.to_datetime(df["날짜"], format="%Y/%m/%d"),
        "적요": df["적요"].astype(str).str.strip(),
        "거래처코드": df["거래처코드"],
        "거래처명": df["거래처명"],
        "차변": pd.to_numeric(df["차변"], errors="coerce").fillna(0),
        "대변": pd.to_numeric(df["대변"], errors="coerce").fillna(0),
        "잔액": pd.to_numeric(df["잔액"], errors="coerce"),
    }))

gl = pd.concat(frames, ignore_index=True).sort_values("전표일자").reset_index(drop=True)
gl["전표월"] = gl["전표일자"].dt.to_period("M").astype(str)
gl.to_csv(OUT, index=False, encoding="utf-8-sig")

# 시산표 저장 (FR-02 역산 대사 검증이 이 파일을 읽음)
tb = pd.DataFrame(tb_rows)
tb.to_csv(TB_OUT, index=False, encoding="utf-8-sig")

# ===== 요약 =====
deb, cre = gl["차변"].sum(), gl["대변"].sum()
print("=" * 62)
print("FR-01 (실데이터) 계정별원장 로드 완료")
print("=" * 62)
print(f"원본 파일      : {SRC.name}")
print(f"처리한 계정시트: {len(frames)} 개  (건너뜀: {skipped})")
print(f"표준 줄 수     : {len(gl):,} 줄")
print(f"기간           : {gl['전표일자'].min().date()} ~ {gl['전표일자'].max().date()}")
print(f"계정 종류      : {gl['계정명'].nunique()} 개")
print(f"거래처 종류    : {gl['거래처명'].notna().sum():,}줄에 거래처 있음 / 고유 {gl['거래처명'].nunique()}개")
print(f"적요 있는 줄   : {(gl['적요'].str.len() > 0).sum():,} 줄")
print(f"차변 합계      : {deb:,.0f} 원")
print(f"대변 합계      : {cre:,.0f} 원")
print(f"대차평형 일치  : {round(deb) == round(cre)}  (차이 {deb-cre:,.0f})")
print("-" * 62)
print("월별 줄 수:")
print(gl["전표월"].value_counts().sort_index().to_string())
print("-" * 62)
print("샘플 5줄 (적요·거래처 포함):")
print(gl[["전표일자", "계정명", "적요", "거래처명", "차변", "대변"]].head(5).to_string(index=False))
print("-" * 62)
print(f"시산표     : {len(tb)}개 계정  (거래있음 {int((tb['거래건수']>0).sum())} / 거래없음 {int((tb['거래건수']==0).sum())})")
print(f"저장: {OUT}")
print(f"저장: {TB_OUT}")
