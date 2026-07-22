/** @type {import('next').NextConfig} */
const nextConfig = {
  // 정적 익스포트 — 서버 없이 도는 순수 정적 사이트(out/). 무서버·무대기·무데이터유출.
  output: "export",
  // next/image 최적화 서버가 없으므로 비활성(정적 배포)
  images: { unoptimized: true },
  // 정적 호스팅에서 새로고침·직접 URL 접근이 안정적이도록 각 경로를 폴더/ 형태로
  trailingSlash: true,
};

export default nextConfig;
