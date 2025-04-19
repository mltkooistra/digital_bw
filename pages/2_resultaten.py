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

    st.subheader("📊 Gemiddelde score over alle domeinen")
    st.metric("Totaal gemiddelde", f"{df['score'].mean():.2f}")

    st.subheader("📈 Gemiddelde score per domein")
    grouped = df.groupby("domain")["score"].mean().reset_index()

    for _, row in grouped.iterrows():
        st.write(f"**{row['domain']}**: {row['score']:.2f}")

    all_text = " ".join(df["text"])
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(all_text)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wordcloud, interpolation='bilinear')
    ax.axis("off")
    st.pyplot(fig)

    st.dataframe(df[["name", "text", "score", "timestamp"]])
else:
    st.info("Nog geen inzendingen.")

import plotly.graph_objects as go

# Group average score per domain
grouped = df.groupby("domain")["score"].mean().reset_index()

# Sort domains for consistent radar shape
grouped = grouped.sort_values("domain")

# Radar chart values
categories = grouped["domain"].tolist()
scores = grouped["score"].tolist()

# Radar chart must close the loop
categories += [categories[0]]
scores += [scores[0]]

# Create radar chart
fig = go.Figure(data=go.Scatterpolar(
    r=scores,
    theta=categories,
    fill='toself',
    name='Gemiddelde score'
))

fig.update_layout(
    polar=dict(
        radialaxis=dict(
            visible=True,
            range=[-2, 2]  # Adjust to match your score scale
        )
    ),
    showlegend=False,
    title="📊 Gemiddelde score per domein (Radar Chart)"
)

# Display in Streamlit
st.plotly_chart(fig)