import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import Nav from "@/components/Nav";
import { manifest } from "@/lib/data";

export const metadata: Metadata = {
  title: "GL 분석적 절차·부정탐지 자동화 | 정여주 포트폴리오",
  description:
    "총계정원장(GL)을 전수 분석해 이상 계정과 부정위험 전표를 자동 선별하는 감사 자동화 도구. 감사기준서 520·240 기반, 합성 데이터 데모.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // 외부 폰트 CDN을 쓰지 않는다(제3자로 나가는 요청 0건 유지).
  // 로컬에 Pretendard가 있으면 쓰고, 없으면 OS 기본 한글 폰트로 떨어진다.
  // 디자인은 단일 테마(PwC)로 고정한다.
  return (
    <html lang="ko" data-theme="pwc">
      <body className="min-h-screen bg-white font-sans text-ink">
        <Nav />
        <main>{children}</main>
        <footer className="mt-24 bg-inverse">
          <div className="container-page flex flex-col gap-5 py-12 text-white">
            <div className="flex items-center gap-2.5">
              <span className="h-4 w-4 bg-rail" aria-hidden />
              <span className="text-sm font-bold tracking-tight">GL 감사 자동화</span>
            </div>
            <div className="border-l-4 border-rail bg-white/5 px-4 py-3 text-sm text-line-soft">
              본 사이트는 <b className="text-white">가상제조(주) 합성 데이터</b>로 만든{" "}
              <b className="text-white">포트폴리오 데모</b>입니다. 실제 감사자료가 아니며, 직접 파일
              업로드 기능은 제공하지 않습니다.
            </div>
            <p className="max-w-prose text-sm leading-relaxed text-line-soft">
              분석적 절차(감사기준서 520) · 부정위험(240) · 위험평가(315) · 중요성(320) ·
              감사증거(500) · 감사문서화(230) · 전반적 목적(200) · 계속기업(570) 개념 참고 · 숫자는 결정론적 코드가 계산
            </p>
            <p className="text-xs text-line">
              데이터 생성 {manifest.generated_at} · 정여주 포트폴리오 ·{" "}
              <Link href="/methodology" className="underline decoration-rail underline-offset-4 hover:text-white">
                분석 방법
              </Link>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
