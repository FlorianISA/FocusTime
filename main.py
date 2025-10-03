import streamlit as st
import json
from supabase import create_client, Client
from datetime import datetime, time

TIMEZONE = 2  # GMT+2

@st.cache_resource
def init_db_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]

    client = create_client(url, key)
    # user = client.auth.sign_in_with_password({"email": st.secrets["USER_EMAIL"], "password": st.secrets["USER_PASS"]})

    return client

def gen_form(title, period, place):
    with st.form(title + f"_p{period}"):
        st.write(title)

        col1, col2 = st.columns([3, 1])
        with col1:
            if place > 3:
                st.info(f"Il reste {place} places")
            elif place > 0:
                st.warning(f"Il reste plus que {place} places")
            else:
                st.error("Il n'y a plus de place")
        with col2:
            if place > 0:
                submitted = st.form_submit_button("Valider", width="stretch")
            else:
                submitted = st.form_submit_button("Valider", width="stretch", disabled=True)
        if submitted:
            data = {
                "email": student_email,
                "name": student_name,
                "choice": title,
                "period": period,
                "degree": student_degree
            }
            client.table("remediations").insert(data).execute()
            st.rerun()

def gen_registration(period: int):

    if period == 910:
        # P9 ET P10
        st.markdown(f"#### Remédiations P9 et P10")
        choice_list = remediations_p910_list
    else:
        st.markdown(f"#### Remédiations P{period}")
        choice_list = remediations_list

    for title, place in choice_list[f"D{student_degree}"].items():
        if title + f" P{period} D{student_degree}" in already_registered:
            place = max(place - already_registered[title + f" P{period} D{student_degree}"], 0)
        gen_form(title, period, place)
    if "D2_D3" in choice_list:
        for title, place in choice_list["D2_D3"].items():
            if title + f" P{period} D2" in already_registered:
                place = max(place - already_registered[title + f" P{period} D2"], 0)
            if title + f" P{period} D3" in already_registered:
                place = max(place - already_registered[title + f" P{period} D3"], 0)
            gen_form(title, period, place)

    st.divider()


st.set_page_config(page_title="Focus Time", page_icon="📚", initial_sidebar_state="expanded")
st.title("Focus Time")
st.sidebar.text("Plateforme d'inscription aux activités du Focus Time")
st.sidebar.image("isa_icon.jpg")

if not st.user.is_logged_in:
    st.warning("Connecte toi avant de continuer")
    if st.button("Connexion"):
        st.login("microsoft")
else:
    student_name = st.user.name
    student_email = st.user.email
    student_degree = 0  # 0 = not fetched yet
    registered_remediations = None
    registered_ateliers = None

    rem_p9 = False
    rem_p10 = False

    client = init_db_connection()
    response = client.table("students").select("degree").ilike("email", student_email).execute()
    if len(response.data) > 0:
        student_degree = int(response.data[0]["degree"])

    response = client.table("remediations").select("*").ilike("email", student_email).execute()
    if len(response.data) > 0:
        registered_remediations = response.data

    response = client.table("remediations").select("*").execute()
    already_registered = {}
    for data in response.data:
        key = data["choice"] + f" P{data['period']} D{data['degree']}"
        if key in already_registered:
            already_registered[key] += 1
        else:
            already_registered[key] = 1

    # region Sidebar
    st.sidebar.divider()
    st.sidebar.write(f"Bonjour, {student_name} ! (D{student_degree})")

    if st.sidebar.button("Déconnexion"):
        st.logout()
    # endregion

    with open("registration_open.json", "r", encoding="utf-8") as file:
        regis_open = json.load(file)
    target_date = datetime.strptime(regis_open["remediations"]["from"], "%d/%m/%Y").date()
    today = datetime.today().date()
    now = datetime.now()

    hour_min = regis_open["remediations"]["from_hour"].split("h")
    cutoff_time = time(int(hour_min[0]) + TIMEZONE, int(hour_min[1]))

    days_diff = (target_date - today).days

    if target_date != today or now.time() < cutoff_time:
        st.info("Aucune inscription pour le moment 😊")
    if 1 <= days_diff <= 3 or (target_date == today and now.time() < cutoff_time):
        st.info(f"Prochaine inscription le {regis_open['remediations']['from']} à {regis_open['remediations']['from_hour']}")
    st.divider()

    if registered_remediations is not None or registered_ateliers is not None:
        st.text(f"Pour le {regis_open['remediations']['for']} :")
        for choice in registered_remediations:
            if choice["period"] == 910:
                st.success(f"Tu es inscrit en {choice["choice"]} (P9 et P10)")
            else:
                st.success(f"Tu es inscrit en {choice["choice"]} (P{choice["period"]})")

            if choice["period"] == 9:
                rem_p9 = True
            elif choice["period"] == 10:
                rem_p10 = True
            elif choice["period"] == 910:
                rem_p9 = True
                rem_p10 = True
        st.divider()

    atelier = False
    remediation = False
    if target_date == now.date() and now.time() > cutoff_time:
        remediation = True

    if remediation:
        with open("remediations.json", "r", encoding="utf-8") as file:
            remediations_list = json.load(file)
        with open("remediations_p910.json", "r", encoding="utf-8") as file:
            remediations_p910_list = json.load(file)

        if student_degree >= 2:
            if not rem_p9:
                gen_registration(period=9)
            if not rem_p10:
                gen_registration(period=10)
            if not rem_p9 and not rem_p10:
                gen_registration(period=910)
        else:
            st.info("Pas de remédiation pour toi")
