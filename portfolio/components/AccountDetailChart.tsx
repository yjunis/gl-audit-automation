"use client";

import { useEffect, useState } from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { MonthlyVariance } from "@/lib/data";

const EOK = 100_000_000;

/** 기대구간 밴드는 강조색(--brand)을 따른다. SVG fill이라 CSS 변수를 직접 못 받아
 *  마운트 후 계산값을 읽어 rgb() 문자열로 만든다. 미측정 시 PwC 오렌지로 폴백. */
function useAccent(): string {
  const [accent, setAccent] = useState("rgb(208 74 2)");
  useEffect(() => {
    const ch = getComputedStyle(document.documentElement).getPropertyValue("--brand").trim();
    if (ch) setAccent(`rgb(${ch})`);
  }, []);
  return accent;
}

interface Props {
  data: MonthlyVariance[];
  account: string;
  curYear: string;
  priorYear: string;
}

interface Point {
  m: string;
  actual: number | null;
  prior: number | null;
  band: [number, number] | null;
  anomaly: boolean;
}

interface DotProps {
  cx?: number;
  cy?: number;
  payload?: Point;
}

function AnomalyDot({ cx, cy, payload }: DotProps) {
  if (!payload?.anomaly || cx == null || cy == null) {
    return <circle cx={cx} cy={cy} r={0} fill="none" />;
  }
  return (
    <g>
      <line x1={cx - 5} y1={cy - 5} x2={cx + 5} y2={cy + 5} stroke="#C4231A" strokeWidth={2.2} />
      <line x1={cx - 5} y1={cy + 5} x2={cx + 5} y2={cy - 5} stroke="#C4231A" strokeWidth={2.2} />
    </g>
  );
}

export default function AccountDetailChart({ data, account, curYear, priorYear }: Props) {
  const accent = useAccent();
  // (계정, 월)의 유일성은 lib/data.ts가 빌드타임에 강제하므로 find로 집은 행이 곧 그 달의 유일한
  // 행이다. 히트맵도 같은 전제로 같은 행을 보므로 두 화면의 이상 표시가 어긋나지 않는다.
  const pick = (year: string, mm: string) =>
    data.find((d) => d.account === account && d.month === `${year}-${mm}`);

  const points: Point[] = Array.from({ length: 12 }, (_, i) => {
    const mm = String(i + 1).padStart(2, "0");
    const cur = pick(curYear, mm);
    const pri = pick(priorYear, mm);
    // 하한>상한이거나 비유한값이면 밴드를 그리지 않는다(없는 구간을 지어내지 않음).
    const bandOk =
      cur != null &&
      cur.lower != null &&
      cur.upper != null &&
      Number.isFinite(cur.lower) &&
      Number.isFinite(cur.upper) &&
      cur.lower <= cur.upper;
    const band: [number, number] | null = bandOk
      ? [cur!.lower! / EOK, cur!.upper! / EOK]
      : null;
    return {
      m: `${i + 1}월`,
      actual: cur?.actual != null ? cur.actual / EOK : null,
      prior: pri?.actual != null ? pri.actual / EOK : null,
      band,
      anomaly: Boolean(cur?.is_anomaly),
    };
  });

  const hasPrior = points.some((p) => p.prior != null);

  return (
    <div className="h-[320px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={points} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#E7E7EC" vertical={false} />
          <XAxis dataKey="m" tick={{ fontSize: 12, fill: "#747480" }} tickLine={false} axisLine={{ stroke: "#C4C4CD" }} />
          <YAxis
            tick={{ fontSize: 11, fill: "#747480" }}
            tickLine={false}
            axisLine={false}
            width={48}
            label={{ value: "억원", angle: -90, position: "insideLeft", fontSize: 11, fill: "#747480" }}
          />
          <Tooltip
            formatter={(v: number | number[], name: string) => {
              if (Array.isArray(v)) return [`${v[0].toFixed(2)} ~ ${v[1].toFixed(2)} 억`, "기대구간"];
              return [`${Number(v).toFixed(2)} 억`, name];
            }}
            contentStyle={{ fontSize: 12, borderRadius: 0, border: "1px solid #C4C4CD" }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area
            dataKey="band"
            name="기대구간"
            stroke="none"
            fill={accent}
            fillOpacity={0.18}
            isAnimationActive={false}
          />
          {hasPrior && (
            <Line
              dataKey="prior"
              name={`전기 ${priorYear}`}
              stroke="#747480"
              strokeWidth={2}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
              />
          )}
          <Line
            dataKey="actual"
            name={`당기 ${curYear}`}
            stroke="#2E2E38"
            strokeWidth={2.4}
            dot={<AnomalyDot />}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
