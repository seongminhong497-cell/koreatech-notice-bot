
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
        profile.get("region_code"),
        target.get("region_codes"),
        nationwide=target.get("nationwide"),
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
