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


# Load effect votes from Supabase
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

# Make sure vote_data is not empty
if vote_data.empty:
    st.warning("Geen stemgegevens gevonden.")
    st.stop()

# Group and summarize
effects = []
grouped = vote_data.groupby("group_id")

for idx, (group_id, group_df) in enumerate(grouped):
    # Get corresponding rows in your main dataset (df)
    try:
        texts = df[df["group_id"] == group_id]["text"].tolist()
        domain = df[df["group_id"] == group_id]["domain"].iloc[0]
    except IndexError:
        continue  # skip if no matching group

    votes = group_df["votes"].sum()
    effects.append({
        "group_id": group_id,
        "text": " / ".join(texts),
        "domain": domain,
        "votes": votes
    })

# Sort results
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
