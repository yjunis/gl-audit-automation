import type { Config } from "tailwindcss";

// 디자인 시스템(PwC: 오렌지 강조 + 세리프 제목) 적용:
//  · 무채색 90% + 오렌지(#D04A02) 강조 2% 이내
//  · 모서리 라운드 0px, 그림자 없음, 그라디언트 없음
//  · 굵기는 400/600/700 세 단계만 (extrabold·black도 700으로 매핑해 강제)
//  · Inter/Pretendard 우선(로컬), 제목은 세리프(Georgia/명조)
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 값은 globals.css의 CSS 변수(공백구분 RGB 채널)에서 온다 → data-theme으로 교체 가능.
        // rgb(var(--x) / <alpha-value>) 형식이라 bg-brand/15 같은 투명도 유틸도 그대로 동작한다.
        black: "rgb(var(--black) / <alpha-value>)", // 강조색 위 글자(어두운 경우)
        ink: "rgb(var(--ink) / <alpha-value>)", // text-primary
        "ink-soft": "rgb(var(--ink) / <alpha-value>)", // primary와 동일 톤으로 통일
        brand: "rgb(var(--brand) / <alpha-value>)", // 강조색(테마별) — 면+글자
        "on-accent": "rgb(var(--on-accent) / <alpha-value>)", // 강조색 위 글자(테마별)
        rail: "rgb(var(--rail) / <alpha-value>)", // 포인트 레일색 — 글자 없는 얇은 면(밑줄·좌측바·로고칩)
        inverse: "rgb(var(--surface-inverse) / <alpha-value>)", // 다크 섹션 배경(히어로·표지·푸터)
        "brand-deep": "rgb(var(--brand-deep) / <alpha-value>)", // 챕터 번호 등은 그레이
        danger: "rgb(var(--danger) / <alpha-value>)", // error
        warning: "rgb(var(--warning) / <alpha-value>)",
        success: "rgb(var(--success) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)", // text-secondary
        line: "rgb(var(--line) / <alpha-value>)", // border-default
        "line-soft": "rgb(var(--line-soft) / <alpha-value>)", // 얕은 구분선·줄무늬
        surface: "rgb(var(--surface) / <alpha-value>)", // bg-subtle
      },
      fontFamily: {
        sans: ["var(--font-sans)"], // 테마별 본문 폰트(globals.css의 --font-sans)
        display: ["var(--font-display)"], // 제목 폰트(PwC 세리프 — globals.css의 --font-display)
        mono: [
          "JetBrains Mono", "D2Coding", "ui-monospace", "monospace",
        ],
      },
      fontSize: {
        // 타입 스케일 — 큰 위계에만 골라 적용
        label: ["0.75rem", { lineHeight: "1.2", letterSpacing: "0.08em" }],
        // 한글은 라틴보다 글자 밀도가 높아, 큰 제목일수록 행간을 넉넉히 주고
        // 음수 자간은 얕게 잡아야 답답해 보이지 않는다.
        lead: ["1.1875rem", { lineHeight: "1.75" }],
        h4: ["1.25rem", { lineHeight: "1.45", letterSpacing: "0" }],
        h3: ["1.625rem", { lineHeight: "1.4", letterSpacing: "-0.005em" }],
        h2: ["2.25rem", { lineHeight: "1.3", letterSpacing: "-0.01em" }],
        display: ["clamp(1.875rem, 4vw, 3rem)", { lineHeight: "1.32", letterSpacing: "-0.015em" }],
        stat: ["clamp(3rem, 6vw, 5rem)", { lineHeight: "1.0", letterSpacing: "-0.03em" }],
      },
      fontWeight: {
        // 400 / 600 / 700 세 단계만. 800·900 요청도 700으로 눌러 규칙을 강제한다.
        normal: "400",
        medium: "600",
        semibold: "600",
        bold: "700",
        extrabold: "700",
        black: "700",
      },
      borderRadius: {
        // 각진 모서리가 이 시스템의 정체성 — 모든 라운드 유틸을 0으로.
        none: "0",
        sm: "0",
        DEFAULT: "0",
        md: "0",
        lg: "0",
        xl: "0",
        "2xl": "0",
        "3xl": "0",
        full: "0",
      },
      boxShadow: {
        // 그림자 금지 — 모든 shadow 유틸을 none으로.
        none: "none",
        sm: "none",
        DEFAULT: "none",
        md: "none",
        lg: "none",
        xl: "none",
        "2xl": "none",
        inner: "none",
      },
      maxWidth: {
        content: "1280px", // 컨테이너 최대 폭
        prose: "720px", // 본문 텍스트 컬럼 최대 폭
      },
    },
  },
  plugins: [],
};

export default config;
