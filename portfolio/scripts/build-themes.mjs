// 단일 디자인(PwC)으로 정적 사이트를 빌드한다.
//   THEME 환경변수 → <html data-theme> 에 구워지지만, 현재 디자인은 pwc 하나로 고정.
//   결과: dist/pwc (완성품).
import { execSync } from "node:child_process";
import { rmSync, cpSync } from "node:fs";
import { join } from "node:path";

const THEMES = ["pwc"];
const root = process.cwd();
const outDir = join(root, "out");
const distRoot = join(root, "dist");

for (const theme of THEMES) {
  console.log(`\n=== 테마 빌드: ${theme} ===`);
  rmSync(outDir, { recursive: true, force: true });
  execSync("next build", { stdio: "inherit", env: { ...process.env, THEME: theme } });

  const dest = join(distRoot, theme);
  rmSync(dest, { recursive: true, force: true });
  cpSync(outDir, dest, { recursive: true });
  console.log(`→ dist/${theme} 완료`);
}

console.log("\n전체 테마 빌드 완료. dist/<테마> 폴더를 회사별로 따로 배포/인쇄하세요.");
