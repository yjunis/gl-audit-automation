# -*- coding: utf-8 -*-
"""
FR-02 · 데이터 무결성 검증 (감사기준서 520.5(b) 대응)
------------------------------------------------------------
목적: 기대치/이상탐지 이전에, 입력 원장이 '믿을 만한지'부터 검사한다.
      문제를 등급화한다 →  ❌실패(ERROR, 분석 신뢰성 훼손) / ⚠️경고(WARNING, 확인 필요)

방법:
  - Pandera 스키마로 '열 단위 규칙'(타입·형식·결측) 검사
  - 추가 업무규칙(대차평형·계정코드 일관성·차대 단면 등)을 직접 검사
입력 : data/gl_clean.csv
출력 : 콘솔 요약 + reports/fr02_검증결과.md
"""

import json
import os
import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Column, Check, DataFrameSchema
from pathlib import Path

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
gl = pd.read_csv(BASE / "data" / "gl_clean.csv",
                 dtype={"계정코드": str, "거래처코드": str},
                 parse_dates=["전표일자"])
REP = BASE / "reports"; REP.mkdir(exist_ok=True)

results = []   # (등급, 항목, 결과, 건수, 설명)


def record(level, name, ok, n, desc):
    results.append(dict(등급=level, 항목=name,
                        결과=("통과" if ok else ("경고" if level == "WARNING" else "실패")),
                        건수=n, 설명=desc))


# ========== 1) 회계기간 확정 → Pandera 스키마 검사 ==========
# [설계 원칙] 회계기간은 '검증 대상인 거래일'과 독립된 근거에서만 받는다.
#   거래일로 기간을 추론해 그 거래일을 검증하면 데이터가 스스로를 정당화하는
#   자기참조가 되어(예: 원장 전체가 1년 밀려도 100% 일치로 통과) 어떤 임계값을
#   덧붙여도 막을 수 없다. 그래서 추론은 '제안값'으로만 쓰고 기준으로는 쓰지 않는다.
#
#   근거 우선순위: 환경변수 → 설정 파일 → 파일 메타데이터
#     ① GL_FY_START·GL_FY_END   (사용자 지정, 비달력 회계연도)
#     ② GL_FY_YEAR              (사용자 지정, 달력연도)
#     ③ <BASE>/fiscal_period.json           (설정 파일)
#     ④ <BASE>/data/ledger_meta.json        (로더가 파일명에서 추출한 메타데이터)
#   하나도 없으면 자동 통과시키지 않고 analysis hold(분석 보류)로 처리한다.


def _year_range(y, src):
    y = int(y)
    return pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31), src


def _period_from_env():
    s, e = os.environ.get("GL_FY_START"), os.environ.get("GL_FY_END")
    if s and e:
        return pd.Timestamp(s), pd.Timestamp(e), "환경변수 GL_FY_START/END"
    y = os.environ.get("GL_FY_YEAR")
    if y and str(y).strip().isdigit():
        return _year_range(y, f"환경변수 GL_FY_YEAR({int(y)})")
    return None


def _period_from_json(path, label):
    if not path.exists():
        return None
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if m.get("fy_start") and m.get("fy_end"):
        return pd.Timestamp(m["fy_start"]), pd.Timestamp(m["fy_end"]), f"{label}(회계기간)"
    if m.get("fy_year"):
        return _year_range(m["fy_year"], f"{label} 회계연도({int(m['fy_year'])})")
    return None


def resolve_fiscal_period(base):
    """독립 근거에서만 회계기간을 확정한다. 거래일 데이터는 참조하지 않는다."""
    base = Path(base)
    for src in (lambda: _period_from_env(),
                lambda: _period_from_json(base / "fiscal_period.json", "설정 파일"),
                lambda: _period_from_json(base / "data" / "ledger_meta.json", "로더 메타데이터")):
        got = src()
        if got and got[0] <= got[1]:
            return got
    return None


def suggest_fiscal_period(dates):
    """거래일 분포로 추정한 '제안값'. 검증 기준이 아니라 사용자 안내용이다.
       거래가 가장 몰린 12개월 창을 돌려준다."""
    d = pd.to_datetime(dates, errors="coerce").dropna()
    if d.empty:
        return None
    counts = d.dt.to_period("M").value_counts().sort_index()
    best = None
    for st in counts.index:
        win = counts[(counts.index >= st) & (counts.index < st + 12)]
        key = (int(win.sum()), int(counts[st]))
        if best is None or key > best[0]:
            best = (key, st)
    (total, _), st = best
    return st.to_timestamp(), (st + 12).to_timestamp() - pd.Timedelta(days=1), total / len(d)


