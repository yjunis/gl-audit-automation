import { Z_REF, type MonthlyVariance } from "@/lib/data";

interface Props {
  data: MonthlyVariance[];
  accounts: string[]; // 위험 순서대로 정렬된 계정명
  year: string;
  selected?: string;
  onSelect?: (account: string) => void;
}

/**
 * 셀 배경색. 이상 여부는 화면에서 다시 판정하지 않고 분석 엔진의 is_anomaly를 그대로 쓴다.
 * (엔진은 |z|>3.5에 더해 판정대상·평가월 조건까지 보므로, 화면이 |z|만으로 재판정하면 어긋난다.)
 * |z|는 색의 진하기에만 쓴다.
 */
function cellColor(absz: number, anomaly: boolean): string {
  const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);
  if (anomaly) {
    const t = Math.min(1, Math.max(0, (absz - Z_REF) / 4.5));
    return `rgb(${lerp(246, 228, t)},${lerp(150, 0, t)},${lerp(170, 43, t)})`;
  }
  if (absz <= 0.01) return "#F8F8FA";
  const t = Math.min(1, absz / Z_REF);
  return `rgb(${lerp(240, 150, t)},${lerp(240, 150, t)},${lerp(244, 160, t)})`;
}

interface Cell {
  z: number;
  anomaly: boolean;
}


export default function RiskHeatmap({
  data,
  accounts,
  year,
  selected,
  onSelect,
}: Props) {
  const months = Array.from({ length: 12 }, (_, i) =>
    `${year}-${String(i + 1).padStart(2, "0")}`,
  );

  // grid[account][month] = { |z|, is_anomaly }
  // (계정, 월)의 유일성은 lib/data.ts가 빌드타임에 보장하므로 병합 규칙이 필요 없다.
  // 상세 그래프(AccountDetailChart)도 같은 전제로 한 행만 집으므로 두 화면이 항상 같은 행을 본다.
  const grid = new Map<string, Map<string, Cell>>();
  for (const r of data) {
    if (!r.month.startsWith(year)) continue;
    if (!grid.has(r.account)) grid.set(r.account, new Map());
    grid.get(r.account)!.set(r.month, {
      z: Math.abs(r.robust_z ?? 0),
      anomaly: Boolean(r.is_anomaly),
    });
  }

  const rows = accounts.filter((a) => grid.has(a));

  if (rows.length === 0) {
    return (
      <p className="rounded-xl border border-line bg-surface px-4 py-6 text-sm text-muted">
        {year}년은 기대치가 산출된 계정이 없습니다.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-separate border-spacing-[2px]">
        <caption className="sr-only">
          {year}년 계정별·월별 기대치 이탈도(|z|) 히트맵. 계정 버튼을 누르면 상세 그래프가 해당
          계정으로 바뀝니다.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="sticky left-0 z-10 bg-white text-left text-[0.7rem] font-semibold text-muted">
              <span className="sr-only">계정</span>
            </th>
            {months.map((m) => (
              <th
                key={m}
                scope="col"
                className="pb-1 text-center text-[0.65rem] font-semibold text-muted"
              >
                {Number(m.slice(5))}월
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((acct) => {
            const cells = grid.get(acct)!;
            const isSel = selected === acct;
            return (
              <tr key={acct}>
                <th
                  scope="row"
                  className="sticky left-0 z-10 whitespace-nowrap bg-white pr-2 text-right"
                >
                  <button
                    type="button"
                    onClick={() => onSelect?.(acct)}
                    aria-pressed={isSel}
                    className={`rounded px-1 text-xs font-semibold ${
                      isSel ? "bg-brand/40 text-ink" : "text-ink-soft hover:bg-surface"
                    }`}
                  >
                    {acct}
                  </button>
                </th>
                {months.map((m) => {
                  const c = cells.get(m);
                  const z = c?.z ?? 0;
                  const anomaly = c?.anomaly ?? false;
                  return (
                    <td
                      key={m}
                      className="h-7 rounded-[3px] p-0 text-center align-middle text-[0.6rem] font-bold"
                      style={{
                        background: cellColor(z, anomaly),
                        outline: isSel ? "1.5px solid #2E2E38" : "none",
                      }}
                    >
                      <span className="sr-only">
                        {acct} {Number(m.slice(5))}월 이탈도 {z.toFixed(1)}
                        {anomaly ? " · 이상 후보" : ""}
                      </span>
                      <span aria-hidden style={{ color: anomaly ? "#fff" : "transparent" }}>
                        {anomaly ? z.toFixed(1) : "·"}
                      </span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[0.7rem] leading-relaxed text-muted">
        색이 진할수록(빨강) 이탈이 큼 · 이상 후보로 판정된 칸에는 이탈도 |z|를 함께 표시해 색만으로
        판단하지 않게 했습니다 · 이상 판정은 분석 엔진 결과를 그대로 씁니다(|z|&gt;{Z_REF} 및 평가
        대상월 조건) · 계정명을 누르면 아래 상세로 이동
      </p>
    </div>
  );
}
