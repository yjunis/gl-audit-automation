# -*- coding: utf-8 -*-
"""
FR-01 · 가상 GL(총계정원장) 데이터 생성기
------------------------------------------------------------
목적: 실제 기밀 데이터 없이 도구를 시연·검증하기 위해,
      '정상 패턴' + '의도적으로 심은 이상값 4종'을 포함한
      가상 총계정원장을 만든다.

설계(기획안/RFP FR-01 준수):
  - 숫자/패턴은 numpy, 텍스트/식별필드(거래처·적요)는 Faker(ko_KR)
  - 난수 시드 고정 → 매번 똑같은 데이터가 나옴(재현성)
  - 이중분개(차변=대변) 구조 → 나중에 FR-02 대차평형 검증이 가능
  - 출력 2개:
      data/gl_data.csv   : '도구가 보게 될' 원장 (정답 라벨 없음)
      data/gl_truth.csv  : '정답지' (어떤 전표가 어떤 이상인지)
"""

import numpy as np
import pandas as pd
from faker import Faker
from pathlib import Path

# ========== 0. 기본 설정 ==========
SEED = 42                       # 난수 시드(고정) → 재현성
N_MONTHS = 24                   # 24개월(2년치) 생성
START = "2024-01"               # 시작 월
SALES_BASE = 300_000_000        # 월 매출 기준 규모(3억)

rng = np.random.default_rng(SEED)   # numpy 난수 발생기
fake = Faker("ko_KR")               # 한국어 가짜 데이터
Faker.seed(SEED)

OUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

months = pd.period_range(START, periods=N_MONTHS, freq="M")

# 이상값을 심을 위치(월 인덱스: 0=첫 달)
M_DEFER_LOW = 18                # 광고선전비를 비정상적으로 줄인 달(기간귀속 오류)
M_DEFER_HIGH = 19               # 다음 달에 몰아서 터뜨린 달
M_FICTITIOUS = 21              # 가공매출을 끼워넣을 달
M_MISCLASS = 14                # 계정 분류 오류가 발생한 달
M_ROUND = 9                    # 단가 조작(반올림 흔적)이 나타난 달


# ========== 1. 정상 월별 목표 금액 만들기 ==========
def monthly_factor(t, period, trend, season):
    """t개월 후의 (추세 × 계절성 × 노이즈) 배수를 계산."""
    f_trend = (1 + trend) ** t
    f_season = 1 + season * np.sin(2 * np.pi * (period.month - 1) / 12)
    f_noise = 1 + rng.normal(0, 0.06)
    return f_trend * f_season * max(f_noise, 0.5)


# 매출 월별 총액(먼저 계산: 매출원가가 여기에 연동되기 때문)
sales_total = {
    m: SALES_BASE * monthly_factor(t, m, trend=0.004, season=0.20)
    for t, m in enumerate(months)
}

# 계정(거래) 템플릿: 차변계정 / 대변계정 / 규모 / 추세 / 계절성 / 건수 / 적요후보
TEMPLATES = [
    dict(key="매출",      dr=("11500", "매출채권"),  cr=("41000", "매출"),
         base="SALES", trend=0.004, season=0.20, n_tx=8,
         desc=["제품 매출", "상품 판매", "용역 제공 매출"]),
    dict(key="매출원가",  dr=("51000", "매출원가"),  cr=("14600", "재고자산"),
         base="COGS", ratio=0.62, trend=0.0, season=0.0, n_tx=8,
         desc=["매출원가 대체", "제품 출고", "재고 대체"]),
    dict(key="급여",      dr=("52000", "급여"),      cr=("10100", "현금"),
         base=80_000_000, trend=0.003, season=0.02, n_tx=3,
         desc=["임직원 급여 지급", "급여 이체"]),
    dict(key="임차료",    dr=("52300", "임차료"),    cr=("10100", "현금"),
         base=15_000_000, trend=0.0, season=0.0, n_tx=1,
         desc=["본사 임차료", "사무실 월세"]),
    dict(key="광고선전비", dr=("53100", "광고선전비"), cr=("10100", "현금"),
         base=20_000_000, trend=0.002, season=0.30, n_tx=4,
         desc=["온라인 광고비", "옥외광고 집행", "판촉물 제작"]),
    dict(key="지급수수료", dr=("53400", "지급수수료"), cr=("10100", "현금"),
         base=10_000_000, trend=0.001, season=0.05, n_tx=3,
         desc=["법률 자문료", "회계 자문료", "외주 용역비"]),
]

transactions = []   # 거래 단위로 모음(한 거래 = 나중에 차변/대변 2줄로 펼침)


def add_tx(period, tpl, total, n_tx, anomaly="정상", round_amounts=False):
    """월 총액(total)을 n_tx건으로 쪼개 거래로 추가."""
    if total <= 0 or n_tx <= 0:
        return
    props = rng.dirichlet(np.ones(n_tx) * 4)     # 건별 비중(고르게)
    for p in props:
        amt = p * total
        if round_amounts:
            amt = round(amt / 10_000_000) * 10_000_000   # 천만원 단위로 '딱 떨어지게'(이상 패턴)
            if amt <= 0:
                amt = 10_000_000
        else:
            amt = int(round(amt, -3))                     # 천원 단위 반올림(정상)
        if amt <= 0:
            continue
        day = int(rng.integers(1, 28))
        date = pd.Timestamp(f"{period}-{day:02d}")
        transactions.append(dict(
            date=date,
            dr_code=tpl["dr"][0], dr_name=tpl["dr"][1],
            cr_code=tpl["cr"][0], cr_name=tpl["cr"][1],
            amount=amt,
            counterparty=fake.company(),
            desc=rng.choice(tpl["desc"]),
            anomaly=anomaly,
        ))


