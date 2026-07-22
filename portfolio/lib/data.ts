// 빌드 타임에 FR-14 결과 JSON을 그대로 읽어 타입과 함께 노출한다.
// 웹은 매번 분석하지 않고 이 JSON만 읽어 시각화한다(서버 불필요·즉시 표시).
import summaryJson from "@/data/summary.json";
import accountRisksJson from "@/data/account_risks.json";
import monthlyVariancesJson from "@/data/monthly_variances.json";
import driverJournalsJson from "@/data/driver_journals.json";
import journalFlagsJson from "@/data/journal_flags.json";
import fraudScoresJson from "@/data/fraud_scores.json";
import validationJson from "@/data/validation_results.json";
import manifestJson from "@/data/index.json";

export interface BalanceQuality {
  /** 완벽 / 사실상 일치 / 근접 / 검토 필요 */
  grade: string;
  diff: number;
  ratio: number;
}

export interface Summary {
  company: string;
  period: string;
  period_prior: string;
  method: string;
  journal_count: number;
  account_count: number;
  high_risk_accounts: number;
  /** 등급 무관, 플래그가 하나라도 있는 계정 수(3초 요약 배너용) */
  flagged_accounts: number;
  flagged_journals: number;
  variance_flags: number;
  high_grade_variances: number;
  fraud_high: number;
  fraud_medium: number;
  /** 성과중요성 = 매출 × 0.5% × 75% (fr04·Streamlit과 동일 규칙) */
  performance_materiality: number | null;
  balance_quality: BalanceQuality;
  is_synthetic: boolean;
}

export interface AccountRisk {
  account: string;
  account_code: string;
  risk_score: number;
  grade: string;
  grade_en: string;
  flagged_months: number;
  worst_month: string;
  worst_direction: string;
  worst_robust_z: number;
  worst_deviation: number;
}

export interface MonthlyVariance {
  account: string;
  account_code: string;
  month: string;
  actual: number | null;
  expected: number | null;
  lower: number | null;
  upper: number | null;
  robust_z: number | null;
  is_anomaly: boolean | null;
  method: string | null;
}

/**
 * 이상월에 그 달 금액이 컸던 전표(원장에서 금액 규모 순, 전표번호 단위 합산).
 * 편차의 분해가 아니다 — 기대치는 과거 분포에서 나온 값이라 개별 전표로 귀속되지 않는다.
 * journal_flags(부정 스크리닝)와도 다른 축 — 수상함이 아니라 금액으로 뽑으므로
 * 정상적인 대형 거래도 포함된다. 부호는 그래프의 월값과 같은 자연방향 기준.
 */
export interface DriverJournal {
  journal_id: string;
  date: string;
  memo: string | null;
  counterparty: string | null;
  amount: number;
  /** amount / month_net. 상쇄가 크면(|net| < 총활동액 10%) null. 100% 초과·음수 가능. */
  share_of_month_net: number | null;
}

export interface DriverGroup {
  account: string;
  account_code: string;
  month: string;
  direction: string;
  deviation: number;
  month_net: number;
  month_gross: number;
  /** 전표 수(원장 행 수 아님 — 전표번호로 합산한 뒤 센 값) */
  journal_count: number;
  line_count: number;
  shown_count: number;
  /** 상위 N건 |금액| 합 / month_gross */
  shown_coverage: number | null;
  journals: DriverJournal[];
}

export interface ReasonDetail {
  code: string;
  name: string;
  points: number;
}

export interface JournalFlag {
  rank: number;
  journal_id: string;
  date: string;
  account: string;
  memo: string | null;
  counterparty: string | null;
  amount: number;
  amount_materiality: number | null;
  counter_account: string | null;
  /** 이 전표에서 걸린 계정이 놓인 분개 방향 — "차변" | "대변"(원장 실집계 기준). */
  account_dc: "차변" | "대변" | null;
  risk_score: number;
  raw_points: number;
  max_possible_points: number;
  risk_level: string;
  risk_level_ko: string;
  reasons: string[];
  reasons_detail: ReasonDetail[];
}

export interface FraudModel {
  model: string;
  name: string;
  score: number | null;
  zone: string | null;
  thresholds: Record<string, number>;
  note: string;
  indicators: Record<string, number | null> | null;
}

