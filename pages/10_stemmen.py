import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from collections import defaultdict

# --- Data ophalen uit Supabase ---
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

df = pd.DataFrame(response.json()).drop_duplicates(subset=["name", "domain", "score", "text"])
df = df[df["session"] == st.session_state.access_code]

# --- Stemgegevens ophalen ---
vote_response = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/effect_votes?select=*",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)

vote_data = pd.DataFrame(vote_response.json()) if vote_response.status_code == 200 else pd.DataFrame(columns=["group_id", "votes"])

# --- Groeperen van gelijke effecten ---
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
effect_groups = []

for idx, group in enumerate(grouped_indices):
    texts = df.loc[group, "text"].tolist()
    domain = df.loc[group[0], "domain"]
    group_id = f"{st.session_state.access_code}_{idx}"
    total_votes = vote_data[vote_data["group_id"] == group_id]["votes"].sum() if not vote_data.empty else 0

    effect_groups.append({
        "domain": domain,
        "text": " / ".join(texts),
        "group_id": group_id,
        "votes": int(total_votes)
    })

# --- Stemmen bijhouden in sessie ---
if "upvotes_used" not in st.session_state:
    st.session_state.upvotes_used = 0
if "downvotes_used" not in st.session_state:
    st.session_state.downvotes_used = 0

MAX_UPVOTES = 10
MAX_DOWNVOTES = 5

st.subheader("🗳️ Stem op effecten!")
st.markdown(f"Stemmen gebruikt: ➕ {st.session_state.upvotes_used} / {MAX_UPVOTES}  |  ➖ {st.session_state.downvotes_used} / {MAX_DOWNVOTES}")

# --- UI voor stemmen ---
unique_domains = sorted(set(e["domain"] for e in effect_groups))
rows = [unique_domains[:4], unique_domains[4:]]

for row_domains in rows:
    cols = st.columns(4)
    for col, domain in zip(cols, row_domains):
        with col:
            st.markdown(f"### {domain}")
            for effect in [e for e in effect_groups if e["domain"] == domain]:
                with st.container():
                    st.markdown(f"**{effect['text']}** ({effect['votes']} stemmen)")
                    vote_cols = st.columns(2)
                    
                    with vote_cols[0]:
                        if st.button("➕", key=f"plus_{effect['group_id']}"):
                            if st.session_state.upvotes_used < MAX_UPVOTES:
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
                                        "group_id": effect["group_id"],
                                        "votes": 1,
                                        "last_updated": datetime.utcnow().isoformat()
                                    }
                                )
                                st.session_state.upvotes_used += 1
                                st.rerun()
                            else:
                                st.warning("Je hebt het maximum aantal upvotes gebruikt.")

                    with vote_cols[1]:
                        if st.button("➖", key=f"minus_{effect['group_id']}"):
                            if st.session_state.downvotes_used < MAX_DOWNVOTES:
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
                                        "group_id": effect["group_id"],
                                        "votes": -1,
                                        "last_updated": datetime.utcnow().isoformat()
                                    }
                                )
                                st.session_state.downvotes_used += 1
                                st.rerun()
                            else:
                                st.warning("Je hebt het maximum aantal downvotes gebruikt.")
