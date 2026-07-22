import type { Metadata } from "next";
import Link from "next/link";
import DashboardClient from "@/components/DashboardClient";
import Gauge from "@/components/Gauge";
import { accountRisks, eok, fraudScores, monthLabel, summary, validation } from "@/lib/data";

export const metadata: Metadata = {
  title: "대시보드 | GL 감사 자동화",
  description:
    "가상제조(주) 2025년 총계정원장 전수 분석 결과 — 이상 계정 목록, 부정위험 전표 우선순위, Beneish M·Altman Z′.",
};

// KPI 4장 — Streamlit 대시보드와 같은 항목·순서.
const bq = summary.balance_quality;
const KPI = [
  { label: "계정 수", value: summary.account_count.toLocaleString("ko-KR"), sub: "" },
  { label: "분개 줄 수", value: summary.journal_count.toLocaleString("ko-KR"), sub: "" },
  { label: "대차 품질", value: bq.grade, sub: `오차율 ${(bq.ratio * 100).toFixed(2)}%` },
  {
    label: "성과중요성",
    value:
      summary.performance_materiality != null
        ? `${eok(summary.performance_materiality)}억`
        : "-",
    sub: "매출 × 0.5% × 75%",
  },
];

export default function DashboardPage() {
  const { altman_z: z, beneish_m: m } = fraudScores.models;
  const ov = validation.overall;

  // 무결성 검증표와 M·Z 게이지는 서버에서 렌더해 탭(클라이언트 컴포넌트)에 넘긴다.
  // 탭 전환에만 클라이언트 상태가 필요하고, 이 두 섹션 자체는 정적이기 때문.
  const validationSlot = (
      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="sec-title">데이터 무결성 검증</h2>
          {ov && (
            <span
              className={`rounded-full px-3 py-1 text-xs font-extrabold ${
                ov.passed ? "bg-green-50 text-green-700" : "bg-red-50 text-danger"
              }`}
            >
              {ov.passed ? "통과" : "실패"} · 검사 {ov.total_checks}개 · 오류{" "}
              {ov.error_fail_count}건 · 경고 {ov.warning_count}건
            </span>
          )}
        </div>
        <p className="cap mt-1">
          분석 전 기본 무결성 검사 · 원장 모집단의 완전성이나 감사증거의 충분성을 이것만으로
          보장하지는 않습니다(감사기준서 500 참고)
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">
              원장 무결성 검사 결과 목록. 구분, 검사 항목, 결과, 설명 순입니다.
            </caption>
            <thead>
              <tr className="border-b border-line text-left text-xs font-bold text-muted">
                <th scope="col" className="py-2 pr-3">구분</th>
                <th scope="col" className="py-2 pr-3">검사 항목</th>
                <th scope="col" className="py-2 pr-3">결과</th>
                <th scope="col" className="py-2 pr-3">설명</th>
              </tr>
            </thead>
            <tbody>
              {validation.checks.map((c, i) => {
                const bad = c.result !== "통과" && c.result !== "PASS";
                return (
                  <tr key={`${c.item}-${i}`} className="border-b border-line/60">
                    <td className="py-2 pr-3">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[0.65rem] font-extrabold ${
                          c.level === "ERROR"
                            ? "bg-red-50 text-danger"
                            : c.level === "WARN"
                              ? "bg-amber-50 text-amber-700"
                              : "bg-surface text-muted"
                        }`}
                      >
                        {c.level}
                      </span>
                    </td>
                    <th scope="row" className="py-2 pr-3 text-left font-bold text-ink">
                      {c.item}
                    </th>
                    <td
                      className={`py-2 pr-3 font-bold ${bad ? "text-danger" : "text-green-700"}`}
                    >
                      {c.result}
                      {c.count != null && c.count > 0 && (
                        <span className="ml-1 font-normal text-muted">({c.count}건)</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted">{c.description ?? "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
  );

  const signalsSlot = (
      <section>
        <h2 className="sec-title mb-1">재무제표 수준 신호</h2>
        <p className="cap mb-4">
          학술 계량모형 기반 참고 지표 · 분식·도산을 확정하지 않으며, 선을 넘었다는 것은 “왜 그런지
          설명을 들어봐야 한다”는 뜻
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <Gauge
            title={m.name}
            value={m.score}
            min={-4}
            max={1}
            judgement={m.zone ?? undefined}
            zones={[
              { to: -2.22, color: "bg-success", label: "보수선 아래 (정상)" },
              { to: -1.78, color: "bg-warning", label: "보수선~표준선 (주의)" },
              { to: 1, color: "bg-danger", label: "표준선 초과 (분식 신호)" },
            ]}
            markers={[
              { at: -2.22, label: "-2.22" },
              { at: -1.78, label: "-1.78" },
            ]}
            caption={`${m.note} · 매출채권 회전(DSRI ${m.indicators?.DSRI}), 발생액(TATA ${m.indicators?.TATA}) 등 8개 지표를 합성한 값입니다. 본 도구가 채택한 임계값을 넘었다는 것은 추가 검토 신호라는 뜻이며, 분식 여부를 판정하지 않습니다.`}
          />
          <Gauge
            title={z.name}
            value={z.score}
            min={0}
            max={5}
            judgement={z.zone ?? undefined}
            zones={[
              { to: 1.23, color: "bg-danger", label: "위험 <1.23" },
              { to: 2.9, color: "bg-warning", label: "회색 1.23~2.9" },
              { to: 5, color: "bg-success", label: "안전 >2.9" },
            ]}
            markers={[
              { at: 1.23, label: "1.23" },
              { at: 2.9, label: "2.9" },
            ]}
            caption={`${z.note} · 운전자본·이익잉여금·영업이익·자본구조·자산회전 5개 비율의 가중합입니다. 상장기업용 원형 Z가 아니라 비상장 제조기업용 Z′ 모형이라 임계값이 다르며, 업종·규모가 다르면 적용에 한계가 있습니다. 계속기업 가정 검토(감사기준서 570)의 보조 신호로만 쓰며, 이 점수 하나로 계속기업 결론을 대신하지 않습니다.`}
          />
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted">⚠️ {fraudScores.disclaimer}</p>
      </section>
  );

  // 3초 요약 — 문장 하나로 "어디가 위험한가"를 끝낸다(Streamlit 대시보드와 같은 구성).
  const top = accountRisks[0];
  const hasHigh = summary.high_grade_variances > 0;

  return (
    <div className="container-page py-6 md:py-8">
      {/* 히어로 */}
      <div className="hero">
        <div className="hero-eyebrow">GL 감사 대시보드</div>
        <div className="hero-title">{summary.company}</div>
        <div className="hero-sub">
          {summary.period}년 · 기준 {summary.method} · 합성 데이터 데모
        </div>
      </div>

      {/* 보고서(PDF) 안내 링크 */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border border-line bg-surface px-4 py-3">
        <span className="text-sm text-ink">
          이 분석 결과를 <b>한 장의 PDF 보고서</b>로 저장하거나 인쇄할 수 있습니다.
        </span>
        <Link href="/report" className="btn-primary shrink-0">
          보고서(PDF)로 보기 →
        </Link>
      </div>

      {/* KPI */}
      <div className="kpi-row">
        {KPI.map((k) => (
          <div key={k.label} className="kpi">
            <div className="kpi-label">{k.label}</div>
            <div className="kpi-val">{k.value}</div>
            {k.sub && <div className="kpi-sub">{k.sub}</div>}
          </div>
        ))}
      </div>

      {/* 3초 요약 */}
      <div className="glance" style={{ borderLeftColor: hasHigh ? "#C4231A" : "#C4C4CD" }}>
        {top ? (
          <>
            <b>{summary.account_count}개 계정</b> 중 <b>{summary.flagged_accounts}개</b>에서 이상{" "}
            <b>{summary.variance_flags}건</b> · 대차 {bq.grade} · 최우선{" "}
            <b>{top.account}</b> ({monthLabel(top.worst_month, false)} {top.worst_direction}, 편차{" "}
            {eok(top.worst_deviation, true)}억)
          </>
        ) : (
          <>이상 없음 — 분석적 절차에서 검토 우선 항목이 발견되지 않았습니다. (대차 {bq.grade})</>
        )}
      </div>

      <DashboardClient validationSlot={validationSlot} signalsSlot={signalsSlot} />
    </div>
  );
}
