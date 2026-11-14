"""B 파트: 공지 본문을 Gemini에 보내 대상, 마감일, 할 일, 준비물, 분류를 뽑는다.

사용법
- 테스트: python src/ai_extract.py ../장학.txt
  (txt 안에 "이미지: 주소 또는 파일경로" 줄이 있으면 그 이미지도 같이 보낸다)
- 실제 처리: python src/ai_extract.py
  (data/notices.json에서 아직 처리 안 된 공지만 처리)
"""

import datetime
import json
import os
import re
import sys
import time

import requests
from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from departments import DEPARTMENTS, normalize_departments, normalize_notices  # noqa: E402

MODEL = "gemini-3.5-flash-lite"
BACKUP_MODEL = "gemma-4-26b-a4b-it"  # 기본 모델이 붐빌 때 쓰는 예비 모델
NOTICES_PATH = "data/notices.json"
MAX_IMAGES = 3  # 공지 하나에 AI로 보낼 이미지 최대 개수
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB보다 큰 이미지는 보내지 않음
MAX_PER_RUN = 30  # 한 번 실행에 처리할 공지 최대 개수. 나머지는 다음 실행 때
TIME_BUDGET = 12 * 60  # AI 정리에 쓸 최대 시간(초). 워크플로 제한(15분) 전에 멈춘다
IMAGE_TIMEOUT = (5, 10)  # 이미지 접속 5초, 받기 10초
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
- 이미지가 함께 오면 이미지 속 글자도 공지 본문으로 보고 똑같이 정보를 뽑아.

target (누구를 위한 공지인지)
- scope: 학생 누구나 해당되면 "all", 특정 학과·학년·학적·집단만 해당되면 "specific",
  판단할 수 없으면 "unknown"
- departments: 대상 학과 목록. 아래 이름 중에서 골라 써. 전공 이름이 나오면 그 전공이 속한 학부를 써.
  {DEPARTMENT_LIST}
  목록에 없는 학과는 공지에 적힌 대로 써. 학과 제한이 없으면 [], 알 수 없으면 null
- years: 대상 학년 숫자 목록. 예: [1, 2]. 학년 제한이 없으면 [], 알 수 없으면 null
- enrollment_statuses: 대상 학적 목록. "재학", "휴학", "졸업예정", "졸업" 중에서만 골라.
  제한이 없으면 [], 알 수 없으면 null
- groups: 대상 집단 목록. "학부생", "대학원생", "교직원", "외국인 유학생", "일반인" 중에서만 골라.
  직원·계약직·연구원 채용은 "교직원"으로 써. 제한이 없으면 [], 알 수 없으면 null
  그냥 "학생" 누구나 대상이면 학부생·대학원생을 적지 말고 []로 둬.
  "대학(원)생", "학부(원)생", "대학생 및 대학원생"은 학부생과 대학원생 둘 다야.
- dorm_required: 생활관생만 해당되면 true, 생활관생이 아닌 사람만 해당되면 false, 상관없거나 알 수 없으면 null

deadline (신청·제출 마감)
- 시간이 적혀 있으면 "YYYY-MM-DDTHH:MM:SS+09:00", 날짜만 있으면 "YYYY-MM-DD"로 써. 시간을 지어내지 마.
- "24:00까지"는 그날 "23:59:00"으로 써.
- 연도가 없으면 작성일을 기준으로 연도를 정해.
- 마감이 여러 개면, 대상 학생 모두가 해야 하는 가장 가까운 신청·제출 마감 하나만 써.
- 특정 학년·집단만 해당하는 일정은 날짜가 더 빨라도 절대 고르지 마.
  예: "4학년 우선 수강신청 11/10"과 "1차 수강신청 11/11"이 있으면
  4학년 우선은 일부 학생만 해당하므로, 모두가 하는 1차 수강신청 11/11을 써.
- 행사 날짜, 작업·점검 시간, 결과 발표일은 마감이 아니야. 신청·제출 마감이 없으면 null

