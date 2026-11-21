
"""Youth-policy matching helpers.

True means match, False means mismatch, and None means uncertain.
Age uses the team convention: Korean calendar year minus birth year.
"""


def match_age(
    birth_year,
    age_min,
    age_max,
    *,
    reference_year,
    unrestricted=None,
):
    """Compare calendar-year age with inclusive policy age limits.

    When unrestricted=False, a single missing bound means no
    restriction on that side. Both missing bounds remain uncertain.
    Explicit unrestricted=True permits any age.
    """
    if unrestricted is True:
        if age_min is not None or age_max is not None:
            return None  # Contradictory policy data.
        return True

    if unrestricted is not None and unrestricted is not False:
        return None

    for bound in (age_min, age_max):
        if bound is not None and (
            type(bound) is not int or bound < 0
        ):
            return None

    if (
        age_min is not None
        and age_max is not None
        and age_min > age_max
    ):
        return None

    if type(reference_year) is not int:
        return None

    if (
        type(birth_year) is not int
        or birth_year < 1
        or birth_year > reference_year
    ):
        return None

    age = reference_year - birth_year

    if age_min is not None and age < age_min:
        return False

    if age_max is not None and age > age_max:
        return False

    # Both missing limits remain uncertain.
    if age_min is None and age_max is None:
        return None

    # A single missing limit is unrestricted on that side
    # when age_unrestricted is explicitly False.
    if unrestricted is False:
        return True

    # Without an explicit False flag, missing limits
    # still require confirmation.
    if age_min is None or age_max is None:
        return None

    return True


def match_region(user_code, region_codes, *, nationwide=None):
    """Compare district/city codes; missing information stays uncertain."""

    def valid_code(value):
        return (
            isinstance(value, str)
            and len(value) == 5
            and value.isascii()
            and value.isdigit()
        )

    # Team rule: missing user region requires confirmation.
    if not valid_code(user_code):
        return None

    if not isinstance(region_codes, list):
        return None

    if nationwide is True:
        return True if region_codes == [] else None

    if nationwide is not False:
        return None

    # An empty list alone does not mean nationwide.
    if not region_codes:
        return None

    city_code = user_code[:4] + "0"

    valid_codes = [
        code for code in region_codes if valid_code(code)
    ]

    if user_code in valid_codes or city_code in valid_codes:
        return True

    # Invalid entries might contain missing matching information.
    if len(valid_codes) != len(region_codes):
        return None

    return False


def classify_region(user_code, region_codes, *, nationwide=None):
    """Return local, wide, nationwide, False (mismatch), or None."""

    matched = match_region(
        user_code,
        region_codes,
        nationwide=nationwide,
    )

    if matched is not True:
        return matched

    if nationwide is True:
        return "nationwide"

    # A known membership match cannot establish scope
    # if codes are malformed.
    if any(
        not isinstance(code, str)
        or len(code) != 5
        or not code.isascii()
        or not code.isdigit()
        for code in region_codes
    ):
        return None

    if all(
        code.startswith(user_code[:4])
        for code in region_codes
    ):
        return "local"

    return "wide"


def evaluate_youth_relevance(notice, profile, *, reference_year):
    """Score age/region relevance, not complete application eligibility."""

    if notice.get("category") in (
        profile.get("excluded_categories") or []
    ):
        return 0, "사용자가 제외한 분류"

    target = notice.get("target")

    if not isinstance(target, dict):
        return (
            1,
            "나이·지역 정보 확인 필요 · 기타 신청 조건은 원문 확인",
        )

    age_match = match_age(
        profile.get("birth_year"),
        target.get("age_min"),
        target.get("age_max"),
        reference_year=reference_year,
        unrestricted=target.get("age_unrestricted"),
    )

    region_match = classify_region(
        profile.get("region_code"),
        target.get("region_codes"),
        nationwide=target.get("nationwide"),
    )

    # A definite mismatch takes priority over uncertainty.
    mismatches = []

    if age_match is False:
        mismatches.append("나이")

    if region_match is False:
        mismatches.append("지역")

    if mismatches:
        return 0, f"{'·'.join(mismatches)} 조건 불일치"

    unknown = []

    if age_match is None:
        unknown.append("나이")

    if region_match is None:
        unknown.append("지역")

    if unknown:
        return (
            1,
            f"{'·'.join(unknown)} 확인 필요 · 기타 신청 조건은 원문 확인",
        )

    has_deadline = bool(notice.get("deadline"))

    if region_match == "local":
        rating = 3 if has_deadline else 2
        area = "우리 시 정책"

    elif region_match == "wide":
        rating = 2 if has_deadline else 1
        area = "광역 정책"

    else:
        interested = "청년정책" in (
            profile.get("interests") or []
        )

        rating = 2 if interested else 1

        area = (
            "전국 정책 · 관심 분야"
            if interested
            else "전국 정책"
        )

    timing = (
        "마감 있음"
        if has_deadline
        else "마감 정보 없음(상시 등)"
    )

    return (
        rating,
        f"{area} · 나이 일치 · {timing} · 기타 신청 조건은 원문 확인",
    )
