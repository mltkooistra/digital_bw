import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import uuid
import difflib
import random

# --- Configuratie ---
MAX_UPVOTES = 10
MAX_DOWNVOTES = 5

# --- Sessiestatus initialiseren ---
for key in ["upvotes_used", "downvotes_used", "voted_ids"]:
    if key not in st.session_state:
        st.session_state[key] = 0 if "used" in key else set()

# --- Vereist: gebruiker moet ingelogd zijn met naam en toegangscode ---
required_session_vars = ["name", "access_code", "info", "description", "prov"]
for var in required_session_vars:
    if var not in st.session_state:
        st.error(f"Sessiestatus '{var}' ontbreekt. Ga terug naar startpagina.")
        st.stop()

if "submission_id" not in st.session_state:
    st.session_state.submission_id = str(uuid.uuid4())

# --- Supabase ophalen (cached) ---
@st.cache_data(ttl=15)
def fetch_submissions():
    url = f"{st.secrets['supabase_url']}/rest/v1/submissions?select=*&order=timestamp.desc&limit=1000"
    headers = {
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
    r = requests.get(url, headers=headers)
    if r.status_code != 200 or not r.json():
        return pd.DataFrame()
    return pd.DataFrame(r.json())

@st.cache_data(ttl=15)
def fetch_votes():
    url = f"{st.secrets['supabase_url']}/rest/v1/effect_votes?select=*"
    headers = {
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
    r = requests.get(url, headers=headers)
    return pd.DataFrame(r.json()) if r.status_code == 200 else pd.DataFrame(columns=["group_id", "votes"])

# --- Ophalen en filteren inzendingen ---
df = fetch_submissions()
df = df.drop_duplicates(subset=["name", "domain", "score", "text"])
df = df[df["session"] == st.session_state.access_code]

if df.empty:
    st.info("Nog geen inzendingen.")
    st.stop()

# --- Groepsselectie ---
n_groups = st.session_state.get("n_groups", 1)
if n_groups <= 1:
    selected_group = "1"
else:
    options = [str(i) for i in range(1, n_groups + 1)]
    selected_group = st.selectbox("Selecteer jouw groep:", options, key="groep_keuze")

# --- Filter submissions op gekozen groep ---
df["assigned_group"] = df.groupby("name", sort=False).ngroup() % n_groups + 1
df["assigned_group"] = df["assigned_group"].astype(str)
df = df[df["assigned_group"] == selected_group]

vote_data = fetch_votes()

# --- Groeperen van gelijke effecten ---
def group_similar_effects(df, similarity_threshold=0.6):
    grouped = []
    used_indices = set()

    for i, row_i in df.iterrows():
        if i in used_indices:
            continue
        group = [i]
        text_i = str(row_i["text"]).lower()

        for j, row_j in df.iterrows():
            if j <= i or j in used_indices:
                continue
            text_j = str(row_j["text"]).lower()
            similarity = difflib.SequenceMatcher(None, text_i, text_j).ratio()
            if similarity >= similarity_threshold:
                group.append(j)
                used_indices.add(j)

        grouped.append(group)
    return grouped

grouped_indices = group_similar_effects(df)
effect_groups = []

for idx, group in enumerate(grouped_indices):
    texts = df.loc[group, "text"].tolist()
    authors = df.loc[group, "name"].unique().tolist()
    group_id = f"{st.session_state.access_code}_{selected_group}_{idx}"
    total_votes = vote_data[vote_data["group_id"] == group_id]["votes"].sum() if not vote_data.empty else 0

    effect_groups.append({
        "text": " / ".join(texts),
        "group_id": group_id,
        "votes": int(total_votes),
        "authors": authors
    })

# --- Stemregistratie ---
def register_vote(group_id, value, text):
    requests.post(
        f"{st.secrets['supabase_url']}/rest/v1/effect_votes",
        headers={
            "apikey": st.secrets["supabase_key"],
            "Authorization": f"Bearer {st.secrets['supabase_key']}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        },
        json={
            "session": st.session_state.access_code,
            "group_id": group_id,
            "votes": value,
            "text": text,
            "last_updated": datetime.utcnow().isoformat()
        }
    )
    st.session_state.voted_ids.add(group_id)

def vote_buttons(effect):
    if st.session_state.name in effect.get("authors", []):
        st.info("Je kunt niet stemmen op je eigen effect.")
        return

    vote_cols = st.columns(2)

    with vote_cols[0]:
        if st.button("➕", key=f"plus_{effect['group_id']}"):
            if st.session_state.upvotes_used < MAX_UPVOTES:
                register_vote(effect["group_id"], +1, effect["text"])
                st.session_state.upvotes_used += 1
                st.rerun()
            else:
                st.warning("Max upvotes bereikt.")

    with vote_cols[1]:
        if st.button("➖", key=f"minus_{effect['group_id']}"):
            if st.session_state.downvotes_used < MAX_DOWNVOTES:
                register_vote(effect["group_id"], -1, effect["text"])
                st.session_state.downvotes_used += 1
                st.rerun()
            else:
                st.warning("Max downvotes bereikt.")

# --- UI ---
st.subheader("🗳️ Stem op effecten!")
st.markdown(f"Stemmen gebruikt: ➕ {st.session_state.upvotes_used} / {MAX_UPVOTES}  |  ➖ {st.session_state.downvotes_used} / {MAX_DOWNVOTES}")
st.markdown(f"Je stemt binnen **groep {selected_group}**.")

# Shuffle effects for random order and remove voted and own
effect_groups_shuffled = [
    e for e in effect_groups
    if e["group_id"] not in st.session_state.voted_ids
    and st.session_state.name not in e.get("authors", [])
]
random.shuffle(effect_groups_shuffled)

# Display in grid layout (3 per row)
cols = st.columns(3)
for idx, effect in enumerate(effect_groups_shuffled):
    with cols[idx % 3]:
        with st.container(border=True):
            st.markdown(f"**{effect['text']}**")
            vote_buttons(effect)

col1, col2 = st.columns(2)
with col1:
    if st.button("➡️ Klik hier om de groepsvragen invullen"):
        st.session_state["group_question_filler"] = True
        st.switch_page("pages/11_groepsopdracht.py")  # Adjust filename/path if needed

with col2:
    if st.button("📄 Klik hier als iemand anders de groepsvragen names je groep invult"):
        st.session_state["group_question_filler"] = False
        st.switch_page("pages/12_rapport.py")  # Adjust filename/path if needed