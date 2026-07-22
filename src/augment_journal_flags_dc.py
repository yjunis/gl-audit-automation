# -*- coding: utf-8 -*-
"""부정위험 전표(journal_flags.json)에 각 전표 플래그 계정의 실제 차변/대변(account_dc)을 붙인다.

원리: 전표번호+계정명으로 합성 원장(gl_clean)에 조인해 그 전표에서 해당 계정 라인의
      실제 차변합-대변합(net)을 구한다. net>0 = 차변, net<0 = 대변. 자연방향 추론이 아니라
      원장의 실제 분개 방향(지상 진실). 상대계정은 반대편.

안전: 합성 데모 원장(web/_build/std_d909daabef)만 읽는다. 실클라이언트 데이터는 건드리지 않는다.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GL = ROOT / "web" / "_build" / "std_d909daabef" / "data" / "gl_clean.csv"
JF = ROOT / "portfolio" / "data" / "journal_flags.json"


def main(write: bool) -> int:
    gl = pd.read_csv(GL, dtype={"전표번호": str, "계정코드": str})

    # 안전 재확인 — 검증된 합성 원장(가상제조)만 읽는다. 실데이터 흔적이 있으면 중단.
    # 마커 목록은 커밋 코드에 두지 않고, 있으면 gitignore된 파일에서 읽는다(없으면 점검 생략).
    marker_file = ROOT / "src" / ".data_markers"
    markers = (
        [m.strip() for m in marker_file.read_text(encoding="utf-8").splitlines() if m.strip()]
        if marker_file.exists() else []
    )
    blob = set()
    for c in gl.select_dtypes(include=["object"]).columns:
        blob |= set(gl[c].dropna().astype(str).unique())
    hit = [b for b in markers if any(b in v for v in blob)]
    if hit:
        print(f"[중단] 원장에 실클라이언트 흔적: {hit}")
        return 1

    net = (gl.groupby(["전표번호", "계정명"])["차변"].sum()
           - gl.groupby(["전표번호", "계정명"])["대변"].sum())

    flags = json.loads(JF.read_text(encoding="utf-8"))
    miss, inconsistent = [], []
    for r in flags:
        key = (r["journal_id"], r["account"])
        if key not in net.index:
            miss.append(key)
            r["account_dc"] = None
            continue
        n = float(net.loc[key])
        r["account_dc"] = "차변" if n > 0 else "대변"
        # 정합성: 원장 net 절대값이 export된 금액 절대값과 맞는지(반올림 오차 허용)
        amt = r.get("amount")
        if amt is not None and abs(abs(n) - abs(amt)) > 1:
            inconsistent.append((key, n, amt))

    print(f"전체 {len(flags)}건 · 조인실패 {len(miss)}건 · 금액불일치 {len(inconsistent)}건")
    if miss[:5]:
        print("  조인실패 예:", miss[:5])
    if inconsistent[:5]:
        print("  불일치 예:", inconsistent[:5])
    # 차/대변 분포
    dist = {}
    for r in flags:
        dist[r["account_dc"]] = dist.get(r["account_dc"], 0) + 1
    print("  account_dc 분포:", dist)

    if write and not miss and not inconsistent:
        JF.write_text(json.dumps(flags, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"→ 기록 완료: {JF}")
    elif write:
        print("[미기록] 실패/불일치가 있어 기록하지 않음")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(write="--write" in sys.argv))
