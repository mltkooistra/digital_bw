import streamlit as st
import pandas as pd
import requests
import math
from collections import Counter
import re
from urllib.parse import quote

st.set_page_config(page_title="Verdiepende feedback", layout="wide")
st.title("Verdiepingsopdracht (alleen-lezen)")

# --- Basischecks ---
if "name" not in st.session_state or "access_code" not in st.session_state:
    st.error("Naam of sessiecode ontbreekt. Ga terug naar de startpagina.")
    st.stop()
if "group_question_filler" not in st.session_state:
    st.error("Deze pagina is niet direct toegankelijk.")
    st.stop()

session_code = st.session_state.access_code
display_name = st.session_state.name

# --- Groep info ---
selected_group = str(st.session_state.get("selected_group", "1"))
group_name = f"Groep {selected_group}"
if st.session_state.get("group_question_filler") is False:
    st.info(f"Je kijkt mee met **{group_name}**. De vragen zijn alleen te bekijken.")
else:
    st.info(f"Je bekijkt de vragen namens **{group_name}** (alleen-lezen).")

headers = {
    "apikey": st.secrets["supabase_key"],
    "Authorization": f"Bearer {st.secrets['supabase_key']}",
}

# =========================
# Helpers (names + polarity)
# =========================
def normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())

def majority_direction(series: pd.Series):
    """Return majority 'pos' of 'neg'; tie -> None."""
    if series is None or len(series) == 0:
        return None
    vals = [str(v).strip().lower() for v in series if pd.notna(v) and str(v).strip() != ""]
    vals = [v for v in vals if v in ("pos", "neg")]
    if not vals:
        return None
    cnt = Counter(vals)
    mc = cnt.most_common()
    if len(mc) >= 2 and mc[0][1] == mc[1][1]:
        return None
    return mc[0][0]

def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

# Match the edit page options
REACH_OPTIONS = [
    "individueel/huishouden",
    "de buurt",
    "wijk/dorp",
    "stad of gemeente",
    "provincie",
    "landelijk",
    "internationaal",
]
WHEN_OPTIONS = ["direct", "weken", "maanden", "jaren", "meer dan 15 jaar"]

def feedback_ui(row, idx, label, disabled=True):
    st.markdown(f"### {row.get('domein','')}: {row['text']}")

    # Q1 — same wording + examples
    st.text_input(
        "1. Voor wie is dit effect het grootst? (bijv. huiseigenaren, mensen met een laag inkomen, ouderen, jongeren, etc.)",
        key=f"{label}_{idx}_q1_ro",
        disabled=disabled,
        placeholder="— alleen bekijken —",
    )

    # Q2 — multiselect reach (same options)
    st.multiselect(
        "2. Hoe ver reikt het effect? (meerdere antwoorden mogelijk)",
        options=REACH_OPTIONS,
        default=[],
        help="Kies alle niveaus waarop het effect relevant is.",
        key=f"{label}_{idx}_q_reikwijdte_list_ro",
        disabled=disabled,
    )

    # Q3 — categorical when (same options)
    st.selectbox(
        "3. Wanneer verwacht je dat het effect zichtbaar wordt?",
        options=WHEN_OPTIONS,
        index=0,
        help="Kies de orde van grootte tot het effect zichtbaar is.",
        key=f"{label}_{idx}_q_start_cat_ro",
        disabled=disabled,
    )

    # Q4 — conditional phrasing
    if label.lower().startswith("pos"):
        q4_label = "4. Zijn er aanpassingen mogelijk om het effect te versterken? (overslaan mogelijk)"
    else:
        q4_label = "4. Zijn er aanpassingen mogelijk aan de interventie om dit effect te beperken of voorkomen?"

    st.text_input(
        q4_label,
        key=f"{label}_{idx}_q3_ro",
        disabled=disabled,
        placeholder="— alleen bekijken —",
    )

    st.markdown("---")

# ---------- DATA: votes ----------
r_votes = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/effect_votes?select=*",
    headers=headers, timeout=15,
)
df_votes = pd.DataFrame(r_votes.json()) if r_votes.status_code == 200 else pd.DataFrame()

