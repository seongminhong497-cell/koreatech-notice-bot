"""Calculate notice relevance and deadlines using explicit profile data."""

import argparse
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = dt.timezone(dt.timedelta(hours=9))


def match_condition(user_value, allowed_values):
    """Return True (match), False (mismatch), or None (unknown)."""
    if allowed_values is None:
        return None
    if allowed_values == []:
        return True
    if user_value is None:
        return None
    return user_value in allowed_values


def match_academic_conditions(profile, target):
    """Compare department, year, and enrollment status."""
    fields = (
        ("department", "departments"),
        ("year", "years"),
        ("enrollment_status", "enrollment_statuses"),
    )
    results = [
        match_condition(profile.get(user_key), target.get(target_key))
        for user_key, target_key in fields
    ]
    if False in results:
        return False
    if None in results:
        return None
    return True


def match_groups(profile, groups):
    """Groups overlap; missing membership information is not a mismatch."""
    if groups is None:
        return None
    if groups == []:
        return True

    known = set(profile.get("groups") or [])
    excluded = set(profile.get("excluded_target_groups") or [])

    # OR: one known matching group is enough.
    if known.intersection(groups):
        return True

    # Hide only when every possible group is explicitly excluded.
    if all(group in excluded for group in groups):
        return False
    return None


def evaluate_relevance(notice, profile):
    """Rate strong matches separately from broad eligibility."""
    category = notice.get("category")
    if category in (profile.get("excluded_categories") or []):
        return 0, "사용자가 제외한 분류"

    target = notice.get("target")
    if not isinstance(target, dict):
        return 1, "대상 정보가 불명확함"

    strong_matches = []
    broad_matches = []
    uncertain = False

    fields = (
        ("department", "departments", "학과", True),
        ("year", "years", "학년", True),
        ("enrollment_status", "enrollment_statuses", "학적 상태", False),
    )

    for user_key, target_key, label, is_strong in fields:
        allowed = target.get(target_key)
        result = match_condition(profile.get(user_key), allowed)

        if result is False:
            return 0, f"{label} 조건 불일치"
        if result is None:
            uncertain = True
        elif allowed:
            if is_strong:
                strong_matches.append(label)
            else:
                broad_matches.append(label)

    groups = target.get("groups")
    group_result = match_groups(profile, groups)
    if group_result is False:
        return 0, "제외 대상 집단 전용 공지"
    if group_result is None:
        uncertain = True
    elif groups:
        broad_matches.append("대상 집단")

    required = target.get("dorm_required")
    if required is not None:
        resident = profile.get("dorm_resident")
        if resident is None:
            uncertain = True
        elif resident != required:
            return 0, "생활관 거주 조건 불일치"
        else:
            strong_matches.append("생활관")

    scope = target.get("scope")
    if scope not in ("all", "specific"):
        return 1, "대상 정보가 불명확함"

    restricted = any(
        target.get(key)
        for key in (
            "departments",
            "years",
            "enrollment_statuses",
            "groups",
        )
    ) or required is not None

    has_deadline = bool(notice.get("deadline"))
    interested = category in (profile.get("interests") or [])

    if scope == "all":
        if restricted:
            return 1, "전체 대상 표시와 세부 조건 확인 필요"
        if interested and has_deadline:
            return 2, "전체 학생 대상 · 관심 분류 · 마감 있음"
        return 1, "전체 학생 대상 · 관심 분류와 마감 조건 미충족"

    if uncertain:
        return 1, "일부 대상 조건 또는 사용자 정보 확인 필요"

    if strong_matches:
        labels = ", ".join(strong_matches)
        if has_deadline:
            return 3, f"좁은 조건({labels}) 일치 · 마감 있음"
        return 1, f"좁은 조건({labels}) 일치 · 마감 정보 없음"

    if broad_matches:
        labels = ", ".join(broad_matches)
        if interested and has_deadline:
            return 2, f"넓은 조건({labels}) 일치 · 관심 분류 · 마감 있음"
        return 1, f"넓은 조건({labels})만 일치"

    return 1, "명확한 대상 조건이 없어 일반 공지로 표시"


def deadline_info(notice, profile, now):
    """Return D-day, expiration, and urgency using Korean time."""
    deadline = notice.get("deadline")
    if not deadline:
        return None, False, False

    if len(deadline) == 10:
        day = dt.date.fromisoformat(deadline)
        expired = day < now.date()
    else:
        moment = dt.datetime.fromisoformat(deadline)
        if moment.tzinfo is None:
            raise ValueError("Deadline timestamp must include a timezone")
        moment = moment.astimezone(KST)
        day = moment.date()
        expired = moment <= now

    days = (day - now.date()).days
    materials = notice.get("materials")
    has_materials = isinstance(materials, list) and bool(materials)
    key = "preparation_days" if has_materials else "urgent_days"
    limit = profile.get(key, 7 if has_materials else 3)

    urgent = (
        notice.get("relevance") in (1, 2, 3)
        and not expired
        and 0 <= days <= limit
    )
    return days, expired, urgent


def process_notices(notices, profile, now=None):
    """Recalculate completed AI results, preserving other notice fields."""
    now = now or dt.datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(KST)

    results = []
    for original in notices:
        notice = dict(original)

        # Never leave an old rating looking current after AI reset/failure.
        if notice.get("extracted") is not True:
            notice.update(
                relevance=None,
                relevance_reason=None,
                processed=False,
                days_left=None,
                is_expired=None,
                is_urgent=False,
            )
            results.append(notice)
            continue

        rating, reason = evaluate_relevance(notice, profile)
        notice["relevance"] = rating
        notice["relevance_reason"] = reason

        days, expired, urgent = deadline_info(notice, profile, now)
        notice.update(
            days_left=days,
            is_expired=expired,
            is_urgent=urgent,
            processed=True,
        )
        results.append(notice)

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--notices", type=Path, default=ROOT / "data/notices.json"
    )
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "data/profile.json"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with args.notices.open(encoding="utf-8") as file:
        notices = json.load(file)
    with args.profile.open(encoding="utf-8") as file:
        profile = json.load(file)

    if not isinstance(notices, list) or not isinstance(profile, dict):
        raise ValueError("Expected a notices array and a profile object")

    results = process_notices(notices, profile)

    for notice in results:
        print(
            f"{notice.get('id')} | "
            f"rating={notice['relevance']} | "
            f"D-day={notice['days_left']} | "
            f"{notice['relevance_reason']}"
        )

    if args.dry_run:
        print("DRY RUN: no files changed.")
        return

    output = args.output or args.notices
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(output)
    print(f"Saved {len(results)} notices to {output}")


if __name__ == "__main__":
    main()