export interface FraudScores {
  disclaimer: string;
  models: { altman_z: FraudModel; beneish_m: FraudModel };
}

export interface ValidationCheck {
  level: string;
  item: string;
  result: string;
  count: number | null;
  description: string | null;
}

export interface Validation {
  overall: {
    passed: boolean;
    error_fail_count: number;
    warning_count: number;
    total_checks: number;
  } | null;
  checks: ValidationCheck[];
}

export interface Manifest {
  company: string;
  period: string;
  generated_at: string;
  is_synthetic: boolean;
  note: string;
  standards: string[];
  schema_notes: Record<string, string>;
  files: string[];
}

export const summary = summaryJson as Summary;
export const accountRisks = accountRisksJson as AccountRisk[];
export const monthlyVariances = monthlyVariancesJson as MonthlyVariance[];
export const driverJournals = driverJournalsJson as DriverGroup[];
export const journalFlags = journalFlagsJson as JournalFlag[];
export const fraudScores = fraudScoresJson as unknown as FraudScores;
export const validation = validationJson as unknown as Validation;
export const manifest = manifestJson as Manifest;

/**
 * 이상 판정 임계값(fr03_expectation.py의 K와 같은 값, 표시용).
 * 화면은 이 값으로 이상 여부를 재판정하지 않는다 — 판정은 엔진의 is_anomaly가 유일한 출처이고
 * (엔진은 |z|>K에 더해 판정대상·평가월 조건까지 본다), 이 상수는 설명 문구와 색 스케일에만 쓴다.
 */
export const Z_REF = 3.5;

// ── 빌드타임 자기검증 ────────────────────────────────────
// "화면의 걸린 이유만 보면 점수가 재현된다"는 주장은 검증돼야 주장이 된다.
// JSON이 갱신됐을 때 화면에 조용히 틀린 숫자가 뜨는 대신 빌드가 깨지게 한다.
for (const j of journalFlags) {
  const tagSum = j.reasons_detail.reduce((s, r) => s + r.points, 0);
  if (tagSum !== j.raw_points) {
    throw new Error(
      `[data] ${j.journal_id}(${j.account}): 배점 태그 합 ${tagSum} ≠ raw_points ${j.raw_points}`,
    );
  }
  const reproduced = Math.round((j.raw_points / j.max_possible_points) * 100);
  if (reproduced !== j.risk_score) {
    throw new Error(
      `[data] ${j.journal_id}(${j.account}): 재현 점수 ${reproduced} ≠ risk_score ${j.risk_score}`,
    );
  }
}

// (계정, 월)과 (계정코드, 월)은 둘 다 유일해야 한다.
//  · (계정,월)   — 히트맵과 상세 그래프가 서로 다른 행을 골라 같은 달을 다르게 그리는 것을 막는다.
//  · (계정코드,월) — 근거 전표 결합이 이 키를 쓴다. 중복이면 Map이 조용히 덮어써 오결합된다.
// 키는 JSON.stringify([코드, 월])로 만든다 — 구분자 문자가 값 안에 들어가도 뭉개지지 않게.
{
  const byName = new Set<string>();
  const byCode = new Set<string>();
  for (const v of monthlyVariances) {
    const kn = JSON.stringify([v.account, v.month]);
    if (byName.has(kn)) {
      throw new Error(`[data] monthly_variances에 (계정,월) 중복: ${v.account} / ${v.month}`);
    }
    byName.add(kn);

    const kc = JSON.stringify([v.account_code, v.month]);
    if (byCode.has(kc)) {
      throw new Error(
        `[data] monthly_variances에 (계정코드,월) 중복: ${v.account_code} / ${v.month}`,
      );
    }
    byCode.add(kc);
  }
}

