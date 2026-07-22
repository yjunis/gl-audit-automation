# -*- coding: utf-8 -*-
"""FR-02 검증 회귀 테스트 — 날짜 검증 범위가 특정 연도에 고정되지 않아야 한다.

fr02_validate.py는 스크립트라 GL_BASE 환경변수로 임시 폴더를 가리키고
서브프로세스로 실행한 뒤, 산출물(data/fr02_results.csv)의 판정을 확인한다.
"""
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
FR02 = ROOT / "src" / "fr02_validate.py"


def _make_base(tmp_path, dates):
    """대차평형·계정일관성 등 다른 검사는 모두 통과하는 최소 원장을 만든다.
       변수는 '전표일자'뿐이므로, 실패하면 날짜 범위 검사 때문이다."""
    n = len(dates)
    codes = [f"{101 + i}" for i in range(n)]
    half = n // 2
    gl = pd.DataFrame({
        "계정코드": codes,
        "계정명": [f"계정{c}" for c in codes],
        "전표일자": dates,
        "전표번호": [f"V{i:04d}" for i in range(n)],
        "적요": ["정상거래"] * n,
        "거래처코드": ["C001"] * n,
        "거래처명": ["거래처A"] * n,
        # 앞 절반은 차변, 뒤 절반은 대변 → 대차 일치
        "차변": [1000.0] * half + [0.0] * (n - half),
        "대변": [0.0] * half + [1000.0] * (n - half),
        "잔액": [0.0] * n,
        "전표월": [str(d)[:7] for d in dates],
    })
    tb = pd.DataFrame({
        "계정코드": codes,
        "계정명": [f"계정{c}" for c in codes],
        "거래건수": [1] * n,
        "기초차변": [0.0] * n,
        "기초대변": [0.0] * n,
        "시스템누계차변": [None] * n,   # 누계 없음 → 역산 대사는 '생략(경고)'
        "시스템누계대변": [None] * n,
    })
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    gl.to_csv(d / "gl_clean.csv", index=False, encoding="utf-8-sig")
    tb.to_csv(d / "trial_balance.csv", index=False, encoding="utf-8-sig")
    return tmp_path


def _run_fr02(base):
    env = dict(os.environ, GL_BASE=str(base), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(FR02)], env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"fr02 실행 실패:\n{r.stdout}\n{r.stderr}"
    res = pd.read_csv(base / "data" / "fr02_results.csv")
    return res


def _schema_result(res):
    row = res[res["항목"].str.contains("스키마", na=False)]
    assert not row.empty, "스키마 검사 항목을 찾지 못함"
    return row.iloc[0]["결과"], row.iloc[0]["설명"]


def _dates(year, n=6, month=1):
    return [f"{year}-{month:02d}-{i + 1:02d}" for i in range(n)]


@pytest.mark.parametrize("year", [2023, 2024, 2025, 2026])
def test_any_calendar_year_passes_date_range(tmp_path, year):
    """2025년 외의 정상 원장도 날짜 범위 검사를 통과해야 한다."""
    base = _make_base(tmp_path, _dates(year))
    result, desc = _schema_result(_run_fr02(base))
    assert result == "통과", f"{year}년 원장이 날짜범위에서 실패: {desc}"


def test_non_calendar_fiscal_year_passes(tmp_path):
    """회계연도가 달력연도와 다른 경우(4월~다음해 3월)도 통과해야 한다."""
    dates = ["2024-04-01", "2024-07-15", "2024-10-31",
             "2025-01-10", "2025-02-20", "2025-03-31"]
    base = _make_base(tmp_path, dates)
    result, desc = _schema_result(_run_fr02(base))
    assert result == "통과", f"비달력 회계연도가 실패: {desc}"


def test_out_of_range_dates_still_detected(tmp_path):
    """날짜 오류(1970 등 비현실적 값)는 여전히 검출돼야 한다(검증력 유지)."""
    dates = _dates(2025, 5) + ["1970-01-01"]   # serial 오해석 시 생기는 값
    base = _make_base(tmp_path, dates)
    result, desc = _schema_result(_run_fr02(base))
    assert result == "실패", f"비현실적 날짜를 놓침: {desc}"
