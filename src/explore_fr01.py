# -*- coding: utf-8 -*-
"""만든 가상 GL 데이터를 단계별로 들여다보는 탐색 스크립트."""
import pandas as pd
from pathlib import Path

pd.set_option("display.unicode.east_asian_width", True)  # 한글 정렬 맞춤
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

D = Path(__file__).resolve().parent.parent / "data"
gl = pd.read_csv(D / "gl_data.csv")
truth = pd.read_csv(D / "gl_truth.csv")

gl["전표일자"] = pd.to_datetime(gl["전표일자"])
gl["월"] = gl["전표일자"].dt.to_period("M").astype(str)


def title(t):
    print("\n" + "=" * 60 + f"\n■ {t}\n" + "=" * 60)


# 1) 원장 맨 위 모습
title("1. 원장(gl_data.csv) 맨 앞 6줄")
print(gl.head(6).to_string(index=False))

# 2) 거래 1건 = 차변 1줄 + 대변 1줄 (이중분개) 확인
title("2. 전표 1건이 '차변/대변 2줄'로 들어간 모습")
one = gl[gl["전표번호"] == gl["전표번호"].iloc[0]]
print(one[["전표번호", "전표일자", "계정명", "차변", "대변", "적요"]].to_string(index=False))
print("→ 한 거래에서 차변 금액 = 대변 금액 (회계의 기본: 이중분개)")

# 3) 계정별로 데이터가 얼마나 있나
title("3. 계정명별 줄 수")
print(gl["계정명"].value_counts().to_string())

# 4) 매출 vs 매출원가 월별 비교 (가공매출이 어떻게 티가 나는지)
title("4. 월별 매출 vs 매출원가, 그리고 원가율(원가/매출)")
pivot = (gl.groupby(["월", "계정명"])["대변"].sum().add(
         gl.groupby(["월", "계정명"])["차변"].sum(), fill_value=0))
sales = gl[gl["계정명"] == "매출"].groupby("월")["대변"].sum()
cogs = gl[gl["계정명"] == "매출원가"].groupby("월")["차변"].sum()
comp = pd.DataFrame({"매출": sales, "매출원가": cogs})
comp["원가율%"] = (comp["매출원가"] / comp["매출"] * 100).round(1)
print(comp.to_string())
print("→ 평소 원가율은 약 62% 부근. '가공매출'을 심은 달은 매출만 늘어 원가율이 뚝 떨어짐(이상 신호).")

# 5) 정답지에서 가공매출 전표 실제 모습
title("5. '가공매출'로 심은 전표 실제 내용")
fake_vouchers = truth[truth["이상유형"] == "가공매출"]
print(fake_vouchers.to_string(index=False))

# 6) 단가조작(반올림) — 금액이 '딱 떨어지는지'
title("6. '단가조작'으로 심은 매출 금액 (천만원 단위로 딱 떨어짐)")
round_v = truth[truth["이상유형"] == "단가조작"][["계정명", "차변"]].head(8)
print(round_v.to_string(index=False))

# 7) 정답지 요약
title("7. 정답지(gl_truth.csv) 요약 — 도구가 맞혀야 할 목록")
print(truth["이상유형"].value_counts().to_string())
print(f"\n총 이상 표시 줄 수: {len(truth)}")
