# -*- coding: utf-8 -*-
"""
FR-06 · 원인 설명 에이전트 (감사기준서 520 문단7 / 240 대응)
------------------------------------------------------------
동작:
  1) MCP 클라이언트로 mcp_server.py(GL 감사 서버)에 stdio로 접속
  2) list_flags 도구로 이상 플래그를 받아온다
  3) 플래그마다  query_transactions(근거 전표) + lookup_standard(기준서 근거)를 호출
  4) 모은 증거를 '설명 백엔드'에 넘겨 감사 조서용 설명문 초안을 생성
     - 지금 백엔드: 규칙기반(RuleBasedExplainer) — 이 PC에서 즉시 작동
     - 교체 시   : LocalLLMExplainer(model=...) 한 줄 (Ollama 있는 PC)
  5) reports/fr06_설명.md + data/fr06_explanations.csv 저장

실행: python src/fr06_explain_agent.py
"""
import os
import sys
import json
import asyncio
import pandas as pd
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from explain_backend import RuleBasedExplainer, LocalLLMExplainer

BASE = Path(os.environ.get("GL_BASE") or Path(__file__).resolve().parent.parent)
SERVER = Path(__file__).resolve().parent / "mcp_server.py"
EOK = 100_000_000


def pick_backend():
    """LLM(Ollama)이 있으면 그걸, 없으면 규칙기반으로 자동 선택."""
    llm = LocalLLMExplainer()
    if llm.available:
        print(f"설명 백엔드: {llm.name}  (로컬 LLM 탐지됨)")
        return llm
    be = RuleBasedExplainer()
    print(f"설명 백엔드: {be.name}")
    print("  (로컬 LLM 미탐지 → 규칙기반 사용. Ollama 있는 PC에선 자동으로 LLM 전환)")
    return be


def _keywords(flag, txns):
    """기준서 검색용 키워드 = 위험요소 태그 + 대표 전표 적요."""
    parts = [str(flag.get("위험요소", "")).replace(",", " ")]
    for t in txns[:2]:
        parts.append(str(t.get("적요", "")))
    return " ".join(parts)


def _text(call_result):
    """MCP 도구 호출 결과(JSON 문자열)를 파이썬 dict로."""
    return json.loads(call_result.content[0].text)


async def run():
    explainer = pick_backend()
    srv_env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    if os.environ.get("GL_BASE"):
        srv_env["GL_BASE"] = os.environ["GL_BASE"]   # 서버도 같은 회사 폴더를 보게 전달
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], env=srv_env)

    memos, records = [], []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print("MCP 서버 접속 완료 · 노출 도구:", [t.name for t in tools])

            flags = _text(await session.call_tool("list_flags", {}))["flags"]
            print(f"검토 대상 플래그 {len(flags)}건 → 증거 수집·설명 생성\n")

            for f in flags:
                # (도구 1) 근거 전표
                tx = _text(await session.call_tool(
                    "query_transactions",
                    {"account": f["계정명"], "month": f["월"], "top_n": 3}))["rows"]
                # (도구 2) 기준서 근거
                refs = _text(await session.call_tool(
                    "lookup_standard", {"keywords": _keywords(f, tx)}))["refs"]
                # 설명 백엔드로 생성
                memo = explainer.explain(f, tx, refs)
                memos.append(memo)
                records.append({
                    "순위": f["순위"], "계정명": f["계정명"], "월": f["월"],
                    "등급": f["등급"], "위험점수": f["위험점수"],
                    "기준서근거": "; ".join(r["id"] for r in refs),
                    "설명초안": memo})
                print(memo + "\n")

    # 저장
    (BASE / "reports" / "fr06_설명.md").write_text(
        "# FR-06 이상 원인 설명 (감사 조서 초안)\n\n"
        f"- 설명 백엔드: {explainer.name}\n"
        f"- 대상 플래그: {len(memos)}건\n\n" + "\n\n".join(memos),
        encoding="utf-8")
    pd.DataFrame(records).to_csv(
        BASE / "data" / "fr06_explanations.csv", index=False, encoding="utf-8-sig")

    print("-" * 62)
    print("저장:", BASE / "reports" / "fr06_설명.md")
    print("저장:", BASE / "data" / "fr06_explanations.csv")


if __name__ == "__main__":
    asyncio.run(run())
