import streamlit as st
import requests
from supabase import create_client, Client
import pandas as pd

st.set_page_config(page_title="Brede Welvaart Werksessie", layout="centered")

# Load Supabase credentials from secrets
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]

# Fetch session metadata from Supabase
response = requests.get(
    f"{url}/rest/v1/session_meta?select=*&order=created_at.desc&limit=1000",
    headers={
        "apikey": key,
        "Authorization": f"Bearer {key}"
    }
)
# Handle errors or empty response
if response.status_code != 200 or not response.json():
    st.info("Geen actieve sessies of geen contact met de server")
    st.stop()

# Load response into DataFrame
sessies = pd.DataFrame(response.json())
sessie_codes = sessies["acces_code"].tolist()

# Session state check
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Authentication flow
if not st.session_state.authenticated:
    st.title("🔐 Toegang vereist")
    code_input = st.text_input("Voer toegangscode in", type="password")

    if code_input:
        if code_input in sessie_codes:
            sessie_info = sessies[sessies["acces_code"] == code_input].iloc[0]

            st.session_state.authenticated = True
            st.session_state.acces_code = code_input
            st.session_state.description = sessie_info["description"]
            st.session_state.info = sessie_info["info"]
            st.session_state.link = sessie_info["link"]



            st.success(f"Toegang verleend: {st.session_state.description}")
            st.rerun()
        else:
            st.error("Onbekende code")
            st.stop()



st.title("Welkom bij de Brede Welvaart Werksessie")

st.markdown(f"""
De interventie: {st.session_state.description}

{st.session_state.info}

{st.session_state.link}

""")

st.markdown("""
Kies hieronder een gebruikersnaam. 
""")
if "name" not in st.session_state:
    st.session_state.name = ""

# Ask for name once
if not st.session_state.name:
    name_input = st.text_input("Gebruikersnaam")
    if name_input:
        st.session_state.name = name_input
        st.success(f"Welkom, {name_input}!")
        st.rerun()
else:
    st.success(f"Je bent ingelogd als: **{st.session_state.name}**")
    if st.button("Klik om aan de slag te gaan"):
        st.switch_page("pages/1_Materiële welvaart.py")