period = resolve_fiscal_period(BASE)
if period is not None:
    dmin, dmax, fy_src = period
    record("ERROR", "회계기간 확정", True, 0,
           f"{dmin:%Y-%m-%d}~{dmax:%Y-%m-%d} · 근거: {fy_src}")
    date_checks = [Check.in_range(dmin, dmax)]
else:
    sug = suggest_fiscal_period(gl["전표일자"])
    hint = (f" 참고(거래 분포 제안값): {sug[0]:%Y-%m-%d}~{sug[1]:%Y-%m-%d} ({sug[2]:.0%} 집중)"
            if sug else "")
    record("ERROR", "회계기간 확정", False, 0,
           "독립 근거 없음(GL_FY_START/END·GL_FY_YEAR·fiscal_period.json·ledger_meta.json) "
           f"→ 날짜 범위 검증 보류(analysis hold).{hint}")
    date_checks = []

schema = DataFrameSchema(
    {
        "계정코드": Column(str, Check.str_matches(r"^\d{3,12}$"), nullable=False),  # 3자리 표준코드(108·504 등)~회사별 다자리
        "계정명":  Column(str, nullable=False),
        "전표일자": Column("datetime64[ns]", date_checks, nullable=False),
        "차변":   Column(float, nullable=False),
        "대변":   Column(float, nullable=False),
    },
    strict=False, coerce=True,
)
try:
    schema.validate(gl, lazy=True)   # lazy=모든 위반을 한 번에 모음
    record("ERROR", "스키마(타입·형식·결측·날짜범위)", True, 0,
           "계정코드 형식, 날짜 범위, 필수값 등 열 단위 규칙 모두 통과")
except pa.errors.SchemaErrors as e:
    fc = e.failure_cases
    record("ERROR", "스키마(타입·형식·결측·날짜범위)", False, len(fc),
           "위반 예: " + "; ".join(
               fc.groupby("check").size().head(5)
                 .reset_index().astype(str).agg(" ".join, axis=1)))

# ========== 2) 대차평형 (전체) — 핵심 ==========
deb, cre = gl["차변"].sum(), gl["대변"].sum()
diff = round(deb - cre)
record("ERROR", "대차평형(차변합=대변합)", diff == 0, abs(diff),
       f"차변 {deb:,.0f} / 대변 {cre:,.0f} / 차이 {diff:,.0f}원")

# ========== 3) 계정코드 ↔ 계정명 1:1 일관성 ==========
dup = gl.groupby("계정코드")["계정명"].nunique()
bad = dup[dup > 1]
record("ERROR", "계정코드-계정명 일관성", bad.empty, len(bad),
       "한 코드에 여러 계정명 없음" if bad.empty
       else f"불일치 코드: {list(bad.index)[:5]}")

# ========== 4) 차/대 단면성 (한 줄은 차변 또는 대변 한쪽만) ==========
both = ((gl["차변"] != 0) & (gl["대변"] != 0)).sum()
record("WARNING", "차변·대변 동시기재 줄", both == 0, int(both),
       "정상: 각 줄은 한쪽만 기재" if both == 0 else f"양쪽 모두 값 있는 줄 {both}건(확인 필요)")

# ========== 5) 금액 0 줄 (차변=0 & 대변=0) ==========
zero = ((gl["차변"] == 0) & (gl["대변"] == 0)).sum()
record("WARNING", "금액 0원 줄", zero == 0, int(zero),
       "없음" if zero == 0 else f"차/대 모두 0원인 줄 {zero}건(대체·메모성 가능)")

# ========== 6) 음수 금액 (역분개·취소 가능) ==========
neg = ((gl["차변"] < 0) | (gl["대변"] < 0)).sum()
record("WARNING", "음수 금액 줄", neg == 0, int(neg),
       "없음" if neg == 0 else f"음수 금액 {neg}건 — 역분개/취소로 추정(정상일 수 있음, 확인 권장)")

# ========== 7) 적요 결측 ==========
emptied = gl["적요"].fillna("").astype(str).str.strip()
empty_n = (emptied == "").sum()
record("WARNING", "적요 결측", empty_n == 0, int(empty_n),
       "모든 줄에 적요 있음" if empty_n == 0 else f"적요 없는 줄 {empty_n}건")

