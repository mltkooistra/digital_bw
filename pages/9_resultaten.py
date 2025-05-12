import streamlit as st
import pandas as pd
import requests
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from collections import defaultdict
import uuid

# --- Setup ---
if "submission_id" not in st.session_state:
    st.session_state.submission_id = str(uuid.uuid4())

# --- Page setup ---
st.set_page_config(page_title="Resultaten", layout="wide")
st.title("Resultaten van de sessie")

# --- Initialize required session variables ---
required_session_vars = ["name", "access_code", "info", "description", "prov"]
for var in required_session_vars:
    if var not in st.session_state:
        st.error(f"Sessiestatus '{var}' ontbreekt. Ga terug naar startpagina.")
        st.stop()

if "submission_id" not in st.session_state:
    st.session_state.submission_id = str(uuid.uuid4())




# --- Access check ---
if "name" not in st.session_state or not st.session_state.name.strip():
    st.warning("⚠️ Vul eerst een code en/of gebruikersnaam in op de startpagina.")
    st.stop()

# --- Check all domains ---
ordered_domains = {
    1: "Materiële welvaart", 2: "Gezondheid", 3: "Arbeid en vrije tijd",
    4: "Wonen", 5: "Sociaal", 6: "Veiligheid", 7: "Milieu", 8: "Welzijn"
}

missing = [
    f"{name}" for i, name in ordered_domains.items()
    if not st.session_state.get(f"submitted_{i}")
]

if missing:
    st.warning(
        "🔒 Je moet eerst alle domeinen invullen voordat je de resultaten kunt bekijken.\n\n"
        f"Nog niet ingevuld: {', '.join(missing)}"
    )
    st.stop()

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

# Compute signed score
df["signed_score"] = df["score"] * df["posneg"]

domains = [
    "Welzijn", "Materiële welvaart", "Gezondheid", "Arbeid en vrije tijd",
    "Wonen", "Sociaal", "Veiligheid", "Milieu"
]

# --- Filter data for user ---
user_df = df[df["name"] == st.session_state.name]

# --- General metrics ---
st.subheader(f"Gemiddelde score voor {st.session_state.description}")
st.metric("Totaal score", f"{df['signed_score'].mean():.2f}")
st.metric("Jouw score", f"{user_df['signed_score'].mean():.2f}" if not user_df.empty else "–")

# --- Spider (polar) charts ---
def make_polar_chart(values, title):
    colors = ["blue" if v >= 0 else "orange" for v in values]
    fig = go.Figure()
    fig.add_trace(go.Barpolar(
        r=[abs(v) for v in values],
        theta=domains,
        marker_color=colors,
        marker_line_color="black",
        marker_line_width=1.5,
        opacity=0.85
    ))
    fig.update_layout(
        title=title,
        polar=dict(
            radialaxis=dict(range=[0, max(5, max(abs(v) for v in values))], showticklabels=False),
            angularaxis=dict(direction='clockwise')
        ),
        showlegend=False
    )
    return fig

# Domain averages
user_grouped = user_df.groupby("domain")["signed_score"].mean().reindex(domains, fill_value=0)
group_grouped = df.groupby("domain")["signed_score"].mean().reindex(domains, fill_value=0)

col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(make_polar_chart(group_grouped, "Gemiddelde scores van alle deelnemers"))

with col2:
    st.plotly_chart(make_polar_chart(user_grouped, "Jouw scores"))

# --- Word cloud section ---
st.subheader("🔤 Word cloud")

domain_options = ["Alle"] + sorted(df["domain"].dropna().unique().tolist())
selected_domain = st.selectbox("Kies een domein voor de word cloud:", domain_options)

filtered_text_df = df if selected_domain == "Alle" else df[df["domain"] == selected_domain]

if not filtered_text_df.empty:
    all_text = " ".join(filtered_text_df["text"].astype(str))
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(all_text)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wordcloud, interpolation='bilinear')
    ax.axis("off")
    st.pyplot(fig)
else:
    st.info("Geen tekst beschikbaar voor dit domein.")


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

