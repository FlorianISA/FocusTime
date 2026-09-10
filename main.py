"""Focus Time : inscriptions configurables et répartition à la génération Excel."""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from supabase import create_client

from allocator import AllocationError
from activity_import import activity_name, parse_activities
from exports import excel_bytes
from service import all_rows, finalize_session, session_data

ROOT = Path(__file__).parent
TZ = ZoneInfo("Europe/Brussels")
st.set_page_config(
    page_title="Focus Time",
    page_icon="📚",
    layout="wide" if st.user.get("is_logged_in", False) else "centered",
)
st.title("Focus Time")


@st.cache_resource
def database():
    return create_client(
        st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
    )


def error_message(exc):
    if isinstance(exc, (AllocationError, ValueError, PermissionError)):
        return str(exc)
    code = getattr(exc, "code", "")
    if code == "23505":
        return "Cet élève a déjà une activité à cette période, ou suit déjà cette même activité à l'autre période. Une activité en double dans le catalogue est aussi refusée."
    if code == "P0001":
        return getattr(exc, "message", "Opération refusée.")
    logging.error("Focus Time : %s (%s)", type(exc).__name__, code)
    return "L'opération a échoué. Actualisez la page et vérifiez la configuration si nécessaire."


def action(name, args):
    try:
        client.rpc(name, args).execute()
        st.session_state["notice"] = "Modification enregistrée."
        st.rerun()
    except Exception as exc:
        st.error(error_message(exc))


def pupil_label(address):
    pupil = roster_map[address]
    return "{} · D{} · {}".format(pupil["name"], pupil["degree"], address)


def activity_details(activity):
    return "{} · {} · {}".format(
        activity["name"], activity["professor"], activity["room"]
    )


def activity_label(aid):
    activity = activity_map[aid]
    remaining = (
        "sans limite"
        if activity["capacity"] is None
        else "{} place(s)".format(activity["capacity"] - counts[aid])
    )
    return "P{} · {} · {}".format(
        activity["period"], activity_details(activity), remaining
    )


if not st.user.get("is_logged_in", False):
    st.info("Connectez-vous avec votre compte Microsoft scolaire.")
    if st.button("Se connecter avec Microsoft", type="primary"):
        st.login("microsoft")
    st.stop()
email = (
    str(st.user.get("email") or st.user.get("preferred_username") or "").strip().lower()
)
if not email:
    st.error(
        "Le compte Microsoft ne fournit pas d'adresse permettant de vous identifier."
    )
    st.stop()
try:
    client = database()
    people = client.table("ft2_people").select("*").eq("email", email).execute().data
    if len(people) != 1:
        st.error(
            "Votre compte n'est pas autorisé. Contactez le responsable du Focus Time."
        )
        st.stop()
    person = people[0]
    teacher = person["degree"] == 4
    admin = teacher and person["is_admin"]
    sessions = all_rows(client, "ft2_sessions")
except Exception as exc:
    st.error(error_message(exc))
    st.stop()
st.sidebar.write(
    "Plateforme d'inscription aux activités du Focus Time"
)
st.sidebar.image(str(ROOT / "isa_icon.jpg"), width=200)
st.sidebar.write(person["name"])
st.sidebar.caption(
    "Administrateur" if admin else ("Professeur" if teacher else "Élève")
)
if st.sidebar.button("Se déconnecter"):
    st.logout()
if "notice" in st.session_state:
    st.toast(st.session_state.pop("notice"))

