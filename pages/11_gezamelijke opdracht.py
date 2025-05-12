import streamlit as st
import pandas as pd
import requests
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from collections import defaultdict
import uuid

import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Verdiepende feedback", layout="wide")
st.title("📋 Verdiepende feedback op top-effecten")

# Load effect votes
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

# Load effect text groups (reuse your group_similar_effects() function)
# Here you assume `df` is already available (if not, you'll need to reload submission data too)
from datetime import datetime

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

# Re-fetch submission data
submission_response = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/submissions?select=*&order=timestamp.desc&limit=1000",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)
if submission_response.status_code != 200:
    st.error("Fout bij laden van inzendingen.")
    st.stop()

df = pd.DataFrame(submission_response.json())
df = df[df["session"] == st.session_state.access_code]

# Group effects
grouped = group_similar_effects(df)
effects = []
for idx, group in enumerate(grouped):
    texts = df.loc[group, "text"].tolist()
    domain = df.loc[group[0], "domain"]
    group_id = f"{st.session_state.access_code}_{idx}"
    votes = vote_data[vote_data["group_id"] == group_id]["votes"].sum()
    effects.append({
        "group_id": group_id,
        "text": " / ".join(texts),
        "domain": domain,
        "votes": votes
    })

# Sort effects
sorted_effects = sorted(effects, key=lambda e: e["votes"], reverse=True)
top_positive = sorted_effects[:5]
top_negative = sorted(effects, key=lambda e: e["votes"])[:5]

# Display feedback form
def render_feedback_block(effect, idx, section):
    st.markdown(f"**{section} #{idx+1}: {effect['text']}**  _(stemmen: {effect['votes']})_")
    q1 = st.text_input(f"1. Waarom is dit effect belangrijk?", key=f"{section}_{idx}_q1")
    q2 = st.text_input(f"2. Wat zou versterkt of verminderd kunnen worden?", key=f"{section}_{idx}_q2")
    q3 = st.text_input(f"3. Wat zijn mogelijke oplossingen of ideeën?", key=f"{section}_{idx}_q3")
    st.markdown("---")

st.header("🔼 Top 5 Positieve Effecten")
for i, effect in enumerate(top_positive):
    render_feedback_block(effect, i, "pos")

st.header("🔽 Top 5 Negatieve Effecten")
for i, effect in enumerate(top_negative):
    render_feedback_block(effect, i, "neg")

if st.button("✅ Verstuur feedback"):
    # (Optional) Submit answers to Supabase or other backend
    st.success("Feedback opgeslagen. Bedankt voor je input!")
