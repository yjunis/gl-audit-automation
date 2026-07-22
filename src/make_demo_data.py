# -*- coding: utf-8 -*-
"""
데모용 가상 계정별원장 생성기 (포트폴리오 공개용 · 합성데이터)
------------------------------------------------------------
목적: 실제 감사자료(비밀유지 대상)를 대신할 '가상제조(주)' 원장을 만든다.
      실무 원장에 가깝도록 계정을 세분화(약 45개: 판관비 세목·자산/부채 세분·내수/수출)
      하고 거래 밀도를 높인다(연 2,500~3,500줄). 단일표형 → adaptive_loader가 그대로 인식.
      2년치(전기 2024 / 당기 2025)를 각각 xlsx로 저장 → 업로드 시 YoY·M-Score까지 시연.

특징(의도적으로 심음):
  · 계절성: 분기 부가세 신고월(3·6·9·12)의 규칙적 스윙, 매출 성수기
  · 성장:   당기 매출이 전기 대비 약 +12%
  · 이상치: 당기 8월 급여 급증·11월 대형 매출·일회성 대형 수수료
  · 부정신호: 수기전표·소급입력·주말·라운드금액·모호적요·이상작성자
  · 대차평형: 모든 거래를 균형분개로 생성 → 차변합 = 대변합
  · 기초잔액: 전기이월을 '차·대변 0, 잔액에만' 반영 → 월 흐름 왜곡 없이 계정·잔액 유지

출력: demo_data/가상제조_GL_2024.xlsx , 가상제조_GL_2025.xlsx
"""
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "demo_data"
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(20260716)

# ── 계정: 코드 → (계정명, 자연차대) ── (3자리: 1·2·3=재무상태표 / 4·5·9=손익)
ACC = {
    # 유동자산
    "101": ("현금", "차변"), "102": ("보통예금", "차변"), "103": ("정기예금", "차변"),
    "108": ("외상매출금", "차변"), "109": ("받을어음", "차변"), "110": ("미수금", "차변"),
    "111": ("선급금", "차변"), "113": ("부가세대급금", "차변"),
    "146": ("원재료", "차변"), "147": ("제품", "차변"), "148": ("재공품", "차변"),
    "149": ("대손충당금", "대변"),
    # 비유동자산
    "201": ("토지", "차변"), "202": ("건물", "차변"), "203": ("기계장치", "차변"),
    "204": ("차량운반구", "차변"), "205": ("비품", "차변"), "206": ("소프트웨어", "차변"),
    "209": ("감가상각누계액", "대변"),
    # 부채
    "251": ("외상매입금", "대변"), "252": ("지급어음", "대변"), "253": ("미지급금", "대변"),
    "254": ("미지급비용", "대변"), "255": ("부가세예수금", "대변"), "256": ("예수금", "대변"),
    "257": ("선수금", "대변"), "261": ("단기차입금", "대변"), "262": ("장기차입금", "대변"),
    "265": ("퇴직급여충당부채", "대변"),
    # 자본
    "331": ("자본금", "대변"), "332": ("자본잉여금", "대변"), "375": ("이익잉여금", "대변"),
    # 수익
    "401": ("제품매출(내수)", "대변"), "402": ("제품매출(수출)", "대변"),
    # 매출원가
    "451": ("제품매출원가", "차변"),
    # 판매관리비
    "504": ("급여", "차변"), "505": ("상여금", "차변"), "506": ("퇴직급여", "차변"),
    "511": ("복리후생비", "차변"), "512": ("지급수수료", "차변"), "513": ("여비교통비", "차변"),
    "514": ("접대비", "차변"), "515": ("감가상각비", "차변"), "516": ("광고선전비", "차변"),
    "517": ("통신비", "차변"), "518": ("수도광열비", "차변"), "519": ("소모품비", "차변"),
    "520": ("임차료", "차변"), "521": ("보험료", "차변"), "522": ("세금과공과", "차변"),
    "523": ("운반비", "차변"), "524": ("수선비", "차변"), "525": ("교육훈련비", "차변"),
    "526": ("대손상각비", "차변"),
    # 영업외
    "901": ("이자수익", "대변"), "931": ("이자비용", "차변"), "932": ("외환차손", "차변"),
}

