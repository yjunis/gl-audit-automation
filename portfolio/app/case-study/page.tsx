import type { Metadata } from "next";
import Link from "next/link";
import { eok, mustFindAccountRisk, mustFindJournal, summary } from "@/lib/data";

export const metadata: Metadata = {
  title: "탐지 사례 | GL 감사 자동화",
  description:
    "합성 원장에서 도구가 실제로 잡아낸 5가지 사례 — 급여 급증, 매출 3계정 동반 급증, 주말 수기 전표, 결산조정 키워드 전표, 중복 의심 전표.",
};

// 사례 선정 키는 수기로 고정하되, 인용하는 값은 전부 FR-14 JSON에서 찾아온다.
// JSON이 갱신돼 해당 전표·계정이 사라지면 화면에 undefined가 뜨는 대신 빌드가 깨진다.
const pay = mustFindAccountRisk("급여");
const ar = mustFindAccountRisk("외상매출금");
const sales = mustFindAccountRisk("제품매출(내수)");
const vat = mustFindAccountRisk("부가세예수금");

const jFee1227 = mustFindJournal("2025-00903", "지급수수료");
const jFee0930 = mustFindJournal("2025-00902", "지급수수료");
const jIns1221 = mustFindJournal("2025-00884", "보험료");

interface Case {
  no: string;
  tag: string;
  title: string;
  found: React.ReactNode;
  why: React.ReactNode;
  rule: React.ReactNode;
  todo: string[];
}

