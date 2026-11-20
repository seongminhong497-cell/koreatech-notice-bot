
import unittest
import datetime as dt

from src.relevance import process_notices

from src.youth_relevance import (
    evaluate_youth_relevance,
    match_age,
    classify_region,
    match_region,
)


class AgeMatchingTests(unittest.TestCase):
    def match(self, birth_year, minimum, maximum, unrestricted=None):
        return match_age(
            birth_year,
            minimum,
            maximum,
            reference_year=2026,
            unrestricted=unrestricted,
        )

    def test_calendar_year_age_matches(self):
        self.assertIs(self.match(2006, 19, 34), True)

    def test_minimum_age_is_inclusive(self):
        self.assertIs(self.match(2007, 19, 34), True)

    def test_above_maximum_age_is_mismatch(self):
        self.assertIs(self.match(1991, 19, 34), False)

    def test_definitely_too_young(self):
        self.assertIs(self.match(2009, 19, 34), False)

    def test_definitely_too_old(self):
        self.assertIs(self.match(1990, 19, 34), False)

    def test_missing_birth_year(self):
        self.assertIsNone(self.match(None, 19, 34))

    def test_explicitly_unrestricted(self):
        self.assertIs(self.match(None, None, None, True), True)

    def test_missing_limits_are_unknown(self):
        self.assertIsNone(self.match(2006, None, None))

    def test_one_missing_limit_cannot_confirm_match(self):
        self.assertIsNone(self.match(2006, 19, None))
        self.assertIsNone(self.match(2006, None, 34))

    def test_known_limit_can_prove_mismatch(self):
        self.assertIs(self.match(2009, 19, None), False)
        self.assertIs(self.match(1990, None, 34), False)

    def test_invalid_or_contradictory_data(self):
        cases = [
            (2027, 19, 34, None),
            (True, 19, 34, None),
            ("2006", 19, 34, None),
            (2006, 34, 19, None),
            (2006, -1, 34, None),
            (2006, 19, 34, True),
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.assertIsNone(self.match(*arguments))


class RegionMatchingTests(unittest.TestCase):
    def test_region_codes(self):
        cases = [
            ("exact district", "44131", ["44131"], False, True),
            ("parent city", "44131", ["44130"], False, True),
            ("another city", "44131", ["44150"], False, False),
            ("another district", "44131", ["44133"], False, False),
            ("multiple codes", "44131", ["44150", "44130"], False, True),
            ("nationwide", "44131", [], True, True),
            ("missing user", None, ["44130"], False, None),
            ("empty user", "", ["44130"], False, None),
            ("nationwide missing user", None, [], True, None),
            ("unknown policy", "44131", None, False, None),
            ("empty local list", "44131", [], False, None),
            ("missing nationwide flag", "44131", [], None, None),
            ("contradictory nationwide", "44131", ["44130"], True, None),
            ("numeric user", 44131, ["44130"], False, None),
            ("short user", "4413", ["44130"], False, None),
            ("invalid policy code", "44131", ["bad"], False, None),
            ("mixed unknown", "44131", ["44150", None], False, None),
            ("known match wins", "44131", ["44130", None], False, True),
        ]
        for label, user, codes, nationwide, expected in cases:
            with self.subTest(case=label):
                self.assertIs(
                    match_region(user, codes, nationwide=nationwide),
                    expected,
                )


class YouthScoringTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "birth_year": 2006,
            "region_code": "44131",
            "excluded_categories": [],
        }
        self.notice = {
            "category": "청년정책",
            "deadline": "2026-12-01",
            "target": {
                "age_min": 19,
                "age_max": 34,
                "age_unrestricted": False,
                "region_codes": ["44130"],
                "nationwide": False,
            },
        }

    def result(self):
        return evaluate_youth_relevance(
            self.notice, self.profile, reference_year=2026
        )

    def test_matches_with_deadline_get_three(self):
        self.assertEqual(self.result()[0], 3)

    def test_matches_without_deadline_get_two(self):
        self.notice["deadline"] = None
        self.assertEqual(self.result()[0], 2)

    def test_uncertain_age_with_deadline_gets_one(self):
        self.profile["birth_year"] = None
        rating, reason = self.result()
        self.assertEqual(rating, 1)
        self.assertIn("나이 확인 필요", reason)

    def test_uncertain_region_with_deadline_gets_one(self):
        self.profile["region_code"] = None
        self.assertEqual(self.result()[0], 1)

    def test_age_mismatch_overrides_unknown_region(self):
        self.profile["birth_year"] = 2009
        self.profile["region_code"] = None
        self.assertEqual(self.result()[0], 0)

    def test_region_mismatch_overrides_unknown_age(self):
        self.profile["birth_year"] = None
        self.profile["region_code"] = "11110"
        self.assertEqual(self.result()[0], 0)

    def test_excluded_category_overrides_matching(self):
        self.profile["excluded_categories"] = ["청년정책"]
        self.assertEqual(self.result()[0], 0)

    def test_missing_target_gets_one(self):
        self.notice["target"] = None
        self.assertEqual(self.result()[0], 1)

    def test_nationwide_without_user_region_requires_confirmation(self):
        self.profile = {}
        self.notice["target"] = {
            "age_unrestricted": True,
            "age_min": None,
            "age_max": None,
            "region_codes": [],
            "nationwide": True,
        }
        self.assertEqual(self.result()[0], 1)

    def test_reason_mentions_other_requirements(self):
        self.assertIn("기타 신청 조건은 원문 확인", self.result()[1])

    def test_region_scope_and_stars(self):
        cases = [
            (["44131"], False, True, False, 3),
            (["44130", "44131", "44133"], False, True, False, 3),
            (["44130"], False, False, False, 2),
            (["44130", "44150"], False, True, False, 2),
            (["44130", "11110"], False, False, True, 1),
            ([], True, True, True, 2),
            ([], True, False, True, 2),
            ([], True, True, False, 1),
            ([], True, False, False, 1),
            (["44133"], False, True, True, 0),
            (["44130", None], False, True, True, 1),
        ]
        for codes, nationwide, deadline, interest, expected in cases:
            with self.subTest(codes=codes, deadline=deadline, interest=interest):
                self.notice["target"].update(
                    region_codes=codes, nationwide=nationwide
                )
                self.notice["deadline"] = "2026-12-01" if deadline else None
                self.profile["interests"] = ["청년정책"] if interest else []
                self.assertEqual(self.result()[0], expected)

    def test_unknown_age_precedes_nationwide_interest(self):
        self.notice["target"].update(nationwide=True, region_codes=[])
        self.profile.update(birth_year=None, interests=["청년정책"])
        self.assertEqual(self.result()[0], 1)

    def test_scope_uses_membership_before_prefix(self):
        self.assertIs(classify_region(
            "44131", ["44133"], nationwide=False
        ), False)
        self.assertEqual(classify_region(
            "44150", ["44150"], nationwide=False
        ), "local")

    def test_maximum_age_is_inclusive(self):
        self.assertIs(match_age(
            1992, 19, 34, reference_year=2026, unrestricted=False
        ), True)


class YouthPipelineTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(
            2026, 11, 19, 12,
            tzinfo=dt.timezone(dt.timedelta(hours=9)),
        )
        self.profile = {
            "birth_year": 2006,
            "region_code": "44131",
            "urgent_days": 3,
            "preparation_days": 7,
        }
        self.notice = {
            "id": "youth-test-001",
            "category": "청년정책",
            "extracted": True,
            "processed": False,
            "is_sample": True,
            "is_new": True,
            "deadline": "2026-11-21",
            "materials": [],
            "target": {
                "age_min": 19,
                "age_max": 34,
                "age_unrestricted": False,
                "region_codes": ["44130"],
                "nationwide": False,
            },
        }

    def result(self):
        return process_notices(
            [self.notice], self.profile, now=self.now
        )[0]

    def test_youth_scoring_and_deadlines_are_connected(self):
        result = self.result()
        self.assertEqual(result["relevance"], 3)
        self.assertTrue(result["processed"])
        self.assertEqual(result["days_left"], 2)
        self.assertFalse(result["is_expired"])
        self.assertTrue(result["is_urgent"])
        self.assertTrue(result["is_sample"])
        self.assertTrue(result["is_new"])
        self.assertFalse(self.notice["processed"])

    def test_unfinished_youth_policy_is_not_scored(self):
        self.notice.update(
            extracted=False,
            processed=True,
            relevance=3,
            relevance_reason="Old result",
        )
        result = self.result()
        self.assertIsNone(result["relevance"])
        self.assertIsNone(result["relevance_reason"])
        self.assertFalse(result["processed"])
        self.assertFalse(result["is_urgent"])

    def test_expired_policy_is_hidden_and_not_urgent(self):
        self.notice["deadline"] = "2026-11-18"
        result = self.result()
        self.assertEqual(result["relevance"], 0)
        self.assertTrue(result["is_expired"])
        self.assertFalse(result["is_urgent"])

    def test_hidden_policy_is_not_urgent(self):
        self.profile["birth_year"] = 2009
        result = self.result()
        self.assertEqual(result["relevance"], 0)
        self.assertFalse(result["is_urgent"])

    def test_uncertain_policy_can_still_have_deadline_warning(self):
        self.profile["birth_year"] = None
        result = self.result()
        self.assertEqual(result["relevance"], 1)
        self.assertTrue(result["is_urgent"])

    def test_age_uses_supplied_korean_year(self):
        self.now = dt.datetime(
            2027, 1, 1, 12,
            tzinfo=dt.timezone(dt.timedelta(hours=9)),
        )
        self.profile["birth_year"] = 2008
        self.notice["deadline"] = "2027-01-02"
        self.assertEqual(self.result()["relevance"], 3)


    def test_expiration_boundaries(self):
        cases = [
            ("2026-11-19", 3, False),
            ("2026-11-18", 0, True),
            ("2026-11-19T12:00:00+09:00", 0, True),
            ("2026-11-19T12:00:01+09:00", 3, False),
            ("2026-11-19T03:00:00+00:00", 0, True),
        ]
        for deadline, rating, expired in cases:
            with self.subTest(deadline=deadline):
                self.notice["deadline"] = deadline
                result = self.result()
                self.assertEqual(result["relevance"], rating)
                self.assertEqual(result["is_expired"], expired)
                if expired:
                    self.assertFalse(result["is_urgent"])

    def test_expired_unknown_policy_is_hidden(self):
        self.profile["birth_year"] = None
        self.notice["deadline"] = "2026-11-18"
        self.assertEqual(self.result()["relevance"], 0)

    def test_year_converts_to_korean_time(self):
        self.now = dt.datetime(2026, 12, 31, 15, tzinfo=dt.timezone.utc)
        self.profile["birth_year"] = 2008
        self.notice["deadline"] = "2027-01-02"
        self.assertEqual(self.result()["relevance"], 3)


if __name__ == "__main__":
    unittest.main()
