#!pip install streamlit pandas wordcloud matplotlib requests

import streamlit as st
import pandas as pd
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import requests

# --------------------- Supabase config --------------------------------------------------------

url = "https://tnvthmgeafgvqhzbetjz.supabase.co"  # Your project URL
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRudnRobWdlYWZndnFoemJldGp6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ5NzU1NDUsImV4cCI6MjA2MDU1MTU0NX0.DE7K3Uzful-ilzK0uUd0mh9Ck5ggc8toeMqocnpT8uQ"

supabase_headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

# ------------------- Page Setup ----------------------------------------------------------------

st.set_page_config(page_title="bw sessie", layout="centered")
st.title("Werksessie brede welvaart")

# ------------------- Input ophalen -------------------------------------------------------------

with st.form("input_form"):
    name = st.text_input("Naam/functie/id")
    text = st.text_area("Effect")
    score = st.slider("Hoe positief is dit effect? (1 = negatief, 5 = positief)", 1, 5, 3)
    submitted = st.form_submit_button("Antwoord opslaan")

    if submitted:
        if text.strip() == "":
            st.warning("Vul een antwoord in.")
        else:
            payload = {
                "name": name if name else "Anonymous",
                "text": text,
                "score": score
            }

            response = requests.post(
                f"{url}/rest/v1/submissions",
                headers=supabase_headers,
                json=payload
            )

            if response.status_code == 201:
                st.success("Bedankt voor het invullen!")
            else:
                st.error("Er ging iets mis bij het opslaan 😕")
                st.write(response.status_code, response.text)

# ----------------- Data ophalen ----------------------------------------------------------------

# Fetch data (READ is okay to do via Supabase REST API)
r = requests.get(
    f"{url}/rest/v1/submissions?select=*&order=timestamp.desc&limit=1000",
    headers=supabase_headers
)

if r.status_code == 200 and r.json():
    df = pd.DataFrame(r.json())

    st.subheader("📊 Score Analysis")
    avg_score = df['score'].mean()
    st.metric("Gemiddelde score", f"{avg_score:.2f}")

    st.subheader("☁️ Word Cloud van effecten")
    all_text = " ".join(df["text"])
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(all_text)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wordcloud, interpolation='bilinear')
    ax.axis("off")
    st.pyplot(fig)

    st.subheader("📋 Alle antwoorden")
    st.dataframe(df[["name", "text", "score", "timestamp"]])
else:
    st.info("Nog geen inzendingen — wees de eerste om iets in te vullen!")
