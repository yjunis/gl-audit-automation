"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import AccountDetailChart from "@/components/AccountDetailChart";
import Tabs, { type TabItem } from "@/components/Tabs";
import {
  accountRisks,
  driverJournals,
  journalFlags,
  monthlyVariances,
  summary,
  eok,
  monthLabel,
  gradeColor,
} from "@/lib/data";

interface Props {
  /** 서버에서 렌더한 무결성 검증 섹션 */
  validationSlot: ReactNode;
  /** 서버에서 렌더한 Beneish M · Altman Z′ 섹션 */
  signalsSlot: ReactNode;
}

// 레드플래그 배점 체계(fraud_weights.json)와 그 배점이 다른 이유, 그리고 감사기준서 매핑.
// 원칙: 정상 거래에서 우연히 나타날 확률이 낮고 통제를 우회하는 신호일수록 높게,
//       흔하고 정황적인 신호일수록 낮게 배점한다.
// 기준서: 규칙 전체가 감사기준서 240 문단 32~33(전표기입·수정사항 검사)과 적용지침 A41~A44를
//        구현하며, 개별 규칙은 A42가 예시로 든 '부적절한 분개의 특징'에 대응한다.
const SCORING_TIERS: { points: number; rules: string[]; why: string; std: string }[] = [
  {
    points: 30,
    rules: ["드문 계정 조합"],
    why: "정상 거래에서는 거의 나오지 않는 계정 조합이라, 단독으로도 부정 가능성이 가장 강한 신호다.",
    std: "240 A42 — 이례적·거의 사용되지 않는 계정에 대한 기입",
  },
  {
    points: 25,
    rules: ["결산조정 단어"],
    why: "결산 직전 조정 전표는 경영진이 이익을 맞추려 개입하기 쉬운 지점이라 높게 뒀다.",
    std: "240 A42 — 결산·결산 직전(또는 결산 후) 기입",
  },
  {
    points: 20,
    rules: ["거래처 없는 큰 금액", "수기 전표", "소급 입력"],
    why: "거래처 검증·자동 입력 같은 내부통제를 우회했을 가능성이 큰 유형이다.",
    std: "240 A41~A44 · 315 — 통제 우회·이례적 처리",
  },
  {
    points: 15,
    rules: ["딱 떨어지는 금액", "중복 의심"],
    why: "의심 정황이지만 정상 거래에서도 흔히 나타나, 단독 신호로는 약하다.",
    std: "240 A42 — 반올림·끝자리 일정 금액",
  },
  {
    points: 10,
    rules: ["주말 입력", "기말 집중", "모호한 적요", "이례적 작성자"],
    why: "정상 업무에서도 자주 발생하는 정황 정보라 보조 신호로만 쓴다.",
    std: "240 A42 — 설명 거의 없는 기입·평소 전표를 만들지 않는 작성자",
  },
];