# ── 기초잔액(자연방향 양수, 억원) — 이익잉여금은 대차 플러그로 자동 계산 ──
OPEN0E = {
    "101": 3, "102": 60, "103": 30, "108": 55, "109": 20, "110": 5, "111": 8,
    "146": 25, "147": 20, "148": 10, "149": 3,
    "201": 80, "202": 100, "203": 90, "204": 15, "205": 8, "206": 12, "209": 60,
    "251": 35, "252": 15, "253": 12, "254": 5, "256": 3, "257": 6,
    "261": 40, "262": 80, "265": 20,
    "331": 150, "332": 30,
}


def opening_with_plug(ope):
    """기초잔액 dict(억) → 원 단위 + 이익잉여금 플러그(대차 균형)."""
    op = {c: v * 1e8 for c, v in ope.items()}
    debit = sum(v for c, v in op.items() if ACC[c][1] == "차변")
    credit = sum(v for c, v in op.items() if ACC[c][1] == "대변")
    op["375"] = debit - credit                 # 이익잉여금(대변) = 자산 - (부채+자본금+잉여금+차감)
    return op


# ── 거래처 풀 ──
CUST = ["대한상사", "한빛전자", "서울금속", "동방물산", "가온테크", "미래산업", "제일무역",
        "삼화정밀", "우성ENG", "코리아시스템", "대성물산", "신성기업"]
EXPORT = ["Nihon Trading", "Pacific Metals", "Orient Global", "Vertex Corp", "Andes SA"]
VEND = ["우진소재", "삼정부품", "대성화학", "신영테크", "광명기업", "동일금속",
        "태창산업", "유진케미칼", "명진철강", "성원산업"]
SVC = {"통신비": "케이티", "수도광열비": "한국전력", "임차료": "정우빌딩",
       "보험료": "삼성화재", "광고선전비": "제일기획", "운반비": "한진택배",
       "수선비": "동양설비", "교육훈련비": "한국능률협회", "여비교통비": "롯데관광",
       "접대비": "그랜드호텔", "소모품비": "오피스디포", "세금과공과": "성남시청",
       "지급수수료": "법무법인정도", "복리후생비": "웰스토리"}
BANK = "우리은행"
TAX = "세무서"
AUTH_MAIN = ["김회계", "이경리", "박전표", "최담당"]


SEASON = {1: .90, 2: .85, 3: 1.05, 4: 1.00, 5: 1.05, 6: 1.15,
          7: .95, 8: .80, 9: 1.10, 10: 1.05, 11: 1.20, 12: 1.25}


def month_days(y, m):
    return pd.Period(f"{y}-{m:02d}").days_in_month


