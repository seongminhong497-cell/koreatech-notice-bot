import html
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "data" / "profile.json"
NOTICES_PATH = Path(
    os.environ.get(
        "YOUTH_POLICY_OUTPUT",
        str(ROOT / "data" / "notices.json"),
    )
)

API_URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
PAGE_SIZE = 100
KST = ZoneInfo("Asia/Seoul")

# API의 lastMdfcnDt를 기존 공지와 비교하기 위해 저장하는 필드
API_MODIFIED_FIELD = "api_last_modified"


def read_json(path, default):
    """JSON 파일을 읽는다. 파일이 없으면 기본값을 반환한다."""
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, data):
    """JSON 파일을 임시 파일에 쓴 다음 교체한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def clean_text(value):
    """API 응답의 공백과 HTML 문자를 정리한다."""
    if value is None:
        return ""

    text = html.unescape(str(value))
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_dates(value):
    """문자열에서 YYYYMMDD 또는 YYYY-MM-DD 형식의 날짜를 찾는다."""
    if not value:
        return []

    matches = re.findall(
        r"\d{4}[./-]?\d{2}[./-]?\d{2}",
        str(value),
    )
    parsed = []

    for match in matches:
        digits = re.sub(r"\D", "", match)

        try:
            parsed.append(datetime.strptime(digits, "%Y%m%d").date())
        except ValueError:
            continue

    return parsed


def parse_region_codes(value):
    """정책의 zipCd를 중복 없는 지역 코드 목록으로 바꾼다."""
    if value is None:
        return []

    if isinstance(value, list):
        parts = value
    else:
        parts = str(value).split(",")

    codes = []
    for part in parts:
        code = str(part).strip()
        if code and code not in codes:
            codes.append(code)

    return codes


def to_int(value):
    """숫자 필드를 정수로 바꾼다. 변환할 수 없으면 0을 반환한다."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def fetch_page(session, api_key, zip_code, page_num):
    """API에서 정책 목록 한 페이지를 가져온다."""
    params = {
        "apiKeyNm": api_key,
        "pageNum": page_num,
        "pageSize": PAGE_SIZE,
        "rtnType": "json",
        "zipCd": zip_code,
    }

    response = session.get(
        API_URL,
        params=params,
        timeout=(5, 15),
    )
    response.raise_for_status()

    payload = response.json()
    result = payload.get("result") or {}

    if "youthPolicyList" not in result:
        raise ValueError(
            f"API 응답에 youthPolicyList가 없습니다: {payload}"
        )

    policies = result.get("youthPolicyList") or []
    if isinstance(policies, dict):
        policies = [policies]

    paging = result.get("pagging") or {}
    total_count = to_int(paging.get("totCount"))

    return policies, total_count


def fetch_all_for_region(session, api_key, zip_code):
    """지역 코드 하나에 해당하는 전체 정책을 페이지 단위로 가져온다."""
    first_page, total_count = fetch_page(
        session,
        api_key,
        zip_code,
        page_num=1,
    )

    policies = list(first_page)
    page_count = math.ceil(total_count / PAGE_SIZE)

    for page_num in range(2, page_count + 1):
        page_items, _ = fetch_page(
            session,
            api_key,
            zip_code,
            page_num=page_num,
        )
        policies.extend(page_items)

    return policies


def fetch_policies(session, api_key, region_code):
    """사용자 지역 코드와 시 코드로 요청하고 정책 ID 기준으로 합친다."""
    region_code = str(region_code).strip()
    city_code = region_code[:4] + "0"

    zip_codes = list(dict.fromkeys([region_code, city_code]))
    unique_policies = {}

    for zip_code in zip_codes:
        policies = fetch_all_for_region(
            session,
            api_key,
            zip_code,
        )

        for policy in policies:
            policy_id = clean_text(policy.get("plcyNo"))
            if policy_id:
                unique_policies[policy_id] = policy

    return list(unique_policies.values())


