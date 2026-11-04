"""B 파트: 공지 본문을 Gemini에 보내 대상, 마감일, 할 일, 준비물, 분류를 뽑는다.

사용법
- 테스트: python src/ai_extract.py ../장학.txt
- 실제 처리: python src/ai_extract.py  (data/notices.json에서 아직 처리 안 된 공지만 처리)
"""

import datetime
import json
import os
import re
import sys
import time

from google import genai
from google.genai import types

MODEL = "gemini-3.5-flash-lite"
NOTICES_PATH = "data/notices.json"
WAIT_SECONDS = 4.5  # 분당 15회 한도를 넘지 않도록 공지 사이에 쉬는 시간

CATEGORIES = ["장학", "학사", "취업·인턴", "교내활동", "대외활동·공모전", "생활관"]
GROUPS = ["학부생", "대학원생", "교직원", "외국인 유학생", "일반인"]
STATUSES = ["재학", "휴학", "졸업예정", "졸업"]
DATE_RE = re.compile(
    r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})"
    r"(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?)?"
)

SYSTEM_PROMPT = """너는 한국기술교육대학교 공지에서 정보를 뽑는 도우미야.
공지 제목과 본문을 읽고, 아래 JSON 형식으로만 답해. 설명이나 다른 글은 쓰지 마.

가장 중요한 규칙
- 공지에 적힌 내용만 쓰고, 적혀 있지 않은 내용은 절대 지어내지 마.
- 판단하기 어려우면 null로 둬.
- 제목에도 마감일이나 대상이 적혀 있을 수 있으니, 제목과 본문을 모두 확인해.

target (누구를 위한 공지인지)
- scope: 학생 누구나 해당되면 "all", 특정 학과·학년·학적·집단만 해당되면 "specific", 판단할 수 없으면 "unknown"
- departments: 대상 학과 목록. "컴퓨터공학부"처럼 정식 이름으로 써. 학과 제한이 없으면 [], 알 수 없으면 null
- years: 대상 학년 숫자 목록. 예: [1, 2]. 학년 제한이 없으면 [], 알 수 없으면 null
- enrollment_statuses: 대상 학적 목록. "재학", "휴학", "졸업예정", "졸업" 중에서만 골라. 제한이 없으면 [], 알 수 없으면 null
- groups: 대상 집단 목록. "학부생", "대학원생", "교직원", "외국인 유학생", "일반인" 중에서만 골라.
  직원·계약직·연구원 채용은 "교직원"으로 써. 제한이 없으면 [], 알 수 없으면 null
- dorm_required: 생활관생만 해당되면 true, 생활관생이 아닌 사람만 해당되면 false, 상관없거나 알 수 없으면 null

deadline (신청·제출 마감)
- 시간이 적혀 있으면 "YYYY-MM-DDTHH:MM:SS+09:00", 날짜만 있으면 "YYYY-MM-DD"로 써. 시간을 지어내지 마.
- "24:00까지"는 그날 "23:59:00"으로 써.
- 연도가 없으면 작성일을 기준으로 연도를 정해.
- 마감이 여러 개면, 대상 학생 모두가 해야 하는 가장 가까운 신청·제출 마감 하나만 써.
  특정 학년만 해당하는 일정(예: 4학년 우선 신청)은 고르지 마.
- 행사 날짜, 작업·점검 시간, 결과 발표일은 마감이 아니야. 신청·제출 마감이 없으면 null

actions (학생이 해야 할 일)
- "포털에서 신청서 제출"처럼 짧은 문장 목록, 최대 3개. 할 일이 없으면 []

materials (준비물·제출 서류)
- 서류나 준비물 이름 목록. 공지에 언급이 없으면 null
- 공지에 "제출 서류 없음"처럼 없다고 분명히 적혀 있을 때만 []

category (분류)
- "장학", "학사", "취업·인턴", "교내활동", "대외활동·공모전", "생활관" 중 하나.
- 시스템 점검, 단순 안내처럼 맞는 게 없으면 억지로 고르지 말고 null

답 형식 (꺾쇠 안의 설명 대신 공지에서 찾은 실제 값을 넣어)
{
  "target": {
    "scope": <"all" 또는 "specific" 또는 "unknown">,
    "departments": <학과 목록 또는 [] 또는 null>,
    "years": <학년 숫자 목록 또는 [] 또는 null>,
    "enrollment_statuses": <학적 목록 또는 [] 또는 null>,
    "groups": <집단 목록 또는 [] 또는 null>,
    "dorm_required": <true 또는 false 또는 null>
  },
  "deadline": <마감 날짜 문자열 또는 null>,
  "actions": <할 일 목록>,
  "materials": <준비물 목록 또는 [] 또는 null>,
  "category": <분류 또는 null>
}

답하기 전에 본문을 끝까지 읽고, 신청 기간·신청 자격·신청 방법·제출 서류 부분을 꼭 확인해."""

_client = None


