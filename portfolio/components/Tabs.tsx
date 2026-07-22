"use client";

import { useRef, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  /** 탭 라벨 옆 작은 배지(건수 등). 없으면 생략. */
  badge?: string;
  content: ReactNode;
}

interface Props {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  /** 탭 목록 위에 항상 보이는 영역(연도 선택 등). 탭별로 다르면 각 content에 넣을 것. */
  toolbar?: ReactNode;
}

/**
 * 접근성 있는 탭. role=tablist/tab/tabpanel + 좌우 화살표 이동(roving tabindex).
 * 비활성 탭은 언마운트하지 않고 hidden 처리 — 탭을 오갈 때 선택 상태가 초기화되지 않게.
 */
export default function Tabs({ items, activeId, onChange, toolbar }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const idx = Math.max(0, items.findIndex((t) => t.id === activeId));

  const move = (next: number) => {
    const n = (next + items.length) % items.length;
    onChange(items[n].id);
    refs.current[n]?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight") { e.preventDefault(); move(idx + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); move(idx - 1); }
    else if (e.key === "Home") { e.preventDefault(); move(0); }
    else if (e.key === "End") { e.preventDefault(); move(items.length - 1); }
  };

  return (
    <div>
      {/* 탭 바 — 현재 위치는 하단 강조색 밑줄(글래스 블러 없이 흰 배경 고정) */}
      <div className="sticky top-[72px] z-40 -mx-5 border-b border-line bg-white px-5 md:-mx-10 md:px-10">
        <div
          role="tablist"
          aria-label="대시보드 항목"
          onKeyDown={onKeyDown}
          className="flex gap-0.5 overflow-x-auto"
        >
          {items.map((t, i) => {
            const on = t.id === activeId;
            return (
              <button
                key={t.id}
                ref={(el) => { refs.current[i] = el; }}
                role="tab"
                id={`tab-${t.id}`}
                aria-selected={on}
                aria-controls={`panel-${t.id}`}
                tabIndex={on ? 0 : -1}
                onClick={() => onChange(t.id)}
                className={`shrink-0 whitespace-nowrap border-b-[3px] px-3.5 py-2 text-[0.92rem] font-semibold transition-colors ${
                  on
                    ? "border-rail text-ink"
                    : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {t.label}
                {t.badge && (
                  <span className="ml-1.5 rounded-full bg-surface px-1.5 py-0.5 text-[0.65rem] font-extrabold text-muted">
                    {t.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        {toolbar}
      </div>

      <div className="pt-6">
        {items.map((t) => (
          <div
            key={t.id}
            role="tabpanel"
            id={`panel-${t.id}`}
            aria-labelledby={`tab-${t.id}`}
            hidden={t.id !== activeId}
          >
            {t.id === activeId && t.content}
          </div>
        ))}
      </div>
    </div>
  );
}
