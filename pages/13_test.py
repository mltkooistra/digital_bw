import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from io import BytesIO
from datetime import date
import statistics
import tempfile
import os

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- Pagina-instellingen ---
st.set_page_config(page_title="Genereer Rapport", layout="wide")
st.title("📄 Download groepsrapport")
st.text("Bedankt voor het meedoen aan de werksessie. In het document vind je een overzicht van de effecten op brede welvaart.")

# --- Sessieverificatie ---
if "access_code" not in st.session_state:
    st.error("Toegangscode ontbreekt.")
    st.stop()

if "group_answers_submitted" not in st.session_state or not st.session_state["group_answers_submitted"]:
    st.warning("De groepsantwoorden zijn nog niet ingediend. Ga terug en vul eerst de groepsvragen in.")
    st.stop()

# --- Gegevens ophalen ---
@st.cache_data(ttl=30)
def load_data():
    headers = {
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}"
    }

    r_sub = requests.get(f"{st.secrets['supabase_url']}/rest/v1/submissions?select=*", headers=headers)
    df_sub = pd.DataFrame(r_sub.json()) if r_sub.status_code == 200 else pd.DataFrame()

    r_group = requests.get(f"{st.secrets['supabase_url']}/rest/v1/group_results?select=*", headers=headers)
    df_group = pd.DataFrame(r_group.json()) if r_group.status_code == 200 else pd.DataFrame()

    return df_sub, df_group

df_sub, df_group = load_data()
df_sub = df_sub[df_sub["session"] == st.session_state.access_code]
df_group = df_group[df_group["session"] == st.session_state.access_code]

if df_sub.empty or df_group.empty:
    st.warning("Niet genoeg data om een rapport te maken.")
    st.stop()

n_participants = df_sub["name"].nunique()
n_groups = df_group["group"].nunique()

domains = [
    "Welzijn", "Materiële welvaart", "Gezondheid", "Arbeid en vrije tijd",
    "Wonen", "Sociaal", "Veiligheid", "Milieu"
]

df_sub["signed_score"] = df_sub["score"] * df_sub["posneg"]
grouped = df_sub.groupby("domain")["signed_score"].mean().reindex(domains, fill_value=0)

def create_spider_chart(data):
    fig = go.Figure()
    fig.add_trace(go.Barpolar(
        r=[abs(v) for v in data],
        theta=domains,
        marker_color=["blue" if v >= 0 else "orange" for v in data],
        opacity=0.85
    ))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True)), showlegend=False)
    return fig

def save_plotly_chart(fig):
    img = BytesIO()
    fig.write_image(img, format="png")
    img.seek(0)
    return img

def generate_wordcloud(text):
    wc = WordCloud(width=800, height=400, background_color="white").generate(text)
    buf = BytesIO()
    plt.figure(figsize=(10, 5))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

def format_stats(values):
    if not values:
        return "geen data"
    return f"min: {min(values)} jaar, max: {max(values)} jaar, gemiddeld: {round(statistics.mean(values), 1)} jaar"

# --- PDF Setup ---
pdf_buffer = BytesIO()
doc = SimpleDocTemplate(pdf_buffer, pagesize=A4,
                        rightMargin=2*cm, leftMargin=2*cm,
                        topMargin=2*cm, bottomMargin=2*cm)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Heading1Colored', parent=styles['Heading1'], textColor=colors.HexColor("#003366")))
styles.add(ParagraphStyle(name='NormalBlue', parent=styles['Normal'], textColor=colors.HexColor("#003366")))

story = []

story.append(Paragraph("Verslag werksessie", styles["Heading1Colored"]))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(f"<b>Datum:</b> {date.today().strftime('%d-%m-%Y')}", styles['NormalBlue']))
story.append(Paragraph(f"<b>Thema:</b> {st.session_state.get('description', '–')}", styles['NormalBlue']))
story.append(Paragraph(f"<b>Informatie:</b> {st.session_state.get('info', '–')}", styles['NormalBlue']))
story.append(Paragraph(f"<b>Aantal deelnemers:</b> {n_participants}", styles['NormalBlue']))
story.append(Paragraph(f"<b>Aantal groepen:</b> {n_groups}", styles['NormalBlue']))
story.append(PageBreak())

# --- Scores per domein ---
story.append(Paragraph("1. Gemiddelde scores per domein", styles["Heading1Colored"]))
story.append(Paragraph("Deelnemers beoordeelden elk domein. De grafiek toont of de beoordeling gemiddeld positief of negatief is.", styles["Normal"]))
chart_img = save_plotly_chart(create_spider_chart(grouped))
with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as chart_file:
    chart_file.write(chart_img.read())
    chart_path = chart_file.name
story.append(Image(chart_path, width=15*cm, height=9*cm))
story.append(PageBreak())

# --- Hoogst gewaardeerde effecten ---
df_group["votes"] = df_group.groupby("text")["text"].transform("count")
df_pos = df_group[df_group["votes"] > 0].sort_values("votes", ascending=False)
df_neg = df_group[df_group["votes"] < 0].sort_values("votes")

