from io import BytesIO
import unittest
from openpyxl import load_workbook
from exports import excel_bytes


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
        self.assertEqual(ws["B1"].value, "Math\n(Prof Math - Local A)")
        self.assertEqual(ws["B2"].data_type, "s")
        self.assertEqual(ws["C19"].value, "Étude\n(Prof Étude - Local B)")
        self.assertEqual(ws["C20"].value, "=1+1")
        self.assertEqual(ws["A2"].value, "P9")
        self.assertEqual(ws["A20"].value, "P10")
        self.assertIn("A2:A13", list(map(str, ws.merged_cells.ranges)))
        self.assertEqual(ws["B2"].fill.fgColor.rgb, "00D9D9D9")
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
        self.assertEqual(wb["D1"]["B31"].value, "Élève 29")
        self.assertEqual(wb["D1"]["A38"].value, "P10")
        self.assertEqual(wb["D1"]["C67"].value, "Élève 29")

    def test_incomplete_excel_refused(self):
        with self.assertRaises(ValueError):
            excel_bytes(
                {"title": "Test", "event_date": "2026-09-15"},
                [{"email": "a", "name": "A", "degree": 2}],
                [],
                [],
            )
