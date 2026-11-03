import copy
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from allocator import AllocationError
from service import finalize_session


class DegreeAllocationTests(unittest.TestCase):
    def setUp(self):
        self.session = {"status": "open", "revision": 7}
        self.roster = [dict(email=f"d{d}", name=f"Eleve {d}", degree=d) for d in (1, 2, 3)]
        self.activities = [
            dict(id=d * 10 + p, degree=d, period=p, name=f"Activite {p}",
                 kind="depassement", capacity=1)
            for d in (1, 2, 3) for p in (9, 10)
        ]
        self.activities[2]["kind"] = "remediation"
        self.activities[4]["kind"] = "remediation"
        self.assignments = [
            dict(email="d2", period=9, activity_id=29, source="teacher"),
            dict(email="d3", period=9, activity_id=39, source="teacher"),
        ]
        self.client = MagicMock()
        self.client.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"degree": 4, "is_admin": True}]
        )
        self.client.table.return_value.insert.return_value.execute.side_effect = self.save_plan

    def save_plan(self):
        rows = self.client.table.return_value.insert.call_args.args[0]
        lookup = {a["id"]: a for a in self.activities}
        for row in rows:
            row = dict(row)
            row["period"] = lookup[row["activity_id"]]["period"]
            self.assignments.append(row)
            self.session["revision"] += 1
        return SimpleNamespace(data=rows)

    def rows(self, client, table, **filters):
        return copy.deepcopy({
            "ft2_roster": self.roster,
            "ft2_activities": self.activities,
            "ft2_assignments": self.assignments,
        }[table])

    def run_allocation(self, skip_degrees=()):
        with patch("service.session_data", side_effect=lambda *_: dict(self.session)), patch(
            "service.all_rows", side_effect=self.rows
        ):
            finalize_session(self.client, 1, "admin@test", skip_degrees=skip_degrees)

    def test_d1_d2_saved_once_and_d3_untouched_on_regeneration(self):
        original = copy.deepcopy(self.assignments)
        self.run_allocation((3,))
        self.client.rpc.assert_not_called()
        self.client.table.return_value.insert.assert_called_once()
        inserted = self.client.table.return_value.insert.call_args.args[0]
        self.assertEqual(len(inserted), 3)
        self.assertEqual({row["email"] for row in inserted}, {"d1", "d2"})
        for row in inserted:
            self.assertEqual(row["session_id"], 1)
            self.assertEqual(row["source"], "automatic")
            self.assertEqual(row["created_by"], "admin@test")
        self.assertEqual(self.assignments[:2], original)
        self.assertEqual(self.session["status"], "open")
        self.run_allocation((3,))
        self.client.table.return_value.insert.assert_called_once()
        self.assertEqual(len(self.assignments), 5)
        # Distributing every degree later only fills D3's remaining period.
        self.run_allocation()
        self.client.rpc.assert_called_once()
        self.assertEqual(self.client.rpc.call_args.args[1]["p_plan"], [{"email": "d3", "activity_id": 40}])

    def test_other_degrees_can_be_excluded_independently(self):
        self.run_allocation((1, 2))
        inserted = self.client.table.return_value.insert.call_args.args[0]
        self.assertEqual([(row["email"], row["activity_id"]) for row in inserted], [("d3", 40)])
        self.client.rpc.assert_not_called()

    def test_all_degrees_excluded_do_not_write(self):
        self.run_allocation((1, 2, 3))
        self.client.table.return_value.insert.assert_not_called()
        self.client.rpc.assert_not_called()

    def test_no_exclusions_uses_existing_atomic_finalization(self):
        self.run_allocation()
        self.client.table.return_value.insert.assert_not_called()
        self.client.rpc.assert_called_once()
        name, args = self.client.rpc.call_args.args
        self.assertEqual(name, "ft2_finalize")
        self.assertEqual(args["p_revision"], 7)
        self.assertEqual(len(args["p_plan"]), 4)
        self.assertEqual({row["email"] for row in args["p_plan"]}, {"d1", "d2", "d3"})

    def test_unsatisfiable_selected_degree_does_not_save_partial_plan(self):
        self.activities = [a for a in self.activities if a["id"] != 20]
        with self.assertRaises(AllocationError):
            self.run_allocation((3,))
        self.client.table.return_value.insert.assert_not_called()
        self.client.rpc.assert_not_called()

    def test_role_revision_and_finalized_checks_still_apply(self):
        with patch("service.session_data", side_effect=[dict(self.session), {"revision": 8}]), patch(
            "service.all_rows", side_effect=self.rows
        ):
            with self.assertRaises(AllocationError):
                finalize_session(self.client, 1, "admin@test", skip_degrees=(3,))
        self.session["status"] = "finalized"
        self.run_allocation((3,))
        self.client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"degree": 4, "is_admin": False}
        ]
        with self.assertRaises(PermissionError):
            self.run_allocation((3,))
        self.client.table.return_value.insert.assert_not_called()
        self.client.rpc.assert_not_called()
