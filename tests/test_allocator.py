import random
import unittest

from allocator import AllocationError, allocate


def student(email, degree=2):
    return {"email": email, "degree": degree, "name": email}


def group(
    aid, period, name="atelier", degree=2, kind="depassement", study=False, capacity=12
):
    return {
        "id": aid,
        "period": period,
        "degree": degree,
        "kind": kind,
        "name": "Étude" if study else name,
        "professor": "Prof",
        "room": "A",
        "capacity": None if study else capacity,
    }


def studies(start=100, degree=2):
    return [
        group(start, 9, degree=degree, study=True),
        group(start + 1, 10, degree=degree, study=True),
    ]


class AllocationTests(unittest.TestCase):
    def test_twelve_limit_and_minimal_study(self):
        roster = [student(str(i)) for i in range(30)]
        groups = [
            group(1, 9, "a"),
            group(2, 10, "a"),
            group(3, 9, "b"),
            group(4, 10, "b"),
            *studies(),
        ]
        plan = allocate(roster, groups, [], random.Random(1))
        self.assertEqual(len(plan), 60)
        self.assertEqual(sum(a["activity_id"] >= 100 for a in plan), 12)
        for aid in (1, 2, 3, 4):
            self.assertEqual(sum(a["activity_id"] == aid for a in plan), 12)
        lookup = {g["id"]: g for g in groups}
        for pupil in roster:
            keys = [
                lookup[a["activity_id"]]["name"]
                for a in plan
                if a["email"] == pupil["email"]
            ]
            self.assertEqual(len(set(keys)), 2)

    def test_no_study_when_two_ordinary_choices_fit(self):
        plan = allocate(
            [student("a")], [group(1, 9, "a"), group(2, 10, "b"), *studies()], []
        )
        self.assertEqual({a["activity_id"] for a in plan}, {1, 2})

    def test_same_workshop_cannot_repeat(self):
        plan = allocate([student("a")], [group(1, 9), group(2, 10), *studies()], [])
        self.assertEqual(sum(a["activity_id"] < 100 for a in plan), 1)
        self.assertEqual(sum(a["activity_id"] >= 100 for a in plan), 1)

    def test_study_cannot_repeat(self):
        with self.assertRaisesRegex(AllocationError, "deux activités différentes"):
            allocate([student("a")], studies(), [])

    def test_study_capacity_above_twelve(self):
        roster = [student(str(i)) for i in range(30)]
        rems = [group(i, 9, f"math-{i}", kind="remediation") for i in (1, 2, 3)]
        existing = [
            {"email": str(i), "activity_id": 1 + i // 12, "period": 9}
            for i in range(30)
        ]
        plan = allocate(roster, [*rems, *studies()], existing)
        self.assertEqual(len(plan), 30)
        self.assertEqual({a["activity_id"] for a in plan}, {101})

    def test_existing_remediation_key_excludes_same_enrichment(self):
        groups = [
            group(1, 9, "math", kind="remediation"),
            group(2, 10, "math"),
            *studies(),
        ]
        existing = [{"email": "a", "activity_id": 1, "period": 9}]
        plan = allocate([student("a")], groups, existing)
        self.assertEqual(plan, [{"email": "a", "activity_id": 101}])
        self.assertEqual(len(existing), 1)

    def test_degrees_are_independent(self):
        groups = [
            group(1, 9, "a", degree=1),
            group(2, 10, "b", degree=1),
            group(3, 9, "c", degree=2),
            group(4, 10, "d", degree=2),
            group(5, 9, "e", degree=3),
            group(6, 10, "f", degree=3),
        ]
        plan = allocate([student("a", 1), student("b", 2), student("c", 3)], groups, [])
        lookup = {g["id"]: g for g in groups}
        for a in plan:
            self.assertEqual(
                lookup[a["activity_id"]]["degree"], {"a": 1, "b": 2, "c": 3}[a["email"]]
            )

    def test_global_assignment_avoids_greedy_dead_end(self):
        # P9 can use A or B, but P10 only A. Choosing A in P9 would force study.
        groups = [group(1, 9, "a"), group(2, 9, "b"), group(3, 10, "a"), *studies()]
        plan = allocate([student("a")], groups, [])
        self.assertEqual({a["activity_id"] for a in plan}, {2, 3})

    def test_empty_and_already_complete(self):
        self.assertEqual(allocate([], [], []), [])
        groups = [group(1, 9, "a"), group(2, 10, "b")]
        assignments = [
            {"email": "a", "activity_id": i, "period": 8 + i} for i in (1, 2)
        ]
        self.assertEqual(allocate([student("a")], groups, assignments), [])

    def test_custom_capacities_and_generic_unlimited_priority(self):
        roster = [student(str(i)) for i in range(6)]
        groups = [
            group(1, 9, "Robotique", capacity=2),
            group(2, 10, "Arts", capacity=3),
            group(3, 9, "Lecture", capacity=None),
            group(4, 10, "Musique", capacity=None),
        ]
        plan = allocate(roster, groups, [], random.Random(2))
        self.assertEqual(sum(a["activity_id"] == 1 for a in plan), 2)
        self.assertEqual(sum(a["activity_id"] == 2 for a in plan), 3)
        self.assertEqual(sum(a["activity_id"] in (3, 4) for a in plan), 7)

    def test_same_name_ignores_case_spaces_and_professor(self):
        groups = [
            group(1, 9, " Math ", kind="remediation"),
            group(2, 10, "MATH"),
            group(3, 10, "Lecture", capacity=None),
        ]
        groups[1]["professor"] = "Autre prof"
        plan = allocate(
            [student("a")], groups, [{"email": "a", "activity_id": 1, "period": 9}]
        )
        self.assertEqual(plan, [{"email": "a", "activity_id": 3}])

    def test_study_name_has_no_special_priority(self):
        groups = [
            group(1, 9, "Étude", capacity=2),
            group(2, 9, "Robotique", capacity=None),
            group(3, 10, "Lecture", capacity=None),
        ]
        plan = allocate([student("a")], groups, [])
        self.assertIn({"email": "a", "activity_id": 1}, plan)
