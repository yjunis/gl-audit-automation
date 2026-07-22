# -*- coding: utf-8 -*-
"""
FR-10 · 계정 분류 검토·수정 화면 (인적 최종통제 / 감사기준서 200·240·315)
------------------------------------------------------------
자동 분류(fr10_classify.py)는 '초안'이다. 감사인이 이 화면에서 드롭다운으로
표준항목을 교정하면 → data/fr10_overrides.json 에 저장(=학습) → 재분류·재검산한다.

실행:  streamlit run src/fr10_review_app.py
저사양 배려: CSV 한 장만 읽는 가벼운 표 편집기(무거운 계산 없음).
"""
import os
import sys
import json
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st

SRC = Path(__file__).resolve().parent
BASE = Path(os.environ.get("GL_BASE") or SRC.parent)
MAP = BASE / "data" / "fr10_account_map.csv"
OVR = BASE / "data" / "fr10_overrides.json"
DICT = json.loads((SRC / "account_dict.json").read_text(encoding="utf-8"))
ITEMS = [c["표준항목"] for c in DICT["categories"]] + ["미분류"]

st.set_page_config(page_title="FR-10 계정 분류 검토", layout="wide")
st.title("✏️ 계정 분류 검토·수정")
st.caption("자동 분류는 초안입니다. 틀린 항목을 드롭다운으로 고치고 **저장 & 재검산**을 누르세요. "
           "수정은 `fr10_overrides.json`에 기억되어 다음 실행부터 자동 반영됩니다. (감사기준서 200·240·315)")


def run_classify():
    env = {**os.environ, "GL_BASE": str(BASE),
           "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, str(SRC / "fr10_classify.py")],
                          env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


if not MAP.exists():
    st.warning("분류 결과가 없습니다. 먼저 자동 분류를 실행하세요.")
    if st.button("▶ 자동 분류 실행"):
        with st.spinner("분류 중..."):
            run_classify()
        st.rerun()
    st.stop()

df = pd.read_csv(MAP, dtype={"계정코드": str})

# ── 상단 요약
c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 계정", f"{len(df)}개")
c2.metric("미분류", f"{int((df['표준항목'] == '미분류').sum())}개")
c3.metric("추정(저확신)", f"{int((df['확신도'] == '추정').sum())}개")
c4.metric("성격 불일치", f"{int((df['성격점검'] == '⚠️불일치').sum())}개")

need = df[(df["표준항목"] == "미분류") | (df["확신도"] == "추정")
          | (df["성격점검"] == "⚠️불일치")]
if len(need):
    with st.expander(f"⚠️ 검토 권장 계정 {len(need)}개 (미분류·추정·성격불일치)", expanded=True):
        st.dataframe(need[["계정코드", "계정명", "표준항목", "확신도", "성격점검", "net(억)"]],
                     use_container_width=True, hide_index=True)

# ── 편집 표: 표준항목만 드롭다운으로 수정
st.subheader("전체 계정 (표준항목 열을 클릭해 수정)")
only_review = st.checkbox("검토 권장 계정만 보기", value=False)
view = need if only_review else df
edited = st.data_editor(
    view[["계정코드", "계정명", "표준항목", "대분류", "확신도", "성격점검", "net(억)", "건수"]],
    use_container_width=True, hide_index=True, height=520,
    disabled=["계정코드", "계정명", "대분류", "확신도", "성격점검", "net(억)", "건수"],
    column_config={"표준항목": st.column_config.SelectboxColumn(
        "표준항목(수정)", options=ITEMS, required=True)},
    key="editor")

# ── 저장 & 재검산
if st.button("💾 저장 & 재검산", type="primary"):
    base_map = df.set_index("계정코드")["표준항목"].to_dict()
    ov = {}
    if OVR.exists():
        try:
            ov = json.loads(OVR.read_text(encoding="utf-8"))
        except Exception:
            ov = {}
    changed = 0
    for _, r in edited.iterrows():
        code, new = str(r["계정코드"]), r["표준항목"]
        if new != base_map.get(code):
            ov[code] = new
            changed += 1
    if changed == 0:
        st.info("변경된 항목이 없습니다.")
    else:
        OVR.write_text(json.dumps(ov, ensure_ascii=False, indent=2), encoding="utf-8")
        with st.spinner(f"{changed}건 저장 후 재분류·재검산 중..."):
            res = run_classify()
        if res.returncode == 0:
            st.success(f"{changed}건 반영 완료. 아래는 갱신된 검산 결과입니다.")
            tail = "\n".join(l for l in res.stdout.splitlines()
                             if any(k in l for k in ("자산순", "미분류 net", "시산표", "확신도 분포")))
            st.code(tail or res.stdout[-800:])
            st.rerun()
        else:
            st.error("재분류 실패:\n" + (res.stderr or "")[-800:])

st.divider()
st.caption(f"저장 위치: `{OVR}` · 대상 폴더 GL_BASE=`{BASE}`")