if admin:
    with st.expander("Créer une séance"):
        st.caption(
            "La séance démarre sans activité. Ajoutez ensuite les remédiations et dépassements pour chaque degré dans Gestion des activités."
        )
        with st.form("create_session"):
            title = st.text_input("Nom de la séance", "Focus Time")
            today = datetime.now(TZ).date()
            event = st.date_input(
                "Date des activités", today + timedelta(days=7), format="DD/MM/YYYY"
            )
            c1, c2 = st.columns(2)
            with c1:
                open_date = st.date_input(
                    "Ouverture des inscriptions", today, format="DD/MM/YYYY"
                )
                open_time = st.time_input(
                    "Heure d'ouverture", datetime.strptime("08:00", "%H:%M").time()
                )
            with c2:
                close_date = st.date_input(
                    "Fin des inscriptions",
                    today + timedelta(days=6),
                    format="DD/MM/YYYY",
                )
                close_time = st.time_input(
                    "Heure de fin", datetime.strptime("16:00", "%H:%M").time()
                )
            degrees = st.multiselect(
                "Degrés participants",
                [1, 2, 3],
                default=[2, 3],
                format_func=lambda d: f"D{d}",
                placeholder="Choisir les degrés participants",
            )
            allow_students = st.checkbox("Autoriser les élèves à s'inscrire eux-mêmes")
            allow_enrichment = st.checkbox(
                "Autoriser les inscriptions aux dépassements"
            )
            submitted = st.form_submit_button("Créer la séance", type="primary")
        if submitted:
            try:
                opens = datetime.combine(open_date, open_time, TZ)
                closes = datetime.combine(close_date, close_time, TZ)
                if (
                    not title.strip()
                    or not degrees
                    or opens >= closes
                    or closes.date() > event
                ):
                    raise ValueError(
                        "Vérifiez le nom, les degrés et les dates d'ouverture/fin des inscriptions."
                    )
                action(
                    "ft2_create_session",
                    {
                        "p_actor": email,
                        "p_title": title.strip(),
                        "p_date": event.isoformat(),
                        "p_opens": opens.isoformat(),
                        "p_closes": closes.isoformat(),
                        "p_degrees": degrees,
                        "p_allow_student_enrollment": allow_students,
                        "p_allow_enrichment_enrollment": allow_enrichment,
                    },
                )
            except Exception as exc:
                st.error(error_message(exc))

if not sessions:
    st.info("Aucune séance n'a encore été créée.")
    st.stop()
sessions.sort(key=lambda s: (s["event_date"], s["id"]), reverse=True)
session_labels = {
    s["id"]: "{} · {}".format(
        datetime.fromisoformat(s["event_date"]).strftime("%d/%m/%Y"), s["title"]
    )
    for s in sessions
}
selected = st.selectbox(
    "Séance",
    list(session_labels),
    format_func=session_labels.get,
    placeholder="Choisir une séance",
)
session = next(s for s in sessions if s["id"] == selected)
try:
    activities = all_rows(client, "ft2_activities", session_id=selected)
    filters = {} if teacher else {"email": email}
    assignments = all_rows(client, "ft2_assignments", session_id=selected)
    counts = {
        a["id"]: sum(r["activity_id"] == a["id"] for r in assignments)
        for a in activities
    }
    if not teacher:
        assignments = [r for r in assignments if r["email"] == email]
    roster = all_rows(client, "ft2_roster", session_id=selected, **filters)
except Exception as exc:
    st.error(error_message(exc))
    st.stop()
activity_map = {a["id"]: a for a in activities}
roster_map = {r["email"]: r for r in roster}
opens = datetime.fromisoformat(session["opens_at"].replace("Z", "+00:00")).astimezone(
    TZ
)
closes = datetime.fromisoformat(session["closes_at"].replace("Z", "+00:00")).astimezone(
    TZ
)
can_enroll = session["status"] == "open" and opens <= datetime.now(TZ) < closes
st.caption(
    f"Inscriptions du {opens:%d/%m/%Y à %H:%M} au {closes:%d/%m/%Y à %H:%M}"
)
if session["status"] == "finalized":
    st.success("La répartition est enregistrée et les groupes sont fixés.")
elif not can_enroll:
    st.info(
        "Les inscriptions sont fermées. La répartition attend la génération de l'Excel par l'administrateur."
    )

