# koreatech-notice-bot

학교·학과·생활관 공지를 모아 AI로 정리하고, 나에게 맞는 공지를 매일 아침 디스코드로 알려주는 봇

## 폴더 구조
- `src/` 파이썬 코드
- `data/` profile.json, notices.json
- `docs/` 웹페이지 (GitHub Pages)
- `.github/workflows/` GitHub Actions 설정

## 브랜치 규칙
1. main 브랜치에는 직접 올리지 않는다
2. 각자 자기 브랜치에서 작업한다
   - 이민서(A): `a-crawler`
   - 한재원(B): `b-ai`
   - 만비카(C): `c-data`
   - 홍성민(D): `d-web`
3. 작업이 끝나면 PR을 올리고, 한 명 이상 리뷰한 뒤 합친다
4. API 키와 웹후크 주소는 코드나 단톡방에 올리지 않는다 (Secrets에만 등록)
