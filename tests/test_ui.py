"""Tests d'écran et de déclenchement sans aucune connexion réelle."""

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import streamlit as st
from streamlit.testing.v1 import AppTest

NOW = datetime.now(timezone.utc)
DATA = {
    "ft2_people": [
        {"email": "admin@test", "name": "Admin", "degree": 4, "is_admin": True},
        {"email": "prof@test", "name": "Prof", "degree": 4, "is_admin": False},
        {"email": "student@test", "name": "Élève", "degree": 2, "is_admin": False},
    ],
    "ft2_sessions": [
        {
            "id": 1,
            "title": "Test",
            "event_date": (NOW + timedelta(days=1)).date().isoformat(),
            "opens_at": (NOW - timedelta(days=2)).isoformat(),
            "closes_at": (NOW - timedelta(days=1)).isoformat(),
            "status": "open",
            "revision": 1,
        }
    ],
    "ft2_roster": [
        {"session_id": 1, "email": "student@test", "name": "Élève", "degree": 2}
    ],
    "ft2_activities": [
        {
            "id": 1,
            "session_id": 1,
            "name": "Math",
            "professor": "Prof Math",
            "room": "A",
            "period": 9,
            "kind": "remediation",
            "degree": 2,
            "capacity": 12,
        },
        {
            "id": 2,
            "session_id": 1,
            "name": "Étude",
            "professor": "Prof Étude",
            "room": "B",
            "period": 10,
            "kind": "depassement",
            "degree": 2,
            "capacity": None,
        },
    ],
    "ft2_assignments": [
        {
            "id": 1,
            "session_id": 1,
            "email": "student@test",
            "activity_id": 1,
            "period": 9,
            "created_by": "prof@test",
            "source": "teacher",
        }
    ],
}


class Query:
    def __init__(self, table, data):
        self.rows = list(data[table])
        self.one = False

    def select(self, *_):
        return self

    def eq(self, key, val):
        self.rows = [r for r in self.rows if r[key] == val]
        return self

    def order(self, *_):
        return self

    def range(self, start, end):
        self.rows = self.rows[start : end + 1]
        return self

    def single(self):
        self.one = True
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows[0] if self.one else self.rows)


