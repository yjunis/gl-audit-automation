# -*- coding: utf-8 -*-
"""
FR-14 · 분석 결과 JSON 내보내기 (Result Export for Web)
------------------------------------------------------------
목적: build_static_site 의 분석 파이프라인(run_pipeline)을 그대로 재사용해,
      HTML에 임베드하던 것과 '동일한 계산 결과'를 웹이 바로 읽을 수 있는
      JSON 세트로 분리 내보낸다. (FR-15 Next.js 사이트의 데이터 소스)

핵심 원칙(RFP):
  - 웹은 매번 분석하지 않는다. Python이 만든 결과 JSON만 읽어 시각화한다.
  - 공개 배포에는 합성 데이터(가상제조(주))만 사용한다. (NFR-01)
  - 숫자·판정은 결정론적 코드가 계산 (재현성 · 설명가능성).

산출(web/data/):
  summary.json            회사·기간·계정수·분개수·고위험계정·플래그수
  account_risks.json      계정별 위험(최고점수·등급·이상 개월·최악 편차)
  monthly_variances.json  계정×월 실제/기대/상하한/이탈z (기대치 엔진 결과)
  journal_flags.json      전표별 부정위험 점수·등급·걸린 이유(배점 분해)
  fraud_scores.json       Beneish M · Altman Z' (지표 기여도 · 임계선 · 참고용)
  validation_results.json 무결성 검증(대차·시산표 역산 등) 통과/경고 내역
  index.json              매니페스트(회사·생성시각·파일목록·주의문구)

실행:  python src/fr14_export_json.py
"""
import os
import re
import sys
import json
import math
import datetime as dt
from numbers import Integral, Real
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
sys.path.insert(0, str(SRC))

# 분석 파이프라인·유틸 재사용 (HTML 빌더와 동일 계산 보장)
from build_static_site import run_pipeline, read_csv, FLAG_NAME

OUT = ROOT / "web" / "data"          # 배포 폴더(_build 만 .vercelignore 제외)
EOK = 100_000_000                     # 1억
_EMO = re.compile(r"[🔴🟠🟡🟢⚪]\s*")
GRADE_EN = {"높음": "High", "중간": "Medium", "낮음": "Low"}
GRADE_RANK = {"높음": 0, "중간": 1, "낮음": 2}


