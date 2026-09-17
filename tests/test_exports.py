from io import BytesIO
import unittest
from openpyxl import load_workbook
from exports import excel_bytes, course_and_year, group_sort_key, surname_first


class ExportTests(unittest.TestCase):
    def test_reference_layout_colors_and_formula_safety(self):
        roster = [{"email": "a", "name": "=1+1", "degree": 2}]
        groups = [
            {
                "id": 1,
                "period": 9,
                "degree": 2,
                "name": "Math",
                "professor": "Prof Math",
                "room": "A",
                "kind": "remediation",
            },
            {
                "id": 2,
                "period": 10,
                "degree": 2,
                "name": "Étude",
                "professor": "Prof Étude",
                "room": "B",
                "kind": "depassement",
            },
        ]
        assignments = [
            {"email": "a", "period": 9, "activity_id": 1},
            {"email": "a", "period": 10, "activity_id": 2},
        ]
        wb = load_workbook(
            BytesIO(
                excel_bytes(
                    {"title": "Test", "event_date": "2026-09-15"},
                    roster,
                    groups,
                    assignments,
                )
            )
        )
        self.assertEqual(wb.sheetnames, ["D1", "D2", "D3"])
        ws = wb["D2"]
        self.assertEqual(ws["B1"].value, "Math\n\nProf Math\nLocal A")
        self.assertEqual(ws["B2"].data_type, "s")
        self.assertEqual(ws["C19"].value, "Étude\n\nProf Étude\nLocal B")
        self.assertEqual(ws["C20"].value, "=1+1")
        self.assertEqual(ws["A1"].value, "P9")
        self.assertEqual(ws["A19"].value, "P10")
        self.assertEqual(ws["A2"].value, 1)
        self.assertEqual(ws["A20"].value, 1)
        self.assertFalse(ws.merged_cells.ranges)
        self.assertIsNone(ws["B2"].fill.patternType)
        self.assertIsNone(ws["B3"].fill.patternType)
        self.assertTrue(ws.sheet_view.showGridLines)
        self.assertTrue(ws.print_options.gridLines)
        self.assertEqual(ws.page_setup.orientation, "landscape")

    def test_unlimited_group_never_truncated_and_next_block_moves(self):
        roster = [
            {"email": str(i), "name": f"Élève {i:02}", "degree": 1} for i in range(30)
        ]
        groups = [
            {
                "id": i,
                "degree": 1,
                "period": 8 + i,
                "name": f"Activité {i}",
                "professor": "Prof",
                "room": "A",
            }
            for i in (1, 2)
        ]
        assignments = [
            {"email": str(i), "activity_id": a, "period": 8 + a}
            for i in range(30)
            for a in (1, 2)
        ]
        wb = load_workbook(
            BytesIO(
                excel_bytes(
                    {"title": "Test", "event_date": "2026-09-15"},
                    roster,
                    groups,
                    assignments,
                )
            )
        )
        self.assertEqual(wb["D1"]["B31"].value, "29 Élève")
        self.assertEqual(wb["D1"]["A37"].value, "P10")
        self.assertEqual(wb["D1"]["C67"].value, "29 Élève")
        self.assertEqual(wb["D1"]["A67"].value, 30)

    def test_year_extraction_and_group_order(self):
        for name, expected in (
            ("Math 2ème", ("Math", "2ème", 2)),
            ("Français 1", ("Français", "1ère", 1)),
            ("Sciences 3e", ("Sciences", "3ème", 3)),
            ("Math 4ième", ("Math", "4ème", 4)),
            ("Math 5ème", ("Math", "5ème", 5)),
            ("Math 6ème", ("Math", "6ème", 6)),
            ("Robotique", ("Robotique", "", None)),
        ):
            with self.subTest(name=name):
                self.assertEqual(course_and_year(name), expected)
        names = [
            ("ÉTUDE accompagnée", "depassement"),
            ("Math 2ème", "remediation"),
            ("Atelier", "depassement"),
            ("Sciences 1ère", "remediation"),
            ("Math", "remediation"),
            ("Zoologie", "depassement"),
        ]
        groups = [{"name": n, "kind": k, "period": 9} for n, k in names]
        self.assertEqual(
            [g["name"] for g in sorted(groups, key=group_sort_key)],
            ["Sciences 1ère", "Math 2ème", "Math", "Atelier", "Zoologie", "ÉTUDE accompagnée"],
        )

    def test_surname_first_preserves_family_name(self):
        self.assertEqual(surname_first("Alice de la Fontaine"), "de la Fontaine Alice")
        self.assertEqual(surname_first("Jean-Pierre Dupont"), "Dupont Jean-Pierre")
        self.assertEqual(surname_first("Alice"), "Alice")

    def test_incomplete_excel_refused(self):
        with self.assertRaises(ValueError):
            excel_bytes(
                {"title": "Test", "event_date": "2026-09-15"},
                [{"email": "a", "name": "A", "degree": 2}],
                [],
                [],
            )