def is_recently_registered(policy, today, nationwide):
    """전국 정책은 최근 30일 안에 등록된 경우만 남긴다."""
    if not nationwide:
        return True

    dates = parse_dates(policy.get("frstRegDt"))
    if not dates:
        return False

    return today - timedelta(days=30) <= dates[0] <= today


def is_open_policy(policy, today):
    """마감된 정책과 신청이 종료된 정책을 제외한다."""
    period_code = clean_text(policy.get("aplyPrdSeCd"))

    if period_code == "0057003":
        return False

    dates = parse_dates(policy.get("aplyYmd"))

    if period_code == "0057001" and dates:
        end_date = dates[-1]
        if end_date < today:
            return False

    return True


def make_body(policy):
    """정책 설명과 지원 내용, 신청 방법을 본문 문자열로 만든다."""
    body_parts = []

    description = clean_text(policy.get("plcyExplnCn"))
    if description and description != "해당 없음":
        body_parts.append(description)

    labeled_fields = (
        ("지원 내용", "plcySprtCn"),
        ("신청 방법", "plcyAplyMthdCn"),
        ("추가 조건", "addAplyQlfcCndCn"),
    )

    for label, field in labeled_fields:
        value = clean_text(policy.get(field))
        if value and value != "해당 없음":
            body_parts.append(f"{label}: {value}")

    return "\n".join(body_parts)


def make_notice(policy, now):
    """온통청년 응답 하나를 notices.json 공지 형식으로 바꾼다."""
    policy_id = clean_text(policy.get("plcyNo"))
    title = clean_text(policy.get("plcyNm"))

    if not policy_id or not title:
        return None

    period_code = clean_text(policy.get("aplyPrdSeCd"))
    application_dates = parse_dates(policy.get("aplyYmd"))

    deadline = None
    other_dates = []

    if period_code == "0057001" and application_dates:
        start_date = application_dates[0]
        end_date = application_dates[-1]

        deadline = f"{end_date.isoformat()}T23:59:00+09:00"
        other_dates.append(
            {
                "label": "신청 시작",
                "date": start_date.isoformat(),
            }
        )

    raw_region_codes = parse_region_codes(policy.get("zipCd"))
    nationwide = len(raw_region_codes) >= 200

    min_age_raw = to_int(policy.get("sprtTrgtMinAge"))
    max_age_raw = to_int(policy.get("sprtTrgtMaxAge"))

    age_min = min_age_raw if min_age_raw > 0 else None
    age_max = max_age_raw if max_age_raw > 0 else None
    age_unrestricted = min_age_raw == 0 and max_age_raw == 0

    age_limited = not age_unrestricted
    region_limited = bool(raw_region_codes) and not nationwide
    scope = "specific" if age_limited or region_limited else "all"

    raw_url = (
        clean_text(policy.get("refUrlAddr1"))
        or clean_text(policy.get("aplyUrlAddr"))
        or "https://www.youthcenter.go.kr"
    )

    published_dates = parse_dates(policy.get("frstRegDt"))
    published_date = (
        published_dates[0].isoformat()
        if published_dates
        else None
    )

    application_method = clean_text(policy.get("plcyAplyMthdCn"))
    actions = (
        [f"신청: {application_method}"]
        if application_method
        else None
    )

    documents = clean_text(policy.get("sbmsnDcmntCn"))
    materials = (
        [documents]
        if documents and documents != "해당 없음"
        else []
    )

    return {
        "id": f"youth-{policy_id}",
        "title": title,
        "url": raw_url,
        "source": "온통청년",
        "source_type": "정부",
        "published_date": published_date,
        "body": make_body(policy),
        "images": [],
        "is_sample": False,
        "extracted": True,
        "processed": False,
        "is_new": True,
        "collected_at": now.isoformat(timespec="seconds"),
        "relevance": None,
        "relevance_reason": None,
        "category": "청년정책",
        "deadline": deadline,
        "other_dates": other_dates,
        "actions": actions,
        "materials": materials,
        "target": {
            "scope": scope,
            "departments": [],
            "years": [],
            "enrollment_statuses": [],
            "groups": [],
            "dorm_required": None,
            "age_min": age_min,
            "age_max": age_max,
            "age_unrestricted": age_unrestricted,
            "region_codes": raw_region_codes,
            "nationwide": nationwide,
        },
        API_MODIFIED_FIELD: clean_text(policy.get("lastMdfcnDt")),
    }


