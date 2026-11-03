"""Accès Supabase réservé au serveur Streamlit."""

from allocator import allocate, AllocationError


def all_rows(client, table, **filters):
    rows, start = [], 0
    while True:
        query = client.table(table).select("*")
        for key, value in filters.items():
            query = query.eq(key, value)
        order = "email" if table in ("ft2_people", "ft2_roster") else "id"
        page = query.order(order).range(start, start + 499).execute().data
        rows.extend(page)
        if len(page) < 500:
            return rows
        start += 500


def session_data(client, sid):
    return (
        client.table("ft2_sessions").select("*").eq("id", sid).single().execute().data
    )


def finalize_session(client, sid, actor, skip_degrees=()):
    """Répartir les degrés choisis ; finaliser seulement si aucun degré n'est exclu."""
    skip_degrees = set(skip_degrees)
    people = client.table("ft2_people").select("*").eq("email", actor).execute().data
    if len(people) != 1 or people[0]["degree"] != 4 or not people[0]["is_admin"]:
        raise PermissionError(
            "La génération de l'Excel est réservée à l'administrateur."
        )
    session = session_data(client, sid)
    if session["status"] == "finalized":
        return
    roster = all_rows(client, "ft2_roster", session_id=sid)
    activities = all_rows(client, "ft2_activities", session_id=sid)
    assignments = all_rows(client, "ft2_assignments", session_id=sid)
    if session_data(client, sid)["revision"] != session["revision"]:
        raise AllocationError(
            "Des inscriptions viennent de changer. Cliquez à nouveau sur Répartir les élèves."
        )
    roster = [pupil for pupil in roster if pupil["degree"] not in skip_degrees]
    activities = [a for a in activities if a["degree"] not in skip_degrees]
    activity_ids = {a["id"] for a in activities}
    assignments = [a for a in assignments if a["activity_id"] in activity_ids]
    plan = allocate(roster, activities, assignments)
    if skip_degrees:
        if plan:
            # One bulk insert is atomic and uses the existing assignment guards.
            client.table("ft2_assignments").insert([
                {
                    **assignment,
                    "session_id": sid,
                    "activity_name": "pending",
                    "period": 9,
                    "source": "automatic",
                    "created_by": actor.strip().lower(),
                }
                for assignment in plan
            ]).execute()
        return
    client.rpc(
        "ft2_finalize",
        {
            "p_actor": actor,
            "p_session": sid,
            "p_revision": session["revision"],
            "p_plan": plan,
        },
    ).execute()
