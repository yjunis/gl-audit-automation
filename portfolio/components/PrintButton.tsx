"use client";

/** 보고서를 브라우저 인쇄 대화상자로 연다(→ "PDF로 저장" 선택). 인쇄물에는 나오지 않는다. */
export default function PrintButton() {
  return (
    <button type="button" onClick={() => window.print()} className="btn-primary no-print">
      PDF로 저장 / 인쇄
    </button>
  );
}