# ========== 2. 정상 거래 생성(+ 기간귀속/단가조작은 생성 중에 주입) ==========
for t, m in enumerate(months):
    for tpl in TEMPLATES:
        # 월 목표액 결정
        if tpl["base"] == "SALES":
            total = sales_total[m]
        elif tpl["base"] == "COGS":
            total = sales_total[m] * tpl["ratio"] * (1 + rng.normal(0, 0.04))
        else:
            total = tpl["base"] * monthly_factor(t, m, tpl["trend"], tpl["season"])

        anomaly = "정상"
        round_amounts = False

        # (이상 2) 비용 이연/기간귀속 오류: 광고선전비를 한 달 죽였다가 다음 달 몰아줌
        if tpl["key"] == "광고선전비":
            if t == M_DEFER_LOW:
                total *= 0.15
                anomaly = "기간귀속오류"
            elif t == M_DEFER_HIGH:
                total *= 1.85
                anomaly = "기간귀속오류"

        # (이상 4) 단가 조작/반올림 흔적: 특정 달 매출을 '딱 떨어지는' 금액으로
        if tpl["key"] == "매출" and t == M_ROUND:
            round_amounts = True
            anomaly = "단가조작"

        add_tx(m, tpl, total, tpl["n_tx"], anomaly=anomaly, round_amounts=round_amounts)


# ========== 3. 더하기로 끼워넣는 이상값(가공매출 / 계정분류오류) ==========
sales_tpl = next(t for t in TEMPLATES if t["key"] == "매출")

# (이상 1) 가공매출: 기말에 매출만 추가(매출원가는 안 늘림) → 매출↔원가 관계 붕괴
add_tx(months[M_FICTITIOUS], sales_tpl, total=120_000_000, n_tx=3, anomaly="가공매출")

# (이상 3) 계정 분류 오류: 평소 거의 안 쓰는 '잡비'에 큰 금액 1건
transactions.append(dict(
    date=pd.Timestamp(f"{months[M_MISCLASS]}-15"),
    dr_code="53900", dr_name="잡비",
    cr_code="10100", cr_name="현금",
    amount=85_000_000,
    counterparty=fake.company(),
    desc="기타 비용 처리",
    anomaly="계정분류오류",
))


# ========== 4. 전표번호 부여 + 차변/대변 2줄로 펼치기 ==========
tx = pd.DataFrame(transactions).sort_values("date").reset_index(drop=True)
tx["voucher_no"] = ["V" + d.strftime("%Y%m") + f"{i:04d}"
                    for i, d in enumerate(tx["date"], start=1)]

rows = []
for _, r in tx.iterrows():
    common = dict(전표번호=r["voucher_no"], 전표일자=r["date"].date(),
                  거래처=r["counterparty"], 적요=r["desc"])
    # 차변 줄
    rows.append({**common, "계정코드": r["dr_code"], "계정명": r["dr_name"],
                 "차변": r["amount"], "대변": 0, "_anomaly": r["anomaly"]})
    # 대변 줄
    rows.append({**common, "계정코드": r["cr_code"], "계정명": r["cr_name"],
                 "차변": 0, "대변": r["amount"], "_anomaly": r["anomaly"]})

gl = pd.DataFrame(rows)


# ========== 5. 저장: 원장(라벨 제외) + 정답지(라벨) ==========
gl_data = gl.drop(columns=["_anomaly"])           # 도구가 보는 원장
gl_truth = (gl[gl["_anomaly"] != "정상"]
            [["전표번호", "계정명", "차변", "대변", "_anomaly"]]
            .rename(columns={"_anomaly": "이상유형"})
            .drop_duplicates())

gl_data.to_csv(OUT_DIR / "gl_data.csv", index=False, encoding="utf-8-sig")
gl_truth.to_csv(OUT_DIR / "gl_truth.csv", index=False, encoding="utf-8-sig")


# ========== 6. 요약 출력 ==========
print("=" * 55)
print("FR-01 가상 GL 생성 완료")
print("=" * 55)
print(f"기간            : {months[0]} ~ {months[-1]} ({N_MONTHS}개월)")
print(f"총 분개 줄 수   : {len(gl_data):,} 줄")
print(f"차변 합계       : {gl_data['차변'].sum():,} 원")
print(f"대변 합계       : {gl_data['대변'].sum():,} 원")
print(f"대차평형 일치   : {gl_data['차변'].sum() == gl_data['대변'].sum()}")
print("-" * 55)
print("심어 둔 이상값(정답지):")
print(gl_truth["이상유형"].value_counts().to_string())
print("-" * 55)
print(f"저장 위치: {OUT_DIR}")
print("  - gl_data.csv  (도구가 보는 원장)")
print("  - gl_truth.csv (정답지)")
