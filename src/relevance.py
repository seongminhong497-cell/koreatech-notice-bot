"""Compare notice targets with the user's profile."""


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
