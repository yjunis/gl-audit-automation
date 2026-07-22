import Link from "next/link";
import { summary, accountRisks, manifest } from "@/lib/data";

const PROBLEMS = [
  {
    title: "표본으로는 못 보는 곳이 남는다",
    body: "전통적 분석적 절차는 계정 몇 개, 전표 몇 장을 골라 본다. 원장이 수천~수만 건이면 사람이 다 볼 수 없어, 정작 문제가 있는 달이 표본 밖에 남는 일이 생긴다.",
  },
  {
    title: "“작년보다 늘었다”는 판단의 기준이 사람마다 다르다",
    body: "얼마나 늘어야 이상한지에 대한 기준선이 없으면, 같은 숫자를 보고도 담당자마다 결론이 갈린다. 조서에도 “증가했으나 합리적”이라는 말만 남는다.",
  },
  {
    title: "부정 징후는 금액이 아니라 패턴에 숨는다",
    body: "주말 입력, 결산 직전 수기 전표, 딱 떨어지는 금액, 모호한 적요처럼 금액만 봐서는 안 보이는 신호가 있다. 사람이 매 전표에서 이걸 일일이 확인하기는 어렵다.",
  },
];

const FEATURES = [
  {
    n: "01",
    title: "원장 무결성 먼저 확인",
    body: "차변·대변 평형, 계정코드-계정명 일관성, 시산표 역산 대사 등 10개 검사를 통과해야 다음 분석으로 넘어간다. 믿을 수 없는 데이터 위에 쌓은 숫자는 의미가 없기 때문이다.",
  },
  {
    n: "02",
    title: "계정별·월별 기대치 자동 생성",
    body: "전년 동월 대비를 기준으로 “이 계정의 이 달이면 이 정도”라는 기대구간을 만든다. 판단 기준을 사람 감이 아니라 데이터가 만든 구간으로 바꾼다.",
  },
  {
    n: "03",
    title: "기대치를 벗어난 곳만 자동 선별",
    body: "중앙값과 MAD 기반 로버스트 z점수로 이탈도를 재, 표준화된 이탈도 |z|가 3.5를 넘는 달을 이상 후보로 올린다. 이상치 몇 개가 기준선 자체를 흔들지 않는 통계를 쓴다.",
  },
  {
    n: "04",
    title: "전표 레드플래그 11종 전수 스크리닝",
    body: "드문 계정 조합, 결산조정 단어, 주말 입력, 수기 전표, 중복 의심 등 규칙을 모든 전표에 걸어 점수화한다. 감사기준서 240의 전표기입 검사에서 어떤 전표를 볼지 고르는 후보 목록을 만드는 것이 목적이다.",
  },
  {
    n: "05",
    title: "왜 걸렸는지 항상 함께 보여준다",
    body: "점수는 걸린 규칙들의 배점 합을 만점으로 나눈 값이라, 화면의 “걸린 이유” 태그만 보면 점수가 그대로 재현된다. 근거를 못 대는 점수는 조서에 쓸 수 없다.",
  },
  {
    n: "06",
    title: "재무제표 수준 신호까지 함께",
    body: "Beneish M-Score와 Altman Z′-Score로 분식 신호와 도산위험을 참고 지표로 산출한다. 전표 단위 신호와 재무제표 단위 신호를 한 화면에서 대조할 수 있다.",
  },
];

const STACK = [
  { g: "분석 엔진", items: ["Python 3.13", "pandas", "numpy", "Pandera", "PyOD"] },
  { g: "통계·모형", items: ["로버스트 z (중앙값·MAD)", "Beneish M", "Altman Z′", "Benford"] },
  { g: "웹", items: ["Next.js 15 (정적 내보내기)", "React 19", "TypeScript", "Tailwind", "Recharts"] },
  { g: "기준", items: ["감사기준서 520", "240", "315", "320", "500", "230", "200", "570"] },
];

