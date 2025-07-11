import streamlit as st
import pandas as pd
import requests
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from collections import defaultdict
import uuid
from nltk.corpus import stopwords


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

