# -*- coding: utf-8 -*-
"""FR-02 검증 회귀 테스트 — 회계기간(날짜 범위) 판정.

핵심 요건:
  - 검증 대상 날짜의 min/max로 허용 범위를 만들지 않는다.
    (오입력이 스스로 허용 범위를 넓혀 자기 자신을 통과시키는 것을 막는다)
  - 우선순위: GL_FY_START/END → 로더 메타데이터 → 설정 회계연도 → 지배적 거래기간
  - 신뢰성 있게 정할 수 없으면 자동 통과 금지 → '보류'
  - 12월 결산 외 비달력 회계연도도 지원

fr02_validate.py는 스크립트라 GL_BASE 환경변수로 임시 폴더를 가리키고
서브프로세스로 실행한 뒤 산출물(data/fr02_results.csv)의 판정을 확인한다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
FR02 = ROOT / "src" / "fr02_validate.py"


def _make_base(tmp_path, dates, meta=None):
    """대차평형·계정일관성 등 다른 검사는 모두 통과하는 최소 원장.
       변수는 '전표일자'뿐이므로, 날짜 관련 판정만 달라진다."""
    n = len(dates)
    codes = [f"{101 + (i % 50)}" for i in range(n)]
    half = n // 2
    gl = pd.DataFrame({
        "계정코드": codes,
        "계정명": [f"계정{c}" for c in codes],
        "전표일자": dates,
        "전표번호": [f"V{i:04d}" for i in range(n)],
        "적요": ["정상거래"] * n,
        "거래처코드": ["C001"] * n,
        "거래처명": ["거래처A"] * n,
        "차변": [1000.0] * half + [0.0] * (n - half),
        "대변": [0.0] * half + [1000.0] * (n - half),
        "잔액": [0.0] * n,
        "전표월": [str(d)[:7] for d in dates],
    })
    uniq = sorted(set(codes))
    tb = pd.DataFrame({
        "계정코드": uniq,
        "계정명": [f"계정{c}" for c in uniq],
        "거래건수": [codes.count(c) for c in uniq],
        "기초차변": [0.0] * len(uniq),
        "기초대변": [0.0] * len(uniq),
        "시스템누계차변": [None] * len(uniq),
        "시스템누계대변": [None] * len(uniq),
    })
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    gl.to_csv(d / "gl_clean.csv", index=False, encoding="utf-8-sig")
    tb.to_csv(d / "trial_balance.csv", index=False, encoding="utf-8-sig")
    if meta is not None:
        (d / "ledger_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _run_fr02(base, **envkw):
    env = dict(os.environ, GL_BASE=str(base), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    for k in ("GL_FY_START", "GL_FY_END", "GL_FY_YEAR"):
        env.pop(k, None)
    env.update({k: str(v) for k, v in envkw.items()})
    r = subprocess.run([sys.executable, str(FR02)], env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"fr02 실행 실패:\n{r.stdout}\n{r.stderr}"
    return pd.read_csv(base / "data" / "fr02_results.csv")


def _row(res, keyword):
    r = res[res["항목"].str.contains(keyword, na=False)]
    assert not r.empty, f"'{keyword}' 검사 항목을 찾지 못함"
    return r.iloc[0]["결과"], str(r.iloc[0]["설명"])


def _schema(res):
    return _row(res, "스키마")


def _period(res):
    return _row(res, "회계기간")


def _spread(year, n, start_month=1):
    """연 12개월에 고르게 퍼진 날짜 n건."""
    out = []
    for i in range(n):
        m = (start_month - 1 + (i * 12) // n) % 12 + 1
        y = year + (start_month - 1 + (i * 12) // n) // 12
        out.append(f"{y}-{m:02d}-{(i % 27) + 1:02d}")
    return out


# ───────────── 지적: 오입력이 허용 범위를 스스로 넓히면 안 된다 ─────────────

def test_prior_year_typo_is_detected(tmp_path):
    """2025년 원장에 2024-12-31 오입력 1건 → 범위가 넓어지지 않고 검출돼야 한다."""
    base = _make_base(tmp_path, _spread(2025, 60) + ["2024-12-31"])
    res = _run_fr02(base)
    assert _schema(res)[0] == "실패", f"전기 오입력을 놓침: {_schema(res)[1]}"


def test_next_year_typo_is_detected(tmp_path):
    """2025년 원장에 2026-01-01 오입력 1건 → 검출돼야 한다."""
    base = _make_base(tmp_path, _spread(2025, 60) + ["2026-01-01"])
    res = _run_fr02(base)
    assert _schema(res)[0] == "실패", f"차기 오입력을 놓침: {_schema(res)[1]}"


def test_non_calendar_fiscal_year(tmp_path):
    """2024-07-01~2025-06-30 비달력 회계연도는 정상 통과해야 한다."""
    base = _make_base(tmp_path, _spread(2024, 60, start_month=7))
    res = _run_fr02(base)
    assert _schema(res)[0] == "통과", f"비달력 회계연도가 실패: {_schema(res)[1]}"
    assert _period(res)[0] == "통과"


def test_non_calendar_fiscal_year_typo_detected(tmp_path):
    """비달력 회계연도(7월~익년 6월)에서 기간 밖 1건도 검출돼야 한다."""
    base = _make_base(tmp_path, _spread(2024, 60, start_month=7) + ["2025-07-15"])
    res = _run_fr02(base)
    assert _schema(res)[0] == "실패", f"비달력 기간 밖 오입력을 놓침: {_schema(res)[1]}"


def test_prior_period_comparatives_mixed_is_held(tmp_path):
    """전기 비교자료가 상당량 섞이면 자동 통과하지 말고 '보류'여야 한다."""
    base = _make_base(tmp_path, _spread(2025, 60) + _spread(2024, 20))
    res = _run_fr02(base)
    result, desc = _period(res)
    assert result == "경고", f"혼입 자료인데 보류가 아님: {result} / {desc}"
    assert "보류" in desc


def test_no_period_metadata_uses_dominant_period(tmp_path):
    """메타데이터가 없어도 지배적 거래기간으로 판정하되, 근거를 밝혀야 한다."""
    base = _make_base(tmp_path, _spread(2025, 60))
    res = _run_fr02(base)
    assert _schema(res)[0] == "통과"
    result, desc = _period(res)
    assert result == "통과"
    assert "2025-01-01" in desc and "2025-12-31" in desc


def test_all_dates_unrealistic_not_auto_passed(tmp_path):
    """전 건이 비현실적(1970 = serial 오해석)이면 조용히 통과시키면 안 된다."""
    base = _make_base(tmp_path, _spread(1970, 60))
    res = _run_fr02(base)
    period_result = _period(res)[0]
    schema_result = _schema(res)[0]
    assert not (period_result == "통과" and schema_result == "통과"), \
        "전건 비현실 날짜가 그대로 통과됨"


# ───────────── 우선순위: 명시 지정 > 메타데이터 > 설정 > 추정 ─────────────

def test_env_fy_range_takes_priority(tmp_path):
    """GL_FY_START/END가 최우선 — 지정 기간 밖이면 실패해야 한다."""
    base = _make_base(tmp_path, _spread(2025, 60))
    res = _run_fr02(base, GL_FY_START="2024-01-01", GL_FY_END="2024-12-31")
    assert _schema(res)[0] == "실패", "명시 지정 기간이 무시됨"
    assert "GL_FY" in _period(res)[1]


def test_loader_metadata_used_when_no_env(tmp_path):
    """환경변수가 없으면 로더 메타데이터(파일명 기반 회계연도)를 쓴다."""
    base = _make_base(tmp_path, _spread(2025, 60),
                      meta={"fy_year": 2024, "year_source": "filename"})
    res = _run_fr02(base)
    assert _schema(res)[0] == "실패", "로더 메타데이터가 무시됨"
    assert "메타데이터" in _period(res)[1]


def test_loader_metadata_explicit_range(tmp_path):
    """메타데이터가 fy_start/fy_end를 주면 비달력연도도 그대로 쓴다."""
    base = _make_base(tmp_path, _spread(2024, 60, start_month=7),
                      meta={"fy_start": "2024-07-01", "fy_end": "2025-06-30"})
    res = _run_fr02(base)
    assert _schema(res)[0] == "통과"
    assert "메타데이터" in _period(res)[1]


def test_config_year_env(tmp_path):
    """메타데이터가 없을 때 GL_FY_YEAR 설정값을 쓴다."""
    base = _make_base(tmp_path, _spread(2025, 60))
    res = _run_fr02(base, GL_FY_YEAR="2024")
    assert _schema(res)[0] == "실패", "GL_FY_YEAR가 무시됨"


@pytest.mark.parametrize("year", [2023, 2024, 2025, 2026])
def test_any_calendar_year_passes(tmp_path, year):
    """연도가 달라도 정상 원장은 통과해야 한다(연도 하드코딩 금지)."""
    base = _make_base(tmp_path, _spread(year, 60))
    assert _schema(_run_fr02(base))[0] == "통과", f"{year}년 원장이 실패"