export default function HomePage() {
  const top = accountRisks[0];

  return (
    <div>
      {/* Hero */}
      <section className="border-b border-line bg-surface">
        <div className="container-page py-16 md:py-24">
          <span className="tag">회계감사 · 데이터분석 포트폴리오</span>
          <h1 className="mt-5 max-w-4xl font-display text-display font-bold text-ink">
            총계정원장 전수를 훑어,
            <br />
            감사인이 볼 곳만 남깁니다
          </h1>
          <p className="mt-6 max-w-prose text-lead font-normal text-ink">
            감사기준서 520의 분석적 절차와 240의 전표기입 검사 <b>개념을 참고해</b>, 원장{" "}
            {summary.journal_count.toLocaleString("ko-KR")}건을 전수 계산하고{" "}
            <b>이상 후보 계정 {summary.high_risk_accounts}개</b>와{" "}
            <b>부정위험 전표 후보 {summary.flagged_journals}건</b>으로 좁힙니다. 각각{" "}
            <b>왜 걸렸는지</b>를 함께 보여줘, 감사인이 어디부터 볼지 정할 수 있게 합니다.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/dashboard" className="btn-primary">
              대시보드 보기 →
            </Link>
            <Link href="/case-study" className="btn-ghost">
              탐지 사례 5건
            </Link>
            <Link href="/methodology" className="btn-ghost">
              분석 방법
            </Link>
          </div>

          <p className="mt-7 max-w-prose text-sm leading-relaxed text-muted">
            본 데모의 모든 숫자는 <b className="text-ink">가상제조(주) 합성 데이터</b>입니다. 실제
            감사자료는 어떤 형태로도 이 사이트에 포함되지 않습니다. 분석은 전부 로컬에서 수행되며, 이
            사이트에는 파일 업로드·분석 API가 없습니다.
          </p>
        </div>
      </section>

      {/* 해결하려는 감사 문제 */}
      <section className="container-page py-14 md:py-16">
        <h2 className="sec-title">어떤 감사 문제를 풀었나</h2>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          {PROBLEMS.map((p) => (
            <div key={p.title} className="card">
              <h3 className="text-base font-extrabold text-ink">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 핵심 기능 */}
      <section className="border-y border-line bg-surface">
        <div className="container-page py-14 md:py-16">
          <h2 className="sec-title">핵심 기능</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.n} className="rounded-2xl border border-line bg-white p-5">
                <span className="text-xs font-extrabold tracking-widest text-brand-deep">
                  {f.n}
                </span>
                <h3 className="mt-1 text-base font-extrabold text-ink">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 화면 미리보기 */}
      <section className="container-page py-14 md:py-16">
        <h2 className="sec-title">화면 미리보기</h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          대시보드는 “원장을 믿어도 되는가 → 어느 계정·어느 달이 이상한가 → 어느 전표를 먼저 볼
          것인가 → 재무제표 전체는 어떤 신호를 주는가” 순서로 읽도록 배치했습니다.
        </p>

        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <div className="card">
            <span className="tag">히트맵</span>
            <h3 className="mt-2 text-base font-extrabold text-ink">계정 × 월 한 장</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              기대치가 산출된 계정의 12개월을 전부 색으로 깔아, 빨간 칸만 따라가면 됩니다. 계정명을
              누르면 그 계정의 상세 그래프로 바로 연결됩니다.
            </p>
          </div>
          <div className="card">
            <span className="tag">상세 그래프</span>
            <h3 className="mt-2 text-base font-extrabold text-ink">기대구간과 실제</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              강조색 띠(기대구간) 밖으로 검은 선(실제)이 튀어나온 달에 빨간 ✕가 찍힙니다. 전기 점선과
              나란히 놓여 증감의 맥락이 보입니다.
            </p>
          </div>
          <div className="card">
            <span className="tag">전표 카드</span>
            <h3 className="mt-2 text-base font-extrabold text-ink">점수와 근거를 같이</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              전표마다 점수와 함께 걸린 규칙·배점을 태그로 붙여, 그 자리에서 계산을 검증하고 조서에
              후보 선정 근거로 인용할 수 있습니다.
            </p>
          </div>
        </div>

        {top && (
          <div className="mt-6 rounded-2xl border border-line bg-white p-5 md:p-6">
            <span className="text-xs font-extrabold text-brand-deep">예시 결과</span>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft md:text-base">
              가장 위험한 계정으로 <b className="text-ink">{top.account}</b>(위험점수{" "}
              {top.risk_score}, {top.grade})가 올라왔습니다. {top.worst_month.slice(0, 4)}년{" "}
              {Number(top.worst_month.slice(5))}월에 기대치보다 크게 {top.worst_direction}해,
              로버스트 표준화 점수 |z|가 <b>{top.worst_robust_z.toFixed(1)}</b>로 측정됐습니다. 왜
              그런지는{" "}
              <Link href="/case-study" className="font-bold text-ink underline">
                탐지 사례
              </Link>
              에서 전표 단위로 풀어 두었습니다.
            </p>
          </div>
        )}
      </section>

      {/* 기술 스택 */}
      <section className="border-t border-line bg-surface">
        <div className="container-page py-14 md:py-16">
          <h2 className="sec-title">기술 스택</h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            숫자는 전부 Python이 로컬에서 계산하고, 웹은 그 결과(JSON)를 읽어 보여주기만 합니다.
            그래서 서버가 없어도 즉시 뜨고, 원장을 주고받는 경로가 사이트에 존재하지 않습니다.
          </p>
          <div className="mt-5 grid gap-4 md:grid-cols-4">
            {STACK.map((s) => (
              <div key={s.g} className="rounded-2xl border border-line bg-white p-5">
                <h3 className="text-sm font-extrabold text-ink">{s.g}</h3>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {s.items.map((i) => (
                    <li
                      key={i}
                      className="rounded-full bg-surface px-2.5 py-1 text-[0.72rem] font-bold text-ink-soft"
                    >
                      {i}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link href="/dashboard" className="btn-primary">
              대시보드 보기 →
            </Link>
            <a
              href="https://github.com/"
              target="_blank"
              rel="noreferrer noopener"
              className="btn-ghost"
            >
              GitHub 저장소
            </a>
            <span className="text-xs text-muted">데이터 생성 {manifest.generated_at}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
