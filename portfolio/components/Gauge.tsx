// 선형 게이지 — 점수(M·Z)가 임계구간 어디에 위치하는지 한눈에.
// 반원 게이지보다 임계선 대비 위치가 명확하고 모바일에서 안정적.

export interface GaugeZone {
  to: number;
  color: string; // tailwind bg 클래스
  label: string;
}

export interface GaugeProps {
  title: string;
  value: number | null;
  min: number;
  max: number;
  zones: GaugeZone[];
  markers?: { at: number; label: string }[];
  caption?: string;
  judgement?: string;
}

function pct(v: number, min: number, max: number): number {
  if (!(max > min) || !Number.isFinite(v)) return 0;
  return Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100));
}

export default function Gauge({
  title,
  value,
  min,
  max,
  zones,
  markers = [],
  caption,
  judgement,
}: GaugeProps) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <div className="mb-1 text-sm font-extrabold text-ink">{title}</div>
      {value !== null ? (
        <>
          <div className="mb-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold tabular-nums text-ink">
              {value.toFixed(2)}
            </span>
            {judgement && (
              <span className="text-sm font-bold text-muted">{judgement}</span>
            )}
          </div>

          <div className="relative">
            {/* 구간 바 */}
            <div className="flex h-3 overflow-hidden rounded-full">
              {zones.map((z, i) => {
                const from = i === 0 ? min : zones[i - 1].to;
                // 구간이 역순이거나 범위를 벗어나도 음수 폭이 나오지 않게 한다.
                const width = Math.max(0, pct(z.to, min, max) - pct(from, min, max));
                return (
                  <div
                    key={z.label}
                    className={z.color}
                    style={{ width: `${width}%` }}
                    title={z.label}
                  />
                );
              })}
            </div>

            {/* 값 마커 */}
            <div
              className="absolute -top-1 h-5 w-0.5 bg-ink"
              style={{ left: `${pct(value, min, max)}%` }}
              aria-hidden
            />
            <div
              className="absolute -top-6 -translate-x-1/2 rounded bg-ink px-1.5 py-0.5 text-[0.65rem] font-bold text-white"
              style={{ left: `${pct(value, min, max)}%` }}
            >
              현재
            </div>

            {/* 임계선 마커 */}
            {markers.map((m) => (
              <div
                key={m.label}
                className="absolute top-3 -translate-x-1/2 text-[0.6rem] font-semibold text-muted"
                style={{ left: `${pct(m.at, min, max)}%` }}
              >
                <div className="mx-auto mb-0.5 h-2 w-px bg-muted" />
                {m.label}
              </div>
            ))}
          </div>

          {/* 구간 범례 */}
          <div className="mt-7 flex flex-wrap gap-x-4 gap-y-1 text-[0.7rem] text-muted">
            {zones.map((z) => (
              <span key={z.label} className="inline-flex items-center gap-1">
                <span className={`h-2 w-2 rounded-full ${z.color}`} />
                {z.label}
              </span>
            ))}
          </div>
        </>
      ) : (
        <p className="py-6 text-sm text-muted">
          2개 연도 데이터가 있어야 산출됩니다.
        </p>
      )}

      {caption && <p className="mt-2 text-[0.72rem] leading-relaxed text-muted">{caption}</p>}
    </div>
  );
}