export default function DashboardClient({ validationSlot, signalsSlot }: Props) {
  const [tab, setTab] = useState("overview");
  // 캡처 모드(?capture=1): 모든 탭을 한 화면에 펼쳐, 대시보드 전체를 한 PDF로 인쇄하기 위한 모드.
  // 차트(Recharts)는 화면에 보일 때만 크기를 재므로, 이 모드에서 모든 패널을 실제로 렌더해야
  // 그래프가 정상적으로 나온다. 인쇄는 가로(A4 landscape)로 — 데스크톱 폭 레이아웃 유지.
  const [captureAll, setCaptureAll] = useState(false);
  useEffect(() => {
    const on = new URLSearchParams(window.location.search).get("capture") === "1";
    setCaptureAll(on);
    if (on) document.documentElement.classList.add("cap-landscape");
    return () => document.documentElement.classList.remove("cap-landscape");
  }, []);
  // 분석 연도는 항상 당기(2025)로 고정 — 연도 선택 기능은 두지 않는다.
  // 전기(priorYear)는 상세 그래프의 전년 대비 점선 비교에만 쓴다.
  const year = summary.period;
  const priorYear = String(Number(year) - 1);

  // 계정 표시 순서 = 당기 이탈이 큰 계정 우선(위험점수 계정을 앞에)
  const ordered = useMemo(() => {
    const worst = new Map<string, number>();
    for (const v of monthlyVariances) {
      if (!v.month.startsWith(year)) continue;
      const z = Math.abs(v.robust_z ?? 0);
      worst.set(v.account, Math.max(worst.get(v.account) ?? 0, z));
    }
    const ranked = accountRisks.map((a) => a.account).filter((a) => worst.has(a));
    const rest = [...worst.entries()]
      .filter(([a]) => !ranked.includes(a))
      .sort((x, y) => y[1] - x[1])
      .map(([a]) => a);
    return [...ranked, ...rest];
  }, [year]);

  const [picked, setPicked] = useState<string | null>(null);
  const account = picked && ordered.includes(picked) ? picked : (ordered[0] ?? "");

  /** 계정을 고르면 상세 탭으로 함께 이동 — 스크롤로 이어보던 흐름을 탭에서도 유지. */
  const selectAccount = (a: string) => {
    setPicked(a);
    setTab("account");
  };

  const risk = accountRisks.find((a) => a.account === account);

  // 이 계정의 이상월별 '편차를 만든' 전표(금액 기여도 순). 부정 스크리닝 점수와 무관하다 —
  // 정상적인 대형 거래가 원인인 경우가 많고, 그게 바로 감사인이 확인할 대상이다.
  const drivers = useMemo(
    () => driverJournals.filter((g) => g.account === account && g.month.startsWith(year)),
    [account, year],
  );

  const topFlags = useMemo(
    () => journalFlags.filter((j) => j.risk_level !== "Low" && j.date.startsWith(year)).slice(0, 12),
    [year],
  );

  // ── 탭 1: 무결성 검증 ───────────────────────────
  const panelValidation = validationSlot;

  // ── 탭 2: 이상 계정 ───────────────────────────
  const panelOverview = (
    <section className="card">
      <h2 className="sec-title mb-1">이상 계정</h2>
      <p className="cap mb-3">
        위험점수 순 · 계정명을 누르면 계정별 상세로 이동 · 위험점수·등급은 전기 대비 비교를 위해
        2개년 병합 원장의 성과중요성으로 산출됩니다(상단 KPI의 당기 성과중요성과 산정 대상 기간이 다름)
      </p>
      <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <caption className="sr-only">{year}년 이상 계정 목록</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs font-bold text-muted">
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
                  const sel = a.account === account;
                  return (
                    <tr
                      key={a.account}
                      className={`border-b border-line/60 ${sel ? "bg-brand/15" : ""}`}
                    >
                      <th scope="row" className="py-2.5 pr-3 text-left">
                        <button
                          type="button"
                          onClick={() => selectAccount(a.account)}
                          className="rounded font-bold text-ink hover:underline"
                        >
                          {a.account}
                        </button>
                        <span className="ml-1.5 text-[0.7rem] font-normal text-muted">
                          {a.account_code}
                        </span>
                      </th>
                      <td className="py-2.5 pr-3 font-extrabold tabular-nums text-ink">
                        {a.risk_score}
                      </td>
                      <td className="py-2.5 pr-3">
                        <span className={`inline-flex items-center gap-1.5 font-bold ${c.text}`}>
                          <span className={`h-2 w-2 rounded-full ${c.dot}`} aria-hidden />
                          {a.grade}
                        </span>
                      </td>
                      <td className="py-2.5 pr-3 tabular-nums text-ink-soft">
                        {a.flagged_months}개월
                      </td>
                      <td className="py-2.5 pr-3 text-ink-soft">
                        {monthLabel(a.worst_month)}{" "}
                        <span className="text-muted">
                          ({a.worst_direction} |z| {a.worst_robust_z.toFixed(1)})
                        </span>
                      </td>
                      <td className="py-2.5 pr-3 text-right font-bold tabular-nums text-ink">
                        {eok(a.worst_deviation, true)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
    </section>
  );

  // ── 탭 3: 계정별 상세 ───────────────────────────
  const panelAccount = (
    <section className="card">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="sec-title">계정별 상세 · {account || "-"}</h2>
        <label className="flex items-center gap-2 text-xs font-bold text-muted">
          계정 선택
          <select
            value={account}
            onChange={(e) => setPicked(e.target.value)}
            className="rounded-lg border border-line bg-white px-3 py-2 text-sm font-bold text-ink"
          >
            {ordered.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="cap mb-3">
        검은 선 = 실제 · 강조색 띠 = 기대구간 · 점선 = 전기 {priorYear}년 · 빨간 ✕ = 이상 후보
      </p>

      {risk && (
        <div className="mb-4 rounded-xl border border-line bg-surface px-4 py-3 text-sm leading-relaxed text-ink-soft">
          <b className="text-ink">{risk.account}</b>은 {year}년 중{" "}
          <b>{risk.flagged_months}개월</b>이 기대치를 벗어났고, 가장 심한 달은{" "}
          <b>{monthLabel(risk.worst_month)}</b>로 기대치보다{" "}
          <b className={risk.worst_deviation >= 0 ? "text-danger" : "text-ink"}>
            {eok(Math.abs(risk.worst_deviation))}억원 {risk.worst_direction}
          </b>
          입니다(로버스트 표준화 점수 |z| {risk.worst_robust_z.toFixed(1)}).
        </div>
      )}

      {account ? (
        <AccountDetailChart
          data={monthlyVariances}
          account={account}
          curYear={year}
          priorYear={priorYear}
        />
      ) : (
        <p className="py-8 text-sm text-muted">표시할 계정이 없습니다.</p>
      )}

      {drivers.map((g) => {
        const offset = g.month_gross > Math.abs(g.month_net) * 1.2; // 상쇄 거래가 뚜렷한 달
        // 이 달의 실제·기대치는 월별 편차표에서 온다(전표 표와 같은 계정·달).
        // 편차 = 실제 − 기대치 로 직접 계산해 세 값이 화면에서 그대로 맞물리게 한다.
        const mv = monthlyVariances.find((x) => x.account === g.account && x.month === g.month);
        const actual = mv?.actual ?? null;
        const expected = mv?.expected ?? null;
        const dev = actual != null && expected != null ? actual - expected : null;
        return (
          <div key={g.month} className="mt-6 rounded-xl border-2 border-danger/25 bg-red-50/40 p-4">
            <h3 className="text-sm font-extrabold text-ink">
              {monthLabel(g.month, false)} 근거 전표
            </h3>
            <p className="cap mt-1">
              이 달 원장 금액 규모 순 · 전표 {g.journal_count}건 중 상위 {g.shown_count}건(총활동액의{" "}
              {g.shown_coverage != null ? `${Math.round(g.shown_coverage * 100)}%` : "-"}) · 부정
              점수가 아니라 금액으로 뽑으므로 정상 거래도 올라옵니다
            </p>

            {/* 이 달 요약 — 실제 금액 · 기대치 · 편차(=실제−기대치). */}
            <div className="mt-3 grid grid-cols-3 divide-x divide-line overflow-hidden rounded-lg border border-line bg-white text-center">
              <div className="px-2 py-2.5">
                <div className="text-label text-muted">실제 금액</div>
                <div className="mt-0.5 text-sm font-extrabold tabular-nums text-ink">
                  {actual != null ? `${eok(actual)}억원` : "—"}
                </div>
              </div>
              <div className="px-2 py-2.5">
                <div className="text-label text-muted">기대치</div>
                <div className="mt-0.5 text-sm font-extrabold tabular-nums text-ink">
                  {expected != null ? `${eok(expected)}억원` : "—"}
                </div>
              </div>
              <div className="px-2 py-2.5">
                <div className="text-label text-muted">편차 (실제−기대)</div>
                <div
                  className={`mt-0.5 text-sm font-extrabold tabular-nums ${
                    dev != null && dev >= 0 ? "text-danger" : "text-brand-deep"
                  }`}
                >
                  {dev != null ? `${eok(dev, true)}억원` : "—"}
                </div>
              </div>
            </div>

            {/* 엑셀 원장에 가까운 표 — 헤더행(음영) + 셀 구분선 + 숫자 우측정렬. */}
            <div className="mt-3 overflow-x-auto rounded-lg border border-line bg-white">
              <table className="w-full min-w-[620px] border-collapse text-sm">
                <caption className="sr-only">
                  {monthLabel(g.month, false)} 근거 전표 목록(금액 규모 순)
                </caption>
                <thead>
                  <tr className="border-b-2 border-ink/25 bg-surface text-left text-[0.7rem] font-bold tracking-wide text-muted">
                    <th scope="col" className="border-r border-line px-2.5 py-2">전표번호</th>
                    <th scope="col" className="border-r border-line px-2.5 py-2">전표일자</th>
                    <th scope="col" className="border-r border-line px-2.5 py-2">적요</th>
                    <th scope="col" className="border-r border-line px-2.5 py-2">거래처</th>
                    <th scope="col" className="border-r border-line px-2.5 py-2 text-right">금액(억원)</th>
                    <th scope="col" className="px-2.5 py-2 text-right">월 순액 대비</th>
                  </tr>
                </thead>
                <tbody>
                  {g.journals.map((j) => {
                    const share = j.share_of_month_net;
                    // 빨간 강조는 '이 달 거래에서 실제로 큰 건'이라는 뜻이라야 한다.
                    // 순액 대비로 잡으면 상쇄가 큰 달에 분모가 작아져 평범한 건도 강조돼 버린다.
                    const major = g.month_gross > 0 && Math.abs(j.amount) / g.month_gross >= 0.5;
                    const counter = j.amount < 0 !== g.month_net < 0; // 순액과 반대 방향 = 상쇄 거래
                    return (
                      <tr
                        key={j.journal_id}
                        className={`border-b border-line-soft last:border-b-0 ${
                          major ? "bg-danger/5" : "odd:bg-white even:bg-surface/40"
                        }`}
                      >
                        <td className="whitespace-nowrap border-r border-line-soft px-2.5 py-2 font-mono text-[0.72rem] text-muted">
                          {j.journal_id}
                        </td>
                        <td className="whitespace-nowrap border-r border-line-soft px-2.5 py-2 text-[0.72rem] text-ink-soft">
                          {j.date}
                        </td>
                        <td className="border-r border-line-soft px-2.5 py-2 text-ink">
                          {j.memo ?? "적요 없음"}
                        </td>
                        <td className="border-r border-line-soft px-2.5 py-2 text-ink-soft">
                          {j.counterparty ?? "—"}
                        </td>
                        <td
                          className={`whitespace-nowrap border-r border-line-soft px-2.5 py-2 text-right font-extrabold tabular-nums ${
                            major ? "text-danger" : "text-ink"
                          }`}
                        >
                          {eok(j.amount, true)}
                        </td>
                        <td
                          className="whitespace-nowrap px-2.5 py-2 text-right tabular-nums text-muted"
                          title="이 달 순액 대비 이 전표의 비율. 상쇄 거래가 있으면 100%를 넘거나 음수일 수 있습니다."
                        >
                          {share != null ? `${Math.round(share * 100)}%` : "—"}
                          {counter && (
                            <span className="ml-1 text-[0.68rem] font-bold text-warning">(상쇄)</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {offset && (
              <p className="cap mt-2.5 rounded-lg bg-white/70 px-3 py-2">
                이 달은 들어온 금액과 나간 금액이 상쇄됩니다(총활동 {eok(g.month_gross)}억 · 순액{" "}
                {eok(g.month_net)}억). 그래서 “월 순액 대비 %”가 100%를 넘거나 음수일 수 있습니다.
              </p>
            )}

            <p className="cap mt-2.5">
              편차를 쪼갠 것이 아니며(기대치는 과거 분포에서 나온 값), 수상하다는 뜻도 아닙니다 ·
              패턴이 수상한 전표는 부정위험 전표 탭에서 따로 봅니다
            </p>
          </div>
        );
      })}
    </section>
  );

  // ── 탭 4: 부정위험 전표 ───────────────────────────
  const panelJournals = (
    <section className="card">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="sec-title">부정위험 전표 우선순위</h2>
        <span className="tag">
          원장 {summary.journal_count.toLocaleString("ko-KR")}건 전수 스크리닝
        </span>
      </div>
      <p className="cap mb-3">
        점수 = 걸린 규칙 배점 합 ÷ 만점 × 100 · 감사기준서 240 전표기입 검사 대상을 고르는 후보
        목록 · 혐의 판정이 아니라 확인 우선순위
      </p>

      {topFlags.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface px-4 py-6 text-sm text-muted">
          {year}년에는 높음·중간 등급으로 걸린 전표가 없습니다.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {topFlags.map((j) => {
            const c = gradeColor(j.risk_level_ko);
            // 상대계정조합은 "차변계정 → 대변계정" 형식(원장 실제 분개 방향).
            const dcParts = (j.counter_account ?? "").split("→").map((s) => s.trim());
            const drAcct = dcParts[0] || "미확인";
            const crAcct = dcParts[dcParts.length - 1] || "미확인";
            const entryAmt = `${eok(Math.abs(j.amount))}억원`;
            return (
              <article
                key={`${j.journal_id}-${j.account}`}
                className={`rounded-xl border border-line p-4 ${c.bg}`}
              >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className={`text-xl font-extrabold tabular-nums ${c.text}`}>
                    {j.risk_score}
                  </span>
                  <span className={`text-xs font-bold ${c.text}`}>{j.risk_level_ko}</span>
                  <span className="font-mono text-xs text-muted">{j.journal_id}</span>
                  <span className="text-xs text-ink-soft">{j.date}</span>
                  <span className="ml-auto text-sm font-extrabold tabular-nums text-ink">
                    {eok(j.amount, true)}억원
                  </span>
                </div>

                {/* 해당 계정 — 이 카드의 주 식별자(크게). */}
                <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <b className="text-base font-extrabold text-ink">{j.account}</b>
                  {j.account_dc && (
                    <span className="rounded bg-white/70 px-1.5 py-0.5 text-[0.66rem] font-bold text-muted">
                      {j.account_dc}측
                    </span>
                  )}
                  {j.counterparty && (
                    <span className="text-xs text-muted">· 거래처 {j.counterparty}</span>
                  )}
                </div>

                {/* 분개 — 차변/대변 표준 표기(분개장 형식). 계정명보다 작고 덜 띄게, 걸린 계정만 강조. */}
                <div className="mt-1 text-xs leading-relaxed text-muted">
                  <span className="mr-1 font-bold text-muted">분개</span>
                  <span>(차)</span>{" "}
                  <span className={drAcct === j.account ? "font-bold text-ink" : "text-ink-soft"}>
                    {drAcct}
                  </span>{" "}
                  <span className="tabular-nums">{entryAmt}</span>
                  <span className="mx-1.5 text-line">/</span>
                  <span>(대)</span>{" "}
                  <span className={crAcct === j.account ? "font-bold text-ink" : "text-ink-soft"}>
                    {crAcct}
                  </span>{" "}
                  <span className="tabular-nums">{entryAmt}</span>
                </div>

                <p className="mt-1.5 text-sm text-ink-soft">{j.memo ?? "적요 없음"}</p>

                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {j.reasons_detail.map((r) => (
                    <span
                      key={r.code}
                      className="rounded-full border border-line bg-white px-2.5 py-0.5 text-[0.7rem] font-bold text-ink-soft"
                    >
                      {r.name} <span className="text-muted">+{r.points}</span>
                    </span>
                  ))}
                </div>
                <p className="mt-2 text-[0.7rem] text-muted">
                  점수 계산: 배점 합 {j.raw_points} ÷ 만점 {j.max_possible_points} × 100 ={" "}
                  {j.risk_score}점
                  {j.amount_materiality != null && (
                    <> · 수행중요성 대비 {(j.amount_materiality * 100).toFixed(0)}%</>
                  )}
                </p>
              </article>
            );
          })}
        </div>
      )}

      <p className="cap mt-3">
        정상 거래도 규칙에 걸릴 수 있으며, 최종 판단은 증빙 확인과 감사인의 전문가적 판단에
        있습니다(감사기준서 200)
      </p>

      {/* 배점 근거 — 규칙마다 배점이 다른 이유. */}
      <div className="mt-5 rounded-xl border border-line bg-surface p-4">
        <h3 className="font-display text-sm font-bold text-ink">배점은 왜 규칙마다 다른가</h3>
        <p className="cap mt-1">
          배점은 <b className="text-ink-soft">그 신호가 부정과 얼마나 강하게 연관되는가</b>에
          비례합니다. 정상 거래에서 우연히 나타날 확률이 낮고 내부통제를 우회하는 신호일수록 높게,
          흔하고 정황적인 신호일수록 낮게 뒀습니다. (등급: 높음 45점↑ · 중간 40점↑)
        </p>
        <p className="cap mt-1.5 border-l-4 border-rail bg-white px-3 py-2">
          <b className="text-ink-soft">감사기준서 매핑</b> — 이 스크리닝 전체는{" "}
          <b className="text-ink-soft">감사기준서 240 문단 32~33</b>(전표기입 및 기타 수정사항 검사)과
          적용지침 <b className="text-ink-soft">A41~A44</b>를 구현한 것입니다. 아래 각 규칙은 A42가
          예시로 든 ‘부적절한 분개의 특징’에 대응합니다.
        </p>
        <div className="mt-3 overflow-x-auto rounded-lg border border-line bg-white">
          <table className="w-full min-w-[680px] table-fixed border-collapse text-sm">
            <caption className="sr-only">레드플래그 배점·근거·감사기준서 매핑</caption>
            <colgroup>
              <col className="w-[62px]" />
              <col className="w-[148px]" />
              <col />
              <col className="w-[224px]" />
            </colgroup>
            <thead>
              <tr className="border-b-2 border-ink/25 bg-surface text-left text-[0.7rem] font-bold tracking-wide text-muted">
                <th scope="col" className="border-r border-line px-3 py-2 text-center">배점</th>
                <th scope="col" className="border-r border-line px-3 py-2">해당 규칙</th>
                <th scope="col" className="border-r border-line px-3 py-2">배점 근거</th>
                <th scope="col" className="px-3 py-2">감사기준서</th>
              </tr>
            </thead>
            <tbody>
              {SCORING_TIERS.map((t, i) => (
                <tr
                  key={t.points}
                  className={`border-b border-line-soft align-top last:border-b-0 ${
                    i % 2 ? "bg-surface/40" : "bg-white"
                  }`}
                >
                  <td className="border-r border-line-soft px-3 py-3 text-center">
                    <span className="text-lg font-extrabold leading-none tabular-nums text-ink">
                      {t.points}
                    </span>
                    <span className="ml-0.5 text-[0.6rem] font-bold text-muted">점</span>
                  </td>
                  <td className="border-r border-line-soft px-3 py-3">
                    <div className="flex flex-col items-start gap-1">
                      {t.rules.map((r) => (
                        <span
                          key={r}
                          className="whitespace-nowrap rounded border border-line bg-white px-1.5 py-0.5 text-[0.72rem] font-bold text-ink-soft"
                        >
                          {r}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="border-r border-line-soft px-3 py-3 text-[0.8rem] leading-relaxed text-ink-soft">
                    {t.why}
                  </td>
                  <td className="px-3 py-3 text-[0.76rem] leading-relaxed text-muted">{t.std}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="cap mt-2">
          배점은 감사인이 조정할 수 있는 값이며(감사기준서 240·315 위험평가), 금액 기준선에는
          수행중요성(감사기준서 320)을 씁니다. 한 전표의 점수 = 걸린 규칙 배점 합 ÷ 활성 규칙 만점 ×
          100.
        </p>
      </div>
    </section>
  );

  const items: TabItem[] = [
    {
      id: "overview",
      label: "이상 계정",
      badge: String(summary.high_risk_accounts),
      content: panelOverview,
    },
    { id: "account", label: "계정별 상세", content: panelAccount },
    { id: "validation", label: "검증·시산표", content: panelValidation },
    {
      id: "journals",
      label: "부정·이상 탐지",
      badge: topFlags.length > 0 ? String(topFlags.length) : undefined,
      content: panelJournals,
    },
    { id: "signals", label: "재무제표 신호", content: signalsSlot },
  ];

  // 캡처 모드 — 모든 탭 내용을 세로로 쌓고, 탭마다 새 페이지에서 시작하도록 페이지 나눔.
  // (각 패널은 자체 제목(h2)을 갖고 있어 어느 화면인지 그대로 읽힌다.)
  if (captureAll) {
    return (
      <div className="flex flex-col gap-8">
        {items.map((t, i) => (
          <div key={t.id} className={i > 0 ? "break-before-page" : ""}>
            {t.content}
          </div>
        ))}
      </div>
    );
  }

  return <Tabs items={items} activeId={tab} onChange={setTab} />;
}