# ── JSON 직렬화 안전 변환 ─────────────────────────────────
def jnum(v, ndigits=None):
    """numpy/pandas 값 → 순수 파이썬 수. NaN/None → None."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, Integral) and not isinstance(v, bool):
        return int(v)                  # np.int64 등 큰 정수도 float 경유 없이 정확히 보존
    if isinstance(v, Real):
        f = float(v)
    else:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return v
    if math.isnan(f) or math.isinf(f):
        return None
    if ndigits is not None:
        f = round(f, ndigits)
    if f == int(f):                    # 정수면 정수로
        return int(f)
    return f


def jstr(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def strip_grade(g):
    """'🔴 높음' → '높음'."""
    return _EMO.sub("", str(g)).strip() if g is not None else None


def to_bool(v):
    return str(v).strip().lower() in ("true", "1", "1.0")


def parse_reasons(s):
    """'기말(10), 라운드금액(15)' → 배점순 [{code, name, points}] + 읽기쉬운 문자열 배열."""
    if not isinstance(s, str):
        return [], []
    pairs = [(nm, int(pt)) for nm, pt in re.findall(r"([가-힣]+)\((\d+)\)", s)]
    pairs.sort(key=lambda x: -x[1])
    detail = [{"code": nm, "name": FLAG_NAME.get(nm, nm), "points": pt} for nm, pt in pairs]
    readable = [FLAG_NAME.get(nm, nm) for nm, _ in pairs]
    return detail, readable


def safe_read(base, name, **kw):
    """CSV 읽기도 개별 격리(NFR-09) — 손상/누락 시 None 반환하고 나머지 산출은 계속."""
    try:
        return read_csv(base, name, **kw)
    except Exception as e:              # noqa: BLE001 — 입력 하나의 실패가 전체를 막지 않도록
        print(f"    [WARN] {name} 읽기 실패 — {type(e).__name__}: {e}", flush=True)
        return None


def write_json(name, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    # allow_nan=False: 혹시라도 변환 누락된 NaN/Infinity가 비표준 JSON으로 새는 것을 차단
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf-8")
    kb = len(path.read_bytes()) / 1024
    print(f"    [OK] {name}  ({kb:,.1f} KB)", flush=True)
    return path


# ============================================================
# 각 JSON 빌더 (실패 격리 · NFR-09)
# ============================================================
def compute_pm(gl):
    """성과중요성 PM = 벤치마크(연간 매출) × 0.5% × 75%.

    fr04_flagging.py(52~63행)·Streamlit 대시보드와 같은 규칙이라야 화면 간 수치가 갈리지 않는다.
    매출 계정이 없으면 총 차변 발생액을 벤치마크로 대용하는 것까지 동일.
    """
    if gl is None or gl.empty:
        return None
    name = gl["계정명"].astype(str)
    ismae = name.str.contains("매출", na=False)
    isexc = name.str.contains("원가|차감|환입|할인|에누리", na=False)
    sel = ismae & ~isexc
    rev = float(gl.loc[sel, "대변"].fillna(0).sum() - gl.loc[sel, "차변"].fillna(0).sum())
    if rev <= 0:
        rev = float(gl["차변"].fillna(0).sum())
    return rev * 0.005 * 0.75


def build_balance_quality(meta):
    """대차 품질 등급·오차율. Streamlit 대시보드(fr09_upload_app.py 406~409행)와 같은 규칙."""
    debit, credit = float(meta.get("debit") or 0), float(meta.get("credit") or 0)
    diff = abs(debit - credit)
    ratio = diff / max(debit, 1)
    grade = ("완벽" if diff < 1 else "사실상 일치" if ratio < 0.001
             else "근접" if ratio < 0.01 else "검토 필요")
    return {"grade": grade, "diff": jnum(diff, 0), "ratio": jnum(ratio, 6)}


def build_summary(meta, company, cur_year, prior_year, flags, fraud, pm=None):
    n_high_acc = 0
    n_flagged_acc = 0
    flagged_var = 0
    high_var = 0
    if flags is not None and not flags.empty:
        g = flags["등급"].map(strip_grade)
        flagged_var = int(len(flags))
        high_var = int((g == "높음").sum())
        n_high_acc = int(flags.loc[g == "높음", "계정명"].nunique())
        # 등급 무관, 플래그가 하나라도 있는 계정 수(Streamlit 3초 요약의 n_facct와 동일).
        n_flagged_acc = int(flags["계정명"].nunique())
    n_hi = n_mid = flagged_j = 0
    if fraud is not None and not fraud.empty:
        fg = fraud["등급"].map(strip_grade)
        n_hi = int((fg == "높음").sum())
        n_mid = int((fg == "중간").sum())
        flagged_j = int(((fg == "높음") | (fg == "중간")).sum())
    return {
        "company": company,
        "period": str(cur_year),
        "period_prior": str(prior_year),
        "method": "전년 동월 대비(YoY)",
        "journal_count": jnum(meta.get("n_rows")),
        "account_count": jnum(meta.get("n_accounts")),
        "high_risk_accounts": n_high_acc,       # 등급 '높음' 계정 수(히트맵 배지용)
        "flagged_accounts": n_flagged_acc,       # 플래그된 전체 계정 수(3초 요약 배너용)
        "flagged_journals": flagged_j,
        "variance_flags": flagged_var,
        "high_grade_variances": high_var,
        "fraud_high": n_hi,
        "fraud_medium": n_mid,
        # 대시보드 KPI용(Streamlit 대시보드와 같은 항목)
        "performance_materiality": jnum(pm, 0),
        "balance_quality": build_balance_quality(meta),
        "is_synthetic": True,
    }


def build_account_risks(flags):
    if flags is None or flags.empty:
        return []
    rows = []
    for (code, name), g in flags.groupby(["계정코드", "계정명"], sort=False):
        grades = g["등급"].map(strip_grade)
        worst = min(grades.map(lambda x: GRADE_RANK.get(x, 3)))
        worst_grade = {v: k for k, v in GRADE_RANK.items()}.get(worst)
        gi = g.assign(_abz=g["로버스트z"].abs()).sort_values("_abz", ascending=False)
        top = gi.iloc[0]
        rows.append({
            "account": name,
            "account_code": jstr(code),
            "risk_score": jnum(g["위험점수"].max()),
            "grade": worst_grade,
            "grade_en": GRADE_EN.get(worst_grade),
            "flagged_months": int(len(g)),
            "worst_month": jstr(top["월"]),
            "worst_direction": jstr(top["방향"]),
            "worst_robust_z": jnum(top["로버스트z"], 2),
            "worst_deviation": jnum(top["편차"], 0),
        })
    rows.sort(key=lambda r: (r["risk_score"] is None, -(r["risk_score"] or 0)))
    return rows


def build_monthly_variances(exp):
    if exp is None or exp.empty:
        return []
    df = exp.copy()
    if "판정대상" in df.columns:
        df = df[df["판정대상"].map(to_bool)]
    rows = []
    for _, r in df.sort_values(["계정명", "월"]).iterrows():
        rows.append({
            "account": jstr(r["계정명"]),
            "account_code": jstr(r["계정코드"]),
            "month": jstr(r["월"]),
            "actual": jnum(r["월값"], 0),
            "expected": jnum(r["기대중앙값"], 0),
            "lower": jnum(r["하한"], 0),
            "upper": jnum(r["상한"], 0),
            "robust_z": jnum(r["로버스트z"], 2),
            "is_anomaly": to_bool(r["이상여부"]) if "이상여부" in df.columns else None,
            "method": jstr(r["적용기법"]) if "적용기법" in df.columns else None,
        })
    return rows


# 월 순액이 총활동액에 비해 너무 작으면(상쇄가 커서 net≈0) 순액 대비 비율이 폭주한다.
# 예: 월 순액 10원인데 +100억/-100억이면 비율이 수억 %가 된다. 그 경우 비율을 내보내지 않는다.
_SHARE_MIN_NET_RATIO = 0.10

_NULLISH = ["", "nan", "none", "<na>", "null"]


def assert_clean_codes(codes, source):
    """계정코드를 '정규화하지 않고' 쓸 수 있는 상태인지 검증한다.

    fr03은 계정코드를 원본 그대로 groupby 하므로, 여기서 strip 등을 적용하면 오히려 키가
    갈린다(fr03은 " 504"와 "504"를 다른 계정으로 보는데 여기서 합치면 자연방향이 달라짐).
    그래서 다듬는 대신, 다듬을 필요가 없음을 확인하고 아니면 멈춘다.

    원장(gl)과 flags 양쪽에 똑같이 적용해야 한다. 한쪽만 검증하면 다른 쪽의 결측이
    str()을 거쳐 "nan"·"<NA>"가 된 뒤 매칭에 실패해 조용히 건너뛰게 된다.

    주의: 결측 검사는 반드시 astype(str) '이전'에 해야 한다. 문자열로 바꾸면 NaN은 "nan",
    pd.NA는 "<NA>"가 되어 isna()가 항상 False가 되기 때문.
    """
    if bool(codes.isna().any()):
        raise ValueError(
            f"[{source}] 계정코드가 결측인 행 {int(codes.isna().sum())}건 — fr03은 groupby/merge"
            "에서 이를 떨어뜨려 월값이 갈린다. 원장 정제(FR-01) 단계에서 먼저 해결해야 한다."
        )
    s = codes.astype(str)
    blank = s.str.strip().str.lower().isin(_NULLISH)
    if bool(blank.any()):
        raise ValueError(
            f"[{source}] 계정코드가 비어 있거나 결측 문자열인 행 {int(blank.sum())}건 — "
            "원장 정제(FR-01) 단계에서 먼저 해결해야 한다."
        )
    if bool((s.str.strip() != s).any()):
        raise ValueError(
            f"[{source}] 계정코드에 앞뒤 공백이 있는 행이 있다 — fr03은 공백을 그대로 키로 쓰므로 "
            "여기서 임의로 다듬으면 월값이 갈린다. 원장 정제(FR-01)에서 먼저 해결해야 한다."
        )
    return s


def build_driver_journals(flags, gl, top_n=5):
    """이상으로 판정된 (계정코드, 월)마다 그 달 금액이 큰 전표를 뽑는다.

    부정 스크리닝(fr09, 240축)과는 완전히 다른 질문에 답한다:
      · fr09  = "패턴이 수상한 전표는?"  → 레드플래그 점수 순
      · 여기  = "이 달 금액을 무엇이 구성했나?" → 원장에서 금액 순
    fr09 결과는 점수 상위 500건만 남아 정상적인 대형 거래(예: 대형 수주 매출)가 빠지므로,
    분석적 절차(520) 드릴다운의 근거로는 쓸 수 없다. 그래서 원장(gl_clean)에서 직접 집계한다.

    주의: 이 목록은 '편차의 분해'가 아니다. 편차는 기대치(중앙값 기반) 대비 값이라
    개별 원장 행으로 귀속되지 않는다. 어디까지나 '이 달 금액을 구성한 큰 거래'다.
    """
    if flags is None or flags.empty or gl is None or gl.empty:
        return []

    d = gl.copy()
    d["_월"] = d["전표일자"].astype(str).str[:7]
    d["차변"] = d["차변"].fillna(0)
    d["대변"] = d["대변"].fillna(0)

    # 원장·flags 양쪽 모두 검증한다(한쪽만 하면 반대쪽 결측이 조용히 매칭 실패로 흘러간다).
    d["계정코드"] = assert_clean_codes(d["계정코드"], "gl_clean")   # 값 변형 없음(dtype만 str 고정)
    flag_codes = assert_clean_codes(flags["계정코드"], "fr04_flags")
    if d.empty:
        return []

    # 부호는 fr03_expectation.py(83~92행)의 '자연방향'과 반드시 같아야 한다.
    # 계정코드별로 연간 차변합>=대변합이면 차변성격(월값=차-대), 아니면 대변성격(월값=대-차).
    # 이 규칙을 안 맞추면 매출·부채처럼 대변성격 계정에서 그래프는 +76억인데
    # 근거 전표는 -76억으로 찍혀 부호가 뒤집힌다.
    tot = d.groupby("계정코드").agg(D=("차변", "sum"), C=("대변", "sum"))
    natural = (tot["D"] >= tot["C"]).map({True: 1, False: -1})   # 차변성격 +1 / 대변성격 -1
    d["_금액"] = (d["차변"] - d["대변"]) * d["계정코드"].map(natural)

    rows = []
    # 위치 기반으로 짝지어 순회한다. flags 인덱스가 중복이면 .loc[idx]가 Series를 반환해
    # 코드 비교가 조용히 깨지므로 라벨 조회를 쓰지 않는다.
    codes_list = flag_codes.tolist()
    for pos, (_, f) in enumerate(flags.iterrows()):
        # 검증을 통과한 flags 코드를 그대로 쓴다(str(f.get(...))로 다시 만들면 결측이
        # "nan"으로 되살아나 검증을 우회한다).
        code = codes_list[pos]
        acct, mon = f.get("계정명"), jstr(f.get("월"))
        # 자연방향은 계정코드별이므로 필터도 계정코드로 한다(같은 계정명에 코드가 여럿일 수 있음).
        g = d[(d["계정코드"] == code) & (d["_월"] == mon)]
        if g.empty:
            continue

        # 감사인이 확인하는 단위는 원장 '행'이 아니라 '전표'다. 한 전표가 같은 계정에
        # 여러 줄로 실릴 수 있으므로 전표번호로 합산한 뒤 순위를 매긴다.
        by_j = (g.groupby("전표번호", sort=False)
                 .agg(_금액=("_금액", "sum"),
                      전표일자=("전표일자", "first"),
                      적요=("적요", "first"),
                      거래처명=("거래처명", "first"))
                 .reset_index())

        net = float(by_j["_금액"].sum())
        gross = float(by_j["_금액"].abs().sum())      # 총활동액(상쇄 전)
        top = by_j.reindex(by_j["_금액"].abs().sort_values(ascending=False).index).head(top_n)

        # 순액 대비 비율은 분모가 총활동액 대비 충분히 클 때만 의미가 있다.
        share_ok = gross > 0 and abs(net) >= _SHARE_MIN_NET_RATIO * gross

        journals = []
        for _, r in top.iterrows():
            amt = float(r["_금액"])
            journals.append({
                "journal_id": jstr(r.get("전표번호")),
                "date": jstr(r.get("전표일자")),
                "memo": jstr(r.get("적요")),
                "counterparty": jstr(r.get("거래처명")),
                "amount": jnum(amt, 0),
                "share_of_month_net": jnum(amt / net, 3) if share_ok else None,
            })

        rows.append({
            "account": jstr(acct),
            "account_code": jstr(code),
            "month": mon,
            "direction": jstr(f.get("방향")),
            "deviation": jnum(f.get("편차"), 0),
            "month_net": jnum(net, 0),
            "month_gross": jnum(gross, 0),
            "journal_count": int(by_j.shape[0]),        # 전표 수(행 수 아님)
            "line_count": int(len(g)),                  # 원장 행 수
            "shown_count": int(len(journals)),
            # 표시한 상위 N건이 그 달 총활동액에서 차지하는 몫 — 5건으로 충분한지 판단 근거.
            "shown_coverage": jnum(float(top["_금액"].abs().sum()) / gross, 3) if gross > 0 else None,
            "journals": journals,
        })

    rows.sort(key=lambda r: (r["account"], r["month"]))
    return rows


def account_dc_side(account, combo):
    """상대계정조합('차변계정 → 대변계정' 형식)에서 걸린 계정이 놓인 분개 방향을 판정.
    화살표 왼쪽이 차변, 오른쪽이 대변. 계정명이 어느 쪽과 일치하는지로 차변/대변을 정한다.
    (원장 실집계 net 부호와 일치함을 augment_journal_flags_dc.py로 500건 전수 검증)."""
    if not account or not combo or "→" not in combo:
        return None
    parts = [p.strip() for p in combo.split("→")]
    dr, cr = parts[0], parts[-1]
    if account == cr:
        return "대변"
    if account == dr:
        return "차변"
    return None


def build_journal_flags(fraud):
    if fraud is None or fraud.empty:
        return []
    rows = []
    for _, r in fraud.iterrows():
        detail, readable = parse_reasons(r.get("걸린이유"))
        grade = strip_grade(r.get("등급"))
        combo = jstr(r.get("상대계정조합"))
        rows.append({
            "rank": jnum(r.get("순위")),
            "journal_id": jstr(r.get("전표번호")),
            "date": jstr(r.get("전표일자")),
            "account": jstr(r.get("계정명")),
            "memo": jstr(r.get("적요")),
            "counterparty": jstr(r.get("거래처명")),
            "amount": jnum(r.get("금액"), 0),
            "amount_materiality": jnum(r.get("금액중요도"), 2),
            "counter_account": combo,
            "account_dc": account_dc_side(jstr(r.get("계정명")), combo),
            "risk_score": jnum(r.get("부정위험점수")),
            "raw_points": jnum(r.get("원배점합")),          # 걸린 레드플래그 배점 합
            "max_possible_points": jnum(r.get("최대배점")),  # 활성 플래그 만점
            "risk_level": GRADE_EN.get(grade, grade),
            "risk_level_ko": grade,
            "reasons": readable,
            "reasons_detail": detail,
        })
    return rows


def build_fraud_scores(fscore):
    if fscore is None or fscore.empty:
        return {}
    out = {
        "disclaimer": "학술 계량모형 기반 참고 지표 · 분식 '확정'이 아니라 추가 절차의 단서 (감사기준서 200·240)",
        "models": {},
    }
    meta = {
        "Altman Z'": {"key": "altman_z", "name": "Altman Z' (도산위험)",
                      "thresholds": {"safe": 2.9, "gray": 1.23},
                      "note": "높을수록 안전 · 안전>2.9 / 회색 1.23~2.9 / 위험<1.23"},
        "Beneish M": {"key": "beneish_m", "name": "Beneish M (분식주의 신호)",
                      "thresholds": {"standard": -1.78, "conservative": -2.22},
                      "note": "낮을수록 정상 · 표준선 -1.78 / 보수선 -2.22 · 확정 아님"},
    }
    for _, r in fscore.iterrows():
        model = jstr(r.get("모형"))
        m = meta.get(model, {"key": model, "name": model, "thresholds": {}, "note": ""})
        try:
            indicators = json.loads(r.get("지표")) if isinstance(r.get("지표"), str) else None
            if isinstance(indicators, dict):
                indicators = {k: jnum(v, 3) for k, v in indicators.items()}
        except (json.JSONDecodeError, TypeError):
            indicators = None
        out["models"][m["key"]] = {
            "model": model,
            "name": m["name"],
            "score": jnum(r.get("점수"), 3),
            "zone": strip_grade(r.get("판정")),
            "thresholds": m["thresholds"],
            "note": m["note"],
            "indicators": indicators,
        }
    return out


def build_validation(validation):
    if validation is None or validation.empty:
        return {"checks": [], "overall": None}
    checks = []
    for _, r in validation.iterrows():
        checks.append({
            "level": jstr(r.get("등급")),
            "item": jstr(r.get("항목")),
            "result": jstr(r.get("결과")),
            "count": jnum(r.get("건수")),
            "description": jstr(r.get("설명")),
        })
    errors = [c for c in checks if c["level"] == "ERROR" and c["result"] != "통과"]
    warnings = [c for c in checks if c["level"] == "WARNING" and c["result"] != "통과"]
    overall = {
        "passed": len(errors) == 0,
        "error_fail_count": len(errors),
        "warning_count": len(warnings),
        "total_checks": len(checks),
    }
    return {"overall": overall, "checks": checks}


# ============================================================
# 오케스트레이션
# ============================================================
def export_all(cur, prior, yoy_base):
    meta = cur["meta"]
    # 데모 표준 회사명(HTML 빌더와 동일). meta['company']는 파일명 유래("가상제조 GL")라 미사용.
    company = "가상제조(주)"

    # HTML 빌더와 동일 소스: flags·exp 는 2년 YoY 재계산 결과, fraud·fscore·검증은 당기 base
    flags = safe_read(yoy_base, "fr04_flags.csv", dtype={"계정코드": str})
    exp = safe_read(yoy_base, "fr03_expectations.csv", dtype={"계정코드": str})
    fraud = safe_read(cur["base"], "fr09_fraud_flags.csv",
                      dtype={"전표번호": str, "계정코드": str})
    fscore = safe_read(cur["base"], "fr11_fraud_scores.csv")
    validation = safe_read(cur["base"], "fr02_results.csv")
    # 근거 전표는 원장에서 직접 집계한다. flags·exp와 같은 2년 base라야 이상월과 짝이 맞는다.
    gl = safe_read(yoy_base, "gl_clean.csv", dtype={"계정코드": str, "전표번호": str})
    # PM은 '당기' 원장으로 계산한다(Streamlit과 동일). 2년 병합본을 쓰면 매출이 2배가 돼 PM도 2배가 된다.
    cur_gl = safe_read(cur["base"], "gl_clean.csv", dtype={"계정코드": str, "전표번호": str})

    builders = {
        "summary.json": lambda: build_summary(meta, company, cur["year"], prior["year"], flags, fraud,
                                              pm=compute_pm(cur_gl)),
        "account_risks.json": lambda: build_account_risks(flags),
        "monthly_variances.json": lambda: build_monthly_variances(exp),
        "driver_journals.json": lambda: build_driver_journals(flags, gl),
        "journal_flags.json": lambda: build_journal_flags(fraud),
        "fraud_scores.json": lambda: build_fraud_scores(fscore),
        "validation_results.json": lambda: build_validation(validation),
    }

    written = []
    for name, fn in builders.items():
        try:
            write_json(name, fn())          # 실패 격리(NFR-09): 한 파일 실패가 전체를 멈추지 않음
            written.append(name)
        except Exception as e:              # noqa: BLE001 — 개별 산출 실패 기록 후 계속
            print(f"    [FAIL] {name} — {type(e).__name__}: {e}", flush=True)

    manifest = {
        "company": company,
        "period": str(cur["year"]),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "is_synthetic": True,
        "note": "가상제조(주) 합성 데이터 · 포트폴리오 데모 · 실제 감사자료 아님",
        # 근거 감사기준서(회계감사기준) — 이 도구가 실제로 구현/참조하는 기준서.
        #   200 전반적 목적·전문가적 판단 / 230 감사문서 / 240 부정 / 315 위험평가 /
        #   320 중요성(성과·수행중요성 산정) / 500 감사증거(무결성 검증) / 520 분석적 절차 /
        #   570 계속기업(Altman Z′를 보조 신호로 참조)
        # 표기는 국내 정식 명칭 "감사기준서 NNN". (과거 'K-AuS'는 비표준 약어라 수정)
        "standards": [
            "감사기준서 200",
            "감사기준서 230",
            "감사기준서 240",
            "감사기준서 315",
            "감사기준서 320",
            "감사기준서 500",
            "감사기준서 520",
            "감사기준서 570",
        ],
        "schema_notes": {
            "journal_flags.risk_score": "round(raw_points / max_possible_points * 100) — 0~100 정규화, reasons_detail의 배점 합이 raw_points",
            "driver_journals": "이상 판정된 (계정코드,월)에서 그 달 금액이 큰 전표 상위 5건(전표번호 단위 합산). 부정 스크리닝(journal_flags, 240축)과 다른 축(520): 수상함이 아니라 금액 규모로 뽑으므로 정상적인 대형 거래도 포함된다. '편차의 분해'가 아님 — 편차는 기대치 대비 값이라 개별 전표로 귀속되지 않는다.",
            "driver_journals.amount": "부호는 fr03의 자연방향(계정별 연간 차변합>=대변합이면 차변성격) 기준이라 monthly_variances.actual과 같은 방향이다.",
            "driver_journals.share_of_month_net": "amount / month_net — 월 순액 대비 몫. 상쇄 거래가 크면(|net| < 총활동액의 10%) 비율이 폭주하므로 null. 상쇄가 있으면 100% 초과·음수 가능.",
            "driver_journals.shown_coverage": "상위 N건 |금액| 합 / month_gross — 표시분이 그 달 총활동액에서 차지하는 몫.",
        },
        "files": written,
    }
    write_json("index.json", manifest)
    return written


def main():
    print("[FR-14] 결과 JSON 내보내기 시작", flush=True)
    cur, prior, yoy_base = run_pipeline()
    print("[FR-14] JSON 조립", flush=True)
    written = export_all(cur, prior, yoy_base)
    print(f"완료 · {len(written) + 1}개 파일 → {OUT}", flush=True)


if __name__ == "__main__":
    main()
