import streamlit as st
import json
import httpx
from supabase import create_client, Client
from datetime import datetime

TIMEZONE = 1  # GMT+1
DEGREE_PROF = 4

ATELIER_MODE = False

# TODO Rename remediations to choice (because now it's remediations + ateliers)

@st.cache_resource
def init_db_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]

    client = create_client(url, key)
    # user = client.auth.sign_in_with_password({"email": st.secrets["USER_EMAIL"], "password": st.secrets["USER_PASS"]})

    return client


@st.dialog("Inscrire un élève", width="medium")
def select_student():

    try:
        response_email = client.table("students").select("*").execute()
    except httpx.ReadError:
        st.rerun()

    all_emails = []
    for email in response_email.data:
        all_emails.append(email["email"].lower())

    email = st.selectbox(
        "Adresse email de l'élève",
        all_emails,
        index=None,
        placeholder="Choisir un email"
    )

    if email is not None:
        for enroll in response_remed.data:
            if enroll["email"].lower() == email.lower():
                st.success(f"{enroll['name']} est déjà inscrit en {enroll['choice']} (P{enroll['period']})")

    with open("remediations.json", "r", encoding="utf-8") as file:
        remed = json.load(file)

    options_list = []
    for degree, remed_names in remed.items():
        for remed_name in remed_names.keys():
            options_list.append(f"{remed_name} ({degree})")

    option_p9 = st.selectbox(
        "Remédiation P9",
        options_list,
        index=None,
        placeholder="Choisir une remédiation"
    )

    if option_p9 is not None:
        option = " ".join(option_p9.split()[:-1]) + f" P9 D{option_p9.split()[-1][2]}"
        if option in already_registered:
            st.info(f"{already_registered[option]} élèves déjà inscrits en {option_p9} (P9)")

    option_p10 = st.selectbox(
        "Remédiation P10",
        options_list,
        index=None,
        placeholder="Choisir une remédiation"
    )

    if option_p10 is not None:
        option = " ".join(option_p10.split()[:-1]) + f" P10 D{option_p10.split()[-1][2]}"
        if option in already_registered:
            st.info(f"{already_registered[option]} élèves déjà inscrits en {option_p10} (P10)")

    st.divider()
    if st.button("Valider"):
        if email is not None:
            name = email.split("@")[0].split(".")
            if len(name) > 1:
                name = name[0].capitalize() + " " + name[1].capitalize()
            else:
                name = name[0].capitalize()
            if option_p9 is not None:
                data = {
                    "email": email,
                    "name": name,
                    "choice": " ".join(option_p9.split()[:-1]),
                    "period": 9,
                    "degree": int(option_p9.split()[-1][2])
                }
                client.table("remediations").insert(data).execute()
            if option_p10 is not None:
                data = {
                    "email": email,
                    "name": name,
                    "choice": " ".join(option_p10.split()[:-1]),
                    "period": 10,
                    "degree": int(option_p10.split()[-1][2])
                }
                client.table("remediations").insert(data).execute()
            if option_p9 is not None or option_p10 is not None:
                st.rerun()


def gen_form(title, period, place):
    with st.form(title + f"_p{period}"):
        st.write(title)

        col1, col2 = st.columns([3, 1])
        with col1:
            if place > 3:
                st.info(f"Il reste {place} places")
            elif place > 0:
                if place > 1:
                    st.warning(f"Il ne reste plus que {place} places")
                else:
                    st.warning(f"Il ne reste plus que {place} place")
            else:
                st.error("Il n'y a plus de place")
        with col2:
            if place > 0:
                submitted = st.form_submit_button("S'inscrire", width="stretch")
            else:
                submitted = st.form_submit_button("S'inscrire", width="stretch", disabled=True)
        if submitted:
            data = {
                "email": student_email,
                "name": student_name,
                "choice": title,
                "period": period,
                "degree": student_degree
            }
            if place > 0:
                client.table("remediations").insert(data).execute()
            st.rerun()

def gen_registration(period: int):

    if period == 910:
        # P9 ET P10
        if ATELIER_MODE:
            st.markdown(f"#### Ateliers")
        else:
            st.markdown(f"#### Remédiations P9 et P10")
        choice_list = remediations_p910_list
    else:
        if ATELIER_MODE:
            st.markdown(f"#### Ateliers P{period}")
        else:
            st.markdown(f"#### Remédiations P{period}")
        choice_list = remediations_list

    for title, place in choice_list[f"D{student_degree}"].items():
        if title + f" P{period} D{student_degree}" in already_registered:
            place = max(place - already_registered[title + f" P{period} D{student_degree}"], 0)
        gen_form(title, period, place)
    if "D2_D3" in choice_list and student_degree > 1:
        for title, place in choice_list["D2_D3"].items():
            if title + f" P{period} D2" in already_registered:
                place = max(place - already_registered[title + f" P{period} D2"], 0)
            if title + f" P{period} D3" in already_registered:
                place = max(place - already_registered[title + f" P{period} D3"], 0)
            gen_form(title, period, place)

    st.divider()