if not teacher:
    st.subheader("Mes activités")
    if not roster:
        st.info("Vous ne participez pas à cette séance.")
    for period in (9, 10):
        found = next((a for a in assignments if a["period"] == period), None)
        if found:
            st.success(
                "P{} · {}".format(
                    period, activity_details(activity_map[found["activity_id"]])
                )
            )
        elif roster:
            st.info(f"P{period} · Aucune activité pour l'instant.")
    if roster and session.get("allow_student_enrollment", False):
        st.subheader("M'inscrire à une activité")
        st.caption(
            "Vous pouvez annuler vos propres inscriptions. Les inscriptions faites par un professeur ne sont pas annulables."
        )
        for row in assignments:
            if row["source"] == "student" and row["created_by"] == email:
                if st.button(
                    "Annuler mon inscription en P{}".format(row["period"]),
                    key="cancel_{}".format(row["id"]),
                    disabled=not can_enroll,
                ):
                    action("ft2_cancel", {"p_actor": email, "p_assignment": row["id"]})
        occupied_periods = {r["period"] for r in assignments}
        chosen_names = {
            activity_name(activity_map[r["activity_id"]]["name"]) for r in assignments
        }
        compatible = [
            a
            for a in activities
            if a["degree"] == roster_map[email]["degree"]
            and (
                a["kind"] == "remediation"
                or session.get("allow_enrichment_enrollment", False)
            )
            and a["period"] not in occupied_periods
            and activity_name(a["name"]) not in chosen_names
            and (a["capacity"] is None or counts[a["id"]] < a["capacity"])
        ]
        if compatible:
            chosen = st.selectbox(
                "Activité",
                [a["id"] for a in compatible],
                format_func=activity_label,
                placeholder="Choisir une activité",
            )
            if st.button("M'inscrire", type="primary", disabled=not can_enroll):
                action(
                    "ft2_enroll",
                    {
                        "p_actor": email,
                        "p_session": selected,
                        "p_email": email,
                        "p_activity": chosen,
                    },
                )
        else:
            st.info("Aucune activité compatible disponible à une période libre.")
    st.stop()

if admin:
    with st.expander("Supprimer la séance"):
        st.warning(
            "Cette action supprime définitivement la séance sélectionnée, ses activités et toutes ses inscriptions."
        )
        if st.button(
            "Supprimer définitivement cette séance",
            key=f"delete_session_{selected}",
        ):
            try:
                client.rpc(
                    "ft2_delete_session", {"p_actor": email, "p_session": selected}
                ).execute()
                st.session_state.pop("excel_{}_{}".format(email, selected), None)
                st.session_state["notice"] = "Séance supprimée."
                st.rerun()
            except Exception as exc:
                st.error(error_message(exc))

