import streamlit as st
import pandas as pd
import requests
from wordcloud import WordCloud
import matplotlib.pyplot as plt

st.title("📊 Resultaten van de sessie")

if not st.session_state.get("has_submitted"):
    st.warning("🔒 Vul eerst je eigen antwoord in op de invoerpagina.")
    st.stop()

response = requests.get(
    "https://your-project.supabase.co/rest/v1/submissions?select=*&order=timestamp.desc&limit=1000",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)

if response.status_code == 200 and response.json():
    df = pd.DataFrame(response.json())
    st.metric("Gemiddelde score", f"{df['score'].mean():.2f}")

    all_text = " ".join(df["text"])
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(all_text)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wordcloud, interpolation='bilinear')
    ax.axis("off")
    st.pyplot(fig)

    st.dataframe(df[["name", "text", "score", "timestamp"]])
else:
    st.info("Nog geen inzendingen.")