if not df_votes.empty and "session" in df_votes.columns:
    df_votes = df_votes[df_votes["session"] == session_code].copy()

mandatory_cols = {"group_id", "votes", "text"}
if df_votes.empty or not mandatory_cols.issubset(set(df_votes.columns)):
    st.warning("Geen stemgegevens beschikbaar voor deze sessie.")
    st.stop()

# Filter op jouw groep
prefix = f"{session_code}_{selected_group}_"
df_votes = df_votes[df_votes["group_id"].astype(str).str.startswith(prefix, na=False)].copy()
if df_votes.empty:
    st.info("Nog geen stemmen voor jouw groep.")
    st.stop()

df_votes["votes"] = pd.to_numeric(df_votes.get("votes", 0), errors="coerce").fillna(0).astype(int)
if "domein" not in df_votes.columns:
    df_votes["domein"] = ""
if "direction" not in df_votes.columns:
    df_votes["direction"] = pd.NA

# ---------- DATA: submissions (bron voor direction) ----------
r_sub = requests.get(
    f"{st.secrets['supabase_url']}/rest/v1/submissions?select=text,direction,session,group_id,domein",
    headers=headers, timeout=15,
)
df_sub = pd.DataFrame(r_sub.json()) if r_sub.status_code == 200 else pd.DataFrame()
if not df_sub.empty:
    if "session" in df_sub.columns:
        df_sub = df_sub[df_sub["session"] == session_code].copy()
    if "group_id" in df_sub.columns:
        df_sub = df_sub[df_sub["group_id"].astype(str).str.startswith(prefix, na=False)].copy()

# ---------- Polarity mapping per TEXT ----------
direction_from_sub = {}
if not df_sub.empty and {"text", "direction"}.issubset(df_sub.columns):
    df_sub["text_norm"] = df_sub["text"].map(norm_text)
    sub_agg = (
        df_sub.groupby("text_norm", dropna=False)["direction"]
        .apply(majority_direction)
        .reset_index(name="dir_maj")
    )
    direction_from_sub = {r["text_norm"]: r["dir_maj"] for _, r in sub_agg.iterrows() if r["text_norm"] != ""}

# ---------- Aggregate ALL voted items ----------
agg = (
    df_votes.groupby("group_id", dropna=False)
    .agg(
        votes=("votes", "sum"),
        text=("text", "first"),
        domein=("domein", "first"),
        direction_votes=("direction", lambda s: majority_direction(pd.Series([v for v in s if pd.notna(v)]))),
    )
    .reset_index()
)

# Koppel direction uit submissions per text (norm)
agg["text_norm"] = agg["text"].map(norm_text)
agg["direction_from_sub"] = agg["text_norm"].map(direction_from_sub)

def pick_direction(row):
    if pd.notna(row.get("direction_from_sub")):
        return row["direction_from_sub"]
    return row.get("direction_votes")

agg["direction_resolved"] = agg.apply(pick_direction, axis=1)

# ---------- Top 3 positief en top 3 negatief ----------
top_pos = (
    agg[agg["direction_resolved"] == "pos"]
    .sort_values("votes", ascending=False)
    .head(3)
    .reset_index(drop=True)
)
top_neg = (
    agg[agg["direction_resolved"] == "neg"]
    .sort_values("votes", ascending=False)
    .head(3)
    .reset_index(drop=True)
)

# ---------- UI (READ-ONLY) ----------
st.header("Top 3 Positieve effecten (meeste stemmen)")
if top_pos.empty:
    st.info("Geen positieve effecten gevonden.")
else:
    for i, row in top_pos.iterrows():
        feedback_ui(row, i, "Pos", disabled=True)

st.header("Top 3 Negatieve effecten (meeste stemmen)")
if top_neg.empty:
    st.info("Geen negatieve effecten gevonden.")
else:
    for i, row in top_neg.iterrows():
        feedback_ui(row, i, "Neg", disabled=True)

# Geen opslaan of verzenden in alleen-lezen weergave
st.info("Deze pagina is alleen ter inzage. Antwoorden kunnen hier niet worden ingevuld of opgeslagen.")