if admin:
    with st.expander("Gestion des activités", expanded=not activities):
        if session["status"] == "finalized":
            st.info(
                "Les activités d'une séance finalisée ne peuvent plus être ajoutées ou supprimées."
            )
        else:
            with st.form("add_activity"):
                group_degree = st.selectbox(
                    "Degré de l'activité",
                    sorted({r["degree"] for r in roster}),
                    format_func=lambda d: f"D{d}",
                    placeholder="Choisir un degré",
                )
                kind = st.selectbox(
                    "Type d'activité",
                    ["remediation", "depassement"],
                    format_func=lambda k: (
                        "Remédiation" if k == "remediation" else "Dépassement"
                    ),
                    placeholder="Choisir un type d'activité",
                )
                name = st.text_input("Nom de l'activité")
                professor = st.text_input("Professeur")
                room = st.text_input("Local")
                unlimited = st.checkbox("Sans limite de places")
                capacity = st.number_input(
                    "Nombre maximum de places",
                    min_value=1,
                    max_value=2147483647,
                    value=12,
                    step=1,
                )
                st.caption(
                    "Si Sans limite de places est coché, le nombre maximum est ignoré."
                )
                group_periods = st.multiselect(
                    "Périodes proposées",
                    [9, 10],
                    default=[9, 10],
                    format_func=lambda p: f"P{p}",
                    placeholder="Choisir les périodes",
                )
                submitted = st.form_submit_button("Ajouter l'activité", type="primary")
            if submitted:
                if not group_periods or not all(
                    v.strip() for v in (name, professor, room)
                ):
                    st.error(
                        "Renseignez le nom, le professeur, le local et au moins une période."
                    )
                else:
                    action(
                        "ft2_add_activity",
                        {
                            "p_actor": email,
                            "p_session": selected,
                            "p_name": name,
                            "p_professor": professor,
                            "p_room": room,
                            "p_kind": kind,
                            "p_periods": group_periods,
                            "p_degree": group_degree,
                            "p_capacity": None if unlimited else int(capacity),
                        },
                    )
            with st.expander("Importer plusieurs activités depuis un CSV"):
                upload = st.file_uploader(
                    "Fichier d'activités", type=["csv"], key="activities_upload"
                )
                if upload is not None:
                    try:
                        imported = parse_activities(
                            upload.getvalue(), {r["degree"] for r in roster}
                        )
                        existing = {
                            (a["degree"], a["period"], activity_name(a["name"]))
                            for a in activities
                        }
                        if any(
                            (a["degree"], a["period"], activity_name(a["name"]))
                            in existing
                            for a in imported
                        ):
                            raise ValueError(
                                "Un nom existe déjà pour le même degré et la même période. Retirez ce doublon du fichier avant l'import."
                            )
                        st.dataframe(
                            imported,
                            hide_index=True,
                            width="stretch",
                            column_config={
                                "name": "Nom",
                                "professor": "Professeur",
                                "room": "Local",
                                "degree": "Degré",
                                "period": "Période",
                                "kind": "Type",
                                "capacity": "Places (vide = illimité)",
                            },
                        )
                        if st.button("Importer les activités", type="primary"):
                            action(
                                "ft2_import_activities",
                                {
                                    "p_actor": email,
                                    "p_session": selected,
                                    "p_activities": imported,
                                },
                            )
                    except ValueError as exc:
                        st.error(str(exc))
            if not activities:
                st.info(
                    "Aucune activité. Ajoutez vos remédiations et dépassements pour chaque degré, ou importez un fichier CSV."
                )
            else:
                st.caption(
                    "La suppression retire un groupe d'une période. Si des élèves y sont inscrits, annulez d'abord leurs inscriptions."
                )
                labels = {
                    a["id"]: "D{} · P{} · {} ({})".format(
                        a["degree"],
                        a["period"],
                        a["name"],
                        "remédiation" if a["kind"] == "remediation" else "dépassement",
                    )
                    for a in activities
                }
                deletion = st.selectbox(
                    "Activité à supprimer",
                    list(labels),
                    format_func=labels.get,
                    index=None,
                    placeholder="Choisir une activité à supprimer",
                )
                assigned = deletion is not None and any(
                    a["activity_id"] == deletion for a in assignments
                )
                if assigned:
                    st.warning(
                        "Ce groupe contient des élèves : sa suppression est bloquée."
                    )
                if st.button(
                    "Supprimer cette activité", disabled=deletion is None or assigned
                ):
                    action(
                        "ft2_delete_activity",
                        {"p_actor": email, "p_activity": deletion},
                    )

counts = {
    a["id"]: sum(r["activity_id"] == a["id"] for r in assignments) for a in activities
}
occupied = {(r["email"], r["period"]) for r in assignments}
used = {
    (r["email"], activity_name(activity_map[r["activity_id"]]["name"]))
    for r in assignments
}
missing = [
    {"Élève": r["name"], "Degré": r["degree"], "Période": p}
    for r in roster
    for p in (9, 10)
    if (r["email"], p) not in occupied
]
c1, c2, c3 = st.columns(3)
c1.metric("Élèves concernés", len(roster))
c2.metric(
    "Inscriptions en remédiation",
    sum(activity_map[a["activity_id"]]["kind"] == "remediation" for a in assignments),
)
c3.metric("Périodes à attribuer", len(missing))
tabs = st.tabs(
    ["Inscrire un élève", "Groupes par degré"]
    + (["Répartition et Excel"] if admin else [])
)
tab_enroll, tab_groups = tabs[:2]
with tab_enroll:
    if not can_enroll:
        st.info("Inscription et annulation disponibles pendant la période d'ouverture.")
    degree_filter = st.selectbox(
        "Degré de l'élève",
        [1, 2, 3],
        index=1,
        format_func=lambda d: f"D{d}",
        placeholder="Choisir un degré",
    )
    candidates = sorted(
        [r for r in roster if r["degree"] == degree_filter],
        key=lambda r: r["name"].casefold(),
    )
    pupil = st.selectbox(
        "Élève",
        [r["email"] for r in candidates],
        index=None,
        format_func=pupil_label,
        placeholder="Choisir un élève",
    )
    if pupil:
        for row in [a for a in assignments if a["email"] == pupil]:
            st.write(
                "P{} · {}".format(
                    row["period"], activity_details(activity_map[row["activity_id"]])
                )
            )
            if row["source"] in ("teacher", "student") and st.button(
                "Annuler cette inscription",
                key="cancel_{}".format(row["id"]),
                disabled=not can_enroll,
            ):
                action("ft2_cancel", {"p_actor": email, "p_assignment": row["id"]})
        compatible = [
            a
            for a in activities
            if (
                a["kind"] == "remediation"
                or session.get("allow_enrichment_enrollment", False)
            )
            and a["degree"] == roster_map[pupil]["degree"]
            and (a["capacity"] is None or counts[a["id"]] < a["capacity"])
            and (pupil, a["period"]) not in occupied
            and (pupil, activity_name(a["name"])) not in used
        ]
        if not compatible:
            st.info(
                "Aucune activité autorisée disponible pour ce degré, différente de celle déjà choisie et à une période libre."
            )
        else:
            chosen = st.selectbox(
                "Activité",
                [a["id"] for a in compatible],
                format_func=activity_label,
                placeholder="Choisir une activité",
            )
            if st.button("Inscrire cet élève", type="primary", disabled=not can_enroll):
                action(
                    "ft2_enroll",
                    {
                        "p_actor": email,
                        "p_session": selected,
                        "p_email": pupil,
                        "p_activity": chosen,
                    },
                )
