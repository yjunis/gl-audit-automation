# -*- coding: utf-8 -*-
"""
FR-01 (실데이터 버전) · 분개장 로더 & 표준화기
------------------------------------------------------------
목적: 실제 회계시스템(더존 계열)에서 뽑은 분개장 엑셀을
      그대로 읽어 '표준 GL 형태'로 정리한다. (가상 생성 X)

입력 : data/분개장_FY2025.4Q_20260204.xlsx  (Sheet1 + Sheet2)
출력 : data/gl_clean.csv  (이후 모든 단계가 읽는 표준 원장)

원본 8개 열 구조:
  0 전표일자 | 1 전표번호 | 2 차변금액 | 3 차변계정 |
  4 대변계정 | 5 대변금액 | 6 작성일자 | 7 작성번호
  - 한 줄 = 차변 한 줄 또는 대변 한 줄 (둘 중 하나만 채워짐)
  - 계정 형식: "[1030001] 보통예금"
  - 전표번호는 '하루 단위'로 1,2,3… 다시 시작 → (일자+번호)로 전표키 생성
"""

import re
import pandas as pd
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "data" / "분개장_FY2025.4Q_20260204.xlsx"
OUT = Path(__file__).resolve().parent.parent / "data" / "gl_clean.csv"

COLS = ["일자", "번호", "차변금액", "차변계정", "대변계정", "대변금액", "작성일자", "작성번호"]


def load_sheet(sheet):
    """시트 하나를 읽어 '날짜로 시작하는 데이터 줄'만 남긴다(머리글·합계행 제거)."""
    df = pd.read_excel(SRC, sheet_name=sheet, header=None)
    df = df.iloc[:, :8].copy()              # 앞 8개 열만 사용(뒤 빈 열 버림)
    df.columns = COLS
    is_data = df["일자"].astype(str).str.match(r"\d{4}/\d{2}/\d{2}")  # 날짜 행만
    return df[is_data].copy()


# 1) 두 시트를 읽어 이어붙임(= 2025년 전체)
raw = pd.concat([load_sheet("Sheet1"), load_sheet("Sheet2")], ignore_index=True)

# 2) 차변 줄/대변 줄 구분 (차변계정이 있으면 차변 줄)
is_debit = raw["차변계정"].notna()

amt_d = pd.to_numeric(raw["차변금액"], errors="coerce").fillna(0)
amt_c = pd.to_numeric(raw["대변금액"], errors="coerce").fillna(0)

# 3) 계정과목 "[코드] 이름" → 코드/이름 분리
acct = raw["차변계정"].where(is_debit, raw["대변계정"]).astype(str)
ext = acct.str.extract(r"\[(\w+)\]\s*(.*)")

# 4) 표준 원장 만들기
gl = pd.DataFrame({
    "전표일자": pd.to_datetime(raw["일자"], format="%Y/%m/%d"),
    "전표번호": pd.to_numeric(raw["번호"], errors="coerce").astype("Int64"),
    "계정코드": ext[0],
    "계정명": ext[1].str.strip(),
    "차변": amt_d.where(is_debit, 0),
    "대변": amt_c.where(~is_debit, 0),
})

# 5) 전표키(=날짜+번호): 전표번호가 하루 단위로 재시작하므로 합쳐서 고유 키 생성
gl.insert(0, "전표키",
          gl["전표일자"].dt.strftime("%Y%m%d") + "-" + gl["전표번호"].astype(str))
gl["전표월"] = gl["전표일자"].dt.to_period("M").astype(str)

# 6) 저장
gl.to_csv(OUT, index=False, encoding="utf-8-sig")

# 7) 요약 출력
deb, cre = gl["차변"].sum(), gl["대변"].sum()
print("=" * 60)
print("FR-01 (실데이터) 분개장 로드 완료")
print("=" * 60)
print(f"원본 파일      : {SRC.name}")
print(f"표준 줄 수     : {len(gl):,} 줄")
print(f"기간           : {gl['전표일자'].min().date()} ~ {gl['전표일자'].max().date()}")
print(f"전표 건수      : {gl['전표키'].nunique():,} 건")
print(f"계정 종류      : {gl['계정명'].nunique():,} 개")
print(f"차변 합계      : {deb:,.0f} 원")
print(f"대변 합계      : {cre:,.0f} 원")
print(f"대차평형 일치  : {round(deb) == round(cre)}  (차이 {deb-cre:,.0f})")
print("-" * 60)
print("월별 분개 줄 수:")
print(gl["전표월"].value_counts().sort_index().to_string())
print("-" * 60)
print("자주 쓰인 계정 Top 10 (줄 수):")
print(gl["계정명"].value_counts().head(10).to_string())
print("-" * 60)
print(f"저장: {OUT}")