other_dates (deadline 말고 다른 일정)
- deadline에 넣지 않은 날짜를 {"label": 일정 이름, "date": 날짜} 목록으로 써. 최대 5개
- 예: 다른 신청 일정, 등록금 납부, 결과 발표, 행사일, 점검 기간 시작일
- 일부 학년·집단만 해당하는 일정은 label에 대상을 함께 써. 예: "4학년 우선 수강신청"
- date는 deadline과 같은 형식으로 쓰고, 날짜를 알 수 없는 일정은 넣지 마.
- 다른 일정이 없으면 []

actions (학생이 해야 할 일)
- "포털에서 신청서 제출"처럼 짧은 문장 목록, 최대 3개
- 공지에 할 일 정보가 없으면 null
  예: 점검 안내, 단순 알림처럼 학생이 할 일이 언급되지 않은 공지는 []가 아니라 null
- 공지에 "따로 할 일 없음"처럼 없다고 분명히 적혀 있을 때만 []

materials (준비물·제출 서류)
- 서류나 준비물 이름 목록. 공지에 언급이 없으면 null
- 공지에 "제출 서류 없음"처럼 없다고 분명히 적혀 있을 때만 []

category (분류)
- "장학", "학사", "취업·인턴", "교내활동", "대외활동·공모전", "생활관" 중 하나.
- 시스템 점검, 단순 안내처럼 맞는 게 없으면 억지로 고르지 말고 null
- "생활관"은 기숙사(생활관) 입주, 퇴사, 점호, 호실처럼 기숙사 공지에만 써.
  통학버스, 셔틀버스, 주차, 교통, 건물·시설 안내는 생활관이 아니야.

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
  "other_dates": <{"label", "date"} 목록 또는 []>,
  "actions": <할 일 목록 또는 [] 또는 null>,
  "materials": <준비물 목록 또는 [] 또는 null>,
  "category": <분류 또는 null>
}

답하기 전에 본문을 끝까지 읽고, 신청 기간·신청 자격·신청 방법·제출 서류 부분을 꼭 확인해."""

SYSTEM_PROMPT = SYSTEM_PROMPT.replace(
    "{DEPARTMENT_LIST}", ", ".join(DEPARTMENTS)
)

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


def _image_type(data):
    """이미지 파일의 앞부분을 보고 종류를 알아낸다. Gemini가 못 읽는 종류면 None."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _read_image(url, headers):
    """인터넷 주소면 내려받고, 컴퓨터에 있는 파일 경로면 그 파일을 읽는다."""
    if not url.startswith(("http://", "https://")):
        try:
            with open(url, "rb") as f:
                return f.read()
        except OSError as e:
            print(f"  이미지 파일 열기 실패, 건너뜀: {url} ({e})")
            return None
    try:
        res = requests.get(url, timeout=IMAGE_TIMEOUT, headers=headers)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"  이미지 받기 실패, 건너뜀: {url} ({e})")
        return None
    return res.content


