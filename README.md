# 한기대 공지비서 (koreatech-notice-bot)

흩어진 학교 공지를 모아 AI로 정리하고, 나에게 맞는 공지만 매일 아침 디스코드로 알려주는 자동 비서입니다.
서버 없이 GitHub Actions와 GitHub Pages만으로 돌아가며, 무료 API만 사용합니다.

- 저장소: https://github.com/seongminhong497-cell/koreatech-notice-bot
- 웹페이지: https://seongminhong497-cell.github.io/koreatech-notice-bot/

## 하는 일

1. **수집**: 학교 게시판 3개(일반, 장학, 학사)와 내 학과 게시판의 첫 페이지를 하루 4번 확인해 새 공지를 쌓습니다.
2. **AI 정리**: Gemini가 공지(이미지 포함)에서 대상, 마감일, 추가 일정, 할 일, 준비물, 분류를 뽑습니다.
3. **날씨**: 기상청 단기예보로 학교 위치의 오늘 날씨를 가져옵니다.
4. **관련도**: 내 설정(학과, 학년, 학적, 생활관, 관심 분야)과 비교해 별점 0~3과 이유를 매깁니다. 대상이 분명히 다르면 숨깁니다.
5. **알림**: 매일 07시 디스코드로 날씨, 마감 임박, 새 공지를 보내고, 웹페이지에 전체 목록을 보여 줍니다.

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `src/crawler.py` | 게시판 공지 수집 |
| `src/ai_extract.py` | AI로 공지 정보 추출 |
| `src/weather.py` | 기상청 날씨 |
| `src/relevance.py` | 별점, 마감 임박 계산 |
| `src/discord_notify.py` | 디스코드 아침 브리핑 |
| `src/apply_settings.py` | 설정 양식 내용을 `data/profile.json`에 반영 |
| `src/departments.py` | 학과 이름 통일 |
| `docs/index.html` | 웹페이지 (GitHub Pages) |
| `data/` | `notices.json`(공지), `profile.json`(내 설정), `weather.json`(날씨) |
| `.github/workflows/daily.yml` | 하루 4번 자동 실행 (07, 09, 13, 18시) |
| `.github/workflows/settings.yml` | 설정 이슈가 올라오면 설정 적용 |
| `.github/ISSUE_TEMPLATE/settings.yml` | "내 설정 바꾸기" 양식 |
| `DATA_FORMAT.md`, `RELEVANCE_RULES.md` | 데이터 형식, 별점 규칙 문서 |

## 필요한 모듈

`requirements.txt`에 있는 외부 패키지 3개만 설치하면 됩니다. 나머지는 파이썬 기본 모듈입니다. (Python 3.12 기준)

| 패키지 | 용도 |
|---|---|
| `requests` | 게시판, 기상청, 디스코드, 이미지 요청 |
| `beautifulsoup4` | 게시판 HTML에서 제목, 본문, 이미지 추출 |
| `google-genai` | Gemini AI 호출 |

## 필요한 키

