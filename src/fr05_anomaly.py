# -*- coding: utf-8 -*-
"""
FR-05 · 보조 이상탐지 (감사기준서 520 + 240 부정위험 보완)
------------------------------------------------------------
목적: FR-03/04의 '계정 × 월 밴드'가 놓치는 이상을 다른 각도로 잡는다.
        ① 벤포드 법칙   : 금액 '첫자리' 분포로 인위적 조작·반올림 신호 탐지
        ② Isolation Forest(PyOD): 여러 특성을 종합해 '분개 한 줄' 단위의 튀는 항목 탐지
      월별 집계로는 안 보이는, 개별 전표의 이상(주말·월말·라운드금액·희소계정 등)을 포착.

왜 필요한가:
  · 밴드(FR-03)는 '월 합계'가 정상 범위면 넘어간다. 그러나 그 안에 수상한
    개별 전표(딱 떨어지는 큰 금액, 주말 심야 대체분개 등)가 숨어 있을 수 있다.
  · 벤포드: 사람이 지어낸 숫자는 자연 발생 분포(첫자리 1이 30%)에서 벗어난다.

입력 : data/gl_clean.csv
출력 : data/fr05_benford.csv, data/fr05_anomalies.csv,
       reports/fr05_보조탐지.md, reports/17~19_*.png
"""

import os
import io
import contextlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import benford as bf
from pyod.models.iforest import IForest
from pathlib import Path

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
gl = pd.read_csv(BASE / "data" / "gl_clean.csv",
                 dtype={"계정코드": str}, parse_dates=["전표일자"])
REP = BASE / "reports"; REP.mkdir(exist_ok=True)
EOK = 100_000_000
DOW = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}


def title(t): print("\n" + "=" * 62 + f"\n■ {t}\n" + "=" * 62)


# ========== 1) 벤포드 법칙 (금액 첫자리 분포) ==========
title("1. 벤포드 법칙 — 금액 첫자리 자연스러움 검사")
amt = gl.loc[gl["차변"] > 0, "차변"].astype(float)
amt = amt[amt >= 10]                                   # 첫자리가 의미 있는 금액만

with contextlib.redirect_stdout(io.StringIO()):        # 라이브러리 자체 출력 억제
    f1 = bf.first_digits(amt, digs=1, decimals=0, confidence=95, show_plot=False)
    f2 = bf.first_digits(amt, digs=2, decimals=0, confidence=95, show_plot=False)

f1.to_csv(BASE / "data" / "fr05_benford.csv", encoding="utf-8-sig")


def mad_verdict(frame, digs):
    mad = (frame["Found"] - frame["Expected"]).abs().mean()
    if digs == 1:
        band = [(0.006, "매우 적합"), (0.012, "허용"), (0.015, "다소 벗어남"), (9, "부적합(조사 권장)")]
    else:
        band = [(0.0012, "매우 적합"), (0.0018, "허용"), (0.0022, "다소 벗어남"), (9, "부적합(조사 권장)")]
    v = next(lbl for th, lbl in band if mad < th)
    return mad, v


mad1, v1 = mad_verdict(f1, 1)
mad2, v2 = mad_verdict(f2, 2)
print(f"표본(차변>0) : {len(amt):,}건")
print(f"첫 1자리 MAD : {mad1:.4f}  → {v1}")
print(f"첫 2자리 MAD : {mad2:.4f}  → {v2}")

sig1 = f1[f1["Z_score"] > 1.96].sort_values("Z_score", ascending=False)
print("\n[기대보다 유의하게 많은 첫자리 (Z>1.96)]")
d1 = sig1.copy()
d1["실제%"] = (d1["Found"] * 100).round(1)
d1["기대%"] = (d1["Expected"] * 100).round(1)
d1["Z"] = d1["Z_score"].round(1)
print(d1[["Counts", "실제%", "기대%", "Z"]].to_string())

sig2 = f2[f2["Z_score"] > 1.96].sort_values("Z_score", ascending=False).head(8)
print("\n[첫 2자리 급증 Top (특정 금액대 반올림 신호)]")
d2 = sig2.copy(); d2["실제%"] = (d2["Found"] * 100).round(2); d2["기대%"] = (d2["Expected"] * 100).round(2)
d2["Z"] = d2["Z_score"].round(1)
print(d2[["Counts", "실제%", "기대%", "Z"]].to_string())


# ========== 2) Isolation Forest (분개 한 줄 단위 종합 이상) ==========
title("2. Isolation Forest — 개별 분개의 종합 이상치 탐지")
df = gl.copy()
df["금액"] = (df["차변"] - df["대변"]).abs()
ai = df["금액"].round().astype("int64")

# 특성 만들기
tz = np.zeros(len(ai), int)                            # 끝자리 0의 개수(라운드 금액 정도)
m = ai > 0
for k in range(1, 10):
    tz[m & (ai % (10 ** k) == 0)] = k
acct_cnt = df["계정코드"].map(df["계정코드"].value_counts())

feat = pd.DataFrame({
    "로그금액": np.log10(df["금액"] + 1),
    "라운드정도": tz,                                    # 끝 0 개수 ↑ = 딱 떨어지는 금액
    "주말": df["전표일자"].dt.dayofweek.isin([5, 6]).astype(int),
    "월말": (df["전표일자"].dt.day >= 28).astype(int),
    "음수": ((df["차변"] < 0) | (df["대변"] < 0)).astype(int),
    "희소계정": -np.log(acct_cnt),                       # 거래 드문 계정일수록 ↑
    "거래처없음": df["거래처명"].isna().astype(int),
})

