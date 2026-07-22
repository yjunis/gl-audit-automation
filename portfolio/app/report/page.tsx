import type { Metadata } from "next";
import Link from "next/link";
import AccountDetailChart from "@/components/AccountDetailChart";
import Gauge from "@/components/Gauge";
import PrintButton from "@/components/PrintButton";
import {
  accountRisks,
  driverJournals,
  eok,
  fraudScores,
  gradeColor,
  journalFlags,
  manifest,
  monthLabel,
  monthlyVariances,
  summary,
  validation,
} from "@/lib/data";

export const metadata: Metadata = {
  title: "감사 분석 보고서 | GL 감사 자동화",
  description:
    "가상제조(주) 총계정원장 전수 분석 결과를 한 문서로 정리한 인쇄용 보고서 — 무결성 검증, 이상 계정, 부정위험 전표, 재무제표 신호. 합성 데이터 데모.",
};

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

// 챕터 번호(강조색 사각형) — 섹션 마커
function Marker({ n, title }: { n: string; title: string }) {
  return (
    <div className="mb-3 flex items-center gap-2.5 break-after-avoid">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center bg-brand text-xs font-bold text-on-accent">
        {n}
      </span>
      <h2 className="font-display text-lg font-bold text-ink">{title}</h2>
    </div>
  );
}

