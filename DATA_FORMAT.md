# 데이터 형식 안내 — 초안

담당: 만비카 (C)

A의 수집, B의 AI 정리, C의 관련도 계산, D의 화면이
같은 필드 이름과 값 형식을 사용하기 위한 문서입니다.

현재 예시는 가상 데이터이며, 팀 리뷰 후 형식을 조정할 수 있습니다.

## 1. 공통 규칙

- 파일 인코딩: UTF-8
- 필드 이름은 아래 영문 이름을 그대로 사용합니다.
- JSON에서 주석은 사용하지 않습니다.
- null: 알 수 없거나 아직 입력·계산되지 않은 값
- []: 항목이 없는 목록
- true / false: 예 / 아니요
- 날짜: YYYY-MM-DD
- 시간이 있는 날짜: YYYY-MM-DDTHH:MM:SS+09:00 (한국 시간)
- 원문에 없는 정보는 추측하지 않습니다.
- 예시 데이터는 is_sample: true로 표시하고 실제 알림에서 제외합니다.

## 2. data/profile.json

사용자 설정을 하나의 객체로 저장합니다.
현재 값은 컴퓨터공학부 1학년 가상 사용자의 예시입니다.

| 필드 | 형식 | 의미 / 예시 |
|---|---|---|
| department | 문자열 또는 null | 학과, 예: 컴퓨터공학부 |
| year | 정수 또는 null | 학년, 예: 1 |
| enrollment_status | 문자열 또는 null | 학적 상태, 예: 재학 |
| dorm_resident | 불리언 또는 null | 생활관 거주 여부 |
| interests | 문자열 목록 | 관심 분류 |
| always_show_categories | 문자열 목록 | 항상 확인할 분류 |
| excluded_categories | 문자열 목록 | 제외할 분류 |
| excluded_target_groups | 문자열 목록 | 제외 대상, 예: 대학원생, 교직원 |
| age | 정수 또는 null | 만 나이, 4주차 사용 |
| region | 문자열 또는 null | 거주 지역, 4주차 사용 |
| urgent_days | 정수 | 일반 마감 임박 기준, 기본 3일 |
| preparation_days | 정수 | 준비물이 있는 경우 기준, 기본 7일 |

설정 목록에 선택 항목이 없으면 []를 사용합니다.
사용자 정보가 미정이면 null을 사용합니다.

항상 보기 분류라도 대상이 명확히 다르거나 제외 조건에
해당하면 숨김을 우선합니다.

## 3. data/notices.json

공지 객체 여러 개를 배열 [ ... ]에 저장합니다.
각 공지는 서로 다른 id를 가집니다.

### A: 수집 정보

| 필드 | 형식 | 의미 |
|---|---|---|
| id | 문자열 | 공지를 구분하는 고유 ID |
| title | 문자열 | 제목 |
| url | 문자열 | 원문 주소 |
| source | 문자열 | 게시판 이름, 예: 학교-장학 |
| source_type | 문자열 | 학교 또는 정부 |
| published_date | 날짜 문자열 또는 null | 게시일 |
| body | 문자열 또는 null | 원문 본문 |

필수 식별 정보인 id, title, url, source, source_type은
값이 있어야 합니다. 게시일이나 본문을 확인하지 못하면 null입니다.

### B: AI 추출 정보

| 필드 | 형식 | 의미 |
|---|---|---|
| target | 객체 | 아래 대상 정보 |
| deadline | 문자열 또는 null | 마감일 또는 마감 시각 |
| actions | 문자열 목록 또는 null | 해야 할 일 |
| materials | 문자열 목록 또는 null | 준비물 |
| category | 문자열 또는 null | 공지 분류 |

분류는 다음 중 하나입니다.

- 장학
- 학사
- 취업·인턴
- 교내활동
- 대외활동·공모전
- 생활관

분류를 판단할 수 없으면 null입니다.
원문에 할 일이나 준비물 정보가 없으면 null입니다.
명시적으로 없다고 확인된 경우에만 []를 사용합니다.

마감 날짜만 있으면 YYYY-MM-DD로 저장합니다.
시간까지 있으면 YYYY-MM-DDTHH:MM:SS+09:00으로 저장합니다.
마감이 없거나 확인되지 않으면 null입니다.
날짜만 있을 때 임의의 마감 시각을 만들어 넣지 않습니다.

### target: 대상 정보

| 필드 | 형식 | 의미 |
|---|---|---|
| scope | 문자열 | all / specific / unknown |
| departments | 문자열 목록 또는 null | 대상 학과 |
| years | 정수 목록 또는 null | 대상 학년 |
| enrollment_statuses | 문자열 목록 또는 null | 대상 학적 상태 |
| groups | 문자열 목록 또는 null | 학부생, 대학원생, 교직원 등 |
| dorm_required | 불리언 또는 null | 생활관 거주 조건 |

- all: 전체 학생 대상이라고 명시됨
- specific: 특정 대상 조건이 명시됨
- unknown: 대상 정보가 없거나 불명확함
- 대상 목록이 null이면 해당 조건을 알 수 없다는 뜻입니다.
- 대상 목록이 []이면 해당 항목에 제한이 없다고 명시된 경우입니다.
- dorm_required가 true이면 거주자 대상입니다.
- dorm_required가 false이면 비거주자 대상입니다.
- dorm_required가 null이면 조건이 명시되지 않았습니다.
- 한 목록 안의 값은 OR, 서로 다른 항목의 조건은 AND로 비교합니다.
- 복잡한 대상 조건을 이 구조로 표현하기 어려우면 팀에 공유합니다.

### C: 관련도 결과 및 상태

| 필드 | 형식 | 의미 |
|---|---|---|
| relevance | 정수 또는 null | 3=★★★, 2=★★, 1=★, 0=숨김 |
| relevance_reason | 문자열 또는 null | 판단 이유 |
| is_new | 불리언 | 새 공지 여부 |
| processed | 불리언 | C의 관련도 계산 완료 여부 |

계산 전에는 relevance와 relevance_reason을 null,
processed를 false로 둡니다.
계산이 완료되면 결과와 이유를 저장하고 processed를 true로 바꿉니다.

is_new의 최초 값은 A의 신규 공지 감지 결과를 사용합니다.
언제 false로 바꿀지는 브리핑 연결 단계에서 협의합니다.

### 예시 표시

| 필드 | 형식 | 의미 |
|---|---|---|
| is_sample | 불리언 | 가상 예시는 true, 실제 공지는 false |

현재 sample-001은 가상 예시이며 원문 링크도 예시 주소입니다.