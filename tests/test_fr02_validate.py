# -*- coding: utf-8 -*-
"""FR-02 회계기간(날짜 범위) 검증 회귀 테스트.

설계 원칙(자기참조 제거):
  - 검증 대상인 거래일로 추론한 기간을 '검증 기준'으로 절대 쓰지 않는다.
  - 회계기간은 독립된 근거에서만 받는다:
      환경변수(GL_FY_START/END, GL_FY_YEAR) → 설정 파일(fiscal_period.json)
      → 파일 메타데이터(data/ledger_meta.json, 로더가 파일명에서 추출)
  - 독립 근거가 없으면 자동 통과시키지 않고 analysis hold 로 처리한다.
  - 거래일 분포 추론은 사용자에게 보여주는 '제안값'으로만 쓴다.
  - 비달력 회계연도를 지원한다.

이 파일은 지금까지 제기된 모든 날짜 반례를 회귀 테스트로 보존한다.
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

# 모든 테스트의 기본 회계기간 근거(독립 근거) — 없는 상황을 시험할 때만 생략한다.
META_2025 = {"fy_year": 2025}


def _make_base(tmp_path, dates, meta=None, config=None):
    """대차평형·계정일관성 등 다른 검사는 통과하는 최소 원장.
       변수는 '전표일자'와 '회계기간 근거'뿐이다."""
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
        (d / "ledger_meta.json").write_text(json.dumps(meta, ensure_ascii=False),
                                            encoding="utf-8")
    if config is not None:
        (tmp_path / "fiscal_period.json").write_text(json.dumps(config, ensure_ascii=False),
                                                     encoding="utf-8")
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
        off = start_month - 1 + (i * 12) // n
        out.append(f"{year + off // 12}-{off % 12 + 1:02d}-{(i % 27) + 1:02d}")
    return out


# ═════════ 1. 자기참조 제거: 독립 근거가 없으면 analysis hold ═════════

def test_no_independent_period_is_analysis_hold(tmp_path):
    """회계기간 근거가 전혀 없으면 자동 통과가 아니라 보류여야 한다."""
    base = _make_base(tmp_path, _spread(2025, 60))          # meta·config·env 모두 없음
    res = _run_fr02(base)
    result, desc = _period(res)
    assert result == "실패", f"근거 없이 통과됨: {result}"
    assert "보류" in desc or "hold" in desc.lower()


def test_hold_message_offers_distribution_suggestion(tmp_path):
    """보류 시 거래일 분포 기반 '제안값'을 참고로 제시해야 한다(기준으로는 쓰지 않음)."""
    base = _make_base(tmp_path, _spread(2025, 60))
    _, desc = _period(_run_fr02(base))
    assert "2025-01-01" in desc and "2025-12-31" in desc, f"제안값 미제시: {desc}"


def test_whole_ledger_shifted_by_one_year_is_not_self_justified(tmp_path):
    """원장 전체가 1년 밀린 경우(집중도 100%) — 자기참조 구조에서는 무조건 통과했다.
       독립 근거(2025)와 대조해 실패로 잡혀야 한다."""
    base = _make_base(tmp_path, _spread(2024, 60), meta=META_2025)
    assert _schema(_run_fr02(base))[0] == "실패", "전건 이동을 놓침(자기참조 잔존)"


# ═════════ 2. 독립 근거의 우선순위 ═════════

def test_env_range_takes_priority(tmp_path):
    """GL_FY_START/END가 최우선 — 메타데이터보다 앞선다."""
    base = _make_base(tmp_path, _spread(2025, 60), meta=META_2025)
    res = _run_fr02(base, GL_FY_START="2024-01-01", GL_FY_END="2024-12-31")
    assert _schema(res)[0] == "실패", "명시 지정이 무시됨"
    assert "GL_FY_START" in _period(res)[1]


def test_env_year_over_config_and_meta(tmp_path):
    """GL_FY_YEAR가 설정 파일·메타데이터보다 우선한다."""
    base = _make_base(tmp_path, _spread(2025, 60), meta=META_2025,
                      config={"fy_year": 2025})
    res = _run_fr02(base, GL_FY_YEAR="2024")
    assert _schema(res)[0] == "실패", "GL_FY_YEAR가 무시됨"


def test_config_file_over_meta(tmp_path):
    """설정 파일(fiscal_period.json)이 로더 메타데이터보다 우선한다."""
    base = _make_base(tmp_path, _spread(2025, 60), meta=META_2025,
                      config={"fy_year": 2024})
    res = _run_fr02(base)
    assert _schema(res)[0] == "실패", "설정 파일이 무시됨"
    assert "설정" in _period(res)[1]


def test_loader_metadata_used(tmp_path):
    """환경변수·설정 파일이 없으면 로더 메타데이터를 쓴다."""
    base = _make_base(tmp_path, _spread(2025, 60), meta={"fy_year": 2024})
    res = _run_fr02(base)
    assert _schema(res)[0] == "실패", "메타데이터가 무시됨"
    assert "메타데이터" in _period(res)[1]


def test_meta_without_year_is_hold(tmp_path):
    """파일명에 연도가 없어 fy_year=None이면 근거가 없는 것 → 보류."""
    base = _make_base(tmp_path, _spread(2025, 60), meta={"company": "X", "fy_year": None})
    assert _period(_run_fr02(base))[0] == "실패"


# ═════════ 3. 기간 밖 오입력 검출 (Codex 제시 반례) ═════════

def test_prior_year_typo_detected(tmp_path):
    """2025년 원장에 2024-12-31 오입력 1건."""
    base = _make_base(tmp_path, _spread(2025, 60) + ["2024-12-31"], meta=META_2025)
    assert _schema(_run_fr02(base))[0] == "실패"


def test_next_year_typo_detected(tmp_path):
    """2025년 원장에 2026-01-01 오입력 1건."""
    base = _make_base(tmp_path, _spread(2025, 60) + ["2026-01-01"], meta=META_2025)
    assert _schema(_run_fr02(base))[0] == "실패"


def test_unrealistic_1970_date_detected(tmp_path):
    """Excel serial 오해석으로 생기는 1970-01-01 혼입."""
    base = _make_base(tmp_path, _spread(2025, 60) + ["1970-01-01"], meta=META_2025)
    assert _schema(_run_fr02(base))[0] == "실패"


def test_all_dates_1970_detected(tmp_path):
    """전건이 1970(로더 오해석) — 독립 근거와 대조되어 실패해야 한다."""
    base = _make_base(tmp_path, _spread(1970, 60), meta=META_2025)
    assert _schema(_run_fr02(base))[0] == "실패"


def test_prior_period_comparatives_mixed_detected(tmp_path):
    """전기 비교자료가 섞이면 당기 기간 밖으로 검출돼야 한다."""
    base = _make_base(tmp_path, _spread(2025, 60) + _spread(2024, 20), meta=META_2025)
    assert _schema(_run_fr02(base))[0] == "실패"


# ═════════ 4. 비달력 회계연도 ═════════

def test_non_calendar_fiscal_year_passes(tmp_path):
    """2024-07-01~2025-06-30 회계연도(설정 파일로 지정)."""
    base = _make_base(tmp_path, _spread(2024, 60, start_month=7),
                      config={"fy_start": "2024-07-01", "fy_end": "2025-06-30"})
    res = _run_fr02(base)
    assert _schema(res)[0] == "통과", f"비달력연도가 실패: {_schema(res)[1]}"
    assert _period(res)[0] == "통과"


def test_non_calendar_fiscal_year_typo_detected(tmp_path):
    """비달력연도에서 기간 밖 1건도 검출돼야 한다."""
    base = _make_base(tmp_path, _spread(2024, 60, start_month=7) + ["2025-07-15"],
                      config={"fy_start": "2024-07-01", "fy_end": "2025-06-30"})
    assert _schema(_run_fr02(base))[0] == "실패"


def test_non_calendar_via_env(tmp_path):
    """환경변수로도 비달력연도를 지정할 수 있다."""
    base = _make_base(tmp_path, _spread(2024, 60, start_month=4))
    res = _run_fr02(base, GL_FY_START="2024-04-01", GL_FY_END="2025-03-31")
    assert _schema(res)[0] == "통과"


# ═════════ 5. 정상 케이스(연도 하드코딩 금지) ═════════

@pytest.mark.parametrize("year", [2023, 2024, 2025, 2026])
def test_any_calendar_year_passes_with_basis(tmp_path, year):
    """근거가 주어지면 어느 연도든 정상 통과해야 한다."""
    base = _make_base(tmp_path, _spread(year, 60), meta={"fy_year": year})
    assert _schema(_run_fr02(base))[0] == "통과", f"{year}년 원장이 실패"