export default function ReportPage() {
  const { altman_z: z, beneish_m: m } = fraudScores.models;
  const ov = validation.overall;
  const top = accountRisks[0];
  const priorYear = String(Number(summary.period) - 1);
  const hasHigh = summary.high_grade_variances > 0;
  // 문서용 표에서는 전표번호 단위로 한 줄만 보인다. 같은 전표의 차변·대변 두 라인이 각각
  // 플래그돼도(예: 지급수수료 라인 + 보통예금 라인) 분개 열에 두 계정이 함께 나오므로,
  // 전표당 최상위 1건만 남겨 중복 인상을 없앤다(순위 순으로 먼저 온 것을 유지).
  const seenVouchers = new Set<string>();
  const topFlags = journalFlags
    .filter((j) => j.risk_level !== "Low")
    .filter((j) => {
      if (seenVouchers.has(j.journal_id)) return false;
      seenVouchers.add(j.journal_id);
      return true;
    })
    .slice(0, 12);

  return (
    <div className="report container-page py-10 md:py-12">
      {/* ── 표지 ── */}
      <header className="border-l-4 border-rail bg-inverse px-6 py-6 text-white md:px-8">
        <div className="text-label font-semibold uppercase text-line-soft">
          감사 분석 보고서 · 합성 데이터 데모
        </div>
        <h1 className="mt-1.5 font-display text-3xl font-bold text-white">{summary.company}</h1>
        <p className="mt-1.5 text-xs text-line-soft">
          {summary.period}년 총계정원장 전수 분석 · 기준 {summary.method} · 감사기준서 520·240 개념 참고
        </p>
      </header>

      {/* 표지 메타 + 인쇄 버튼 */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-4 border-b border-line pb-6">
        <dl className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-label uppercase text-muted">작성</dt>
            <dd className="font-semibold text-ink">정여주</dd>
          </div>
          <div>
            <dt className="text-label uppercase text-muted">데이터 생성</dt>
            <dd className="font-semibold text-ink">{manifest.generated_at}</dd>
          </div>
          <div>
            <dt className="text-label uppercase text-muted">대상 기간</dt>
            <dd className="font-semibold text-ink">{summary.period}년</dd>
          </div>
          <div>
            <dt className="text-label uppercase text-muted">데이터</dt>
            <dd className="font-semibold text-ink">합성(가상)</dd>
          </div>
        </dl>
        <PrintButton />
      </div>

      {/* 3초 요약 */}
      <div
        className="glance mt-6"
        style={{ borderLeftColor: hasHigh ? "#C4231A" : "#C4C4CD" }}
      >
        {top ? (
          <>
            <b>{summary.account_count}개 계정</b> 중 <b>{summary.flagged_accounts}개</b>에서 이상{" "}
            <b>{summary.variance_flags}건</b> · 대차 {bq.grade} · 최우선 <b>{top.account}</b> (
            {monthLabel(top.worst_month, false)} {top.worst_direction}, 편차{" "}
            {eok(top.worst_deviation, true)}억)
          </>
        ) : (
          <>이상 없음 — 분석적 절차에서 검토 우선 항목이 발견되지 않았습니다. (대차 {bq.grade})</>
        )}
      </div>

      {/* KPI — 보고서에서는 화면 대시보드보다 작게(문서용 컴팩트 스타일) */}
      <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {KPI.map((k) => (
          <div key={k.label} className="border border-line px-3 py-2.5">
            <div className="text-label font-semibold uppercase text-muted">{k.label}</div>
            <div className="mt-1 text-lg font-bold leading-none text-ink">{k.value}</div>
            {k.sub && <div className="mt-1 text-[0.66rem] leading-tight text-muted">{k.sub}</div>}
          </div>
        ))}
      </div>

      {/* ── 분석 개요(서문) ── */}
      <section className="report-section mt-9">
        <h2 className="font-display text-lg font-bold text-ink">분석 개요</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink">
          본 보고서는 {summary.company}의 {summary.period}년 총계정원장{" "}
          <b>{summary.journal_count.toLocaleString("ko-KR")}개 분개 줄</b>을 표본 없이 전수 계산해,
          감사인이 먼저 확인할 계정과 전표를 좁힌 결과입니다. 모든 판정에는 그 근거(검사 결과·편차·배점)가
          함께 제시되며, 숫자는 전부 결정론적 코드가 산출합니다. 아래 다섯 단계는{" "}
          <b>“데이터를 믿어도 되는가 → 어디가 이상한가 → 어떤 모양인가 → 어느 전표부터 볼 것인가 →
          전체 위험 신호는 무엇인가”</b>의 순서로 읽도록 구성했습니다.
        </p>
        <ol className="mt-4 grid gap-2 sm:grid-cols-2">
          {[
            ["1", "데이터 무결성 검증", "대차 평형·계정 일관성 등 기본 검사로 원장을 믿을 수 있는지 확인 (감사기준서 500 참고)"],
            ["2", "이상 계정", "계정×월 기대구간을 벗어난 곳을 로버스트 통계로 선별 (감사기준서 520 분석적 절차)"],
            ["3", "계정별 상세", "이상으로 뽑힌 계정마다 실제·기대구간·전기 추이를 그래프로 대조하고, 그 이상을 만든 근거 전표를 함께 제시"],
            ["4", "부정위험 전표", "전표 레드플래그를 전수 스크리닝해 확인 우선순위를 부여 (감사기준서 240)"],
            ["5", "재무제표 신호", "Beneish M·Altman Z′로 분식·도산 신호를 참고 지표로 산출 (감사기준서 570 계속기업 참고)"],
          ].map(([n, t, d]) => (
            <li
              key={n}
              className={`flex gap-2.5 border border-line px-3 py-2 ${
                n === "5" ? "sm:col-span-2" : ""
              }`}
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center bg-brand text-[0.7rem] font-bold text-on-accent">
                {n}
              </span>
              <div>
                <div className="text-sm font-semibold text-ink">{t}</div>
                <div className="mt-0.5 text-xs leading-relaxed text-muted">{d}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* ── 1. 무결성 검증 ── */}
      <section className="report-section mt-10">
        <Marker n="1" title="데이터 무결성 검증" />
        {ov && (
          <p className="mb-3 text-sm font-semibold text-ink">
            종합 판정: {ov.passed ? "통과" : "실패"} · 검사 {ov.total_checks}개 · 오류{" "}
            {ov.error_fail_count}건 · 경고 {ov.warning_count}건
          </p>
        )}
        <p className="cap mb-3">
          분석 전 기본 무결성 검사 · 원장 모집단의 완전성이나 감사증거의 충분성을 이것만으로 보장하지는
          않습니다(감사기준서 500 참고)
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b-2 border-ink text-left text-xs font-semibold text-muted">
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
                  <tr key={`${c.item}-${i}`} className="break-inside-avoid border-b border-line-soft">
                    <td className="py-2 pr-3 text-xs font-semibold text-muted">{c.level}</td>
                    <th scope="row" className="py-2 pr-3 text-left font-semibold text-ink">
                      {c.item}
                    </th>
                    <td className={`py-2 pr-3 font-semibold ${bad ? "text-danger" : "text-success"}`}>
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

      {/* ── 2. 이상 계정 ── */}
      <section className="report-section mt-10">
        <Marker n="2" title="이상 계정" />
        <p className="cap mb-3">
          위험점수 순 · 위험점수·등급은 전기 대비 비교를 위해 2개년 병합 원장의 성과중요성으로
          산출됩니다(상단 KPI의 당기 성과중요성과 산정 대상 기간이 다름)
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b-2 border-ink text-left text-xs font-semibold text-muted">
                <th scope="col" className="py-2 pr-3">계정</th>
                <th scope="col" className="py-2 pr-3">위험점수</th>
                <th scope="col" className="py-2 pr-3">등급</th>
                <th scope="col" className="py-2 pr-3">이탈 월</th>
                <th scope="col" className="py-2 pr-3">가장 심한 달</th>
                <th scope="col" className="py-2 pr-3 text-right">편차(억원)</th>
              </tr>
            </thead>
            <tbody>
              {accountRisks.map((a) => {
                const c = gradeColor(a.grade);
                return (
                  <tr key={a.account} className="break-inside-avoid border-b border-line-soft">
                    <th scope="row" className="py-2.5 pr-3 text-left font-semibold text-ink">
                      {a.account}
                      <span className="ml-1.5 text-[0.7rem] font-normal text-muted">
                        {a.account_code}
                      </span>
                    </th>
                    <td className="py-2.5 pr-3 font-bold tabular-nums text-ink">{a.risk_score}</td>
                    <td className="py-2.5 pr-3">
                      <span className={`inline-flex items-center gap-1.5 font-semibold ${c.text}`}>
                        <span className={`h-2 w-2 ${c.dot}`} aria-hidden />
                        {a.grade}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 tabular-nums text-ink">{a.flagged_months}개월</td>
                    <td className="py-2.5 pr-3 text-ink">
                      {monthLabel(a.worst_month)}{" "}
                      <span className="text-muted">
                        ({a.worst_direction} |z| {a.worst_robust_z.toFixed(1)})
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-right font-semibold tabular-nums text-ink">
                      {eok(a.worst_deviation, true)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── 3. 계정별 상세(차트) — 이상으로 뽑힌 계정 전체 ── */}
      <section className="report-section mt-10">
        <Marker n="3" title={`계정별 상세 (이상 계정 ${accountRisks.length}개 전체)`} />
        <p className="cap mb-5">
          검은 선 = 실제 · 강조색 띠 = 기대구간 · 점선 = 전기 {priorYear}년 · 빨간 ✕ = 이상 후보 ·
          이상으로 선별된 계정을 위험점수 순으로 모두 표시
        </p>
        <div className="flex flex-col gap-7">
          {accountRisks.map((a) => {
            const c = gradeColor(a.grade);
            const dg = driverJournals.find((g) => g.account === a.account);
            return (
              <div key={a.account} className="break-inside-avoid">
                <div className="mb-2 flex items-center gap-2 border-b border-line pb-1.5">
                  <h3 className="font-display text-base font-bold text-ink">{a.account}</h3>
                  <span className="text-[0.7rem] text-muted">{a.account_code}</span>
                  <span className="ml-auto flex items-center gap-2 text-xs">
                    <span className="tabular-nums text-muted">위험점수 {a.risk_score}</span>
                    <span className={`inline-flex items-center gap-1 font-semibold ${c.text}`}>
                      <span className={`h-2 w-2 ${c.dot}`} aria-hidden />
                      {a.grade}
                    </span>
                  </span>
                </div>
                <p className="mb-3 border-l-2 border-line bg-surface px-4 py-2 text-sm leading-relaxed text-ink">
                  <b>{a.account}</b>은 {summary.period}년 중 <b>{a.flagged_months}개월</b>이 기대치를
                  벗어났고, 가장 심한 달은 <b>{monthLabel(a.worst_month)}</b>로 기대치보다{" "}
                  <b className={a.worst_deviation >= 0 ? "text-danger" : "text-ink"}>
                    {eok(Math.abs(a.worst_deviation))}억원 {a.worst_direction}
                  </b>
                  입니다(로버스트 표준화 점수 |z| {a.worst_robust_z.toFixed(1)}).
                </p>
                {/* 좌: 그래프(절반 폭) · 우: 그 이상을 만든 근거 전표 */}
                <div className="grid grid-cols-2 items-start gap-5">
                  <AccountDetailChart
                    data={monthlyVariances}
                    account={a.account}
                    curYear={summary.period}
                    priorYear={priorYear}
                  />
                  <div>
                    {dg ? (
                      <>
                        <div className="mb-1.5 flex items-baseline justify-between gap-2 border-b border-line pb-1">
                          <h4 className="text-xs font-bold text-ink">
                            근거 전표 · {monthLabel(dg.month, false)}
                          </h4>
                          <span className="text-[0.62rem] text-muted">
                            {dg.journal_count}건 중 상위 {dg.shown_count}
                          </span>
                        </div>
                        <table className="w-full table-fixed border-collapse text-[0.7rem]">
                          <colgroup>
                            <col className="w-[74px]" />
                            <col />
                            <col className="w-[58px]" />
                          </colgroup>
                          <thead>
                            <tr className="border-b border-ink/25 bg-surface text-left text-[0.6rem] font-bold text-muted">
                              <th scope="col" className="px-1.5 py-1">전표·일자</th>
                              <th scope="col" className="px-1.5 py-1">적요·거래처</th>
                              <th scope="col" className="px-1.5 py-1 text-right">금액(억)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {dg.journals.map((jj) => {
                              const big =
                                dg.month_gross > 0 &&
                                Math.abs(jj.amount) / dg.month_gross >= 0.5;
                              return (
                                <tr
                                  key={jj.journal_id}
                                  className="border-b border-line-soft align-top last:border-b-0"
                                >
                                  <td className="whitespace-nowrap px-1.5 py-1 leading-snug">
                                    <span className="font-mono text-[0.66rem] text-muted">
                                      {jj.journal_id}
                                    </span>
                                    <br />
                                    <span className="text-[0.64rem] text-muted">{jj.date}</span>
                                  </td>
                                  <td className="px-1.5 py-1 leading-snug text-ink-soft">
                                    {jj.memo ?? "적요 없음"}
                                    {jj.counterparty && (
                                      <span className="text-muted"> · {jj.counterparty}</span>
                                    )}
                                  </td>
                                  <td
                                    className={`whitespace-nowrap px-1.5 py-1 text-right font-bold tabular-nums ${
                                      big ? "text-danger" : "text-ink"
                                    }`}
                                  >
                                    {eok(jj.amount, true)}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                        <p className="mt-1.5 text-[0.6rem] leading-relaxed text-muted">
                          금액 규모 순(부정 점수 아님) · 정상 대형 거래 포함 · 빨강 = 그 달 총활동의
                          50%↑
                        </p>
                      </>
                    ) : (
                      <p className="text-xs text-muted">표시할 근거 전표가 없습니다.</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── 4. 부정위험 전표 — 문서용 압축 표 ── */}
      <section className="report-section mt-10">
        <Marker n="4" title="부정위험 전표 우선순위" />
        <p className="cap mb-1.5">
          점수 = 걸린 규칙 배점 합 ÷ 만점 × 100 · 감사기준서 240 전표기입 검사 대상을 고르는 후보
          목록(혐의 판정이 아니라 확인 우선순위) · 상위 {topFlags.length}건
        </p>
        <p className="cap mb-3">
          분개는 원장 실집계 기준 차변/대변이며 걸린 계정을 굵게 표시했습니다. 사유 뒤 숫자는 그
          규칙의 배점입니다.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] table-fixed border-collapse text-sm">
            <colgroup>
              <col className="w-[54px]" />
              <col className="w-[92px]" />
              <col className="w-[128px]" />
              <col className="w-[58px]" />
              <col />
            </colgroup>
            <thead>
              <tr className="border-b-2 border-ink text-left text-xs font-semibold text-muted">
                <th scope="col" className="py-2 pr-2 text-right">점수</th>
                <th scope="col" className="py-2 pr-2">전표·일자</th>
                <th scope="col" className="py-2 pr-2">분개 (차/대변)</th>
                <th scope="col" className="py-2 pr-2 text-right">금액(억)</th>
                <th scope="col" className="py-2 pr-2">걸린 사유 (배점)</th>
              </tr>
            </thead>
            <tbody>
              {topFlags.map((j) => {
                const c = gradeColor(j.risk_level_ko);
                const parts = (j.counter_account ?? "").split("→").map((s) => s.trim());
                const drAcct = parts[0] || "미확인";
                const crAcct = parts[parts.length - 1] || "미확인";
                return (
                  <tr
                    key={`${j.journal_id}-${j.account}`}
                    className="break-inside-avoid border-b border-line-soft align-top"
                  >
                    <td className="whitespace-nowrap py-2.5 pr-2 text-right">
                      <span className={`font-bold tabular-nums ${c.text}`}>{j.risk_score}</span>
                      <br />
                      <span className={`text-[0.62rem] font-semibold ${c.text}`}>
                        {j.risk_level_ko}
                      </span>
                    </td>
                    <td className="whitespace-nowrap py-2.5 pr-2 text-xs leading-snug">
                      <span className="font-mono text-ink">{j.journal_id}</span>
                      <br />
                      <span className="text-muted">{j.date}</span>
                    </td>
                    <td className="whitespace-nowrap py-2.5 pr-2 text-xs leading-snug">
                      <span className="text-muted">(차)</span>{" "}
                      <span className={drAcct === j.account ? "font-bold text-ink" : "text-ink"}>
                        {drAcct}
                      </span>
                      <br />
                      <span className="text-muted">(대)</span>{" "}
                      <span className={crAcct === j.account ? "font-bold text-ink" : "text-ink"}>
                        {crAcct}
                      </span>
                    </td>
                    <td className="whitespace-nowrap py-2.5 pr-2 text-right font-semibold tabular-nums text-ink">
                      {eok(Math.abs(j.amount))}
                    </td>
                    <td className="py-2.5 pr-2 text-[0.7rem] leading-relaxed text-muted">
                      {j.reasons_detail.map((r) => `${r.name}+${r.points}`).join(" · ")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── 5. 재무제표 신호(게이지) ── */}
      <section className="report-section mt-10">
        <Marker n="5" title="재무제표 수준 신호" />
        <p className="cap mb-4">
          학술 계량모형 기반 참고 지표 · 분식·도산을 확정하지 않으며, 선을 넘었다는 것은 “왜 그런지
          설명을 들어봐야 한다”는 뜻
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="break-inside-avoid">
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
              caption={m.note}
            />
          </div>
          <div className="break-inside-avoid">
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
              caption={z.note}
            />
          </div>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted">⚠️ {fraudScores.disclaimer}</p>
      </section>

      {/* ── 면책 / 근거 ── */}
      <section className="report-section mt-10 border-t-2 border-ink pt-6">
        <p className="max-w-prose text-xs leading-relaxed text-muted">
          본 보고서의 모든 수치는 <b className="text-ink">가상제조(주) 합성 데이터</b>로 만든{" "}
          <b className="text-ink">포트폴리오 데모</b>이며 실제 회사·감사 결과와 무관합니다. 모든
          금액·점수·판정은 결정론적 코드가 계산했고, 걸린 이유(배점)로 그 자리에서 재현·검산됩니다. 최종
          판단은 증빙 확인과 감사인의 전문가적 판단에 있습니다(감사기준서 200·230·240·315·320·500·520·570).
        </p>
        <p className="mt-3 text-xs text-muted">
          근거 감사기준서: {manifest.standards.join(" · ")}
        </p>
        <div className="no-print mt-6 flex flex-wrap gap-3">
          <PrintButton />
          <Link href="/dashboard" className="btn-ghost">
            ← 대화형 대시보드로
          </Link>
        </div>
      </section>
    </div>
  );
}
