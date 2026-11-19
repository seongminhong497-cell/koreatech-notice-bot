"""Youth-policy matching helpers.

True means match, False means mismatch, and None means uncertain.
Birth year alone gives a conservative range of possible ages.
"""


def match_age(
    birth_year,
    age_min,
    age_max,
    *,
    reference_year,
    unrestricted=None,
):
    """Compare possible ages with inclusive policy age limits.

    A missing bound means unknown, not automatically unlimited.
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

    oldest = reference_year - birth_year
    youngest = max(0, oldest - 1)

    # Every possible age fails a known restriction.
    if age_min is not None and oldest < age_min:
        return False
    if age_max is not None and youngest > age_max:
        return False

    # Cannot confirm eligibility with an unknown boundary.
    if age_min is None or age_max is None:
        return None

    if youngest >= age_min and oldest <= age_max:
        return True

    return None  # Birthday could change the answer.


def match_region(user_sido, user_sigungu, regions):
    """Match region pairs with OR; return True, False, or None."""
    if not isinstance(regions, list):
        return None
    if not regions:
        return True  # Explicitly nationwide.

    def clean(value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    user_sido = clean(user_sido)
    user_sigungu = clean(user_sigungu)
    uncertain = False

    for region in regions:
        if not isinstance(region, dict):
            uncertain = True
            continue

        sido = clean(region.get("sido"))
        if sido is None or "sigungu" not in region:
            uncertain = True
            continue

        raw_sigungu = region["sigungu"]
        sigungu = clean(raw_sigungu)

        if raw_sigungu is not None and sigungu is None:
            uncertain = True
            continue

        if user_sido is None:
            uncertain = True
            continue

        if user_sido != sido:
            continue

        if raw_sigungu is None:
            return True  # Entire matching province/city.

        if user_sigungu is None:
            uncertain = True
        elif user_sigungu == sigungu:
            return True

    return None if uncertain else False


def evaluate_youth_relevance(notice, profile, *, reference_year):
    """Score age/region relevance, not complete application eligibility."""
    if notice.get("category") in (
        profile.get("excluded_categories") or []
    ):
        return 0, "사용자가 제외한 분류"

    target = notice.get("target")
    if not isinstance(target, dict):
        return 1, "나이·지역 정보 확인 필요 · 기타 신청 조건은 원문 확인"

    age_match = match_age(
        profile.get("birth_year"),
        target.get("age_min"),
        target.get("age_max"),
        reference_year=reference_year,
        unrestricted=target.get("age_unrestricted"),
    )
    region_match = match_region(
        profile.get("region_sido"),
        profile.get("region_sigungu"),
        target.get("regions"),
    )

    # A definite mismatch takes priority over uncertainty elsewhere.
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

    if notice.get("deadline"):
        return (
            3,
            "나이·지역 조건 충족 · 마감 있음 · 기타 신청 조건은 원문 확인",
        )

    return (
        2,

        "나이·지역 조건 충족 · 마감 정보 없음 · 기타 신청 조건은 원문 확인",
    )
