import unittest
import datetime as dt

from src.relevance import process_notices

from src.youth_relevance import (
    evaluate_youth_relevance,
    match_age,
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

    def test_both_possible_ages_match(self):
        self.assertIs(self.match(2006, 19, 34), True)

    def test_minimum_birthday_boundary_is_unknown(self):
        self.assertIsNone(self.match(2007, 19, 34))

    def test_maximum_birthday_boundary_is_unknown(self):
        self.assertIsNone(self.match(1991, 19, 34))

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
    def test_nationwide_without_user_region(self):
        self.assertIs(match_region(None, None, []), True)

    def test_unknown_policy_region(self):
        self.assertIsNone(match_region("충청남도", "천안시", None))

    def test_exact_city_match(self):
        regions = [{"sido": "충청남도", "sigungu": "천안시"}]
        self.assertIs(
            match_region("충청남도", "천안시", regions), True
        )

    def test_entire_province(self):
        regions = [{"sido": "충청남도", "sigungu": None}]
        self.assertIs(match_region("충청남도", None, regions), True)

    def test_different_province(self):
        regions = [{"sido": "서울특별시", "sigungu": None}]
        self.assertIs(
            match_region("충청남도", "천안시", regions), False
        )

    def test_different_city(self):
        regions = [{"sido": "충청남도", "sigungu": "아산시"}]
        self.assertIs(
            match_region("충청남도", "천안시", regions), False
        )

    def test_missing_user_city(self):
        regions = [{"sido": "충청남도", "sigungu": "천안시"}]
        self.assertIsNone(match_region("충청남도", None, regions))

    def test_missing_user_province(self):
        regions = [{"sido": "충청남도", "sigungu": "천안시"}]
        self.assertIsNone(match_region(None, "천안시", regions))

    def test_any_matching_region_is_enough(self):
        regions = [
            {"sido": "서울특별시", "sigungu": None},
            {"sido": "충청남도", "sigungu": "천안시"},
        ]
        self.assertIs(
            match_region("충청남도", "천안시", regions), True
        )

    def test_province_and_city_stay_paired(self):
        regions = [
            {"sido": "충청남도", "sigungu": "아산시"},
            {"sido": "다른도", "sigungu": "천안시"},
        ]
        self.assertIs(
            match_region("충청남도", "천안시", regions), False
        )

    def test_malformed_alternative_prevents_false_mismatch(self):
        regions = [
            {"sido": "서울특별시", "sigungu": None},
            {"sido": "충청남도"},
        ]
        self.assertIsNone(
            match_region("충청남도", "천안시", regions)
        )

    def test_malformed_region_values(self):
        for regions in (
            "전국",
            [None],
            [{"sido": None, "sigungu": None}],
            [{"sido": "충청남도", "sigungu": ""}],
        ):
            with self.subTest(regions=regions):
                self.assertIsNone(
                    match_region("충청남도", "천안시", regions)
                )
class YouthScoringTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "birth_year": 2006,
            "region_sido": "충청남도",
            "region_sigungu": "천안시",
            "excluded_categories": [],
        }
        self.notice = {
            "category": "청년정책",
            "deadline": "2026-12-01",
            "target": {
                "age_min": 19,
                "age_max": 34,
                "age_unrestricted": False,
                "regions": [
                    {"sido": "충청남도", "sigungu": "천안시"}
                ],
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
        self.profile["birth_year"] = 2007
        rating, reason = self.result()
        self.assertEqual(rating, 1)
        self.assertIn("나이 확인 필요", reason)

    def test_uncertain_region_with_deadline_gets_one(self):
        self.profile["region_sigungu"] = None
        self.assertEqual(self.result()[0], 1)

    def test_age_mismatch_overrides_unknown_region(self):
        self.profile["birth_year"] = 2009
        self.profile["region_sigungu"] = None
        self.assertEqual(self.result()[0], 0)

    def test_region_mismatch_overrides_unknown_age(self):
        self.profile["birth_year"] = None
        self.profile["region_sido"] = "서울특별시"
        self.assertEqual(self.result()[0], 0)

    def test_excluded_category_overrides_matching(self):
        self.profile["excluded_categories"] = ["청년정책"]
        self.assertEqual(self.result()[0], 0)

    def test_missing_target_gets_one(self):
        self.notice["target"] = None
        self.assertEqual(self.result()[0], 1)

    def test_explicitly_unrestricted_conditions(self):
        self.profile = {}
        self.notice["target"] = {
            "age_unrestricted": True,
            "age_min": None,
            "age_max": None,
            "regions": [],
        }
        self.assertEqual(self.result()[0], 3)

    def test_reason_mentions_other_requirements(self):
        self.assertIn("기타 신청 조건은 원문 확인", self.result()[1])
class YouthPipelineTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(
            2026, 11, 19, 12,
            tzinfo=dt.timezone(dt.timedelta(hours=9)),
        )
        self.profile = {
            "birth_year": 2006,
            "region_sido": "충청남도",
            "region_sigungu": "천안시",
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
                "regions": [
                    {"sido": "충청남도", "sigungu": "천안시"}
                ],
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

    def test_expired_policy_keeps_rating_but_is_not_urgent(self):
        self.notice["deadline"] = "2026-11-18"
        result = self.result()
        self.assertEqual(result["relevance"], 3)
        self.assertTrue(result["is_expired"])
        self.assertFalse(result["is_urgent"])

    def test_hidden_policy_is_not_urgent(self):
        self.profile["birth_year"] = 2009
        result = self.result()
        self.assertEqual(result["relevance"], 0)
        self.assertFalse(result["is_urgent"])

    def test_uncertain_policy_can_still_have_deadline_warning(self):
        self.profile["birth_year"] = 2007
        result = self.result()
        self.assertEqual(result["relevance"], 1)
        self.assertTrue(result["is_urgent"])

    def test_age_uses_supplied_korean_year(self):
        self.now = dt.datetime(
            2027, 1, 1, 12,
            tzinfo=dt.timezone(dt.timedelta(hours=9)),
        )
        self.profile["birth_year"] = 2007
        self.assertEqual(self.result()["relevance"], 3)
if __name__ == "__main__":
    unittest.main()