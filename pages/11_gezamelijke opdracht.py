import streamlit as st
import pandas as pd
import requests


st.set_page_config(page_title="Verdiepende feedback", layout="wide")
st.title("Verdiepingsopdracht")

# --- Check gebruiker ---
if "name" not in st.session_state or "access_code" not in st.session_state:
    st.error("Naam of sessiecode ontbreekt. Ga terug naar de startpagina.")
    st.stop()

# Optional: redirect if no session state set
if "group_question_filler" not in st.session_state:
    st.error("Deze pagina is niet direct toegankelijk.")
    st.stop()

# If this user is not the one filling in the group questions
if st.session_state["group_question_filler"] == False:
    st.info("⏳ Wacht tot je groepslid de groepsvragen heeft ingevuld. ")
    st.stop()

# --- Group selection from session ---
selected_group = st.session_state.get("selected_group", "1")
group_name = f"Groep {selected_group}"
st.info(f"Je vult feedback in namens **{group_name}**.")

# --- Stemmen ophalen ---
r_votes = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/effect_votes?select=*",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)
df_votes = pd.DataFrame(r_votes.json()) if r_votes.status_code == 200 else pd.DataFrame()

# --- Filter op sessie ---
session_code = st.session_state.access_code
df_votes = df_votes[df_votes["session"] == session_code]

# --- Controle ---
if df_votes.empty or "text" not in df_votes.columns:
    st.warning("Geen stemgegevens met teksten beschikbaar voor deze sessie.")
    st.stop()

# --- Stemmen samenvoegen per unieke tekst ---
vote_sums = df_votes.groupby("text")["votes"].sum().reset_index()
vote_sums = vote_sums.sort_values("votes", ascending=False)

# --- Top & bottom N effecten ---
n = st.session_state.get("n_effects", 3)
top_pos = vote_sums.head(n)
top_neg = vote_sums.tail(n)

# --- Feedback UI ---
def feedback_ui(effect, idx, label):
    st.markdown(f"### {effect['text']}")
    st.text_input("1. Op welke groepen is het effect het grootst?", key=f"{label}_{idx}_q1")
    st.text_input("2. Op welke gebied(en) is het effect het grootst?", key=f"{label}_{idx}_q2")

    st.selectbox(
        "3. Hoe ver reikt het effect?",
        options=[
            "-- geen antwoord --",
            "de buurt",
            "wijk/dorp",
            "stad of gemeente",
            "provincie",
            "landelijk",
            "internationaal"
        ],
        index=0,
        key=f"{label}_{idx}_q_reikwijdte"
    )

    st.slider(
        "4. Wanneer verwacht je dat het effect zichtbaar wordt?",
        min_value=0,
        max_value=50,
        value=0,
        step=1,
        format="%d jaar",
        help="0 = meteen vanaf de start, 50 = pas over 50 jaar of later",
        key=f"{label}_{idx}_q_start_year"
    )
    st.text_input("5. Zijn er aanpassingen aan de interventie mogelijk of nodig?", key=f"{label}_{idx}_q3")
    st.markdown("---")

# --- Weergave Positief ---
st.header(f"Top {n} Positieve Effecten")
if top_pos.empty:
    st.info("Geen positieve effecten gevonden.")
else:
    for i, row in top_pos.iterrows():
        feedback_ui(row, i, "Pos")

# --- Weergave Negatief ---
st.header(f"Top {n} Negatieve Effecten")
if top_neg.empty:
    st.info("Geen negatieve effecten gevonden.")
else:
    for i, row in top_neg.iterrows():
        feedback_ui(row, i, "Neg")

# --- Versturen ---
if st.button("✅ Versturen"):
    for label, group in [("Pos", top_pos), ("Neg", top_neg)]:
        for idx, row in group.iterrows():
            requests.post(
                f"{st.secrets['supabase_url']}/rest/v1/group_results?on_conflict=group,text",
                headers={
                    "apikey": st.secrets["supabase_key"],
                    "Authorization": f"Bearer {st.secrets['supabase_key']}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation"
                },
                json={
                    "session": session_code,
                    "group": group_name,
                    "text": row["text"],
                    "feedback_group_impact": st.session_state.get(f"{label}_{idx}_q1", ""),
                    "feedback_place_impact": st.session_state.get(f"{label}_{idx}_q2", ""),
                    "feedback_distance": st.session_state.get(f"{label}_{idx}_q_reikwijdte", ""),
                    "feedback_improvements": st.session_state.get(f"{label}_{idx}_q3", ""),
                    "feedback_start": st.session_state.get(f"{label}_{idx}_q_start_year")
                }
            )
    st.success("Feedback opgeslagen.")
    st.session_state["group_answers_submitted"] = True
    st.switch_page("pages/12_rapport.py")  # Or navigate as needed