def is_within_new_period(notice, now):
    """처음 수집한 지 24시간이 지나지 않았는지 판단한다."""
    collected_at = notice.get("collected_at")
    if not collected_at:
        return bool(notice.get("is_new"))

    try:
        collected_time = datetime.fromisoformat(collected_at)
    except ValueError:
        return bool(notice.get("is_new"))

    if collected_time.tzinfo is None:
        collected_time = collected_time.replace(tzinfo=KST)

    age = now - collected_time
    return timedelta(0) <= age <= timedelta(hours=24)


def merge_notices(saved_notices, fetched_notices, now):
    """기존 공지를 보존하고 새 정책을 추가하거나 수정된 정책만 갱신한다."""
    positions = {
        notice.get("id"): index
        for index, notice in enumerate(saved_notices)
        if notice.get("id")
    }

    for notice in saved_notices:
        notice["is_new"] = is_within_new_period(notice, now)

    added = 0
    updated = 0

    for fresh in fetched_notices:
        old_index = positions.get(fresh["id"])

        if old_index is None:
            saved_notices.append(fresh)
            positions[fresh["id"]] = len(saved_notices) - 1
            added += 1
            continue

        old = saved_notices[old_index]
        changed_fields = (
            "title",
            "url",
            "published_date",
            "body",
            "deadline",
            "other_dates",
            "actions",
            "materials",
            "target",
            API_MODIFIED_FIELD,
        )
        changed = any(
            old.get(field) != fresh.get(field)
            for field in changed_fields
        )

        if not changed:
            continue

        # 수정된 정책은 기존 수집 시각을 유지하고 재처리하도록 표시한다.
        fresh["collected_at"] = old.get(
            "collected_at",
            fresh["collected_at"],
        )
        fresh["is_new"] = is_within_new_period(fresh, now)
        fresh["processed"] = False
        fresh["relevance"] = None
        fresh["relevance_reason"] = None

        saved_notices[old_index] = fresh
        updated += 1

    return saved_notices, added, updated


def main():
    profile = read_json(PROFILE_PATH, default={})
    region_code = str(
        os.environ.get("YOUTH_REGION_CODE")
        or profile.get("region_code")
        or ""
    ).strip()

    if not region_code:
        print(
            "profile.json에 region_code가 없어 청년정책 수집을 건너뜁니다.",
            file=sys.stderr,
        )
        return

    api_key = os.environ.get("YOUTH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "YOUTH_API_KEY 환경 변수가 설정되지 않았습니다."
        )

    now = datetime.now(KST)
    today = now.date()

    with requests.Session() as session:
        policies = fetch_policies(
            session,
            api_key,
            region_code,
        )

    eligible_policies = []

    for policy in policies:
        codes = parse_region_codes(policy.get("zipCd"))
        nationwide = len(codes) >= 200

        if not is_open_policy(policy, today):
            continue

        if not is_recently_registered(policy, today, nationwide):
            continue

        eligible_policies.append(policy)

    fetched_notices = []
    for policy in eligible_policies:
        notice = make_notice(policy, now)
        if notice:
            fetched_notices.append(notice)

    saved_notices = read_json(NOTICES_PATH, default=[])
    if not isinstance(saved_notices, list):
        raise ValueError("data/notices.json은 JSON 목록이어야 합니다.")

    merged, added, updated = merge_notices(
        saved_notices,
        fetched_notices,
        now,
    )
    write_json(NOTICES_PATH, merged)

    print(
        "청년정책 수집 완료: "
        f"API {len(policies)}개 확인, "
        f"{len(fetched_notices)}개 대상, "
        f"{added}개 추가, {updated}개 갱신"
    )


if __name__ == "__main__":
    main()