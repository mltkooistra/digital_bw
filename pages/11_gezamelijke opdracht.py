import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Verdiepende feedback", layout="wide")
st.title("Verdiepingsopdracht")

# --- Ophalen van inzendingen uit Supabase ---
response = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/submissions?select=*",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)

if response.status_code != 200 or not response.json():
    st.error("Fout bij laden van inzendingen.")
    st.stop()

df = pd.DataFrame(response.json()).drop_duplicates(subset=["name", "domain", "score", "text"])

# Groep-ID opnieuw aanmaken zoals bij stemming
def group_similar_effects(df, min_common_words=5):
    grouped = []
    used_indices = set()

    for i, row_i in df.iterrows():
        if i in used_indices:
            continue
        group = [i]
        words_i = set(str(row_i["text"]).lower().split())

        for j, row_j in df.iterrows():
            if j <= i or j in used_indices or row_i["domain"] != row_j["domain"]:
                continue
            words_j = set(str(row_j["text"]).lower().split())
            if len(words_i.intersection(words_j)) >= min_common_words:
                group.append(j)
                used_indices.add(j)

        grouped.append(group)
    return grouped

grouped_indices = group_similar_effects(df)
df["group_id"] = None

for idx, group in enumerate(grouped_indices):
    group_id = f"{df.iloc[0]['session']}_{idx}" if 'session' in df.columns else f"group_{idx}"
    df.loc[group, "group_id"] = group_id

# --- Ophalen van stemmen uit Supabase ---
vote_response = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/effect_votes?select=*",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)

if vote_response.status_code != 200:
    st.error("Fout bij laden van stemgegevens.")
    st.stop()

vote_data = pd.DataFrame(vote_response.json())

if vote_data.empty:
    st.warning("Geen stemgegevens gevonden.")
    st.stop()

# --- Groeperen en samenvatten ---
effects = []
grouped = vote_data.groupby("group_id")

for group_id, group_df in grouped:
    matching_rows = df[df["group_id"] == group_id]
    if matching_rows.empty:
        continue

    texts = matching_rows["text"].tolist()
    domain = matching_rows["domain"].iloc[0]
    votes = group_df["votes"].sum()

    effects.append({
        "group_id": group_id,
        "text": " / ".join(texts),
        "domain": domain,
        "votes": votes
    })

# --- Top-5 per richting ---
# --- Top-N per richting ---
n_effects = st.session_state.get("n_effects", 3)
sorted_effects = sorted(effects, key=lambda e: e["votes"], reverse=True)
top_positive = sorted_effects[:n_effects]
top_negative = sorted(effects, key=lambda e: e["votes"])[:n_effects]

# --- UI voor feedback ---
def render_feedback_block(effect, idx, section):
    st.markdown(f"### {section.capitalize()} #{idx + 1}")
    st.write(f"_Stemmen: {effect['votes']}_")
    st.markdown(f"**Effecttekst:** {effect['text']}")
    
    st.text_input("1. Op welke groepen is het effect het grootst?", key=f"{section}_{idx}_q1")
    st.text_input("2. Op welke gebieden is het effect het grootst?", key=f"{section}_{idx}_q2")
    st.text_input("3. Zijn er aanpassingen aan de interventie mogelijk of nodig?", key=f"{section}_{idx}_q3")
    st.markdown("---")

st.header(f"Top {n_effects} Positieve Effecten")
for i, effect in enumerate(top_positive):
    render_feedback_block(effect, i, "pos")

st.header(f"Top {n_effects} Negatieve Effecten")
for i, effect in enumerate(top_negative):
    render_feedback_block(effect, i, "neg")

if st.button("✅ Versturenk"):
    # Hier kun je feedback opslaan naar Supabase als je dat wil uitbreiden
    st.success("Opgeslagen")
