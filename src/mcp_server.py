# -*- coding: utf-8 -*-
"""
FR-06 · GL 감사 MCP 서버 (FastMCP)
------------------------------------------------------------
'도구(tool)'를 표준 MCP 프로토콜로 노출한다. 어떤 MCP 클라이언트(우리 에이전트,
Claude Desktop, ollmcp 등)든 이 서버에 접속해 아래 도구를 호출할 수 있다.

노출 도구:
  · list_flags()                         : FR-04 이상 플래그 목록
  · query_transactions(account, month)   : 특정 계정·월의 큰 분개(적요·거래처·금액)
  · lookup_standard(keywords)            : 이상 특성에 맞는 감사기준서 근거 요약
  · get_expectation(account)             : FR-03 월별 기대구간·실제값

실행(독립 서버로): python src/mcp_server.py   ← stdio 전송으로 대기
※ mcp 1.28 + pydantic 2.10 호환을 위해 도구에 '반환 타입 주석'은 달지 않는다.
"""
import os
import pandas as pd
from pathlib import Path
from mcp.server.fastmcp import FastMCP

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
srv = FastMCP("gl-audit")

# 원장은 서버 기동 시 1회만 로드(도구 호출마다 다시 안 읽도록 캐시)
_GL = pd.read_csv(BASE / "data" / "gl_clean.csv",
                  dtype={"계정코드": str}, parse_dates=["전표일자"])
_GL["월"] = _GL["전표일자"].dt.to_period("M").astype(str)

# ---- 감사기준서 로컬 지식베이스 (키워드 → 근거 요약) --------------------
# 실제 프로덕션에선 이 도구를 ifrs MCP 등 외부 근거 서버로 교체 가능.
_KB = [
    {"id": "감사기준서 520 문단5", "제목": "분석적 절차 — 유의적 차이 조사",
     "키워드": ["분석", "차이", "기대", "증감", "추세", "변동"],
     "요약": "기대치와 실제의 유의적 차이는 경영진 질문 및 추가 감사절차로 원인을 규명해야 한다(520.5d)."},
    {"id": "감사기준서 240 문단32", "제목": "부적절한 수정분개 검토(경영진 통제 무력화)",
     "키워드": ["역분개", "취소", "수정분개", "결산", "기말", "대체", "정리", "경영진"],
     "요약": "기말·비경상 수정분개는 경영진의 통제 무력화·부정 위험이 높아 표본을 추출해 적정성을 검토한다."},
    {"id": "감사기준서 315/표시·분류", "제목": "재분류·표시 적정성",
     "키워드": ["매출차감", "재분류", "분류", "표시", "총액", "순액"],
     "요약": "비용을 매출 차감으로 처리하는 등 재분류는 총액/순액 표시 적정성과 계정 성격을 확인해야 한다."},
    {"id": "감사기준서 540", "제목": "회계추정의 감사",
     "키워드": ["충당", "평가", "상각", "대손", "추정", "계리", "손상"],
     "요약": "충당금·평가·상각 등 회계추정은 가정의 합리성과 산정 근거를 검토한다(540)."},
    {"id": "자본거래 유의사항", "제목": "배당·자본거래 검토",
     "키워드": ["배당", "자본", "감자", "증거금", "잉여금"],
     "요약": "배당·자본거래는 이사회/주총 결의 등 승인 근거와 회계처리 시점을 확인한다."},
]


@srv.tool()
def list_flags():
    """FR-04가 산출한 감사 검토 대상(이상 플래그) 목록 전체를 돌려준다."""
    f = pd.read_csv(BASE / "data" / "fr04_flags.csv", dtype={"계정코드": str})
    return {"count": len(f), "flags": f.to_dict(orient="records")}


@srv.tool()
def query_transactions(account: str, month: str, top_n: int = 5):
    """특정 계정명·월(YYYY-MM)에서 금액이 큰 분개 top_n건의 적요·거래처·금액을 돌려준다."""
    d = _GL[(_GL["계정명"] == account) & (_GL["월"] == month)].copy()
    if d.empty:
        return {"account": account, "month": month, "rows": []}
    d["금액"] = d["차변"] - d["대변"]
    d = d.reindex(d["금액"].abs().sort_values(ascending=False).index).head(top_n)
    has_doc = "전표번호" in d.columns
    rows = [{"전표번호": (str(r["전표번호"]) if has_doc else ""),
             "적요": str(r["적요"]),
             "거래처": (None if pd.isna(r["거래처명"]) else str(r["거래처명"])),
             "금액": float(r["금액"])} for _, r in d.iterrows()]
    return {"account": account, "month": month, "rows": rows}


@srv.tool()
def lookup_standard(keywords: str):
    """공백으로 구분된 키워드에 맞는 감사기준서 근거 요약(1~3건)을 돌려준다."""
    kws = [k for k in keywords.replace(",", " ").split() if k]
    scored = []
    for e in _KB:
        hit = sum(any(k in kw or kw in k for kw in kws) for k in e["키워드"])
        if hit:
            scored.append((hit, e))
    scored.sort(key=lambda x: -x[0])
    refs = [{"id": e["id"], "제목": e["제목"], "요약": e["요약"]} for _, e in scored[:3]]
    if not refs:  # 못 찾으면 기본으로 520 제공
        e = _KB[0]
        refs = [{"id": e["id"], "제목": e["제목"], "요약": e["요약"]}]
    return {"keywords": kws, "refs": refs}


@srv.tool()
def get_expectation(account: str):
    """FR-03 기대치 엔진이 만든 특정 계정의 월별 실제값·기대구간을 돌려준다."""
    e = pd.read_csv(BASE / "data" / "fr03_expectations.csv", dtype={"계정코드": str})
    d = e[e["계정명"] == account][["월", "월값", "기대중앙값", "하한", "상한", "이상여부"]]
    return {"account": account, "series": d.to_dict(orient="records")}


if __name__ == "__main__":
    srv.run()  # stdio 전송으로 대기(클라이언트가 subprocess로 띄움)
