import streamlit as st
import pandas as pd
import requests
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from collections import defaultdict
import uuid
from nltk.corpus import stopwords
#--- stopwords setup ---

import os
from pathlib import Path

import streamlit as st
import nltk

# Put NLTK data inside the project so it's always writable
NLTK_DIR = Path(__file__).resolve().parents[1] / ".nltk_data"
NLTK_DIR.mkdir(exist_ok=True)
if str(NLTK_DIR) not in nltk.data.path:
    nltk.data.path.insert(0, str(NLTK_DIR))

@st.cache_resource
def ensure_dutch_stopwords():
    # Make sure 'stopwords' corpus exists; download to our local folder if missing
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords", download_dir=str(NLK_DIR := NLTK_DIR))
        # Ensure the just-downloaded dir is on the search path
        if str(NLTK_DIR) not in nltk.data.path:
            nltk.data.path.insert(0, str(NLTK_DIR))

    from nltk.corpus import stopwords
    try:
        return set(stopwords.words("dutch"))
    except OSError:
        # Fallback (offline/no download): a minimal built-in set so the app keeps working
        return {
            "de","het","een","en","of","maar","want","dat","die","dit","er","je","jij",
            "u","we","wij","ze","zij","ik","hij","het","in","op","aan","met","voor",
            "van","naar","bij","als","dan","niet","geen","wel","ook","om","te","tot",
        }

dutch_stopwords = ensure_dutch_stopwords()


# --- Setup ---
if "submission_id" not in st.session_state:
    st.session_state.submission_id = str(uuid.uuid4())

# --- Page setup ---

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

# --- Check all domains (DB-based, survives refresh) ---

ordered_domains = {
    1: "Materiële welvaart", 2: "Gezondheid", 3: "Arbeid en vrije tijd",
    4: "Wonen", 5: "Sociaal", 6: "Veiligheid", 7: "Milieu", 8: "Welzijn"
}
required_domains = list(ordered_domains.values())

# If you want to require a *non-empty* text (not just a placeholder " "), set True:
REQUIRE_NON_EMPTY = False

# --- Fetch data from Supabase (robust) ---

import json

BASE_URL = st.secrets["supabase_url"].rstrip("/")
HEADERS = {
    "apikey": st.secrets["supabase_key"],
    "Authorization": f"Bearer {st.secrets['supabase_key']}",
    "Accept": "application/json",
}

def fetch_supabase_json(path: str, params: dict | None = None, *, timeout: int = 12):
    """GET {BASE_URL}{path} with standard headers; ensure JSON back or stop with a helpful error."""
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=timeout)
    except requests.RequestException as e:
        st.error(f"Kon geen verbinding maken met Supabase ({e.__class__.__name__}).")
        st.stop()

    if r.status_code != 200:
        # show a concise server message to help debugging
        msg = r.text.strip()
        if len(msg) > 500:
            msg = msg[:500] + "..."
        st.error(f"Supabase gaf {r.status_code} terug.\n\n{msg}")
        st.stop()

    # Must be JSON
    try:
        return r.json()
    except ValueError:
        # sometimes proxies or errors return HTML; surface a snippet
        snippet = r.text.strip()
        if len(snippet) > 500:
            snippet = snippet[:500] + "..."
        st.error("Onverwacht antwoord: geen geldige JSON van Supabase.\n\n"
                 f"Content-Type: {r.headers.get('Content-Type')}\n\n"
                 f"Body (eerste 500 chars):\n{snippet}")
        st.stop()

# Use params instead of hand-assembling the query string
data = fetch_supabase_json(
    "/rest/v1/submissions",
    params={
        "select": "*",
        "order": "timestamp.desc",
        "limit": 1000,
        # You already filter later, but you can pre-filter here too:
        # "session": f"eq.{st.session_state.access_code}",
    },
)

if not data:
    st.info("Nog geen inzendingen.")
    st.stop()

# ✅ Parse data into DataFrame
df = pd.DataFrame(data).drop_duplicates(subset=["name", "domain", "score", "text"])



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

dutch_stopwords = set(stopwords.words('dutch'))

domain_options = ["Alle"] + sorted(df["domain"].dropna().unique().tolist())
selected_domain = st.selectbox("Kies een domein voor de word cloud:", domain_options)

filtered_text_df = df if selected_domain == "Alle" else df[df["domain"] == selected_domain]


if not filtered_text_df.empty:
    all_text = " ".join(filtered_text_df["text"].astype(str))
    wordcloud = WordCloud(width=600, height=300, background_color='white', colormap='coolwarm', stopwords=dutch_stopwords).generate(all_text)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wordcloud, interpolation='bilinear')
    ax.axis("off")
    st.pyplot(fig)
else:
    st.info("Geen tekst beschikbaar voor dit domein.")

