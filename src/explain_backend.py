# -*- coding: utf-8 -*-
"""
FR-06 · 설명 '두뇌' (교체 가능한 추론 백엔드)
------------------------------------------------------------
에이전트가 MCP로 모아온 증거(플래그 + 전표 + 기준서)를 받아 '설명문 초안'을 만든다.
백엔드는 같은 인터페이스(explain)를 공유하므로 한 줄 교체로 갈아끼운다.

  · RuleBasedExplainer : LLM 없이 규칙/템플릿으로 즉시 생성 (지금 사용, 이 PC에서 작동)
  · LocalLLMExplainer  : 로컬 LLM(Ollama)로 생성 (사양 좋은 PC에서 활성화) — 스텁

교체 예:
    # explainer = RuleBasedExplainer()
    explainer = LocalLLMExplainer(model="qwen2.5:14b")   # 이 한 줄만 바꾸면 됨
"""
from __future__ import annotations

EOK = 100_000_000


def driver_txns(gl_sub, 자연방향, 급증, top=5):
    """편차 '방향'을 실제로 만든(그 방향으로 민) 전표를 자연방향 기준으로 골라 반환.
    - 자연방향='대변성격'이면 기여=대변-차변, 아니면 차변-대변 (= FR-03 '월값'과 같은 부호 체계)
    - 급증이면 기여>0(증가시킨 전표), 급감이면 기여<0(감소시킨 전표) 중에서 크기순으로.
    이렇게 하면 '절댓값 최대'를 기계적으로 집지 않고 이상 방향과 논리적으로 일치한다."""
    d = gl_sub.copy()
    d["기여"] = (d["대변"] - d["차변"]) if 자연방향 == "대변성격" else (d["차변"] - d["대변"])
    drivers = d[d["기여"] > 0] if 급증 else d[d["기여"] < 0]
    if len(drivers) == 0:                       # 방향 일치 전표가 없으면 전체에서
        drivers = d
    return drivers.reindex(drivers["기여"].abs().sort_values(ascending=False).index).head(top)


def _cause(txns):
    """상위 전표의 적요/거래처로 '추정 원인' 문장을 만든다."""
    if not txns:
        return "해당 월의 개별 전표를 특정하지 못했습니다."
    top = txns[0]
    text = " ".join(str(t.get("적요", "")) for t in txns)
    cp = top.get("거래처") or "거래처 미상"
    amt = top.get("금액", 0) / EOK
    if "매출차감" in text or "매출 차감" in text:
        return (f"'{cp}' 관련 비용({amt:+.1f}억)을 비용 계정이 아니라 '매출 차감'으로 "
                f"처리한 재분류가 주된 원인으로 보입니다.")
    if "취소" in text or "역분개" in text:
        return f"전월·전기 분개를 취소/역분개(대표: {cp}, {amt:+.1f}억)한 것으로 보입니다."
    if "배당" in text:
        return f"배당금 확정·지급 관련 분개(대표: {cp}, {amt:+.1f}억)가 원인으로 보입니다."
    if any(k in text for k in ["결산", "대체", "정리", "수정분개"]):
        return f"기말 결산 수정·계정 대체 분개(대표: {cp}, {amt:+.1f}억)가 원인으로 보입니다."
    if any(k in text for k in ["충당", "평가", "상각", "대손", "계리", "손상"]):
        return f"회계추정(충당금·평가·상각 등) 반영 분개(대표: {cp}, {amt:+.1f}억)가 원인으로 보입니다."
    return f"'{cp}'에 대한 대형 거래({amt:+.1f}억)가 주된 원인으로 보입니다."


def _procedure(flag, txns):
    """위험요소에 맞는 권고 감사절차."""
    tags = str(flag.get("위험요소", ""))
    text = " ".join(str(t.get("적요", "")) for t in txns)
    if "매출차감" in text or "재분류" in tags:
        return "계약·정산서로 거래 성격을 확인하고, 총액/순액 표시 및 계정 분류 적정성을 검토."
    if "역분개" in tags or any(k in text for k in ["취소", "역분개", "결산", "대체"]):
        return "기말 수정분개 표본을 입수해 승인권자·근거를 확인하고 상대 계정과 대사."
    return "관련 증빙(계약·세금계산서·이체증)을 입수하고 담당자에게 질문, 상대 계정을 추적."


