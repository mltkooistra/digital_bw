import streamlit as st
import pandas as pd
import requests
import math
from collections import Counter
import re

st.set_page_config(page_title="Verdiepende feedback", layout="wide")
st.title("Verdiepingsopdracht")

# --- Basischecks ---
if "name" not in st.session_state or "access_code" not in st.session_state:
    st.error("Naam of sessiecode ontbreekt. Ga terug naar de startpagina.")
    st.stop()

if "group_question_filler" not in st.session_state:
    st.error("Deze pagina is niet direct toegankelijk.")
    st.stop()

if st.session_state["group_question_filler"] is False:
    st.info("⏳ Wacht tot je groepslid de groepsvragen heeft ingevuld.")
    st.stop()

# --- Groep info ---
selected_group = str(st.session_state.get("selected_group", "1"))
group_name = f"Groep {selected_group}"
st.info(f"Je vult feedback in namens **{group_name}**.")

session_code = st.session_state.access_code
headers = {
    "apikey": st.secrets["supabase_key"],
    "Authorization": f"Bearer {st.secrets['supabase_key']}",
}

# ========================
# Helpers
# ========================
def majority_posneg(series: pd.Series):
    """Meerderheid van {-1, 1}. Bij gelijkstand of geen geldige waarden -> None."""
    if series is None or len(series) == 0:
        return None
    vals = []
    for v in series:
        if pd.isna(v):
            continue
        try:
            vv = int(float(v))
            if vv in (-1, 1):
                vals.append(vv)
        except Exception:
            continue
    if not vals:
        return None
    cnt = Counter(vals)
    mc = cnt.most_common()
    if len(mc) >= 2 and mc[0][1] == mc[1][1]:
        return None
    return mc[0][0]

def as_posneg_int(val):
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
        v = int(val)
        return v if v in (-1, 1) else None
    except Exception:
        return None