story.append(Paragraph("2. Hoogst gewaardeerde effecten", styles["Heading1Colored"]))
top_n = n_groups * 3
story.append(Paragraph("Positieve effecten", styles["Heading2"]))
for _, row in df_pos.head(top_n).iterrows():
    story.append(Paragraph(f"• {row['text']} ({row['votes']} stemmen)", styles["Normal"]))

story.append(Spacer(1, 0.5*cm))
story.append(Paragraph("Negatieve effecten", styles["Heading2"]))
for _, row in df_neg.head(top_n).iterrows():
    story.append(Paragraph(f"• {row['text']} ({row['votes']} stemmen)", styles["Normal"]))

story.append(PageBreak())

# --- Samenvatting wie waar wanneer ---
pos_groups, neg_groups = [], []
pos_places, neg_places = [], []
pos_reach, neg_reach = [], []

pos_start_vals = [safe_int(r.get("feedback_start")) for r in df_group[df_group["votes"] >= 0].to_dict(orient="records")]
neg_start_vals = [safe_int(r.get("feedback_start")) for r in df_group[df_group["votes"] < 0].to_dict(orient="records")]
pos_start_vals = [v for v in pos_start_vals if v is not None]
neg_start_vals = [v for v in neg_start_vals if v is not None]

story.append(Paragraph("3. Samenvatting wie waar wanneer", styles["Heading1Colored"]))
story.append(Paragraph("Positieve effecten", styles["Heading2"]))
story.append(Paragraph(f"• Groepen: {', '.join(filter(None, pos_groups))}", styles["Normal"]))
story.append(Paragraph(f"• Plaatsen: {', '.join(filter(None, pos_places))}", styles["Normal"]))
story.append(Paragraph(f"• Reikwijdte: {', '.join(filter(None, pos_reach))}", styles["Normal"]))
story.append(Paragraph(f"• Verwachte start effect: {format_stats(pos_start_vals)}", styles["Normal"]))
story.append(Spacer(1, 0.5*cm))

story.append(Paragraph("Negatieve effecten", styles["Heading2"]))
story.append(Paragraph(f"• Groepen: {', '.join(filter(None, neg_groups))}", styles["Normal"]))
story.append(Paragraph(f"• Plaatsen: {', '.join(filter(None, neg_places))}", styles["Normal"]))
story.append(Paragraph(f"• Reikwijdte: {', '.join(filter(None, neg_reach))}", styles["Normal"]))
story.append(Paragraph(f"• Verwachte start effect: {format_stats(neg_start_vals)}", styles["Normal"]))

story.append(PageBreak())

# --- Feedback per effect ---
story.append(Paragraph("4. Groepsfeedback voor de belangrijkste effecten", styles["Heading1Colored"]))
for label, group_df in [("Positief", df_pos), ("Negatief", df_neg)]:
    story.append(Paragraph(f"{label}e effecten", styles["Heading2"]))
    for _, row in group_df.iterrows():
        story.append(Paragraph(f"<b>Effect:</b> {row['text']}", styles["Normal"]))
        story.append(Paragraph(f"Groep: {row.get('group', '–')}", styles["Normal"]))
        story.append(Paragraph(f"- Groepsimpact: {row.get('feedback_group_impact', '')}", styles["Normal"]))
        story.append(Paragraph(f"- Plaatsimpact: {row.get('feedback_place_impact', '')}", styles["Normal"]))
        story.append(Paragraph(f"- Reikwijdte: {row.get('feedback_distance', '')}", styles["Normal"]))
        story.append(Paragraph(f"- Verbeteringen: {row.get('feedback_improvements', '')}", styles["Normal"]))
        story.append(Spacer(1, 0.5*cm))

        if label == "Positief":
            pos_groups.append(row.get('feedback_group_impact', ''))
            pos_places.append(row.get('feedback_place_impact', ''))
            pos_reach.append(row.get('feedback_distance', ''))
        else:
            neg_groups.append(row.get('feedback_group_impact', ''))
            neg_places.append(row.get('feedback_place_impact', ''))
            neg_reach.append(row.get('feedback_distance', ''))
story.append(PageBreak())

# --- Thema-analyse ---
story.append(Paragraph("5. Thema-analyse", styles["Heading1Colored"]))
for domain in domains:
    story.append(Paragraph(domain, styles["Heading2"]))
    domain_df = df_sub[df_sub["domain"] == domain]
    story.append(Paragraph(f"Aantal stemmen in dit domein: {len(domain_df)}", styles["Normal"]))

    text = " ".join(domain_df["text"].astype(str)).strip()
    if text:
        wc_img = generate_wordcloud(text)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as wc_file:
            wc_file.write(wc_img.read())
            wc_path = wc_file.name
        story.append(Image(wc_path, width=14*cm, height=6*cm))
    else:
        story.append(Paragraph("⚠️ Geen tekst beschikbaar voor dit domein.", styles["Normal"]))

story.append(PageBreak())

# --- PDF opslaan ---
doc.build(story)

# --- Downloadknop ---
st.download_button(
    label="📄 Download rapport als PDF-bestand",
    data=pdf_buffer.getvalue(),
    file_name="groepsrapport.pdf",
    mime="application/pdf"
)