class RuleBasedExplainer:
    """LLM 없이 규칙·템플릿으로 감사 설명문 초안을 생성."""
    name = "규칙기반 설명기 (LLM 없이 즉시 실행)"

    def explain(self, flag, txns, refs):
        acct, month = flag["계정명"], flag["월"]
        direction = flag["방향"]
        real = flag["월값"] / EOK
        exp = flag["기대중앙값"] / EOK
        dev = flag["편차"] / EOK
        z = flag["로버스트z"]
        grade = flag["등급"]
        score = flag["위험점수"]

        cause = _cause(txns)
        proc = _procedure(flag, txns)
        ref_line = "; ".join(f"{r['id']}({r['제목']})" for r in refs)
        ref_detail = refs[0]["요약"] if refs else ""

        lines = [
            f"### {grade}  {acct} · {month}  (위험점수 {score})",
            f"- **현상**: {acct}이(가) {month}에 기대 {exp:,.1f}억 대비 크게 {direction}하여 "
            f"{real:,.1f}억을 기록(편차 {dev:+,.1f}억, 수정z {z:.1f}).",
            f"- **추정 원인**: {cause}",
            f"- **감사 시사점**: {ref_detail} (근거: {ref_line})",
            f"- **권고 절차**: {proc}",
        ]
        if txns:
            lines.append("- **근거 전표(상위)**:")
            for t in txns[:3]:
                cp = t.get("거래처") or "-"
                doc = str(t.get("전표번호") or "").strip()
                docs = f"[{doc}] " if doc and doc.lower() != "nan" else ""
                lines.append(f"    · {docs}{t['금액']/EOK:+,.1f}억  {str(t['적요'])[:30]}  /{cp}")
        return "\n".join(lines)


class LocalLLMExplainer:
    """
    로컬 LLM(Ollama)로 설명문 생성 — 사양 좋은 PC에서 활성화하는 백엔드(스텁).
    이 PC(RAM 3.9GB)에서는 모델 구동이 불가하여 호출 시 안내 후 규칙기반으로 위임.
    """
    name = "로컬 LLM 설명기 (Ollama)"

    def __init__(self, model="qwen2.5:14b", host="http://localhost:11434"):
        self.model = model
        self.host = host
        self._fallback = RuleBasedExplainer()
        self.available = self._check()

    def _check(self):
        try:
            import httpx
            httpx.get(self.host + "/api/tags", timeout=1.5)
            return True
        except Exception:
            return False

    def _prompt(self, flag, txns, refs):
        tx = "\n".join(f"- {t['금액']/EOK:+.1f}억 {t['적요']} /{t.get('거래처')}" for t in txns)
        rf = "\n".join(f"- {r['id']}: {r['요약']}" for r in refs)
        return (
            "당신은 회계감사 보조원이다. 아래 이상 항목의 원인을 감사 조서용으로 "
            "간결히(4줄 이내) 설명하라. 근거 전표와 기준서를 인용하라.\n"
            f"[이상] {flag['계정명']} {flag['월']} 편차 {flag['편차']/EOK:+.1f}억 "
            f"(실제 {flag['월값']/EOK:.1f}억 vs 기대 {flag['기대중앙값']/EOK:.1f}억)\n"
            f"[전표]\n{tx}\n[기준서]\n{rf}\n")

    def explain(self, flag, txns, refs):
        if not self.available:      # 서버/모델 없으면 규칙기반으로 안전 위임
            return self._fallback.explain(flag, txns, refs)
        import httpx
        r = httpx.post(self.host + "/api/generate", timeout=120,
                       json={"model": self.model, "prompt": self._prompt(flag, txns, refs),
                             "stream": False})
        return r.json().get("response", "").strip()