def download_images(urls, referer=None):
    """이미지 주소들을 내려받아 AI에게 보낼 수 있는 모양으로 만든다.

    학교 사이트는 공지 페이지에서 눌렀을 때만 파일을 주는 경우가 있어서,
    referer(공지 주소)를 같이 보내 "이 공지에서 왔다"고 알려준다.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    parts = []
    for url in (urls or [])[:MAX_IMAGES]:  # 앞에서 3장까지만 시도
        data = _read_image(url, headers)
        if data is None:
            continue
        mime = _image_type(data)
        if mime is None or len(data) > MAX_IMAGE_BYTES:
            print(f"  보낼 수 없는 이미지라 건너뜀: {url}")
            continue
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    return parts


def _lines_with(text, label):
    """테스트용 txt에서 "label: 값" 줄을 찾아 값 목록을 만든다."""
    values = []
    for line in text.splitlines():
        if line.strip().startswith(label + ":"):
            value = line.split(":", 1)[1].strip()
            if value:
                values.append(value)
    return values


def _parse_json(text):
    """AI 답에서 JSON 부분만 꺼낸다. ```json 같은 감싸기가 있어도 괜찮다."""
    text = (text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("답에 JSON이 없습니다")
    return json.loads(text[start:end + 1])


def _ask(model, contents):
    """모델 하나에 한 번 물어본다. 예비 모델은 JSON 모드를 쓰지 않는다."""
    if model == MODEL:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0,
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        )
    else:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
        )
    res = get_client().models.generate_content(
        model=model, contents=contents, config=config
    )
    return _parse_json(res.text)


def call_ai(text, image_parts=None):
    """AI를 부르고 JSON을 받는다. 실패하면 끝내 None.

    기본 모델이 붐비면 15초, 30초 쉬며 다시 시도하고,
    그래도 안 되면 예비 모델(Gemma)로 바꿔서 2번 더 시도한다.
    """
    contents = [text] + list(image_parts or [])
    for model, tries in ((MODEL, 3), (BACKUP_MODEL, 2)):
        for attempt in range(1, tries + 1):
            try:
                result = _ask(model, contents)
                if model != MODEL:
                    print(f"  예비 모델({model})로 처리했습니다.")
                return result
            except Exception as e:
                print(f"  AI 호출 실패 ({model} {attempt}/{tries}): {e}")
                if attempt < tries:
                    time.sleep(15 * attempt)
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


def _fix_past_year(deadline, published_date):
    """마감일이 작성일보다 90일 넘게 앞서면 연도 오타로 보고 1년을 올린다.

    예: 2026-08-31에 올라온 공지의 마감 "2025.12.31" → 2026-12-31
    다시 올린 공지(끌올)처럼 마감이 조금 지난 경우는 그대로 둔다.
    1년을 올려도 작성일보다 앞서면 고치지 않는다.
    """
    if not deadline or not isinstance(published_date, str):
        return deadline
    try:
        posted = datetime.date.fromisoformat(published_date[:10])
        day = datetime.date.fromisoformat(deadline[:10])
    except ValueError:
        return deadline
    if (posted - day).days <= 90:
        return deadline
    try:
        fixed = day.replace(year=day.year + 1)
    except ValueError:  # 2월 29일
        return deadline
    if fixed < posted:
        return deadline
    return fixed.isoformat() + deadline[10:]


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


def _other_dates(value):
    """other_dates를 [{"label", "date"}] 목록으로 정리한다. 이상한 항목은 버린다."""
    if not isinstance(value, list):
        return []
    items = []
    for x in value:
        if not isinstance(x, dict):
            continue
        label = x.get("label")
        date = _date(x.get("date"))
        if isinstance(label, str) and label.strip() and date:
            items.append({"label": label.strip(), "date": date})
    return items[:5]


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
    if actions is not None:
        actions = actions[:3]

    category = result.get("category")
    if category not in CATEGORIES:
        category = None

    target = {
        "scope": scope,
        "departments": normalize_departments(
            _str_list(t.get("departments"))
        ),
        "years": _year_list(t.get("years")),
        "enrollment_statuses": _str_list(
            t.get("enrollment_statuses"), STATUSES
        ),
        "groups": _str_list(t.get("groups"), GROUPS),
        "dorm_required": dorm,
    }
    # 학부생과 대학원생이 둘 다면 사실상 학생 전체라 제한 없음으로 본다
    if target["groups"] and set(target["groups"]) == {"학부생", "대학원생"}:
        target["groups"] = []
    # 대상 조건이 하나라도 있으면 "all"이나 "unknown"이 아니라 "specific"
    has_condition = dorm is not None or any(
        target[k]
        for k in ("departments", "years", "enrollment_statuses", "groups")
    )
    if has_condition:
        target["scope"] = "specific"

    return {
        "target": target,
        "deadline": deadline,
        "other_dates": _other_dates(result.get("other_dates")),
        "actions": actions,
        "materials": _str_list(result.get("materials")),
        "category": category,
    }


def extract(text, images=None, referer=None, show_raw=False):
    """공지 글과 이미지 주소를 넣으면 정리된 정보를 돌려준다. 실패하면 None.

    images, referer를 안 주면 글 안의 "이미지:", "링크:" 줄을 쓴다(테스트용).
    """
    if images is None:
        images = _lines_with(text, "이미지")
    if referer is None:
        links = _lines_with(text, "링크")
        referer = links[0] if links else None
    image_parts = download_images(images, referer)
    if show_raw and images:
        print(f"[이미지 {len(image_parts)}장을 같이 보냄]")
    raw = call_ai(text, image_parts)
    if show_raw:
        print("[AI 원래 답]")
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        print("[정리한 결과]")
    return clean(raw)


def _save(path, data):
    """임시 파일에 쓴 뒤 바꿔치기해서, 중간에 끊겨도 파일이 깨지지 않게 한다."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _board_department(source):
    """'컴퓨터공학부-일반'처럼 학과 게시판에서 온 공지면 그 학과 표준 이름을 돌려준다."""
    if not isinstance(source, str) or "-" not in source:
        return None
    names = normalize_departments([source.split("-")[0]])
    if len(names) == 1 and names[0] in DEPARTMENTS:
        return names[0]
    return None


def process_notices(path=NOTICES_PATH):
    """notices.json에서 아직 AI 정리가 안 된 공지만 처리한다.

    공지를 하나 처리할 때마다 바로 저장해서, 워크플로가 중간에 끊겨도
    처리한 만큼은 남는다. 한 번에 MAX_PER_RUN개까지만 처리한다.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    notices = data["notices"] if isinstance(data, dict) else data

    # 예전에 저장된 공지의 학과 이름도 표준 이름으로 맞춘다 (관련도 계산 전에)
    renamed = normalize_notices(notices)
    if renamed:
        print(f"저장된 공지의 학과 이름 통일: {renamed}개")
        _save(path, data)

    todo = [
        n for n in notices
        if not n.get("is_sample") and not n.get("extracted")
    ]
    # 본문도 이미지도 없으면 AI가 제목만 보고 추측하게 되므로 건너뛴다.
    # extracted는 false로 남아서, 크롤러가 본문을 채운 다음 실행 때 처리된다.
    empty = [n for n in todo if not (n.get("body") or "").strip()
             and not n.get("images")]
    todo = [n for n in todo if n not in empty]
    if empty:
        print(f"본문이 비어 있어 다음에 처리할 공지: {len(empty)}개")
    if len(todo) > MAX_PER_RUN:
        print(f"이번에는 {MAX_PER_RUN}개만 처리하고 "
              f"나머지 {len(todo) - MAX_PER_RUN}개는 다음 실행 때 처리합니다.")
        todo = todo[:MAX_PER_RUN]
    print(f"처리할 공지: {len(todo)}개")
    if not todo:
        return  # 바꿀 게 없으면 파일을 다시 쓰지 않는다(불필요한 커밋 방지)

    started = time.monotonic()
    for i, notice in enumerate(todo, 1):
        if time.monotonic() - started > TIME_BUDGET:
            print(f"시간 예산({TIME_BUDGET // 60}분)을 다 써서 멈춥니다. "
                  f"남은 {len(todo) - i + 1}개는 다음 실행 때 처리합니다.")
            break
        print(f"[{i}/{len(todo)}] {notice.get('title', '')}", flush=True)
        info = extract(
            build_text(notice),
            images=notice.get("images") or [],
            referer=notice.get("url"),
        )
        if info is None:
            print("  실패, 다음 실행 때 다시 처리합니다.")
        else:
            info["deadline"] = _fix_past_year(
                info["deadline"], notice.get("published_date")
            )
            # 학과 게시판 공지인데 AI가 대상 학과를 못 찾으면, 그 게시판의 학과로 채운다
            board_department = _board_department(notice.get("source"))
            target = info.get("target") or {}
            if board_department and not target.get("departments"):
                target["departments"] = [board_department]
                target["scope"] = "specific"
                info["target"] = target
            notice.update(info)
            notice["extracted"] = True
            _save(path, data)  # 하나 끝날 때마다 저장
        if i < len(todo):
            time.sleep(WAIT_SECONDS)
    print("저장 완료")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 테스트: txt 파일을 그대로 AI에게 보내고 결과만 보여준다 (notices.json은 안 건드림)
        with open(sys.argv[1], encoding="utf-8") as f:
            info = extract(f.read(), show_raw=True)
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        process_notices()