const CASES: Case[] = [
  {
    no: "01",
    tag: "분석적 절차 · 520",
    title: `${pay?.worst_month.slice(0, 4)}년 8월 급여가 기대치를 크게 벗어남`,
    found: (
      <>
        급여 계정의 8월 발생액이 기대구간 위로 튀어나왔습니다. 기대치 대비 편차{" "}
        <b>{eok(pay.worst_deviation)}억원</b>으로, 로버스트 표준화 점수 |z|가{" "}
        <b>{pay.worst_robust_z.toFixed(1)}</b>입니다(평소 변동폭을 크게 벗어났다는 뜻). 계정
        위험점수는 <b>{pay.risk_score}점({pay.grade})</b>으로 분석 대상 계정 중 1위입니다.
      </>
    ),
    why: (
      <>
        급여는 인원과 급여율이 정해져 있어 <b>월별로 가장 완만해야 하는 계정</b>입니다. 그런
        계정이 특정 달만 튀었다면 상여 지급·퇴직 정산 같은 <b>정상적 사유가 있거나</b>, 인건비를
        빌린 가공 지출·기간귀속 조작일 수 있습니다. 어느 쪽인지는 숫자만으로 알 수 없고, 그래서
        확인 대상이 됩니다.
      </>
    ),
    rule: (
      <>
        전년 동월 대비로 기대치를 만든 뒤, 중앙값·MAD 기반 <b>로버스트 z점수</b>가 3.5를 넘는 달을
        이상 후보로 올립니다. 평균 대신 중앙값을 쓰기 때문에, 튄 값 자체가 기준선을 끌고 가서
        이상을 못 잡는 문제를 피합니다.
      </>
    ),
    todo: [
      "8월 급여대장과 원천징수이행상황신고서를 대조해 인원·지급총액이 맞는지 확인",
      "상여·연차수당 등 일시성 항목이 8월에 몰린 사유와 근거 서류 입수",
      "신규 입사·퇴직 정산 내역이 인사기록과 일치하는지 표본 확인",
      "정상 사유가 확인되면 그 근거를 조서에 남기고 기대치 예외로 기록",
    ],
  },
  {
    no: "02",
    tag: "분석적 절차 · 520",
    title: "11월 매출·외상매출금·부가세예수금 3계정 동반 급증",
    found: (
      <>
        11월에 <b>외상매출금 {eok(ar?.worst_deviation)}억원</b>(|z| {ar?.worst_robust_z.toFixed(1)}
        ), <b>제품매출(내수) {eok(sales?.worst_deviation)}억원</b>(|z|{" "}
        {sales?.worst_robust_z.toFixed(1)}), <b>부가세예수금 {eok(vat?.worst_deviation)}억원</b>(|z|{" "}
        {vat?.worst_robust_z.toFixed(1)})이 <b>같은 달에 함께</b> 기대치를 벗어났습니다.
      </>
    ),
    why: (
      <>
        세 계정이 같은 방향으로 함께 움직인 것은 <b>실제 매출 거래가 일어났다는 정황</b>이기도
        하지만, 동시에 <b>기말 밀어내기(cut-off) 위험</b>의 전형적 모습이기도 합니다. 기말 직전
        매출을 앞당겨 인식하면 매출·채권·부가세가 정확히 이렇게 같이 부풀기 때문입니다. 감사기준서
        240은 수익인식에 부정위험이 있다고 추정할 것을 요구합니다.
      </>
    ),
    rule: (
      <>
        계정을 하나씩 보는 데서 끝내지 않고, <b>같은 달에 함께 이탈한 계정들을 히트맵의 세로줄로
        나란히</b> 보여줍니다. 매출과 부가세 관련 계정이 함께 움직였다는 사실 자체가 단서이며,
        증가액의 비율이 적용 세율 및 과세·면세 구성과 정합한지는 별도로 검증해야 합니다.
      </>
    ),
    todo: [
      "11월 말 대형 매출건의 출하증빙·인수증·세금계산서 발행일을 대조해 귀속시기 확인",
      "12월 초 반품·매출취소가 몰려 있는지 확인(밀어내기의 흔적)",
      "해당 거래처의 기말 후 회수 여부와 채권 연령 확인",
      "매출 증가분과 부가세 증가분의 비율이 과세·면세 구성 및 적용 세율과 정합한지 검증",
    ],
  },
  {
    no: "03",
    tag: "부정 전표 · 240",
    title: "12월 27일 토요일, 거래처 없는 2억원 수기 전표",
    found: (
      <>
        전표 <b>{jFee1227?.journal_id}</b>({jFee1227?.date}) — 지급수수료{" "}
        <b>{eok(jFee1227?.amount)}억원</b>, 적요는 “{jFee1227?.memo}” 한 단어, 거래처는 비어
        있습니다. 위험점수 <b>{jFee1227?.risk_score}점({jFee1227?.risk_level_ko})</b>으로 전체{" "}
        {summary.journal_count.toLocaleString("ko-KR")}건 중 1위입니다.
      </>
    ),
    why: (
      <>
        하나만 보면 넘어갈 수 있는 신호가 <b>{jFee1227?.reasons_detail.length}개나 겹쳤습니다</b> —
        주말 입력, 기말 집중, 수기 전표, 딱 떨어지는 금액, 거래처 없는 큰 금액, 모호한 적요, 이례적
        작성자. 정상 거래라면 이 중 몇 개는 보통 해당되지 않습니다. 특히 <b>거래처가 없는 2억원
        정확히</b>는 실재성 자체를 확인해야 하는 조합입니다.
      </>
    ),
    rule: (
      <>
        레드플래그 규칙 11종을 전표마다 걸고 배점을 합산합니다. 이 전표는 배점 합{" "}
        <b>{jFee1227.raw_points}점</b>을 만점 <b>{jFee1227.max_possible_points}점</b>으로 나눠{" "}
        <b>{jFee1227.risk_score}점</b>이 됐습니다. 점수의 근거가 태그로 전부 노출되므로, 조서 작성
        시 <b>후보 선정 근거</b>로 인용할 수 있습니다(감사증거와 감사인의 결론은 별도로 문서화해야
        합니다).
      </>
    ),
    todo: [
      "지급수수료 2억원의 계약서·용역완료보고서·세금계산서 등 증빙 일체 입수",
      "거래처 정보가 비어 있는 사유와 실제 자금 수취인(계좌) 확인",
      "주말·수기로 입력해야 했던 업무상 사유를 작성자에게 질문",
      "해당 작성자의 다른 수기 전표를 전수로 재검토",
    ],
  },
  {
    no: "04",
    tag: "부정 전표 · 240",
    title: "9월 30일 소급 입력된 3억원 “컨설팅 대체” 전표",
    found: (
      <>
        전표 <b>{jFee0930?.journal_id}</b>({jFee0930?.date}) — {jFee0930?.counterparty}에 대한
        지급수수료 <b>{eok(jFee0930?.amount)}억원</b>, 적요 “{jFee0930?.memo}”. 위험점수{" "}
        <b>{jFee0930?.risk_score}점({jFee0930?.risk_level_ko})</b>. 걸린 이유는{" "}
        {jFee0930?.reasons.join(" · ")}입니다.
      </>
    ),
    why: (
      <>
        <b>소급 입력</b>(거래일보다 한참 뒤에 입력)과 <b>결산조정 단어</b>(“대체”)가 분기말
        일자에 겹쳤습니다. 이는 실제 발생 시점이 아니라 <b>결산 숫자를 맞추려고 뒤늦게 끼워
        넣은 전표</b>일 가능성을 시사합니다. 금액이 3억원 정확히 떨어지는 점도 실제 용역대가라기보다
        협의된 금액이라는 신호입니다.
      </>
    ),
    rule: (
      <>
        적요에서 “대체·수정·조정·정정” 같은 <b>결산조정 키워드</b>를 찾고, 전표의 <b>입력일과
        거래일의 간격</b>을 계산해 소급 입력을 잡습니다. 후자는 원장에 입력일 메타필드가 있을 때만
        켜지고, 없는 회사에서는 자동으로 건너뛰어 오류 없이 동작합니다.
      </>
    ),
    todo: [
      "컨설팅 용역계약서와 실제 산출물(보고서 등) 존재 여부 확인",
      "9월 30일자 전표가 언제 입력됐는지 시스템 로그로 확인하고 지연 사유 청취",
      "동일 거래처의 연간 거래 내역과 대금 지급 흐름 추적",
      "“대체” 적요가 붙은 다른 결산 전표를 함께 검토",
    ],
  },
  {
    no: "05",
    tag: "부정 전표 · 240",
    title: "같은 금액·같은 거래처가 반복된 보험료 전표",
    found: (
      <>
        전표 <b>{jIns1221?.journal_id}</b>({jIns1221?.date}) — {jIns1221?.counterparty} 보험료{" "}
        <b>{eok(jIns1221?.amount)}억원</b>이 <b>중복 의심</b>으로 걸렸습니다. 위험점수{" "}
        <b>{jIns1221?.risk_score}점({jIns1221?.risk_level_ko})</b>, 함께 걸린 이유는{" "}
        {jIns1221?.reasons.join(" · ")}입니다.
      </>
    ),
    why: (
      <>
        보험료처럼 정기적인 비용은 <b>같은 금액이 반복되는 게 오히려 정상</b>일 수 있습니다.
        그래서 이 사례는 “걸렸다 = 부정”이 아니라는 점을 보여주는 예입니다. 다만 <b>이중 계상</b>
        (같은 청구서를 두 번 회계처리)일 가능성이 남아 있어 확인은 해야 하고, 확인 후 정상이면 그
        판단을 조서에 남기면 됩니다.
      </>
    ),
    rule: (
      <>
        <b>거래처·금액·계정 조합이 반복</b>되는 전표를 중복 후보로 표시합니다. 여기에 주말 입력과
        기말 집중이 겹쳐 점수가 올라갔지만, 배점 합{" "}
        <b>
          {jIns1221?.raw_points}/{jIns1221?.max_possible_points}
        </b>{" "}
        수준이라 <b>“높음”이 아닌 “중간”</b>으로 분류돼 우선순위가 뒤에 놓입니다. 점수의 역할은
        판정이 아니라 <b>보는 순서를 정하는 것</b>입니다.
      </>
    ),
    todo: [
      "보험증권·청구서와 대조해 동일 건이 두 번 계상됐는지 확인",
      "연간 보험료 총액을 계약 기준 예상액과 대사",
      "이중 계상이 아니라면 정기 비용임을 조서에 기록하고 종결",
    ],
  },
];