clf = IForest(contamination=0.005, n_estimators=200, random_state=42)
clf.fit(feat.values)
df["이상점수"] = clf.decision_scores_                   # 높을수록 이상
df["이상"] = clf.labels_                                # 1 = 이상(상위 0.5%)
df["라운드정도"] = tz
df["요일"] = df["전표일자"].dt.dayofweek.map(DOW)

flagged = df[df["이상"] == 1].sort_values("이상점수", ascending=False).reset_index(drop=True)
flagged.insert(0, "순위", flagged.index + 1)

cols = ["순위", "전표일자", "요일", "계정명", "적요", "거래처명", "금액",
        "라운드정도", "이상점수"]
flagged[cols].to_csv(BASE / "data" / "fr05_anomalies.csv", index=False, encoding="utf-8-sig")

print(f"전체 {len(df):,}줄 중 이상 표시 {len(flagged):,}줄 (상위 0.5%)")
print("\n[Isolation Forest 이상 Top 15]")
show = flagged.head(15).copy()
show["금액(억)"] = (show["금액"] / EOK).round(2)
show["점수"] = show["이상점수"].round(3)
show["적요"] = show["적요"].astype(str).str[:24]
print(show[["순위", "전표일자", "요일", "계정명", "적요", "금액(억)", "라운드정도", "점수"]]
      .to_string(index=False))

# 이상군 vs 전체 특성 비교(왜 걸렸나 해석)
title("3. 이상으로 걸린 전표의 특징 (전체 대비)")
comp = pd.DataFrame({
    "전체": [df["금액"].median() / EOK, df["전표일자"].dt.dayofweek.isin([5, 6]).mean() * 100,
            (df["전표일자"].dt.day >= 28).mean() * 100, (tz >= 6).mean() * 100],
    "이상군": [flagged["금액"].median() / EOK,
             flagged["전표일자"].dt.dayofweek.isin([5, 6]).mean() * 100,
             (flagged["전표일자"].dt.day >= 28).mean() * 100,
             (flagged["라운드정도"] >= 6).mean() * 100],
}, index=["금액 중앙값(억)", "주말 비중(%)", "월말 비중(%)", "백만단위 딱떨어짐(%)"]).round(2)
print(comp.to_string())


# ========== 4) 그래프 ==========
# 17) 벤포드 1자리
fig, ax = plt.subplots(figsize=(8, 4))
digs = f1.index.astype(int)
ax.bar(digs, f1["Found"] * 100, color="#4c72b0", label="실제")
ax.plot(digs, f1["Expected"] * 100, color="#c44e52", marker="o", label="벤포드 기대")
ax.set_xticks(digs); ax.set_title(f"벤포드 첫자리 분포 (MAD={mad1:.4f}, {v1})")
ax.set_xlabel("첫자리"); ax.set_ylabel("%"); ax.legend(); ax.grid(alpha=.3, axis="y")
plt.tight_layout(); plt.savefig(REP / "17_벤포드_1자리.png", dpi=110); plt.close()

# 18) 벤포드 2자리
fig, ax = plt.subplots(figsize=(11, 4))
d = f2.index.astype(int)
ax.bar(d, f2["Found"] * 100, color="#4c72b0", width=.8, label="실제")
ax.plot(d, f2["Expected"] * 100, color="#c44e52", lw=1, label="벤포드 기대")
ax.set_title(f"벤포드 첫 2자리 분포 (MAD={mad2:.4f}, {v2})")
ax.set_xlabel("첫 2자리(10~99)"); ax.set_ylabel("%"); ax.legend(); ax.grid(alpha=.3, axis="y")
plt.tight_layout(); plt.savefig(REP / "18_벤포드_2자리.png", dpi=110); plt.close()

# 19) 이상점수 분포
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(df["이상점수"], bins=60, color="#9ecae1", edgecolor="w")
thr = df.loc[df["이상"] == 1, "이상점수"].min()
ax.axvline(thr, color="#c44e52", ls="--", label=f"이상 임계(상위 0.5%)")
ax.set_title("Isolation Forest 이상점수 분포"); ax.set_xlabel("이상점수"); ax.set_ylabel("전표 수")
ax.legend(); ax.grid(alpha=.3, axis="y")
plt.tight_layout(); plt.savefig(REP / "19_이상점수분포.png", dpi=110); plt.close()


# ========== 5) 마크다운 리포트 ==========
md = ["# FR-05 보조 이상탐지 결과\n",
      "## ① 벤포드 법칙 (금액 첫자리)",
      f"- 표본: {len(amt):,}건 (차변>0)",
      f"- 첫 1자리 MAD = {mad1:.4f} → **{v1}**",
      f"- 첫 2자리 MAD = {mad2:.4f} → **{v2}**",
      f"- 기대보다 많은 첫자리(Z>1.96): {', '.join(str(i) for i in sig1.index.astype(int))}",
      "\n## ② Isolation Forest (분개 단위 종합 이상)",
      f"- 전체 {len(df):,}줄 중 이상 표시 **{len(flagged):,}줄**(상위 0.5%)",
      "\n### 이상 Top 15\n",
      show[["순위", "전표일자", "요일", "계정명", "적요", "금액(억)", "라운드정도", "점수"]].to_markdown(index=False),
      "\n### 이상군 특징(전체 대비)\n",
      comp.to_markdown()]
(REP / "fr05_보조탐지.md").write_text("\n".join(md), encoding="utf-8")

print("\n" + "-" * 62)
print("저장:", BASE / "data" / "fr05_benford.csv")
print("저장:", BASE / "data" / "fr05_anomalies.csv")
print("저장:", REP / "fr05_보조탐지.md")
print("그래프: 17_벤포드_1자리.png, 18_벤포드_2자리.png, 19_이상점수분포.png")