// 근거 전표는 그래프와 짝을 이뤄야 의미가 있다. 어긋나면 빌드를 깬다.
// 자연방향은 '계정코드'별 규칙이므로 결합·검증 키도 계정코드를 포함해야 한다.
{
  const byKey = new Map(
    monthlyVariances.map((v) => [JSON.stringify([v.account_code, v.month]), v] as const),
  );
  const seen = new Set<string>();
  for (const g of driverJournals) {
    const k = JSON.stringify([g.account_code, g.month]);
    if (seen.has(k)) throw new Error(`[data] 근거 전표 그룹 중복: ${k}`);
    seen.add(k);

    const v = byKey.get(k);
    if (!v) throw new Error(`[data] 근거 전표의 (계정코드,월)이 monthly_variances에 없음: ${k}`);
    if (!v.is_anomaly) throw new Error(`[data] 이상月이 아닌데 근거 전표가 붙음: ${k}`);
    if (v.account !== g.account) {
      throw new Error(`[data] ${k}: 계정명 불일치 — ${v.account} vs ${g.account}`);
    }
    // 부호 규칙(자연방향)이 fr03과 어긋나면 매출·부채 계정에서 그래프 +76억 / 근거 -76억으로
    // 뒤집힌다. actual이 없으면 대조할 수 없으므로 그것도 실패로 본다.
    if (v.actual == null) throw new Error(`[data] ${k}: actual이 없어 month_net을 대조할 수 없음`);
    if (Math.abs(v.actual - g.month_net) > 1) {
      throw new Error(
        `[data] ${k}: month_net ${g.month_net} ≠ 그래프 월값 ${v.actual} — 부호 규칙(자연방향) 불일치 의심`,
      );
    }
    // 구조 불변식
    if (g.journals.length !== g.shown_count) {
      throw new Error(`[data] ${k}: shown_count ${g.shown_count} ≠ journals ${g.journals.length}`);
    }
    if (g.shown_count > g.journal_count) {
      throw new Error(`[data] ${k}: 표시 ${g.shown_count} > 전표 수 ${g.journal_count}`);
    }
    if (g.month_gross + 1 < Math.abs(g.month_net)) {
      throw new Error(`[data] ${k}: 총활동액(${g.month_gross}) < |순액|(${g.month_net})`);
    }
  }
}

/** 사례 페이지가 참조하는 전표·계정이 JSON에 없으면 화면에 undefined를 흘리지 않고 빌드를 깬다. */
export function mustFindJournal(id: string, account: string): JournalFlag {
  const j = journalFlags.find((x) => x.journal_id === id && x.account === account);
  if (!j) throw new Error(`[data] 사례가 참조하는 전표 없음: ${id} / ${account}`);
  return j;
}

export function mustFindAccountRisk(account: string): AccountRisk {
  const a = accountRisks.find((x) => x.account === account);
  if (!a) throw new Error(`[data] 사례가 참조하는 계정 없음: ${account}`);
  return a;
}

/** monthly_variances에 실제로 기대치가 산출된 연도 목록(내림차순). */
export const analyzedYears: string[] = [
  ...new Set(monthlyVariances.map((v) => v.month.slice(0, 4))),
].sort((a, b) => b.localeCompare(a));

/** 월별 기대치 분석이 수행된 계정 수(원장 전체 계정 수와 다를 수 있다). */
export const analyzedAccountCount = new Set(monthlyVariances.map((v) => v.account)).size;

// ── 포맷 헬퍼 ───────────────────────────────────────────
const EOK = 100_000_000;

/** 원 → 억원 문자열(부호 옵션). 1_234_000_000 → "12.34" */
export function eok(won: number | null | undefined, signed = false): string {
  if (won === null || won === undefined) return "-";
  const v = won / EOK;
  const s = v.toLocaleString("ko-KR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return signed && v > 0 ? `+${s}` : s;
}

/** "2025-08" → "25년 8월" (multi) 또는 "8월" */
export function monthLabel(m: string, multi = true): string {
  const [y, mm] = m.split("-");
  return multi ? `${y.slice(2)}년 ${Number(mm)}월` : `${Number(mm)}월`;
}

/** 등급(높음/중간/낮음) → 색 클래스 */
export function gradeColor(grade: string): { text: string; bg: string; dot: string } {
  if (grade === "높음" || grade === "High")
    return { text: "text-danger", bg: "bg-red-50", dot: "bg-danger" };
  if (grade === "중간" || grade === "Medium")
    return { text: "text-amber-600", bg: "bg-amber-50", dot: "bg-amber-500" };
  return { text: "text-muted", bg: "bg-surface", dot: "bg-gray-300" };
}