def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def build_text(notice):
    """notices.json의 공지 하나를 AI에게 보낼 글로 만든다."""
    return (
        f"제목: {notice.get('title', '')}\n"
        f"게시판: {notice.get('source', '')}\n"
        f"작성일: {notice.get('published_date', '')}\n\n"
        f"본문:\n{notice.get('body', '')}"
    )


def call_ai(text, retries=3):
    """AI를 부르고 JSON을 받는다. 실패하면 잠깐 쉬고 다시 시도하고, 끝내 실패하면 None."""
    for attempt in range(1, retries + 1):
        try:
            res = get_client().models.generate_content(
                model=MODEL,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0,
                    thinking_config=types.ThinkingConfig(thinking_level="LOW"),
                ),
            )
            return json.loads(res.text)
        except Exception as e:
            print(f"  AI 호출 실패 ({attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(10 * attempt)
    return None


def _date(value):
    """AI가 쓴 날짜를 "YYYY-MM-DD" 또는 "YYYY-MM-DDTHH:MM:SS+09:00"으로 맞춘다."""
    if not isinstance(value, str):
        return None
    m = DATE_RE.match(value.strip())
    if not m:
        return None
    y, mo, d, h, mi, sec = m.groups()
    try:
        day = datetime.date(int(y), int(mo), int(d))
    except ValueError:
        return None
    if h is None:
        return day.isoformat()
    h, mi, sec = int(h), int(mi), int(sec or 0)
    if h == 24:  # "24:00까지"는 그날 23:59로
        h, mi, sec = 23, 59, 0
    if h > 23 or mi > 59 or sec > 59:
        return day.isoformat()
    return f"{day.isoformat()}T{h:02d}:{mi:02d}:{sec:02d}+09:00"


def _str_list(value, allowed=None):
    """문자열 목록으로 정리한다. 허용 목록 밖의 값은 버리고, 전부 버려지면 '모름'(None)으로 본다."""
    if not isinstance(value, list):
        return None
    items = [v.strip() for v in value if isinstance(v, str) and v.strip()]
    if allowed is not None:
        kept = [v for v in items if v in allowed]
        if items and not kept:
            return None  # 이상한 값만 있었으면 '제한 없음'([])이 아니라 '모름'
        items = kept
    return items


def _year_list(value):
    if not isinstance(value, list):
        return None
    years = []
    for v in value:
        try:
            y = int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= y <= 5 and y not in years:
            years.append(y)
    if value and not years:
        return None
    return sorted(years)


def clean(result):
    """AI 답을 DATA_FORMAT.md 형식에 맞게 다듬는다. 형식이 틀린 값은 null로 바꾼다."""
    if not isinstance(result, dict):
        return None
    t = result.get("target") if isinstance(result.get("target"), dict) else {}

    scope = t.get("scope")
    if scope not in ("all", "specific", "unknown"):
        scope = "unknown"

    dorm = t.get("dorm_required")
    if not isinstance(dorm, bool):
        dorm = None

    deadline = _date(result.get("deadline"))

    actions = _str_list(result.get("actions"))
    if actions is None:
        actions = []

    category = result.get("category")
    if category not in CATEGORIES:
        category = None

    target = {
        "scope": scope,
        "departments": _str_list(t.get("departments")),
        "years": _year_list(t.get("years")),
        "enrollment_statuses": _str_list(
            t.get("enrollment_statuses"), STATUSES
        ),
        "groups": _str_list(t.get("groups"), GROUPS),
        "dorm_required": dorm,
    }
    # 대상 조건이 하나라도 있으면 "all"이 아니라 "specific"
    has_condition = dorm is not None or any(
        target[k]
        for k in ("departments", "years", "enrollment_statuses", "groups")
    )
    if has_condition and target["scope"] == "all":
        target["scope"] = "specific"

    return {
        "target": target,
        "deadline": deadline,
        "actions": actions[:3],
        "materials": _str_list(result.get("materials")),
        "category": category,
    }


def extract(text, show_raw=False):
    """공지 글 하나를 넣으면 정리된 정보를 돌려준다. 실패하면 None."""
    raw = call_ai(text)
    if show_raw:
        print("[AI 원래 답]")
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        print("[정리한 결과]")
    return clean(raw)


def process_notices(path=NOTICES_PATH):
    """notices.json에서 아직 AI 정리가 안 된 공지만 처리하고 저장한다."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    notices = data["notices"] if isinstance(data, dict) else data

    todo = [n for n in notices if not n.get("is_sample") and not n.get("extracted")]
    print(f"처리할 공지: {len(todo)}개")

    for i, notice in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {notice.get('title', '')}")
        info = extract(build_text(notice))
        if info is None:
            print("  실패, 다음 실행 때 다시 처리합니다.")
        else:
            notice.update(info)
            notice["extracted"] = True
        if i < len(todo):
            time.sleep(WAIT_SECONDS)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("저장 완료")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 테스트: txt 파일을 그대로 AI에게 보내고 결과만 보여준다 (notices.json은 안 건드림)
        with open(sys.argv[1], encoding="utf-8") as f:
            info = extract(f.read(), show_raw=True)
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        process_notices()