def gen_year(year, opening, growth):
    """한 해 원장 생성. opening=기초잔액 dict(원). 반환: (DataFrame, 기말잔액 dict)."""
    bal = {c: 0.0 for c in ACC}
    rows = []
    doc = [0]

    def post(date, code, debit, credit, memo, cp, jtype, author, gap=0):
        nat = ACC[code][1]
        bal[code] += (debit - credit) if nat == "차변" else (credit - debit)
        inp = (date + pd.Timedelta(days=gap)).strftime("%Y-%m-%d")
        rows.append([date, f"{year}-{doc[0]:05d}", code, ACC[code][0], memo, cp,
                     jtype, author, inp, round(debit), round(credit), round(bal[code])])

    def d(y, m, day):
        return pd.Timestamp(y, m, min(day, month_days(y, m)))

    def au():
        return rng.choice(AUTH_MAIN)

    def M(mean, lo=.7, hi=1.3):
        """원 단위 비라운드 금액(mean 중심, 배수 변동) — 라운드금액 오탐 회피."""
        return int(mean * rng.uniform(lo, hi)) + int(rng.integers(11, 9_997))

    # ── 전기이월(기초잔액): 차·대변 0, 잔액에만 반영 ──
    doc[0] += 1
    dt0 = pd.Timestamp(year, 1, 1)
    for code, amt in opening.items():
        if amt == 0:
            continue
        bal[code] = amt
        post(dt0, code, 0, 0, "전기이월", "", "이월", "결산")

    base_sale = 33e8 * growth
    prev_wh = 2.0e8                    # 전월 원천징수 예수액(다음달 납부)

    for m in range(1, 13):
        seas = SEASON[m]
        pur_total = 0.0

        # ── 매출: 내수(부가세 O) ──
        for _ in range(int(rng.integers(9, 15))):
            a = M(base_sale * seas * 0.07)
            vat = int(round(a * .1))
            doc[0] += 1; dt = d(year, m, int(rng.integers(2, 27))); cp = rng.choice(CUST)
            post(dt, "108", a + vat, 0, f"제품매출 {cp}", cp, "매출전표", au())
            post(dt, "401", 0, a, f"제품매출 {cp}", cp, "매출전표", au())
            post(dt, "255", 0, vat, "부가세 예수", cp, "매출전표", au())
        # ── 매출: 수출(부가세 X) ──
        for _ in range(int(rng.integers(2, 5))):
            a = M(base_sale * seas * 0.06)
            doc[0] += 1; dt = d(year, m, int(rng.integers(2, 27))); cp = rng.choice(EXPORT)
            post(dt, "108", a, 0, f"수출매출 {cp}", cp, "매출전표", au())
            post(dt, "402", 0, a, f"수출매출 {cp}", cp, "매출전표", au())
        # ── 소매(현금영수증) ──
        for _ in range(int(rng.integers(1, 3))):
            a = M(base_sale * seas * 0.03); vat = int(round(a * .1))
            doc[0] += 1; dt = d(year, m, int(rng.integers(2, 27)))
            post(dt, "102", a + vat, 0, "현금매출", "", "입금전표", au())
            post(dt, "401", 0, a, "현금매출", "", "입금전표", au())
            post(dt, "255", 0, vat, "부가세 예수", "", "입금전표", au())

        # ── 매출채권 회수(보통예금/받을어음) ──
        for _ in range(int(rng.integers(7, 11))):
            c = M(base_sale * seas * 0.07); cp = rng.choice(CUST)
            doc[0] += 1; dt = d(year, m, int(rng.integers(3, 28)))
            if rng.random() < 0.25:
                post(dt, "109", c, 0, f"어음 수취 {cp}", cp, "대체전표", au())
            else:
                post(dt, "102", c, 0, f"매출대금 입금 {cp}", cp, "입금전표", au(), gap=1)
            post(dt, "108", 0, c, f"매출대금 회수 {cp}", cp, "입금전표", au(), gap=1)
        # 받을어음 만기 입금
        for _ in range(int(rng.integers(1, 3))):
            c = M(base_sale * seas * 0.04)
            doc[0] += 1; dt = d(year, m, int(rng.integers(5, 27)))
            post(dt, "102", c, 0, "어음 만기 입금", BANK, "입금전표", au())
            post(dt, "109", 0, c, "어음 만기 결제", BANK, "입금전표", au())

        # ── 원재료 매입(부가세 O) ──
        ap_added = 0.0                    # 이번 달 외상매입금 증가액(지급 연동용)
        for _ in range(int(rng.integers(7, 12))):
            p = M(base_sale * seas * 0.055); vin = int(round(p * .1))
            doc[0] += 1; dt = d(year, m, int(rng.integers(2, 26))); v = rng.choice(VEND)
            post(dt, "146", p, 0, f"원재료 매입 {v}", v, "매입전표", au())
            post(dt, "113", vin, 0, "부가세 대급", v, "매입전표", au())
            if rng.random() < 0.2:
                post(dt, "252", 0, p + vin, f"원재료 매입(어음) {v}", v, "매입전표", au())
            else:
                post(dt, "251", 0, p + vin, f"원재료 매입 {v}", v, "매입전표", au())
                ap_added += p + vin
            pur_total += p

        # ── 매출원가 인식(재고 안정: 매입액 근사) ──
        cogs_total = pur_total * rng.uniform(0.96, 1.06)
        for _ in range(int(rng.integers(2, 4))):
            cg = M(cogs_total / 3, .8, 1.2)
            doc[0] += 1; dt = d(year, m, int(rng.integers(24, 28)))
            post(dt, "451", cg, 0, "매출원가 대체", "", "대체전표", au(), gap=2)
            post(dt, "146", 0, cg, "매출원가 대체", "", "대체전표", au(), gap=2)

        # ── 매입대금 지급(이번 달 외상매입 증가분에 연동 → 외상매입금 잔액 안정) ──
        n_pay = int(rng.integers(6, 10))
        pay_total = ap_added * rng.uniform(0.90, 1.02)
        ws = rng.uniform(0.6, 1.4, n_pay); ws = ws / ws.sum()
        for k in range(n_pay):
            pay = int(pay_total * ws[k]) + int(rng.integers(11, 9_997)); v = rng.choice(VEND)
            doc[0] += 1; dt = d(year, m, int(rng.integers(5, 28)))
            post(dt, "251", pay, 0, f"매입대금 지급 {v}", v, "출금전표", au())
            post(dt, "102", 0, pay, f"매입대금 지급 {v}", v, "출금전표", au())
        # 지급어음 결제
        for _ in range(int(rng.integers(1, 3))):
            pay = M(base_sale * seas * 0.03)
            doc[0] += 1; dt = d(year, m, int(rng.integers(5, 27)))
            post(dt, "252", pay, 0, "지급어음 결제", BANK, "출금전표", au())
            post(dt, "102", 0, pay, "지급어음 결제", BANK, "출금전표", au())

        # ── 급여(원천징수 예수) ──
        gross = 8.5e8 * growth * rng.uniform(.98, 1.02)
        if year == 2025 and m == 8:
            gross *= 2.0                                # [이상] 당기 8월 급여 급증
        gross = M(gross, .99, 1.01)
        wh = int(round(gross * .09)); net = gross - wh
        doc[0] += 1; dt = d(year, m, 25)
        post(dt, "504", gross, 0, f"{m}월 급여", "", "급여전표", au())
        post(dt, "256", 0, wh, f"{m}월 급여 원천징수", "", "급여전표", au())
        post(dt, "102", 0, net, f"{m}월 급여 지급", "", "급여전표", au())
        # 전월 원천세 납부
        doc[0] += 1; dt = d(year, m, 10)
        post(dt, "256", prev_wh, 0, "원천세 납부", TAX, "출금전표", au())
        post(dt, "102", 0, prev_wh, "원천세 납부", TAX, "출금전표", au())
        prev_wh = wh
        # 상여금(6·12월)
        if m in (6, 12):
            bo = M(4.0e8 * growth)
            doc[0] += 1; dt = d(year, m, 20)
            post(dt, "505", bo, 0, f"{m}월 상여금", "", "급여전표", au())
            post(dt, "102", 0, bo, f"{m}월 상여금 지급", "", "급여전표", au())
        # 퇴직급여 설정
        doc[0] += 1; dt = d(year, m, 28)
        rb = M(0.45e8)
        post(dt, "506", rb, 0, "퇴직급여 설정", "", "결산전표", au(), gap=3)
        post(dt, "265", 0, rb, "퇴직급여충당부채 전입", "", "결산전표", au(), gap=3)

        # ── 판관비 세목 ──
        EXP = [("511", 0.25e8, True), ("513", 0.18e8, False), ("514", 0.22e8, False),
               ("516", 0.50e8, True), ("517", 0.12e8, True), ("518", 0.15e8, True),
               ("519", 0.14e8, True), ("520", 0.60e8, True), ("521", 0.20e8, False),
               ("522", 0.25e8, False), ("523", 0.30e8, True), ("524", 0.22e8, True),
               ("525", 0.12e8, False), ("512", 0.35e8, True)]
        for code, base, taxable in EXP:
            for _ in range(int(rng.integers(1, 3))):
                a = M(base)
                nm = ACC[code][0]; cp = SVC.get(nm, rng.choice(VEND))
                doc[0] += 1; dt = d(year, m, int(rng.integers(3, 27)))
                post(dt, code, a, 0, nm, cp, "경비전표", au(), gap=1)
                if taxable:
                    vv = int(round(a * .1))
                    post(dt, "113", vv, 0, "부가세 대급", cp, "경비전표", au(), gap=1)
                    tgt = "253" if rng.random() < 0.4 else "102"
                    post(dt, tgt, 0, a + vv, nm, cp, "경비전표", au(), gap=1)
                else:
                    tgt = "253" if rng.random() < 0.3 else "102"
                    post(dt, tgt, 0, a, nm, cp, "경비전표", au(), gap=1)

        # ── 감가상각(월) ──
        doc[0] += 1; dt = d(year, m, 28)
        dep = M(1.30e8, .98, 1.02)
        post(dt, "515", dep, 0, "감가상각비", "", "결산전표", au(), gap=3)
        post(dt, "209", 0, dep, "감가상각누계액", "", "결산전표", au(), gap=3)

        # ── 이자비용·이자수익 ──
        doc[0] += 1; dt = d(year, m, 15)
        it = M(0.50e8, .9, 1.1)
        post(dt, "931", it, 0, "차입금 이자", BANK, "출금전표", au())
        post(dt, "102", 0, it, "차입금 이자", BANK, "출금전표", au())
        doc[0] += 1; dt = d(year, m, 20)
        iv = M(0.10e8)
        post(dt, "102", iv, 0, "예금 이자", BANK, "입금전표", au())
        post(dt, "901", 0, iv, "예금이자 수익", BANK, "입금전표", au())

        # ── 미지급금 결제(전월 경비) ──
        if bal["253"] > 3e8:
            pay = M(bal["253"] * 0.5, .8, 1.0)
            doc[0] += 1; dt = d(year, m, int(rng.integers(8, 25)))
            post(dt, "253", pay, 0, "미지급금 지급", rng.choice(VEND), "출금전표", au())
            post(dt, "102", 0, pay, "미지급금 지급", "", "출금전표", au())

        # ── 분기 부가세 신고·납부(3·6·9·12) → 부가세 계정 규칙적 스윙(계절성) ──
        if m in (3, 6, 9, 12):
            vout = bal["255"]; vin = bal["113"]; netv = vout - vin
            doc[0] += 1; dt = d(year, m, 25)
            post(dt, "255", vout, 0, "부가세 예수 반제", TAX, "대체전표", au(), gap=1)
            post(dt, "113", 0, vin, "부가세 대급 반제", TAX, "대체전표", au(), gap=1)
            post(dt, "102", 0, netv, "부가세 납부", TAX, "출금전표", au(), gap=1)
            # 장기차입금 분기 상환
            rp = M(2.0e8)
            doc[0] += 1; dt = d(year, m, 28)
            post(dt, "262", rp, 0, "장기차입금 상환", BANK, "출금전표", au())
            post(dt, "102", 0, rp, "장기차입금 상환", BANK, "출금전표", au())

    # ── 연 1회 이벤트: 설비투자(7월, 현금취득·소규모) ──
    cap = M(2.5e8)
    doc[0] += 1; dt = d(year, 7, 12); v = rng.choice(VEND)
    post(dt, "205", cap, 0, "비품 취득", v, "대체전표", au())
    post(dt, "102", 0, cap, "비품 취득", v, "대체전표", au())
    # 대손충당금 보충(12월)
    doc[0] += 1; dt = d(year, 12, 28)
    bd = M(1.0e8)
    post(dt, "526", bd, 0, "대손충당금 설정", "", "결산전표", au(), gap=3)
    post(dt, "149", 0, bd, "대손충당금 전입", "", "결산전표", au(), gap=3)

    # ── [이상] 당기 이상치 (11월 대형매출·6월 원가급증) ──
    if year == 2025:
        # 11월 대형 매출(외상·부가세 동반) → 제품매출·외상매출금·부가세예수금 동반 이상
        doc[0] += 1; dt = d(year, 11, 18)
        big = M(45e8, .99, 1.01); bvat = int(round(big * .1))
        post(dt, "108", big + bvat, 0, "대형 수주 매출 미래산업", "미래산업", "매출전표", "김회계")
        post(dt, "401", 0, big, "대형 수주 매출 미래산업", "미래산업", "매출전표", "김회계")
        post(dt, "255", 0, bvat, "부가세 예수", "미래산업", "매출전표", "김회계")
        # 6월 매출원가 급증(마진 이상) — 제품 출고로 원가만 이례적 증가
        doc[0] += 1; dt = d(year, 6, 26)
        ex = M(13e8, .98, 1.02)
        post(dt, "451", ex, 0, "재고 대량 출고 원가", "", "대체전표", "이경리", gap=2)
        post(dt, "147", 0, ex, "재고 대량 출고 원가", "", "대체전표", "이경리", gap=2)
        # [부정신호] 일회성 대형 수수료 · 라운드금액 · 소급입력(20일) · 결산키워드 · 일반전표
        doc[0] += 1; dt = d(year, 9, 30)
        post(dt, "512", 300_000_000, 0, "컨설팅 대체", "가온테크", "일반전표", "박전표", gap=20)
        post(dt, "102", 0, 300_000_000, "컨설팅 대체", "가온테크", "일반전표", "박전표", gap=20)
        # [부정신호] 기말·주말·수기·라운드·모호적요·이상작성자
        doc[0] += 1; dt = pd.Timestamp(2025, 12, 27)      # 토요일
        post(dt, "512", 200_000_000, 0, "대체", "", "수기", "관리자B")
        post(dt, "102", 0, 200_000_000, "대체", "", "수기", "관리자B")

    cols = ["전표일자", "전표번호", "계정코드", "계정명", "적요", "거래처명",
            "전표유형", "작성자", "입력일", "차변", "대변", "잔액"]
    df = pd.DataFrame(rows, columns=cols).sort_values("전표일자").reset_index(drop=True)
    df["전표일자"] = pd.to_datetime(df["전표일자"]).dt.strftime("%Y/%m/%d")
    return df, dict(bal)


