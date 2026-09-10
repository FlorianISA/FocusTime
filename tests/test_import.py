import csv
import io
from pathlib import Path
import unittest
from activity_import import parse_activities


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "degree": "D2",
                "name": "Math",
                "professor": "Prof",
                "room": "A",
                "kind": "remediation",
                "periods": "9|10",
                "capacity": "",
                "unlimited": "false",
            }
        ]

    def content(self, delimiter=";"):
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(self.rows[0]), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(self.rows)
        return out.getvalue()

    def parse(self):
        return parse_activities(self.content(), {1, 2, 3})

    def test_default_capacity_and_fields(self):
        result = self.parse()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["capacity"], 12)
        self.assertEqual(result[0]["professor"], "Prof")

    def test_unlimited_for_any_activity(self):
        self.rows[0]["unlimited"] = "true"
        self.assertIsNone(self.parse()[0]["capacity"])

    def test_duplicate_normalized_name(self):
        self.rows.append({**self.rows[0], "name": " MATH "})
        with self.assertRaises(ValueError):
            self.parse()

    def test_invalid_capacity(self):
        for value in ("0", "-1", "true", "1.5"):
            self.rows[0]["capacity"] = value
            with self.assertRaises(ValueError):
                self.parse()

    def test_professor_room_required(self):
        for field in ("professor", "room"):
            self.rows[0][field] = ""
            with self.assertRaises(ValueError):
                self.parse()
            self.rows[0][field] = "Exemple"

    def test_wrong_degree(self):
        with self.assertRaises(ValueError):
            parse_activities(self.content(), {1, 3})

    def test_period_910_rejected(self):
        self.rows[0]["periods"] = "910"
        with self.assertRaises(ValueError):
            self.parse()

    def test_example(self):
        example = Path(__file__).parents[1] / "activities.example.csv"
        result = parse_activities(example.read_bytes(), {1, 2, 3})
        self.assertEqual(len(result), 18)
        self.assertEqual({r["degree"] for r in result}, {1, 2, 3})

    def test_csv_comma_bom_and_quoted_semicolon(self):
        self.rows[0]["name"] = "Math; approfondissement"
        result = parse_activities("\ufeff" + self.content(), {2})
        self.assertEqual(result[0]["name"], "Math; approfondissement")
        self.assertEqual(len(parse_activities(self.content(","), {2})), 2)

    def test_invalid_header_and_encoding(self):
        for content in (b"\xff", "{}", "", "degree;name\nD2;Math"):
            with self.assertRaises(ValueError):
                parse_activities(content, {2})
