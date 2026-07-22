import type { Metadata } from "next";
import Link from "next/link";
import { fraudScores, manifest, validation } from "@/lib/data";

export const metadata: Metadata = {
  title: "분석 방법 | GL 감사 자동화",
  description:
    "무결성 검증 → 기대치 생성 → 이상탐지 → 전표 레드플래그 → 계정 자동분류 → M/Z 스코어. 각 단계가 감사기준서 520·240과 어떻게 연결되는지 설명합니다.",
};

interface Step {
  n: string;
  title: string;
  std: string;
  what: string;
  how: React.ReactNode;
  why: string;
}

const STEPS: Step[] = [
  {
    n: "01",
    title: "원장 무결성 검증",
    std: "감사기준서 500 (감사증거)",
    what: "받은 원장 파일을 그대로 믿지 않고, 분석에 쓸 수 있는 데이터인지부터 확인합니다.",
    how: (
      <>
        Pandera 스키마로 필수 컬럼·자료형·계정코드 형식을 검사하고, 그 위에 회계 규칙 검사를
        얹습니다 — <b>전표별 차변·대변 평형</b>, <b>전체 시산표 평형</b>,{" "}
        <b>계정코드-계정명 일관성</b>, <b>시산표 역산 대사</b> 등 총{" "}
        {validation.overall?.total_checks ?? 10}개 검사를 돌립니다. 오류(ERROR)가 하나라도 나면 뒤
        숫자를 신뢰할 수 없으므로 원인부터 해결합니다.
      </>
    ),
    why: "잘못된 데이터 위에서 아무리 정교한 통계를 돌려도 결론은 틀립니다. 다만 이 검사는 분석 전 기본 무결성 검사이며, 원장 모집단의 완전성·추출조건·IT 의존통제나 감사증거의 충분성·적합성을 단독으로 보장하지는 않습니다.",
  },
  {
    n: "02",
    title: "계정별·월별 기대치 생성",
    std: "감사기준서 520 문단 5 (분석적 절차)",
    what: "“이 계정의 이 달이라면 이 정도가 정상”이라는 기준선을 데이터로 만듭니다.",
    how: (
      <>
        기본은 <b>전년 동월 대비(YoY)</b>입니다. 계절성이 있는 계정(난방비·상여 등)에서 전월 대비는
        오해를 낳지만, 전년 같은 달과 비교하면 계절 효과가 상쇄되기 때문입니다. 2개 연도가 있으면
        두 해를 병합해 기대치를 잡고, 회귀 기반 예측구간 등 다른 기대치 방식도 같은 인터페이스로
        갈아 끼울 수 있게 설계했습니다.
      </>
    ),
    why: "기대치가 없으면 “늘었다/줄었다”만 남고, 이상 여부는 담당자 감에 맡겨집니다. 다만 감사기준서 520의 실증적 분석절차는 기대치 개발 외에도 데이터의 신뢰성 평가, 기대치의 정밀도, 허용 가능한 차이금액 설정, 차이에 대한 조사까지 포함합니다. 이 도구는 그중 기대치 개발과 차이 식별을 자동화한 것이지, 절차 전체를 대체하지 않습니다.",
  },
  {
    n: "03",
    title: "이상 탐지 — 로버스트 z점수",
    std: "감사기준서 520 문단 5(d)·7",
    what: "기대치에서 얼마나 벗어났는지를 재서, 사람이 볼 후보만 남깁니다.",
    how: (
      <>
        평균·표준편차 대신 <b>중앙값과 MAD(중앙값 절대편차)</b>를 씁니다. 평균은 튄 값 하나에 끌려가
        기준선 자체가 이상해지지만, 중앙값은 버팁니다. 로버스트 표준화 점수{" "}
        <b>z = 0.6745 × (x − 중앙값) / MAD</b>를 구해 <b>|z| &gt; 3.5</b>면 이상 후보로 올립니다
        (Iglewicz–Hoaglin 기준). 0.6745는 정규분포 가정에서 MAD를 표준편차에 대응시키는 보정계수라,
        |z|는 “MAD의 몇 배”가 아니라 <b>표준화된 이탈도</b>로 읽어야 합니다. MAD가 0에 가까운
        계정(값이 거의 변하지 않아 분모가 무너지는 경우)에는 <b>산포 하한을 중앙값의 15%로 두어</b>,
        미미한 변동이 |z|를 무한대로 밀어 올리는 것을 막습니다. 이 임계값과 기대구간이 화면의 강조색
        띠와 빨간 ✕로 그대로 이어집니다.
      </>
    ),
    why: "부정은 흔하지 않기에, 이상치에 강건한 통계를 써야 “이상치가 기준을 오염시켜 이상치를 못 잡는” 역설을 피할 수 있습니다.",
  },
  {
    n: "04",
    title: "전표 레드플래그 스크리닝",
    std: "감사기준서 240 문단 32(a) (전표 검사)",
    what: "계정 수준에서 못 보는 전표 하나하나의 패턴을 전수로 훑어, 검사 대상 후보를 고릅니다.",
    how: (
      <>
        11종 규칙을 모든 전표에 겁니다 — 드문 계정 조합, 결산조정 단어, 거래처 없는 큰 금액, 중복
        의심, 딱 떨어지는 금액, 기말 집중, 주말 입력, 모호한 적요, 수기 전표, 소급 입력, 이례적
        작성자. 각 규칙에 배점을 두고, <b>위험점수 = round(걸린 배점 합 ÷ 만점 × 100)</b>으로
        0~100 정규화합니다. 뒤 3종은 원장에 전표유형·작성자·입력일 메타필드가 있을 때만 켜지고,
        없으면 자동으로 건너뜁니다.
      </>
    ),
    why: "감사기준서 240은 경영진의 통제무력화 위험에 대응해 전표기입과 기타 조정을 검사하도록 요구합니다. 수천~수만 건을 사람이 다 볼 수 없으니, 규칙으로 전수를 훑어 검사 대상 후보를 고르는 데 씁니다. 어떤 전표를 실제로 검사할지는 위험평가에 따라 감사인이 정하고, 증빙·승인·업무상 근거는 별도로 확인해야 합니다.",
  },
  {
    n: "05",
    title: "계정 자동 분류",
    std: "감사기준서 315 (위험평가)",
    what: "회사마다 다른 계정명을 표준 범주(매출·매출채권·인건비 등)로 자동 매핑합니다.",
    how: (
      <>
        계정코드 체계와 계정명 키워드를 함께 보고 표준 범주를 추정하되, 자신 없는 건은{" "}
        <b>사람이 고칠 수 있게 남깁니다</b>. 사용자가 고친 결과는 저장돼 다음 회사·다음 연도에
        재사용되므로, 쓸수록 손이 덜 갑니다.
      </>
    ),
    why: "“매출액·제품매출·상품매출액”이 회사마다 다르게 불려도 같은 잣대로 비교하려면 표준 범주가 필요합니다. 이게 M-Score·Z-Score 계산의 전제이기도 합니다.",
  },
  {
    n: "06",
    title: "재무제표 수준 신호 — Beneish M · Altman Z′",
    std: "감사기준서 240 · 570 (계속기업)",
    what: "전표 단위 신호와 별개로, 재무제표 전체가 주는 신호를 참고 지표로 냅니다.",
    how: (
      <>
        <b>Beneish M-Score</b>는 매출채권 회전(DSRI), 매출총이익 변화(GMI), 발생액(TATA) 등 8개
        지표를 합성해 분식 가능성 신호를 냅니다(표준선{" "}
        {fraudScores.models.beneish_m.thresholds.standard}). <b>Altman Z′-Score</b>는 운전자본·
        이익잉여금·영업이익·자본구조·자산회전 5개 비율로 도산위험을 봅니다(안전{" "}
        {fraudScores.models.altman_z.thresholds.safe} 초과 / 위험{" "}
        {fraudScores.models.altman_z.thresholds.gray} 미만).
      </>
    ),
    why: "두 모형 모두 학술 계량모형이지, 분식·도산의 확정 판정이 아닙니다. 선을 넘었다는 것은 “왜 그런지 설명을 들어봐야 한다”는 뜻이고, 이 도구는 딱 거기까지만 말합니다.",
  },
];

