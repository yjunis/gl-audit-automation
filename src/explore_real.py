# -*- coding: utf-8 -*-
"""실제 분개장(gl_clean.csv)을 집계·시각화하며 같이 탐색."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)

BASE = Path(__file__).resolve().parent.parent
gl = pd.read_csv(BASE / "data" / "gl_clean.csv")
gl["전표일자"] = pd.to_datetime(gl["전표일자"])
REP = BASE / "reports"; REP.mkdir(exist_ok=True)

EOK = 100_000_000  # 1억


def title(t): print("\n" + "=" * 60 + f"\n■ {t}\n" + "=" * 60)


# 1) 계정별 발생액(차변+대변 합) Top 15
title("1. 계정별 발생액 Top 15 (단위: 억원)")
gl["발생액"] = gl["차변"] + gl["대변"]
top = (gl.groupby("계정명")["발생액"].sum().sort_values(ascending=False).head(15) / EOK).round(1)
print(top.to_string())

# 2) 월별 제품매출 추세 (매출은 대변에 기록)
title("2. 월별 제품매출 (대변 합, 억원)")
sales = gl[gl["계정명"] == "제품매출"].groupby(gl["전표일자"].dt.to_period("M"))["대변"].sum() / EOK
print(sales.round(1).to_string())

# 3) 월별 주요 비용 추세 (비용은 차변에 기록)
title("3. 월별 주요 비용 (차변 합, 억원)")
cost_accts = ["광고선전비", "지급수수료", "복리후생비"]
cost = (gl[gl["계정명"].isin(cost_accts)]
        .groupby([gl["전표일자"].dt.to_period("M"), "계정명"])["차변"].sum()
        .unstack(fill_value=0) / EOK).round(2)
print(cost.to_string())

# 4) 요일별 전표 건수 (주말 거래 = 감사 관심사)
title("4. 요일별 전표 건수")
dow_map = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
vouchers = gl.drop_duplicates("전표키").copy()
vouchers["요일"] = vouchers["전표일자"].dt.dayofweek
dow = vouchers["요일"].map(dow_map).value_counts().reindex(list(dow_map.values()))
print(dow.to_string())
wk = vouchers["요일"].isin([5, 6]).mean() * 100
print(f"→ 주말 전표 비중: {wk:.1f}%")

# 5) 전표 규모 (전표당 줄 수)
title("5. 전표당 줄 수 분포 + 큰 전표 Top 5")
lines_per = gl.groupby("전표키").size()
print(f"최소 {lines_per.min()} / 중앙값 {int(lines_per.median())} / 최대 {lines_per.max()} 줄")
big = gl.groupby("전표키")["차변"].sum().sort_values(ascending=False).head(5) / EOK
print("금액 큰 전표 Top 5 (차변합, 억원):"); print(big.round(1).to_string())

# 6) 벤포드 첫자리 미리보기 (차변>0 금액의 맨 앞 숫자)
title("6. 벤포드 법칙 미리보기 (차변 금액 첫자리 분포 %)")
amt = gl.loc[gl["차변"] > 0, "차변"].astype(float)
first = amt.astype(str).str.replace(".", "", regex=False).str.lstrip("0").str[0]
first = pd.to_numeric(first, errors="coerce").dropna().astype(int)
obs = first.value_counts(normalize=True).reindex(range(1, 10), fill_value=0) * 100
ben = pd.Series({d: np.log10(1 + 1 / d) * 100 for d in range(1, 10)})
cmp = pd.DataFrame({"실제%": obs.round(1), "벤포드이론%": ben.round(1)})
print(cmp.to_string())

# ===== 그래프 4장 저장 =====
# (a) 월별 제품매출
fig, ax = plt.subplots(figsize=(9, 4))
sales.index = sales.index.astype(str)
ax.plot(sales.index, sales.values, marker="o")
ax.set_title("월별 제품매출 추세 (억원)"); ax.set_ylabel("억원"); ax.grid(alpha=.3)
plt.xticks(rotation=45); plt.tight_layout(); plt.savefig(REP / "01_월별매출.png", dpi=110); plt.close()

# (b) 월별 주요 비용
fig, ax = plt.subplots(figsize=(9, 4))
for c in cost_accts:
    ax.plot(cost.index.astype(str), cost[c].values, marker="o", label=c)
ax.set_title("월별 주요 비용 추세 (억원)"); ax.set_ylabel("억원"); ax.legend(); ax.grid(alpha=.3)
plt.xticks(rotation=45); plt.tight_layout(); plt.savefig(REP / "02_월별비용.png", dpi=110); plt.close()

# (c) 요일별 전표 건수
fig, ax = plt.subplots(figsize=(7, 4))
colors = ["#4c72b0"] * 5 + ["#c44e52"] * 2
ax.bar(dow.index, dow.values, color=colors)
ax.set_title("요일별 전표 건수 (빨강=주말)"); ax.set_ylabel("건수"); ax.grid(alpha=.3, axis="y")
plt.tight_layout(); plt.savefig(REP / "03_요일별.png", dpi=110); plt.close()

# (d) 벤포드
fig, ax = plt.subplots(figsize=(7, 4))
ax.bar(cmp.index, cmp["실제%"], color="#4c72b0", label="실제")
ax.plot(cmp.index, cmp["벤포드이론%"], color="#c44e52", marker="o", label="벤포드 이론")
ax.set_title("벤포드 법칙: 금액 첫자리 분포"); ax.set_xlabel("첫자리"); ax.set_ylabel("%")
ax.legend(); ax.grid(alpha=.3, axis="y")
plt.tight_layout(); plt.savefig(REP / "04_벤포드.png", dpi=110); plt.close()

print("\n" + "-" * 60)
print(f"그래프 4장 저장: {REP}")
for f in ["01_월별매출.png", "02_월별비용.png", "03_요일별.png", "04_벤포드.png"]:
    print("  -", f)
