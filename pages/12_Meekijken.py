import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Verdiepende feedback", layout="wide")
st.title("Verdiepingsopdracht")

# --- Basischecks ---
if "name" not in st.session_state or "access_code" not in st.session_state:
    st.error("Naam of sessiecode ontbreekt. Ga terug naar de startpagina.")
    st.stop()

if "group_question_filler" not in st.session_state:
    st.error("Deze pagina is niet direct toegankelijk.")
    st.stop()

# --- Alleen-lezen modus bepalen ---
read_only = not bool(st.session_state["group_question_filler"])

# --- Groep tonen ---
selected_group = st.session_state.get("selected_group", "1")
group_name = f"Groep {selected_group}"
mode_badge = "👀 Alleen-lezen" if read_only else "✍️ Invullen"
st.info(f"Je bekijkt feedback namens **{group_name}** — {mode_badge}.")

# --- Stemmen ophalen ---
r_votes = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/effect_votes?select=*",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}",
    },
)
df_votes = pd.DataFrame(r_votes.json()) if r_votes.status_code == 200 else pd.DataFrame()

# --- Filter op sessie ---
session_code = st.session_state.access_code
if not df_votes.empty and "session" in df_votes.columns:
    df_votes = df_votes[df_votes["session"] == session_code]

# --- Controle ---
required_cols = {"text", "votes"}
if df_votes.empty or not required_cols.issubset(df_votes.columns):
    st.warning("Geen stemgegevens met teksten beschikbaar voor deze sessie.")
    st.stop()

# --- Stemmen samenvoegen per unieke tekst ---
vote_sums = (
    df_votes.groupby("text", as_index=False)["votes"]
    .sum()
    .sort_values("votes", ascending=False)
)

# --- Top & bottom N effecten ---
n = int(st.session_state.get("n_effects", 3))
top_pos = vote_sums.head(n)
top_neg = vote_sums.tail(n)

# --- UI helper ---
def feedback_ui(effect, idx, label):
    st.markdown(f"### {effect['text']}")
    st.text_input(
        "1. Op welke groepen is het effect het grootst?",
        key=f"{label}_{idx}_q1",
        value=st.session_state.get(f"{label}_{idx}_q1", ""),
        disabled=True,
    )
    st.text_input(
        "2. Op welke gebied(en) is het effect het grootst?",
        key=f"{label}_{idx}_q2",
        value=st.session_state.get(f"{label}_{idx}_q2", ""),
        disabled=True,
    )
    st.selectbox(
        "3. Hoe ver reikt het effect?",
        options=[
            "-- geen antwoord --",
            "de buurt",
            "wijk/dorp",
            "stad of gemeente",
            "provincie",
            "landelijk",
            "internationaal",
        ],
        index=0,
        key=f"{label}_{idx}_q_reikwijdte",
        disabled=True,
    )
    st.slider(
        "4. Wanneer verwacht je dat het effect zichtbaar wordt?",
        min_value=0,
        max_value=50,
        value=int(st.session_state.get(f"{label}_{idx}_q_start_year", 0)),
        step=1,
        format="%d jaar",
        help="0 = meteen vanaf de start, 50 = pas over 50 jaar of later",
        key=f"{label}_{idx}_q_start_year",
        disabled=True,
    )
    st.text_input(
        "5. Zijn er aanpassingen aan de interventie mogelijk of nodig?",
        key=f"{label}_{idx}_q3",
        value=st.session_state.get(f"{label}_{idx}_q3", ""),
        disabled=True,
    )
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

# =========================================================
#  ONDERKANT VAN DE PAGINA
# =========================================================
st.divider()

if not read_only:
    # --- Voor invuller ---
    if st.button("✅ Versturen"):
        for label, group in [("Pos", top_pos), ("Neg", top_neg)]:
            for idx, row in group.iterrows():
                requests.post(
                    f"{st.secrets['supabase_url']}/rest/v1/group_results?on_conflict=group,text",
                    headers={
                        "apikey": st.secrets["supabase_key"],
                        "Authorization": f"Bearer {st.secrets['supabase_key']}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation",
                    },
                    json={
                        "session": session_code,
                        "group": group_name,
                        "text": row["text"],
                        "feedback_group_impact": st.session_state.get(f"{label}_{idx}_q1", ""),
                        "feedback_place_impact": st.session_state.get(f"{label}_{idx}_q2", ""),
                        "feedback_distance": st.session_state.get(f"{label}_{idx}_q_reikwijdte", ""),
                        "feedback_improvements": st.session_state.get(f"{label}_{idx}_q3", ""),
                        "feedback_start": st.session_state.get(f"{label}_{idx}_q_start_year"),
                    },
                )
        st.success("Feedback opgeslagen.")
        st.session_state["group_answers_submitted"] = True
        st.switch_page("pages/13_rapport.py")

else:
    # --- Voor niet-invuller (alleen-lezen) ---
    st.caption("Je hebt alleen-lezen toegang tot deze pagina. Invullen en versturen zijn uitgeschakeld.")

    st.markdown("### ✅ Controle door groepslid")
    st.write("Wanneer je gecontroleerd hebt dat alles is ingevuld door je groepslid, kun je hieronder bevestigen.")
    if st.button("☑️ Alles is ingevuld door mijn groepslid"):
        st.session_state["group_feedback_checked"] = True
        st.success("Bevestigd: alles is ingevuld door je groepslid.")
        st.switch_page("pages/13_rapport.py")