export default function MethodologyPage() {
  return (
    <div className="container-page py-10 md:py-14">
      <header className="mb-12 max-w-prose">
        <span className="tag">방법론</span>
        <h1 className="mt-4 font-display text-h2 font-bold text-ink">
          어떻게 계산했나
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-muted md:text-base">
          이 도구는 <b>원장을 믿어도 되는지 확인 → 기대치를 만들고 → 벗어난 곳을 재고 → 전표
          패턴을 훑고 → 재무제표 신호로 맥락을 보는</b> 순서로 동작합니다. 각 단계가 감사기준서의
          어느 요구사항에 대응하는지 함께 적었습니다.
        </p>
      </header>

      <div className="flex flex-col gap-5">
        {STEPS.map((s) => (
          <article key={s.n} className="card">
            <div className="flex flex-wrap items-center gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center bg-brand text-sm font-bold text-on-accent">
                {s.n}
              </span>
              <h2 className="text-lg font-extrabold tracking-tight text-ink">{s.title}</h2>
              <span className="tag">{s.std}</span>
            </div>

            <p className="mt-3 text-sm font-bold leading-relaxed text-ink md:text-base">
              {s.what}
            </p>

            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-line bg-surface p-4">
                <h3 className="text-xs font-extrabold text-muted">어떻게</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{s.how}</p>
              </div>
              <div className="rounded-xl border border-line bg-surface p-4">
                <h3 className="text-xs font-extrabold text-muted">왜 이렇게</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{s.why}</p>
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* 설계 원칙 */}
      <section className="mt-12 border-2 border-ink bg-white p-6 md:p-8">
        <span className="tag">설계 원칙</span>
        <h2 className="mt-2 text-h3 font-bold text-ink">
          숫자는 코드가 계산하고, 자연어는 설명만 한다
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-soft md:text-base">
          이 도구에서 <b>모든 금액·점수·판정은 결정론적 코드가 계산</b>합니다. 같은 원장을 넣으면
          언제나 같은 숫자가 나오고, 화면의 점수는 “걸린 이유” 태그의 배점 합으로 그 자리에서
          검증됩니다. 자연어가 하는 일은 <b>이미 계산된 숫자에 설명을 붙이는 것뿐</b>이며, 숫자를
          지어내거나 판정을 내리지 않습니다.
        </p>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-soft md:text-base">
          감사조서에 들어갈 숫자는 <b>재현되고 추적돼야</b> 하기 때문입니다(감사기준서 230).
          설명 생성만 분리해 두면, 규칙기반에서 향후 로컬 언어모델로 바꿔도 숫자는 흔들리지 않습니다.
        </p>

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          {[
            {
              t: "재현 가능성",
              d: "점수 = 배점 합 ÷ 만점 × 100. 원배점합과 만점을 결과에 함께 담아, 제3자가 손으로도 검산할 수 있습니다.",
            },
            {
              t: "판정이 아닌 우선순위",
              d: "높은 점수는 “부정이다”가 아니라 “먼저 보라”입니다. 최종 판단은 증빙과 감사인의 전문가적 판단에 있습니다(200).",
            },
            {
              t: "원장은 로컬에 머문다",
              d: "분석 파이프라인은 전부 로컬에서 돌며 원장을 외부로 보내지 않습니다. 이 사이트에는 파일 업로드·분석 API가 없고, 포함된 합성 JSON 외의 원장 데이터가 없습니다(외부 폰트·스크립트 CDN도 쓰지 않습니다).",
            },
          ].map((x) => (
            <div key={x.t} className="rounded-xl bg-surface p-4">
              <h3 className="text-sm font-extrabold text-ink">{x.t}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{x.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 기준 매핑 */}
      <section className="mt-8">
        <h2 className="sec-title">근거 감사기준서</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {manifest.standards.map((s) => (
            <span
              key={s}
              className="rounded-full border border-line bg-white px-3 py-1.5 text-xs font-bold text-ink-soft"
            >
              {s}
            </span>
          ))}
        </div>
        <p className="mt-4 text-xs leading-relaxed text-muted">
          ⚠️ {fraudScores.disclaimer} · 본 사이트의 모든 수치는 합성 데이터 기준이며 실제 회사·감사
          결과와 무관합니다.
        </p>
      </section>

      <div className="mt-10 flex flex-wrap gap-3">
        <Link href="/dashboard" className="btn-primary">
          대시보드 보기 →
        </Link>
        <Link href="/case-study" className="btn-ghost">
          탐지 사례 5건
        </Link>
      </div>
    </div>
  );
}
