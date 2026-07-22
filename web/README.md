# GL 감사 대시보드 — 정적 데모 (Vercel 배포용)

**가상제조(주) 합성 데이터**로 만든 포트폴리오 데모입니다.
분석적 절차(감사기준서 520)·부정 스크리닝(240)·분식위험(Beneish M/Altman Z')의 결과 화면을
서버 없이 도는 단일 `index.html`로 담았습니다. **실제 감사자료는 포함되어 있지 않습니다.**

## 폴더 구성
```
web/
├── index.html      ← 배포되는 실제 페이지 (자체 완결형)
├── vercel.json     ← Vercel 설정
├── .vercelignore   ← _build 제외 (배포엔 index.html만 올라감)
└── _build/         ← 중간 산출물(합성데이터 파이프라인 결과) · 배포 제외
```

## 다시 굽는 법 (데이터/디자인 수정 시)
```
python src/make_demo_data.py       # 합성 원장 재생성
python src/build_static_site.py    # web/index.html 재생성
```

## Vercel 배포 (이 web/ 폴더만 올림)
```
cd web
vercel            # 최초 1회: 로그인 + 프로젝트 생성 (프리뷰 링크)
vercel --prod     # 정식 배포 (공개 링크)
```
> ⚠️ 반드시 **web/ 폴더에서만** 배포하세요. 상위 폴더에는 실제 클라이언트 자료가 있어
> 절대 공개되면 안 됩니다.
