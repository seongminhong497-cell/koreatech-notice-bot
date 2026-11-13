"""설정 이슈(Issue Forms)의 내용을 읽어 data/profile.json을 바꾼다.

사용법 (워크플로에서 실행)
    ISSUE_BODY="이슈 본문" python src/apply_settings.py

양식에 없는 칸(groups, excluded_target_groups, age, region)은 그대로 둔다.
잘못된 값이 있으면 아무것도 바꾸지 않고 오류로 끝난다.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from departments import DEPARTMENTS  # noqa: E402

PROFILE_PATH = "data/profile.json"
CATEGORIES = ["장학", "학사", "취업·인턴", "교내활동", "대외활동·공모전", "생활관"]
NO_RESPONSE = "_No response_"

# 양식(.github/ISSUE_TEMPLATE/settings.yml)의 질문 제목
LABELS = {
    "department": "학과",
    "year": "학년",
    "enrollment_status": "학적",
    "dorm_resident": "생활관에 살고 있나요?",
    "interests": "관심 분야",
    "always_show": "항상 보기",
    "excluded": "안 보기",
    "urgent_days": "마감 임박 기준 (일)",
    "preparation_days": "준비물이 있는 공지의 마감 임박 기준 (일)",
}


def parse_sections(body):
    """'### 제목' 아래 내용을 {제목: 내용}으로 나눈다."""
    sections = {}
    title = None
    lines = []
    for line in body.replace("\r\n", "\n").split("\n"):
        if line.startswith("### "):
            if title is not None:
                sections[title] = "\n".join(lines).strip()
            title = line[4:].strip()
            lines = []
        elif title is not None:
            lines.append(line)
    if title is not None:
        sections[title] = "\n".join(lines).strip()
    return sections


def checked(text):
    """체크박스 내용에서 체크된 항목만 꺼낸다. 예: '- [X] 장학'"""
    items = re.findall(r"^- \[[xX]\] (.+)$", text or "", re.MULTILINE)
    return [i.strip() for i in items if i.strip() in CATEGORIES]


def day_value(text, default, errors, label):
    """마감 임박 기준(일)을 숫자로. 비어 있으면 기본값."""
    text = (text or "").strip()
    if text in ("", NO_RESPONSE):
        return default
    if not text.isdigit() or not 1 <= int(text) <= 30:
        errors.append(f"{label}: 1에서 30 사이 숫자로 적어주세요 (입력: {text})")
        return default
    return int(text)


def build_profile(body, old):
    """이슈 본문과 기존 설정으로 새 설정을 만든다. (새 설정, 오류 목록)"""
    s = parse_sections(body)
    get = {key: s.get(label, "") for key, label in LABELS.items()}
    errors = []

    department = get["department"]
    if department not in DEPARTMENTS:
        errors.append(f"학과: 목록에 없는 값입니다 ({department})")

    year = get["year"]
    if year not in ("1", "2", "3", "4"):
        errors.append(f"학년: 1~4 중에서 골라주세요 ({year})")

    status = get["enrollment_status"]
    if status not in ("재학", "휴학"):
        errors.append(f"학적: 재학 또는 휴학을 골라주세요 ({status})")

    dorm = get["dorm_resident"]
    if dorm not in ("예", "아니요"):
        errors.append(f"생활관: 예 또는 아니요를 골라주세요 ({dorm})")

    profile = dict(old)
    profile.update(
        department=department,
        year=int(year) if year.isdigit() else old.get("year"),
        enrollment_status=status,
        dorm_resident=(dorm == "예"),
        interests=checked(get["interests"]),
        always_show_categories=checked(get["always_show"]),
        excluded_categories=checked(get["excluded"]),
        urgent_days=day_value(
            get["urgent_days"], 3, errors, LABELS["urgent_days"]
        ),
        preparation_days=day_value(
            get["preparation_days"], 7, errors, LABELS["preparation_days"]
        ),
    )
    return profile, errors


def summary(profile):
    """댓글로 보여줄 설정 요약."""
    def join(items):
        return ", ".join(items) if items else "없음"

    return "\n".join([
        f"- 학과: {profile['department']}",
        f"- 학년: {profile['year']}학년",
        f"- 학적: {profile['enrollment_status']}",
        f"- 생활관: {'예' if profile['dorm_resident'] else '아니요'}",
        f"- 관심 분야: {join(profile['interests'])}",
        f"- 항상 보기: {join(profile['always_show_categories'])}",
        f"- 안 보기: {join(profile['excluded_categories'])}",
        f"- 마감 임박 기준: {profile['urgent_days']}일 "
        f"(준비물 있으면 {profile['preparation_days']}일)",
    ])


def main():
    body = os.environ.get("ISSUE_BODY", "")
    with open(PROFILE_PATH, encoding="utf-8") as f:
        old = json.load(f)

    profile, errors = build_profile(body, old)
    if errors:
        print("설정을 바꾸지 못했습니다.")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)

    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("설정을 바꿨습니다.")
    print(summary(profile))


if __name__ == "__main__":
    main()