def norm_text(s: str) -> str:
    """Normaliseer tekst om robuuster te matchen tussen tables."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

REACH_OPTIONS = [
    "-- geen antwoord --",
    "de buurt",
    "wijk/dorp",
    "stad of gemeente",
    "provincie",
    "landelijk",
    "internationaal",
]

def feedback_ui(row, idx, label):
    st.markdown(f"### {row.get('domein','')}: {row['text']}")
    st.text_input("1. Op welke groepen is het effect het grootst?", key=f"{label}_{idx}_q1")
    st.text_input("2. Op welke gebied(en) is het effect het grootst?", key=f"{label}_{idx}_q2")
    st.selectbox(
        "3. Hoe ver reikt het effect?",
        options=REACH_OPTIONS,
        index=0,
        key=f"{label}_{idx}_q_reikwijdte"
    )
    st.slider(
        "4. Wanneer verwacht je dat het effect zichtbaar wordt?",
        min_value=0, max_value=50, value=0, step=1,
        format="%d jaar",
        help="0 = meteen vanaf de start, 50 = pas over 50 jaar of later",
        key=f"{label}_{idx}_q_start_year"
    )
    st.text_input("5. Zijn er aanpassingen aan de interventie mogelijk of nodig?", key=f"{label}_{idx}_q3")
    st.markdown("---")

# ========================
# DATA OPHALEN
# ========================

# 1) Votes
r_votes = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/effect_votes?select=*",
    headers=headers,
    timeout=15,
)
df_votes = pd.DataFrame(r_votes.json()) if r_votes.status_code == 200 else pd.DataFrame()

# Filter op sessie
if not df_votes.empty and "session" in df_votes.columns:
    df_votes = df_votes[df_votes["session"] == session_code].copy()

# Guard rails
mandatory_cols = {"group_id", "votes", "text"}
if df_votes.empty or not mandatory_cols.issubset(set(df_votes.columns)):
    st.warning("Geen stemgegevens beschikbaar voor deze sessie.")
    st.stop()

# Filter op jouw groep via group_id-prefix
prefix = f"{session_code}_{selected_group}_"
df_votes = df_votes[df_votes["group_id"].astype(str).str.startswith(prefix, na=False)].copy()

if df_votes.empty:
    st.info("Nog geen stemmen voor jouw groep.")
    st.stop()

# Typen & kolommen
df_votes["votes"] = pd.to_numeric(df_votes.get("votes", 0), errors="coerce").fillna(0).astype(int)
if "domein" not in df_votes.columns:
    df_votes["domein"] = ""
if "posneg" not in df_votes.columns:
    df_votes["posneg"] = pd.NA

# 2) Submissions (bron voor polariteit)
# We halen ten minste text & posneg op. (session en group_id om te filteren)
r_sub = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/submissions?select=text,posneg,session,group_id,domein",
    headers=headers,
    timeout=15,
)
df_sub = pd.DataFrame(r_sub.json()) if r_sub.status_code == 200 else pd.DataFrame()

if not df_sub.empty:
    if "session" in df_sub.columns:
        df_sub = df_sub[df_sub["session"] == session_code].copy()
    if "group_id" in df_sub.columns:
        df_sub = df_sub[df_sub["group_id"].astype(str).str.startswith(prefix, na=False)].copy()

# ========================
# POLARITEIT UIT SUBMISSIONS
# ========================
# Maak een mapping van genormaliseerde text -> majority posneg uit submissions
posneg_from_sub = {}
if not df_sub.empty and "text" in df_sub.columns and "posneg" in df_sub.columns:
    df_sub["text_norm"] = df_sub["text"].map(norm_text)
    # Groepeer per text_norm en neem meerderheid van posneg
    sub_agg = (
        df_sub.groupby("text_norm", dropna=False)["posneg"]
        .apply(majority_posneg)
        .reset_index(name="posneg_majority")
    )
    # Zet in dict
    posneg_from_sub = {
        row["text_norm"]: row["posneg_majority"]
        for _, row in sub_agg.iterrows()
        if row["text_norm"] != ""
    }

# ========================
# AGGREGATIE STEMMEN PER EFFECTGROEP
# ========================
agg = (
    df_votes.groupby("group_id", dropna=False)
    .agg(
        votes=("votes", "sum"),
        text=("text", "first"),
        domein=("domein", "first"),
        posneg_votes=("posneg", majority_posneg),  # fallback indien submissions niets heeft
    )
    .reset_index()
)

# Match text -> polarity uit submissions
agg["text_norm"] = agg["text"].map(norm_text)
agg["posneg_from_sub"] = agg["text_norm"].map(posneg_from_sub)

# Definitieve polariteit: eerst submissions, anders majority uit votes
def pick_polarity(row):
    if pd.notna(row.get("posneg_from_sub")):
        return as_posneg_int(row["posneg_from_sub"])
    return as_posneg_int(row.get("posneg_votes"))

agg["posneg_resolved"] = agg.apply(pick_polarity, axis=1)

# ========================
# DEBUG
# ========================
with st.expander("🔎 Debug"):
    st.write("Aantal stemmen (na sessie+groep-filter):", len(df_votes))
    st.write("Unieke effectgroepen:", agg["group_id"].nunique())
    st.write("Submissions records (na filter):", 0 if df_sub is None else len(df_sub))
    st.write("Met posneg=1:", len(agg[agg["posneg_resolved"] == 1]))
    st.write("Met posneg=-1:", len(agg[agg["posneg_resolved"] == -1]))
    st.write("Onbekende polariteit:", len(agg[agg["posneg_resolved"].isna()]))
    st.write("Voorbeeld records:", agg.head(5))

# ========================
# TOPLIJSTEN (meeste stemmen binnen elke polariteit)
# ========================
n = int(st.session_state.get("n_effects", 3))

top_pos = (
    agg[agg["posneg_resolved"] == 1]
    .sort_values("votes", ascending=False)
    .head(n)
    .reset_index(drop=True)
)

top_neg = (
    agg[agg["posneg_resolved"] == -1]
    .sort_values("votes", ascending=False)
    .head(n)
    .reset_index(drop=True)
)

unknown = (
    agg[agg["posneg_resolved"].isna()]
    .sort_values("votes", ascending=False)
    .reset_index(drop=True)
)

# ========================
# FEEDBACK UI
# ========================
st.header(f"Top {n} Positieve effecten (meeste stemmen)")
if top_pos.empty:
    st.info("Geen positieve effecten (met bekende polariteit) gevonden voor jouw groep.")
else:
    for i, row in top_pos.iterrows():
        feedback_ui(row, i, "Pos")

st.header(f"Top {n} Negatieve effecten (meeste stemmen)")
if top_neg.empty:
    st.info("Geen negatieve effecten (met bekende polariteit) gevonden voor jouw groep.")
else:
    for i, row in top_neg.iterrows():
        feedback_ui(row, i, "Neg")

st.header("⚖️ Onbekende polariteit (pos/neg niet gevonden)")
if unknown.empty:
    st.caption("Geen effecten met onbekende polariteit.")
else:
    for i, row in unknown.iterrows():
        feedback_ui(row, i, "Unk")

# ========================
# OPSLAAN
# ========================
if st.button("✅ Versturen"):
    ok = 0
    to_save = [("Pos", top_pos), ("Neg", top_neg)]
    # Wil je unknown ook opslaan? -> to_save.append(("Unk", unknown))

    for label, group_df in to_save:
        for idx, row in group_df.iterrows():
            posneg_to_save = row.get("posneg_from_sub")
            if pd.isna(posneg_to_save):
                posneg_to_save = row.get("posneg_votes")  # fallback

            payload = {
                "session": session_code,
                "group": group_name,
                "text": row["text"],
                "domein": row.get("domein", ""),
                "posneg": as_posneg_int(posneg_to_save),  # -1 of 1
                "feedback_group_impact": st.session_state.get(f"{label}_{idx}_q1", ""),
                "feedback_place_impact": st.session_state.get(f"{label}_{idx}_q2", ""),
                "feedback_distance": st.session_state.get(f"{label}_{idx}_q_reikwijdte", ""),
                "feedback_improvements": st.session_state.get(f"{label}_{idx}_q3", ""),
                "feedback_start": st.session_state.get(f"{label}_{idx}_q_start_year", 0),
                "group_id": row.get("group_id", None),
            }

            r = requests.post(
                f"{st.secrets['supabase_url']}/rest/v1/group_results?on_conflict=group,text",
                headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
                json=payload,
                timeout=15,
            )
            if r.status_code in (200, 201):
                ok += 1
            else:
                st.error(f"Opslaan mislukt voor “{row['text']}”: {r.status_code} {r.text}")

    st.success(f"Feedback opgeslagen ({ok} items).")
    st.session_state["group_answers_submitted"] = True
    st.switch_page("pages/14_rapport.py")