# ========== 8) 거래처 결측 (정보성) ==========
cp_null = gl["거래처명"].isna().sum()
record("WARNING", "거래처 결측", cp_null == 0, int(cp_null),
       f"거래처 없는 줄 {cp_null}건 (이자·대체 등 거래처 없는 분개 가능)")

# ========== 9) 시산표 역산 대사 (계정별 상세합 = 시스템 누계) ==========
# 원리: 표준화한 원장의 계정별 (기초잔액 + 상세 차/대 합)이
#       회계시스템이 [누계] 행에 직접 찍어준 누적 차/대 합계와 일치해야 한다.
#       하나라도 어긋나면 = 표준화 과정에서 분개 줄을 빠뜨렸거나 잘못 읽은 것(치명적).
tb = pd.read_csv(BASE / "data" / "trial_balance.csv", dtype={"계정코드": str})
det = (gl.groupby("계정코드")
         .agg(상세차변=("차변", "sum"), 상세대변=("대변", "sum")).reset_index())
m = tb.merge(det, on="계정코드", how="left")
m[["상세차변", "상세대변"]] = m[["상세차변", "상세대변"]].fillna(0)

# 시스템 누계 정보가 있는 계정만 대사 (단일표형·타 시스템은 누계 없음 → 생략)
mv = m[(m["거래건수"] > 0)
       & m["시스템누계차변"].notna() & m["시스템누계대변"].notna()].copy()
if mv.empty:
    record("WARNING", "시산표 역산 대사(상세합=시스템누계)", True, 0,
           "시스템 누계 정보 없음 → 대사 생략(단일표형/타 회계시스템)")
else:
    mv["역산차변"] = mv["기초차변"] + mv["상세차변"]
    mv["역산대변"] = mv["기초대변"] + mv["상세대변"]
    mv["차변차이"] = (mv["시스템누계차변"] - mv["역산차변"]).round()
    mv["대변차이"] = (mv["시스템누계대변"] - mv["역산대변"]).round()
    bad_tb = mv[(mv["차변차이"].abs() > 1) | (mv["대변차이"].abs() > 1)]
    record("ERROR", "시산표 역산 대사(상세합=시스템누계)", bad_tb.empty, len(bad_tb),
           f"거래계정 {len(mv)}개 전부 시스템 누계와 일치 (분개 누락·중복 없음)"
           if bad_tb.empty else
           f"불일치 {len(bad_tb)}개: {bad_tb['계정명'].head(5).tolist()}")

# ========== 10) 전체 시산표 대차평형 (기초+거래 포함) ==========
tot_d = round(m["기초차변"].sum() + m["상세차변"].sum())
tot_c = round(m["기초대변"].sum() + m["상세대변"].sum())
record("ERROR", "전체 시산표 대차평형(기초+거래)", tot_d == tot_c, abs(tot_d - tot_c),
       f"총차변 {tot_d:,.0f} / 총대변 {tot_c:,.0f} / 차이 {tot_d - tot_c:,.0f}원")


# ========== 결과 정리·출력 ==========
res = pd.DataFrame(results)[["등급", "항목", "결과", "건수", "설명"]]
n_err = (res["결과"] == "실패").sum()
n_warn = (res["결과"] == "경고").sum()

print("=" * 64)
print("FR-02 데이터 무결성 검증 결과")
print("=" * 64)
print(f"대상: gl_clean.csv  ({len(gl):,}줄)")
print(f"종합: 실패(ERROR) {n_err}건 / 경고(WARNING) {n_warn}건")
print("-" * 64)
with pd.option_context("display.unicode.east_asian_width", True,
                       "display.width", 200, "display.max_colwidth", 60):
    print(res.to_string(index=False))

verdict = ("✅ 분석 진행 가능 (치명적 오류 없음)" if n_err == 0
           else "❌ 분석 보류 — ERROR 항목 먼저 해결 필요")
print("-" * 64)
print("판정:", verdict)

# 마크다운 리포트 저장
md = ["# FR-02 데이터 무결성 검증 결과\n",
      f"- 대상: `gl_clean.csv` ({len(gl):,}줄)",
      f"- 종합: 실패 {n_err}건 / 경고 {n_warn}건",
      f"- 판정: {verdict}\n",
      res.to_markdown(index=False)]
(REP / "fr02_검증결과.md").write_text("\n".join(md), encoding="utf-8")
res.to_csv(BASE / "data" / "fr02_results.csv", index=False, encoding="utf-8-sig")
print("리포트 저장:", REP / "fr02_검증결과.md")
print("데이터 저장:", BASE / "data" / "fr02_results.csv")
