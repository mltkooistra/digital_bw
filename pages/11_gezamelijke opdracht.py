import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Verdiepende feedback", layout="wide")
st.title("Verdiepingsopdracht")

# --- Check gebruiker ---
if "name" not in st.session_state or "access_code" not in st.session_state:
    st.error("Naam of sessiecode ontbreekt. Ga terug naar de startpagina.")
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
        "Hoe ver reikt het effect?",
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

    st.text_input("3. Zijn er aanpassingen aan de interventie mogelijk of nodig?", key=f"{label}_{idx}_q3")
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
                    "feedback_improvements": st.session_state.get(f"{label}_{idx}_q3", "")
                }
            )
    st.success("Feedback opgeslagen.")