class UiTests(unittest.TestCase):
    def render(
        self, info, generate=False, empty=False, students=False, enrichment=False,
        skip_degrees=(), regenerate=False, extra_degrees=False,
    ):
        st.cache_resource.clear()
        data = copy.deepcopy(DATA)
        data["ft2_sessions"][0]["allow_student_enrollment"] = students
        data["ft2_sessions"][0]["allow_enrichment_enrollment"] = enrichment
        if students:
            data["ft2_sessions"][0]["closes_at"] = (NOW + timedelta(days=1)).isoformat()
        if empty:
            data["ft2_activities"] = []
            data["ft2_assignments"] = []
        if extra_degrees:
            data["ft2_roster"].extend([
                dict(session_id=1, email=f"d{d}@test", name=f"Eleve Degre{d}", degree=d)
                for d in (1, 3)
            ])
            data["ft2_activities"].extend([
                dict(id=d * 10 + p, session_id=1, name="Choix A" if p == 9 else "Choix B", professor="Prof", room="A",
                     period=p, kind="depassement", degree=d, capacity=12)
                for d in (1, 3) for p in (9, 10)
            ])
        client = SimpleNamespace(table=lambda table: Query(table, data))

        def finalize(_client, sid, actor, skip_degrees=()):
            self.assertEqual(actor, "admin@test")
            if data["ft2_sessions"][0]["status"] == "finalized":
                return
            if not skip_degrees:
                data["ft2_sessions"][0]["status"] = "finalized"
            occupied = {(a["email"], a["period"]) for a in data["ft2_assignments"]}
            for pupil in data["ft2_roster"]:
                if pupil["degree"] in skip_degrees:
                    continue
                for period in (9, 10):
                    if (pupil["email"], period) in occupied:
                        continue
                    group = next(a for a in data["ft2_activities"]
                                 if a["degree"] == pupil["degree"] and a["period"] == period)
                    data["ft2_assignments"].append(dict(
                        id=len(data["ft2_assignments"]) + 1, session_id=1, email=pupil["email"],
                        activity_id=group["id"], period=period, created_by=actor, source="automatic",
                    ))

        with patch("streamlit.user_info._get_user_info", return_value=info), patch(
            "supabase.create_client", return_value=client
        ), patch("service.finalize_session", side_effect=finalize) as finalizer:
            at = AppTest.from_file(str(Path(__file__).parents[1] / "main.py"))
            at.secrets["SUPABASE_URL"] = "https://example.supabase.co"
            at.secrets["SUPABASE_SERVICE_ROLE_KEY"] = "fake-key"
            at.run(timeout=10)
            self.assertEqual(list(at.exception), [])
            finalizer.assert_not_called()
            if generate:
                for degree in skip_degrees:
                    next(
                        field for field in at.checkbox
                        if field.label == f"D{degree}"
                    ).check().run(timeout=10)
                label = "Générer l'Excel sans répartition" if len(skip_degrees) == 3 else "Répartir les élèves et générer l'Excel"
                next(b for b in at.button if b.label == label).click().run(timeout=10)
                self.assertEqual(list(at.exception), [])
                if len(skip_degrees) == 3:
                    finalizer.assert_not_called()
                    self.assertEqual(data["ft2_sessions"][0]["status"], "open")
                    self.assertEqual(data["ft2_assignments"], [] if empty else DATA["ft2_assignments"])
                else:
                    finalizer.assert_called_once_with(client, 1, "admin@test", skip_degrees=skip_degrees)
                    self.assertEqual(data["ft2_sessions"][0]["status"], "open" if skip_degrees else "finalized")
                self.assertIn("excel_admin@test_1", at.session_state)
                self.assertEqual(len(at.get("download_button")), 1)
                if regenerate:
                    next(b for b in at.button if b.label == label).click().run(timeout=10)
                    self.assertEqual(list(at.exception), [])
                    if len(skip_degrees) == 3:
                        finalizer.assert_not_called()
                        self.assertEqual(data["ft2_assignments"], [] if empty else DATA["ft2_assignments"])
                    self.assertEqual(len(at.get("download_button")), 1)
                if skip_degrees:
                    next(
                        field for field in at.checkbox
                        if field.label == f"D{skip_degrees[0]}"
                    ).uncheck().run(timeout=10)
                    self.assertEqual(len(at.get("download_button")), 0)
                    next(
                        field for field in at.checkbox
                        if field.label == f"D{skip_degrees[0]}"
                    ).check().run(timeout=10)
                    self.assertEqual(len(at.get("download_button")), 1)
            return at

    def test_logged_out(self):
        at = self.render({"is_logged_in": False})
        self.assertEqual([b.label for b in at.button], ["Se connecter avec Microsoft"])

    def test_student_read_only(self):
        at = self.render({"is_logged_in": True, "email": "student@test"})
        self.assertEqual([b.label for b in at.button], ["Se déconnecter"])

    def test_teacher_cannot_generate(self):
        at = self.render({"is_logged_in": True, "email": "prof@test"})
        self.assertNotIn("Répartir les élèves et générer l'Excel", [b.label for b in at.button])
        self.assertNotIn("Répartition et Excel", [tab.label for tab in at.tabs])
        self.assertNotIn("Actualiser", [b.label for b in at.button])

    def test_admin_render_does_not_allocate_even_after_deadline(self):
        at = self.render({"is_logged_in": True, "email": "admin@test"})
        self.assertIn("Répartir les élèves et générer l'Excel", [b.label for b in at.button])

    def test_admin_click_generates_excel(self):
        self.render({"is_logged_in": True, "email": "admin@test"}, generate=True)

    def test_admin_skip_unregistered_generates_and_regenerates_excel(self):
        from io import BytesIO
        from openpyxl import load_workbook
        at = self.render(
            {"is_logged_in": True, "email": "admin@test"},
            generate=True, skip_degrees=(1, 2, 3), regenerate=True,
        )
        option = next(
            field for field in at.checkbox
            if field.label == "D2"
        )
        self.assertTrue(option.value)
        self.assertFalse(option.disabled)
        wb = load_workbook(BytesIO(at.session_state["excel_admin@test_1"]))
        self.assertEqual(wb["D2"]["D19"].value, "Non inscrits")
        self.assertEqual(wb["D2"]["D20"].value, "Élève")
        self.assertIsNone(wb["D2"]["C20"].value)
        # A session with no activities can also export with this option.
        self.render(
            {"is_logged_in": True, "email": "admin@test"},
            generate=True, empty=True, skip_degrees=(1, 2, 3),
        )

    def test_admin_distributes_d1_d2_but_not_d3(self):
        from io import BytesIO
        from openpyxl import load_workbook
        at = self.render(
            {"is_logged_in": True, "email": "admin@test"}, generate=True,
            skip_degrees=(3,), extra_degrees=True, regenerate=True,
        )
        self.assertFalse(next(field for field in at.checkbox if field.label == "D1").value)
        self.assertFalse(next(field for field in at.checkbox if field.label == "D2").value)
        self.assertTrue(next(field for field in at.checkbox if field.label == "D3").value)
        wb = load_workbook(BytesIO(at.session_state["excel_admin@test_1"]))
        self.assertEqual(wb["D1"]["B2"].value, "Degre1 Eleve")
        self.assertEqual(wb["D1"]["C20"].value, "Degre1 Eleve")
        self.assertEqual(wb["D2"]["C20"].value, "Élève")
        for degree in (1, 2):
            self.assertNotIn("Non inscrits", [cell.value for cell in wb[f"D{degree}"][1]])
        self.assertEqual(wb["D3"]["D2"].value, "Degre3 Eleve")
        self.assertEqual(wb["D3"]["D20"].value, "Degre3 Eleve")
        self.assertIsNone(wb["D3"]["B2"].value)

    def test_unknown_denied(self):
        at = self.render({"is_logged_in": True, "email": "unknown@test"})
        self.assertTrue(any("pas autorisé" in e.value for e in at.error))

    def test_admin_can_manage_empty_session_without_json(self):
        at = self.render({"is_logged_in": True, "email": "admin@test"}, empty=True)
        self.assertIn("Ajouter l'activité", [b.label for b in at.button])
        self.assertEqual(len(at.text_area), 0)
        self.assertTrue(any("Aucune activité" in item.value for item in at.info))

    def test_teacher_cannot_manage_activities(self):
        at = self.render({"is_logged_in": True, "email": "prof@test"})
        self.assertNotIn("Ajouter l'activité", [b.label for b in at.button])
        self.assertNotIn("Supprimer cette activité", [b.label for b in at.button])

    def test_admin_fields_and_selections(self):
        at = self.render({"is_logged_in": True, "email": "admin@test"}, empty=True)
        self.assertIn("Professeur", [field.label for field in at.text_input])
        self.assertEqual(
            [field.label for field in at.checkbox],
            [
                "Autoriser les élèves à s’inscrire eux-mêmes".replace("’", "'"),
                "Autoriser les inscriptions aux dépassements",
                "Sans limite de places",
                "D1", "D2", "D3",
            ],
        )
        self.assertEqual(
            [field.label for field in at.multiselect],
            ["Degrés participants", "Périodes proposées"],
        )
        delete = next(
            b for b in at.button if b.label == "Supprimer définitivement cette séance"
        )
        self.assertFalse(delete.disabled)

    def test_teacher_cannot_delete_session(self):
        at = self.render({"is_logged_in": True, "email": "prof@test"})
        self.assertNotIn(
            "Supprimer définitivement cette séance", [b.label for b in at.button]
        )

    def test_student_can_choose_enrichment_when_both_options_enabled(self):
        at = self.render(
            {"is_logged_in": True, "email": "student@test"},
            students=True,
            enrichment=True,
        )
        self.assertIn("M'inscrire", [b.label for b in at.button])
        self.assertNotIn("Élève", [s.label for s in at.selectbox])
        self.assertNotIn("Annuler mon inscription en P9", [b.label for b in at.button])
        self.assertNotIn("Répartition et Excel", [t.label for t in at.tabs])

    def test_student_cannot_choose_enrichment_with_only_student_option(self):
        at = self.render({"is_logged_in": True, "email": "student@test"}, students=True)
        self.assertNotIn("M'inscrire", [b.label for b in at.button])
