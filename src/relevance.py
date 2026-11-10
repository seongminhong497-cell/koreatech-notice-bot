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