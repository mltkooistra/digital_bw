import streamlit as st
import pandas as pd
import requests
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from collections import defaultdict
import uuid

# --- Fetch data from Supabase ---
response = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/submissions?select=*&order=timestamp.desc&limit=1000",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)

if response.status_code != 200 or not response.json():
    st.info("Nog geen inzendingen.")
    st.stop()

# ✅ Parse data into DataFrame
df = pd.DataFrame(response.json()).drop_duplicates(subset=["name", "domain", "score", "text"])

# ✅ Filter only this session's data
df = df[df["session"] == st.session_state.access_code]
# ---- effects voting------
from datetime import datetime

# Load existing votes from Supabase
vote_response = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/effect_votes?select=*",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)

if vote_response.status_code == 200:
    vote_data = pd.DataFrame(vote_response.json())
else:
    vote_data = pd.DataFrame(columns=["group_id", "votes"])

# Helper: group similar effects
def group_similar_effects(df, min_common_words=5):
    grouped = []
    used_indices = set()

    for i, row_i in df.iterrows():
        if i in used_indices:
            continue
        group = [i]
        words_i = set(str(row_i["text"]).lower().split())

        for j, row_j in df.iterrows():
            if j <= i or j in used_indices:
                continue
            if row_i["domain"] != row_j["domain"]:
                continue
            words_j = set(str(row_j["text"]).lower().split())
            common_words = words_i.intersection(words_j)
            if len(common_words) >= min_common_words:
                group.append(j)
                used_indices.add(j)

        grouped.append(group)
    return grouped

# Group and process effects
grouped_indices = group_similar_effects(df)
effect_groups = []

for idx, group in enumerate(grouped_indices):
    texts = df.loc[group, "text"].tolist()
    domain = df.loc[group[0], "domain"]
    combined_text = " / ".join(texts)
    group_id = f"{st.session_state.access_code}_{idx}"

    existing_votes = vote_data[vote_data["group_id"] == group_id]["votes"].sum() if not vote_data.empty else 0

    effect_groups.append({
        "domain": domain,
        "text": combined_text,
        "group_id": group_id,
        "votes": int(existing_votes)
    })

# Track votes per user in session
if "upvotes_used" not in st.session_state:
    st.session_state.upvotes_used = 0
if "downvotes_used" not in st.session_state:
    st.session_state.downvotes_used = 0

MAX_UPVOTES = 10
MAX_DOWNVOTES = 5

# Display vote UI
unique_domains = sorted(set(effect["domain"] for effect in effect_groups))
rows = [unique_domains[:4], unique_domains[4:]]

st.subheader("🗳️ Stem op effecten!")

st.markdown(f"uitgedeelde stemmen: \n\n ➕  {st.session_state.upvotes_used} / {MAX_UPVOTES} \n\n ➖  {st.session_state.downvotes_used} / {MAX_DOWNVOTES}" )

for row_domains in rows:
    cols = st.columns(4)
    for col, domain in zip(cols, row_domains):
        with col:
            st.markdown(f"### {domain}")
            domain_effects = [e for e in effect_groups if e["domain"] == domain]
            for effect in domain_effects:
                with st.container():
                    st.markdown(f"**{effect['text']}**")
                    vote_cols = st.columns([1, 1])
                    with vote_cols[0]:
                        if st.button("➕", key=f"plus_{effect['group_id']}"):
                            if st.session_state.upvotes_used < MAX_UPVOTES:
                                requests.post(
                                    f"{st.secrets['supabase_url']}/rest/v1/effect_votes",
                                    headers={
                                        "apikey": st.secrets["supabase_key"],
                                        "Authorization": f"Bearer {st.secrets['supabase_key']}",
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "session": st.session_state.access_code,
                                        "group_id": effect["group_id"],
                                        "votes": effect["votes"] + 1,
                                        "last_updated": datetime.utcnow().isoformat()
                                    }
                                )
                                st.session_state.upvotes_used += 1
                                st.rerun()
                            else:
                                st.warning("Je hebt het maximum aantal upvotes gebruikt (10).")

                    

                    with vote_cols[1]:
                        if st.button("➖", key=f"minus_{effect['group_id']}"):
                            if st.session_state.downvotes_used < MAX_DOWNVOTES:
                                requests.post(
                                    f"{st.secrets['supabase_url']}/rest/v1/effect_votes",
                                    headers={
                                        "apikey": st.secrets["supabase_key"],
                                        "Authorization": f"Bearer {st.secrets['supabase_key']}",
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "session": st.session_state.access_code,
                                        "group_id": effect["group_id"],
                                        "votes": effect["votes"] - 1,
                                        "last_updated": datetime.utcnow().isoformat()
                                    }
                                )
                                st.session_state.downvotes_used += 1
                                st.rerun()
                            else:
                                st.warning("Je hebt het maximum aantal downvotes gebruikt (5).")

