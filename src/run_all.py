# -*- coding: utf-8 -*-
"""
다회사 배치 실행기 (원클릭 파이프라인)
------------------------------------------------------------
data/ 의 계정별원장 엑셀들을 회사별로 각각 처리한다.

  파일마다:
    1) 적응형 로더로 표준 원장(gl_clean.csv)·시산표(trial_balance.csv) 생성
    2) output/<회사>/ 폴더에 저장
    3) FR-02→FR-05 분석 파이프라인을 그 폴더 대상으로 실행(실패해도 다음 단계/회사로)
    4) 대차일치 기반 '데이터 품질 점수' 부여
  마지막: output/_실행요약.md 에 회사별 성적표 + 성공/실패 기록

핵심: '실패 격리' — 한 회사가 깨져도 전체는 멈추지 않고 사유를 남긴다.

실행:  python src/run_all.py
"""
import os
import re
import sys
import glob
import json
import shutil
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adaptive_loader import load_ledger

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUTROOT = ROOT / "output"
EOK = 100_000_000
MAX_MB = 100                       # 이보다 큰 파일은 이 PC 메모리 초과 위험 → 건너뜀
STEPS = [("FR-02 검증", "fr02_validate.py"),
         ("FR-03 기대치", "fr03_expectation.py"),
         ("FR-04 플래깅", "fr04_flagging.py"),
         ("FR-05 이상탐지", "fr05_anomaly.py"),
         ("FR-09 부정스크리닝", "fraud_screen.py"),
         ("FR-10 계정분류", "fr10_classify.py")]


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|]', "_", str(s)).strip()
    return s[:40] or "회사"


def balance_grade(d, c):
    diff = abs(d - c)
    ratio = diff / max(d, 1)
    if diff < 1:
        return "✅ 완벽", ratio
    if ratio < 0.001:
        return "🟢 사실상일치", ratio
    if ratio < 0.01:
        return "🟡 근접", ratio
    return "🔴 검토필요", ratio


def run_steps(cdir):
    env = {**os.environ, "GL_BASE": str(cdir),
           "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "MPLBACKEND": "Agg"}
    out = []
    for label, script in STEPS:
        try:
            r = subprocess.run([sys.executable, str(SRC / script)], env=env,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            if r.returncode == 0:
                out.append((label, "✅", ""))
            else:
                tail = (r.stderr or "").strip().splitlines()
                out.append((label, "❌", tail[-1][:70] if tail else "오류"))
        except subprocess.TimeoutExpired:
            out.append((label, "⏱️", "시간초과(900s)"))
        except Exception as e:
            out.append((label, "❌", f"{type(e).__name__}: {str(e)[:50]}"))
    return out


def main():
    files = sorted(f for f in glob.glob(str(ROOT / "data" / "*.xls*"))
                   if "분개장" not in os.path.basename(f))
    OUTROOT.mkdir(exist_ok=True)
    rows, used = [], set()

    for f in files:
        name = os.path.basename(f)
        mb = os.path.getsize(f) / 1e6
        print(f"\n{'='*66}\n▶ {name}  ({mb:.0f}MB)", flush=True)

        if mb > MAX_MB:
            print(f"  건너뜀: {mb:.0f}MB — 이 PC 메모리 초과 위험", flush=True)
            rows.append(dict(파일=name, 회사="-", 구조="-", 계정="-", 행수="-",
                             품질="⏭️ 건너뜀(대용량)", 단계="-"))
            continue
        try:
            r = load_ledger(f)                        # ── 적응형 로드
        except Exception as e:
            print(f"  ❌ 로드 실패: {type(e).__name__}: {e}", flush=True)
            rows.append(dict(파일=name, 회사="-", 구조="-", 계정="-", 행수="-",
                             품질=f"❌ 로드실패({type(e).__name__})", 단계="-"))
            continue

        m = r["meta"]
        cname = safe_name(m["company"])
        while cname in used:
            cname += "_2"
        used.add(cname)
        cdir = OUTROOT / cname
        (cdir / "data").mkdir(parents=True, exist_ok=True)
        (cdir / "reports").mkdir(parents=True, exist_ok=True)
        r["gl"].to_csv(cdir / "data" / "gl_clean.csv", index=False, encoding="utf-8-sig")
        r["tb"].to_csv(cdir / "data" / "trial_balance.csv", index=False, encoding="utf-8-sig")
        # FR-02 회계기간 판정 근거(원장 날짜와 독립) — 파일명에서 찾은 연도만 담긴다.
        (cdir / "data" / "ledger_meta.json").write_text(
            json.dumps({k: m[k] for k in ("company", "layout", "fy_year")},
                       ensure_ascii=False), encoding="utf-8")

        grade, ratio = balance_grade(m["debit"], m["credit"])
        print(f"  회사={m['company']} | {m['layout']} | 계정 {m['n_accounts']} | "
              f"행 {m['n_rows']:,} | 대차 {grade}(오차율 {ratio:.4%})", flush=True)

        steps = run_steps(cdir)                       # ── 분석 파이프라인(실패 격리)
        for lbl, mk, msg in steps:
            print(f"    {mk} {lbl}" + (f" — {msg}" if msg else ""), flush=True)

        rows.append(dict(파일=name, 회사=m["company"], 구조=m["layout"],
                         계정=m["n_accounts"], 행수=f"{m['n_rows']:,}",
                         품질=f"{grade} ({ratio:.3%})",
                         단계=" ".join(f"{s[1]}{s[0][:5]}" for s in steps),
                         폴더=str(cdir)))

    # ── 실행 요약 마크다운
    md = ["# 다회사 배치 실행 요약\n",
          f"- 대상 파일: {len(files)}개 · 출력: `output/<회사>/`\n",
          "| 파일 | 회사 | 구조 | 계정 | 행수 | 대차품질 | 분석단계 |",
          "|---|---|---|---:|---:|---|---|"]
    for x in rows:
        md.append(f"| {x['파일'][:26]} | {x.get('회사','-')} | {x.get('구조','-')} | "
                  f"{x['계정']} | {x['행수']} | {x['품질']} | {x.get('단계','-')} |")
    md += ["\n## 범례",
           "- 대차품질: ✅완벽 / 🟢사실상일치(<0.1%) / 🟡근접(<1%) / 🔴검토필요 / ⏭️건너뜀 / ❌로드실패",
           "- 분석단계: ✅성공 ❌실패 ⏱️시간초과 (FR-02 검증→FR-05 이상탐지)",
           "- 🔴/❌ 회사는 형식이 특수하여 수치 재확인이 필요합니다(결과는 생성되나 신뢰도 주의)."]
    (OUTROOT / "_실행요약.md").write_text("\n".join(md), encoding="utf-8")

    print(f"\n{'='*66}\n배치 완료 · 회사 {len([x for x in rows if x.get('회사','-')!='-'])}개 처리")
    print("요약:", OUTROOT / "_실행요약.md")
    print("출력 폴더:", OUTROOT)


if __name__ == "__main__":
    main()