export default function CaseStudyPage() {
  return (
    <div className="container-page py-10 md:py-14">
      <header className="mb-12 max-w-prose">
        <span className="tag">합성 데이터 데모</span>
        <h1 className="mt-4 font-display text-h2 font-bold text-ink">
          도구가 실제로 잡아낸 5가지
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-muted md:text-base">
          아래 사례는 {summary.company} {summary.period}년 합성 원장{" "}
          {summary.journal_count.toLocaleString("ko-KR")}건을 전수 분석한 결과에서 그대로 가져온
          것입니다. 각 사례를 <b className="text-ink">무엇을 발견했나 · 왜 위험한가 · 어떤 규칙이
          잡았나 · 감사인은 무엇을 확인해야 하나</b> 네 칸으로 나눠, 화면의 숫자가 실제 감사 절차로
          이어지는 길을 보였습니다.
        </p>
        <p className="mt-5 border-l-4 border-brand bg-surface px-4 py-3 text-xs leading-relaxed text-ink">
          걸렸다는 것은 <b>혐의가 아니라 확인 순서</b>입니다. 정상 거래도 규칙에 걸릴 수 있고(사례
          05가 그 예), 최종 판단은 증빙 확인과 감사인의 전문가적 판단에 있습니다(감사기준서 200).
        </p>
      </header>

      <div className="flex flex-col gap-6">
        {CASES.map((c) => (
          <article key={c.no} className="card">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-xs font-extrabold tracking-widest text-brand-deep">
                CASE {c.no}
              </span>
              <span className="tag">{c.tag}</span>
            </div>
            <h2 className="mt-2 text-lg font-extrabold tracking-tight text-ink md:text-xl">
              {c.title}
            </h2>

            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div className="rounded-xl border border-line bg-surface p-4">
                <h3 className="text-xs font-extrabold text-muted">무엇을 발견했나</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{c.found}</p>
              </div>
              <div className="rounded-xl border border-line bg-surface p-4">
                <h3 className="text-xs font-extrabold text-muted">왜 위험한가</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{c.why}</p>
              </div>
              <div className="rounded-xl border border-line bg-surface p-4">
                <h3 className="text-xs font-extrabold text-muted">어떤 규칙이 잡았나</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{c.rule}</p>
              </div>
            </div>

            <div className="mt-4 rounded-xl border border-line p-4">
              <h3 className="text-xs font-extrabold text-muted">감사인이 확인할 것</h3>
              <ul className="mt-2 flex flex-col gap-1.5">
                {c.todo.map((t) => (
                  <li key={t} className="flex gap-2 text-sm leading-relaxed text-ink-soft">
                    <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-deep" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          </article>
        ))}
      </div>

      <div className="mt-10 flex flex-wrap gap-3">
        <Link href="/dashboard" className="btn-primary">
          대시보드에서 직접 보기 →
        </Link>
        <Link href="/methodology" className="btn-ghost">
          어떻게 계산했나
        </Link>
      </div>
    </div>
  );
}
