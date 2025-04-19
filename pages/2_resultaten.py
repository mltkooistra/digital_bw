import streamlit as st
import pandas as pd
import requests
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import plotly.graph_objects as go




st.title("📊 Resultaten van de sessie")

if not st.session_state.get("has_submitted"):
    st.warning("🔒 Vul eerst je eigen antwoord in op de invoerpagina.")
    st.stop()

response = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/submissions?select=*&order=timestamp.desc&limit=1000",
    headers={
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }
)

if response.status_code == 200 and response.json():
    df = pd.DataFrame(response.json())
    df = df.drop_duplicates(subset=["name", "submission_id", "domain", "score", "text"])


    st.subheader("Gemiddelde score voor de interventie")
    st.metric("Totaal gemiddelde", f"{df['score'].mean():.2f}")

   

    if not df.empty and "domain" in df.columns:
        domain_options = ["Alle"] + sorted(df["domain"].dropna().unique().tolist())
        selected_domain = st.selectbox("🗂️ Kies een domein voor de word cloud:", domain_options)

        filtered_df = df if selected_domain == "Alle" else df[df["domain"] == selected_domain]

        if not filtered_df.empty:
            all_text = " ".join(filtered_df["text"].astype(str))
            wordcloud = WordCloud(width=800, height=400, background_color='white').generate(all_text)

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.imshow(wordcloud, interpolation='bilinear')
            ax.axis("off")
            st.pyplot(fig)
        else:
            st.info("Geen tekst beschikbaar voor dit domein.")
    else:
        st.info("Geen data beschikbaar om een word cloud te maken.")


else:
    st.info("Nog geen inzendingen.")

import plotly.graph_objects as go
#---------------------------------------spiderweb charts-----------
# Filtered DataFrame for current user
filtered_df = df[
    (df["session"] == st.session_state.access_code) &
    (df["name"] == st.session_state.name)
]

# Create layout with two columns
col1, col2 = st.columns(2)

# --- Column 1: All data ---
with col1:
    st.markdown("### 🌐 Alle deelnemers")

    all_grouped = df.groupby("domain")["score"].mean().reset_index().sort_values("domain")
    categories = all_grouped["domain"].tolist()
    scores = all_grouped["score"].tolist()

    categories += [categories[0]]
    scores += [scores[0]]

    fig_all = go.Figure(data=go.Scatterpolar(
        r=scores,
        theta=categories,
        fill='toself',
        name='Alle scores'
    ))

    fig_all.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[-2, 2])),
        showlegend=False,
        title="Groepsresultaten"
    )

    st.plotly_chart(fig_all)

# --- Column 2: Personal data ---
with col2:
    

    if filtered_df.empty:
        st.info("Nog geen eigen inzendingen.")
    else:
        user_grouped = filtered_df.groupby("domain")["score"].mean().reset_index().sort_values("domain")
        cat = user_grouped["domain"].tolist()
        val = user_grouped["score"].tolist()

        cat += [cat[0]]
        val += [val[0]]

        fig_user = go.Figure(data=go.Scatterpolar(
            r=val,
            theta=cat,
            fill='toself',
            name='Jij'
        ))

        fig_user.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[-2, 2])),
            showlegend=False,
            title="Jouw resultaten"
        )

        st.plotly_chart(fig_user)