st.set_page_config(page_title="Focus Time", page_icon="📚", initial_sidebar_state="auto")
st.title("Focus Time")
st.sidebar.text("Plateforme d'inscription aux activités du Focus Time")
st.sidebar.image("isa_icon.jpg")

# if False:
if not st.user.is_logged_in:
    st.warning("Connecte toi avant de continuer")
    if st.button("Connexion"):
        st.login("microsoft")
else:
    student_name = st.user.name
    student_email = st.user.email
    # student_name = "Test1"
    # student_email = "test1@isa-florenville.be"
    student_degree = 0  # 0 = not fetched yet, 4 = Prof
    registered_remediations = []

    rem_p9 = False
    rem_p10 = False

    client = init_db_connection()
    try:
        response_degree = client.table("students").select("degree").ilike("email", student_email).execute()
    except httpx.ReadError:
        st.rerun()

    if len(response_degree.data) > 0:
        student_degree = int(response_degree.data[0]["degree"])

    try:
        response_remed = client.table("remediations").select("*").execute()
    except httpx.ReadError:
        st.rerun()

    already_registered = {}
    for data in response_remed.data:
        if data["email"].lower() == student_email.lower():
            registered_remediations.append(data)

        key = data["choice"] + f" P{data['period']} D{data['degree']}"
        if key in already_registered:
            already_registered[key] += 1
        else:
            already_registered[key] = 1

    # region Sidebar
    st.sidebar.divider()
    if student_degree == DEGREE_PROF:
        st.sidebar.write(f"Bonjour, {student_name} ! (Prof)")
    else:
        st.sidebar.write(f"Bonjour, {student_name} ! (D{student_degree})")

    if st.sidebar.button("Déconnexion"):
        st.logout()
    # endregion

    if student_degree == DEGREE_PROF:

        if st.button("Inscrire un élève", width="stretch", type="primary", disabled=ATELIER_MODE):
            select_student()
        if st.button("Voir les groupes", width="stretch"):
            if len(response_remed.data) > 0:
                with st.container(border=True):
                    table_data = {}
                    for data in response_remed.data:
                        if not data["choice"] in table_data:
                            table_data[data["choice"]] = []
                        table_data[data["choice"]].append({"name": data["name"],
                                                           "degree": data["degree"],
                                                           "period": data["period"]})

                    for key, value in table_data.items():
                        st.markdown(f"**{key}**")

                        st.dataframe(value, use_container_width=True, hide_index=True,
                                     column_order=["name", "degree", "period"],
                                     column_config={"name": "Prénom/Nom",
                                                    "degree": st.column_config.NumberColumn(
                                                        "Degré",
                                                        format="D%d",
                                                    ),
                                                    "period": st.column_config.NumberColumn(
                                                        "Période",
                                                        format="P%d",
                                                    )})
                        st.divider()
            else:
                st.info("Aucun groupe pour l'instant")
    else:
        with open("registration_open.json", "r", encoding="utf-8") as file:
            regis_open = json.load(file)

        target_time = datetime.strptime(regis_open["remediations"]["from"] + " " + regis_open["remediations"]["from_hour"],
                                        "%d/%m/%Y %Hh%M")
        target_time = target_time.replace(hour=target_time.hour - TIMEZONE)

        close_date = datetime.strptime(regis_open["remediations"]["for"],"%d/%m/%Y").date()

        today = datetime.today().date()
        now = datetime.now()
        days_diff = (target_time.date() - today).days

        remediation = False
        if now < target_time or today >= close_date:
            st.info("Aucune inscription pour le moment 😊")
            if 0 <= days_diff <= 3:
                st.info(f"Prochaine inscription le {regis_open['remediations']['from']} à {regis_open['remediations']['from_hour']}")
            st.divider()
        else:
            remediation = True

        if len(registered_remediations) > 0:
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

        if remediation:
            with open("remediations.json", "r", encoding="utf-8") as file:
                remediations_list = json.load(file)
            with open("remediations_p910.json", "r", encoding="utf-8") as file:
                remediations_p910_list = json.load(file)

            no_registration = True
            if student_degree >= 1:
                if len(remediations_list[f"D{student_degree}"]) > 0:
                    if not rem_p9:
                        gen_registration(period=9)
                    if not rem_p10:
                        gen_registration(period=10)
                    no_registration = False
                if len(remediations_p910_list[f"D{student_degree}"]) > 0:
                    if not rem_p9 and not rem_p10:
                        gen_registration(period=910)
                    no_registration = False

            if no_registration:
                st.info("Aucune inscription pour toi")