with tab_groups:
    view_degree = st.radio(
        "Degré",
        [1, 2, 3],
        horizontal=True,
        format_func=lambda d: f"D{d}",
    )
    for kind, label in (
        ("remediation", "Remédiations"),
        ("depassement", "Dépassements"),
    ):
        st.subheader(label)
        for period in (9, 10):
            if period == 10:
                st.markdown("")
            groups = sorted(
                [
                    a
                    for a in activities
                    if a["degree"] == view_degree
                    and a["kind"] == kind
                    and a["period"] == period
                ],
                key=lambda a: (a["period"], a["name"].casefold()),
            )
            if not groups:
                st.caption("Aucune activité pour ce degré à cette période.")
            for group in groups:
                members = [a for a in assignments if a["activity_id"] == group["id"]]
                capacity = (
                    "sans limite"
                    if group["capacity"] is None
                    else str(group["capacity"])
                )
                with st.expander(
                    "P{} · {} · {} / {}".format(
                        group["period"], activity_details(group), len(members), capacity
                    )
                ):
                    rows = [{"Élève": roster_map[a["email"]]["name"]} for a in members]
                    if rows:
                        st.dataframe(
                            sorted(rows, key=lambda r: r["Élève"].casefold()),
                            hide_index=True,
                            width="stretch",
                        )
                    else:
                        st.caption("Aucun élève inscrit.")

if admin:
    with tabs[2]:
        st.caption(
            "Deux activités différents par élève. Les dépassements à capacité limitée sont remplis en priorité, puis les dépassements sans limite."
        )
        if missing:
            st.dataframe(missing, hide_index=True, width="stretch")
        else:
            st.success("Toutes les périodes sont attribuées.")
        if session["status"] == "open":
            st.info(
                "Répartir les élèves attribue les périodes libres et ferme définitivement les inscriptions de cette séance, même avant la date de fin prévue."
            )
        if st.button("Répartir les élèves", type="primary"):
            try:
                with st.spinner("Préparation des groupes et du fichier Excel…"):
                    finalize_session(client, selected, email)
                    current = session_data(client, selected)
                    final_roster = all_rows(client, "ft2_roster", session_id=selected)
                    final_activities = all_rows(
                        client, "ft2_activities", session_id=selected
                    )
                    final_assignments = all_rows(
                        client, "ft2_assignments", session_id=selected
                    )
                    data = excel_bytes(
                        current, final_roster, final_activities, final_assignments
                    )
                    st.session_state["excel_{}_{}".format(email, selected)] = data
                    st.session_state["notice"] = (
                        "Répartition enregistrée. Le fichier Excel est prêt à télécharger dans l'onglet Répartition et Excel."
                    )
                st.rerun()
            except Exception as exc:
                st.error(error_message(exc))
        export_key = "excel_{}_{}".format(email, selected)
        if session["status"] == "finalized" and export_key in st.session_state:
            st.download_button(
                "Télécharger l'Excel",
                data=st.session_state[export_key],
                file_name="FocusTime_{}.xlsx".format(session["event_date"]),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                on_click="ignore",
            )
