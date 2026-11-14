import copy
import datetime as dt
import unittest

from src.relevance import KST, process_notices


class RelevanceTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 11, 18, tzinfo=KST)
        self.profile = {
            "department": "CS",
            "year": 1,
            "enrollment_status": "enrolled",
            "dorm_resident": True,
            "groups": ["학부생"],
            "excluded_target_groups": ["대학원생", "교직원"],
            "excluded_categories": [],
            "interests": ["장학"],
            "always_show_categories": ["학사"],
            "urgent_days": 3,
            "preparation_days": 7,
        }
        self.notice = {
            "id": "test",
            "extracted": True,
            "processed": False,
            "is_new": True,
            "is_sample": True,
            "category": "장학",
            "deadline": "2026-11-14",
            "materials": [],
            "other_dates": [],
            "target": {
                "scope": "specific",
                "departments": ["CS"],
                "years": [1, 2],
                "enrollment_statuses": ["enrolled"],
                "groups": ["학부생"],
                "dorm_required": None,
            },
        }

    def result(self):
        return process_notices(
            [self.notice], self.profile, self.now
        )[0]

    def test_specific_match(self):
        result = self.result()
        self.assertEqual(result["relevance"], 3)
        self.assertTrue(result["processed"])
        self.assertTrue(result["relevance_reason"])

    def test_mismatch_overrides_always_show(self):
        self.notice["category"] = "학사"
        self.notice["target"]["years"] = [3]
        self.assertEqual(self.result()["relevance"], 0)

    def test_unknown_user_information(self):
        self.profile["year"] = None
        self.assertEqual(self.result()["relevance"], 1)

    def test_all_students(self):
        self.notice["target"] = {
            "scope": "all",
            "departments": [],
            "years": [],
            "enrollment_statuses": [],
            "groups": [],
            "dorm_required": None,
        }
        self.assertEqual(self.result()["relevance"], 2)
        self.notice["category"] = "교내활동"
        self.assertEqual(self.result()["relevance"], 1)

    def test_unknown_target(self):
        self.notice["target"] = None
        self.assertEqual(self.result()["relevance"], 1)

    def test_excluded_category(self):
        self.profile["excluded_categories"] = ["장학"]
        self.assertEqual(self.result()["relevance"], 0)

    def test_groups_or_and_unknown(self):
        self.notice["target"]["groups"] = ["대학원생"]
        self.assertEqual(self.result()["relevance"], 0)
        self.notice["target"]["groups"] = ["학부생", "대학원생"]
        self.assertEqual(self.result()["relevance"], 3)
        self.notice["target"]["groups"] = ["외국인 유학생"]
        self.assertEqual(self.result()["relevance"], 1)

    def test_dorm(self):
        self.notice["target"]["dorm_required"] = False
        self.assertEqual(self.result()["relevance"], 0)
        self.notice["target"]["dorm_required"] = True
        self.assertEqual(self.result()["relevance"], 3)
        self.profile["dorm_resident"] = None
        self.assertEqual(self.result()["relevance"], 1)

    def test_unfinished_ai_clears_old_results(self):
        self.notice.update(
            extracted=False, processed=True, relevance=3
        )
        result = self.result()
        self.assertIsNone(result["relevance"])
        self.assertFalse(result["processed"])
        self.assertFalse(result["is_urgent"])

    def test_urgency_boundaries(self):
        self.assertTrue(self.result()["is_urgent"])
        self.notice["deadline"] = "2026-11-15"
        self.assertFalse(self.result()["is_urgent"])
        self.notice["materials"] = ["Form"]
        self.notice["deadline"] = "2026-11-18"
        self.assertTrue(self.result()["is_urgent"])
        self.notice["deadline"] = "2026-11-19"
        self.assertFalse(self.result()["is_urgent"])

    def test_expiration(self):
        for deadline, expired in [
            ("2026-11-11T17:00:00+09:00", True),
            ("2026-11-11T18:00:00+09:00", True),
            ("2026-11-11T19:00:00+09:00", False),
            ("2026-11-11", False),
            ("2026-11-10", True),
        ]:
            with self.subTest(deadline=deadline):
                self.notice["deadline"] = deadline
                result = self.result()
                self.assertEqual(result["is_expired"], expired)
                if expired:
                    self.assertFalse(result["is_urgent"])

    def test_hidden_is_not_urgent(self):
        self.notice["target"]["years"] = [3]
        self.assertFalse(self.result()["is_urgent"])

    def test_other_dates_are_not_deadlines(self):
        self.notice["deadline"] = None
        self.notice["other_dates"] = [
            {"label": "Event", "date": "2026-11-12"}
        ]
        result = self.result()
        self.assertIsNone(result["days_left"])
        self.assertFalse(result["is_urgent"])

    def test_preserves_data_and_recalculates(self):
        original = copy.deepcopy(self.notice)
        first = self.result()
        self.assertEqual(self.notice, original)
        self.assertTrue(first["is_sample"])
        self.assertTrue(first["is_new"])
        self.assertEqual(first["target"], original["target"])
        again = process_notices(
            [first], self.profile, self.now
        )[0]
        self.assertEqual(first, again)
        self.profile["year"] = 4
        changed = process_notices(
            [first], self.profile, self.now
        )[0]
        self.assertEqual(changed["relevance"], 0)

    def make_broad_target(self):
        self.notice["target"].update(
            departments=[],
            years=[],
            dorm_required=None,
        )

    def test_broad_interest_and_deadline_gets_two(self):
        self.make_broad_target()
        self.assertEqual(self.result()["relevance"], 2)

    def test_broad_without_interest_gets_one(self):
        self.make_broad_target()
        self.notice["category"] = "교내활동"
        self.assertEqual(self.result()["relevance"], 1)

    def test_broad_without_deadline_gets_one(self):
        self.make_broad_target()
        self.notice["deadline"] = None
        self.assertEqual(self.result()["relevance"], 1)

    def test_always_show_alone_does_not_raise_rating(self):
        self.make_broad_target()
        self.notice["category"] = "학사"
        self.assertEqual(self.result()["relevance"], 1)

    def test_each_strong_condition_can_get_three(self):
        cases = (
            {"departments": ["CS"]},
            {"years": [1]},
            {"dorm_required": True},
            {"dorm_required": False},
        )
        for condition in cases:
            with self.subTest(condition=condition):
                self.make_broad_target()
                self.notice["target"].update(condition)
                self.profile["dorm_resident"] = condition.get(
                    "dorm_required", True
                )
                self.assertEqual(self.result()["relevance"], 3)

    def test_strong_match_without_deadline_gets_one(self):
        self.notice["deadline"] = None
        self.assertEqual(self.result()["relevance"], 1)

    def test_strong_match_does_not_override_broad_mismatch(self):
        self.notice["target"]["enrollment_statuses"] = ["on_leave"]
        self.assertEqual(self.result()["relevance"], 0)

    def test_broad_unknown_membership_gets_one(self):
        self.make_broad_target()
        self.profile["groups"] = None
        self.assertEqual(self.result()["relevance"], 1)

    def test_all_students_requires_interest_and_deadline(self):
        self.notice["target"] = {
            "scope": "all",
            "departments": [],
            "years": [],
            "enrollment_statuses": [],
            "groups": [],
            "dorm_required": None,
        }
        self.assertEqual(self.result()["relevance"], 2)
        self.notice["deadline"] = None
        self.assertEqual(self.result()["relevance"], 1)
        self.notice["deadline"] = "2026-11-14"
        self.notice["category"] = "학사"
        self.assertEqual(self.result()["relevance"], 1)


if __name__ == "__main__":
    unittest.main()