def carry_forward(end_bal):
    """B/S 계정(코드 1·2·3) 기말잔액 → 다음 해 기초. 손익(4·5·9) 리셋.
       이익잉여금은 '자산-(부채+자본금·잉여금)' 플러그로 두어 개시분개가 균형(전년 이익 누적)."""
    nxt = {c: end_bal.get(c, 0.0) for c in ACC if c[0] in ("1", "2", "3")}
    debit = sum(v for c, v in nxt.items() if ACC[c][1] == "차변")
    credit = sum(v for c, v in nxt.items() if ACC[c][1] == "대변" and c != "375")
    nxt["375"] = debit - credit
    return nxt


open24 = opening_with_plug(OPEN0E)
df24, end24 = gen_year(2024, open24, growth=1.0)
open25 = carry_forward(end24)
df25, _ = gen_year(2025, open25, growth=1.12)

for year, df in ((2024, df24), (2025, df25)):
    p = OUT / f"가상제조_GL_{year}.xlsx"
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="GL", index=False)
    bal = df["차변"].sum() - df["대변"].sum()
    print(f"{p.name}: {len(df):,}행 · 차변합 {df['차변'].sum()/1e8:,.1f}억 · "
          f"대차차이 {bal:,.0f} · 계정 {df['계정명'].nunique()}개 · "
          f"기간 {df['전표일자'].min()}~{df['전표일자'].max()}")
print("저장 위치:", OUT)