| 이름 | 받는 곳 | 비고 |
|---|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) → Create API key | 무료 |
| `WEATHER_API_KEY` | [공공데이터포털](https://www.data.go.kr) → "기상청_단기예보 조회서비스" 활용신청 | **일반 인증키(Decoding)** 사용 |
| `DISCORD_WEBHOOK` | 디스코드 채널 → 채널 편집 → 연동 → 웹후크 → 새 웹후크 → URL 복사 | 브리핑을 받을 채널 |

키는 코드나 채팅방에 올리지 말고 GitHub Secrets(또는 내 컴퓨터의 환경 변수)에만 넣습니다.

## 설치 방법 A: 내 GitHub에서 자동으로 쓰기 (추천)

컴퓨터에 아무것도 설치하지 않아도 됩니다.

1. 이 저장소 오른쪽 위 **Use this template → Create a new repository**로 내 저장소를 만듭니다. (Public 권장)
2. 내 저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 위의 키 3개를 같은 이름으로 등록합니다.
3. **Settings → Actions → General → Workflow permissions**에서 **Read and write permissions**를 고르고 저장합니다.
4. **Settings → Pages**에서 Source를 **Deploy from a branch**, Branch를 **main / docs**로 고르고 저장합니다.
5. **Issues → New issue → 내 설정 바꾸기**에서 내 학과, 학년, 관심 분야를 고르고 제출합니다. 1분쯤 뒤 설정이 적용되고 이슈가 닫힙니다.
6. **Actions → 공지 자동 정리 → Run workflow**로 첫 실행을 합니다. 이후로는 하루 4번 자동으로 실행됩니다.
7. `https://내아이디.github.io/저장소이름/`에서 웹페이지를 확인합니다. 웹페이지와 디스코드 링크는 내 저장소 주소를 자동으로 따라갑니다.

참고
- 처음 복사한 저장소에는 원래 저장소의 공지와 설정이 들어 있습니다. 5번에서 내 설정으로 바꾸면 별점이 다시 계산됩니다.
- 학과를 바꾸면 다음 실행부터 그 학과 게시판을 수집합니다.
- GitHub의 예약 실행은 몇 시간씩 늦을 때가 있습니다. 바로 확인하려면 Run workflow를 누르세요.
- main 브랜치를 보호한 경우에만 `BOT_PUSH_TOKEN`(Contents 쓰기 권한이 있는 토큰)을 Secrets에 추가합니다. 없으면 기본 토큰을 씁니다.

## 설치 방법 B: 내 컴퓨터에서 직접 실행하기

코드를 확인하거나 고칠 때 씁니다. 아래는 Windows PowerShell 기준입니다.

```
git clone https://github.com/seongminhong497-cell/koreatech-notice-bot.git
cd koreatech-notice-bot
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

키를 환경 변수로 넣습니다. (창을 닫으면 사라집니다)

```
$env:GEMINI_API_KEY="내 키"
$env:WEATHER_API_KEY="내 키"
$env:DISCORD_WEBHOOK="내 웹후크 주소"
```

순서대로 실행합니다.

```
python src/crawler.py
python src/ai_extract.py
python src/weather.py
python src/relevance.py
python src/discord_notify.py --dry-run
```

- `--dry-run`은 디스코드로 보내지 않고 화면에만 출력합니다. 실제로 보내려면 빼고 실행합니다.
- 실행하면 `data/` 파일이 바뀝니다. 테스트로 바뀐 파일은 커밋하지 말고 `git checkout -- data/`로 되돌립니다.
- 관련도 테스트: `python test_relevance.py`

## 수집 범위를 첫 페이지로 정한 이유

공지 하나를 정리할 때마다 AI를 한 번 부르는데, 무료 한도가 하루 500번입니다. 여러 페이지를 모으면 처음에 1,000개가 넘어 정리에만 1주일 이상 걸립니다. 첫 페이지를 6시간마다 확인하며 쌓으면 새 공지는 빠지지 않습니다.

## 팀 (창의적공학설계 2팀)

| 이름 | 담당 | 브랜치 |
|---|---|---|
| 이민서 (A) | 공지 수집 | `a-crawler` |
| 한재원 (B, 팀장) | AI 정리, 날씨, 자동 실행, 설정 | `b-ai` |
| 만비카 (C) | 데이터 형식, 관련도 | `c-data` |
| 홍성민 (D) | 저장소, 웹페이지, 디스코드 | `d-web` |

## 브랜치 규칙

1. main 브랜치에는 직접 올리지 않는다
2. 각자 자기 브랜치에서 작업하고 PR을 올린다
3. 다른 팀원 한 명 이상이 리뷰·승인한 뒤 합친다 (본인 PR은 본인이 머지하지 않는다)
4. API 키와 웹후크 주소는 코드나 단톡방에 올리지 않는다 (Secrets에만 등록)
