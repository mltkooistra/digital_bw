import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import uuid
import difflib
import random
import re
from collections import Counter

# =======================
# Configuratie
# =======================
MAX_UPVOTES = 10
MAX_DOWNVOTES = 5

st.set_page_config(page_title="Stemmen op effecten", layout="wide")

# =======================
# Sessie-initialisatie
# =======================
for key in ["upvotes_used", "downvotes_used", "voted_ids"]:
    if key not in st.session_state:
        st.session_state[key] = 0 if "used" in key else set()

required_session_vars = ["name", "access_code", "info", "description", "prov"]
for var in required_session_vars:
    if var not in st.session_state:
        st.error(f"Sessiestatus '{var}' ontbreekt. Ga terug naar startpagina.")
        st.stop()

if "submission_id" not in st.session_state:
    st.session_state.submission_id = str(uuid.uuid4())

SESSION = st.session_state.access_code
USERNAME = st.session_state.name

HEADERS = {
    "apikey": st.secrets["supabase_key"],
    "Authorization": f"Bearer {st.secrets['supabase_key']}",
}

# =======================
# Helpers
# =======================
def parse_group_number(g) -> int | None:
    """Parseert groep-nummer uit int/float/'3'/'Groep 3'/etc."""
    if g is None or (isinstance(g, float) and pd.isna(g)):
        return None
    if isinstance(g, int):
        return g
    if isinstance(g, float):
        return int(g)
    s = str(g)
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None

def normalize_name(s: str) -> str:
    """Case-insensitive naam-normalisatie met spaties gecondenseerd."""
    if not isinstance(s, str):
        return ""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def majority_posneg(series: pd.Series) -> int:
    """Return majority van {-1, 1}; bij tie/geen waarden -> 0."""
    if series is None or len(series) == 0:
        return 0
    vals = []
    for v in series.tolist():
        if pd.isna(v) or str(v).strip() == "":
            continue
        try:
            vv = int(float(v))
            if vv in (-1, 1):
                vals.append(vv)
            elif vv == 0:
                vals.append(0)
        except Exception:
            continue
    if not vals:
        return 0
    cnt = Counter(vals)
    mc = cnt.most_common()
    if len(mc) >= 2 and mc[0][1] == mc[1][1]:
        return 0
    return mc[0][0] if mc[0][0] in (-1, 0, 1) else 0

def group_similar_effects(df_local, similarity_threshold=0.6):
    """Groepeer vergelijkbare 'text' waarden binnen hetzelfde domein."""
    grouped = []
    used_indices = set()
    for i, row_i in df_local.iterrows():
        if i in used_indices:
            continue
        group = [i]
        text_i = str(row_i.get("text", "")).lower()
        for j, row_j in df_local.iterrows():
            if j <= i or j in used_indices:
                continue
            text_j = str(row_j.get("text", "")).lower()
            similarity = difflib.SequenceMatcher(None, text_i, text_j).ratio()
            if similarity >= similarity_threshold:
                group.append(j)
                used_indices.add(j)
        grouped.append(group)
    return grouped

def norm_text(s: str) -> str:
    """Normaliseer tekst om robuuster te matchen tussen tables."""
    if not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())

# =======================
# Data ophalen (cached)
# =======================
@st.cache_data(ttl=15)
def fetch_submissions():
    url = (
        f"{st.secrets['supabase_url']}/rest/v1/submissions"
        f"?select=*&order=timestamp.desc&limit=1000&session=eq.{SESSION}"
    )
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return pd.DataFrame()
    data = r.json()
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)

@st.cache_data(ttl=15)
def fetch_votes():
    url = (
        f"{st.secrets['supabase_url']}/rest/v1/effect_votes"
        f"?select=*&session=eq.{SESSION}"
    )
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return pd.DataFrame(columns=["group_id", "votes"])
    data = r.json()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=["group_id", "votes"])

@st.cache_data(ttl=15)
def fetch_groups_for_session():
    url = (
        f"{st.secrets['supabase_url']}/rest/v1/groups"
        f"?select=session,name,group&session=eq.{SESSION}"
    )
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return pd.DataFrame(columns=["session", "name", "group"])
    data = r.json()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=["session", "name", "group"])

# =======================
# Ophalen + GROEP VIA NAAM (uit groups)
# =======================
df_submissions_all = fetch_submissions()
df = df_submissions_all.drop_duplicates(subset=["name", "domain", "score", "text"]) if not df_submissions_all.empty else pd.DataFrame()
if df.empty:
    st.info("Nog geen inzendingen.")
    st.stop()

groups_df = fetch_groups_for_session()
if groups_df.empty:
    st.error("Geen groepsindeling gevonden. Vraag de organisator om je in een groep te plaatsen.")
    st.stop()

# Normaliseer namen voor matching
df["name_norm"] = df["name"].apply(normalize_name)
groups_df["name_norm"] = groups_df["name"].apply(normalize_name)
current_user_norm = normalize_name(USERNAME)

# Bepaal groepnummer en label van de huidige gebruiker (uit groups)
groups_df["group_number"] = groups_df["group"].apply(parse_group_number)

my_row = groups_df[groups_df["name_norm"] == current_user_norm].head(1)
if my_row.empty or pd.isna(my_row.iloc[0]["group_number"]):
    st.error("Jouw naam is niet te vinden in de groups-tabel, of je hebt geen groep toegewezen.")
    with st.expander("🔎 Debug: groups-gegevens"):
        st.write(groups_df)
    st.stop()

selected_group_num = int(my_row.iloc[0]["group_number"])
selected_group = str(selected_group_num)
# Originele label zoals in de tabel (bijv. 'Groep 3'); valt terug op 'Groep X' als None
selected_group_label = str(my_row.iloc[0]["group"]) if "group" in my_row.columns else f"Groep {selected_group}"

# Groepsleden bepalen aan de hand van dezelfde group_number
group_members_norm = groups_df.loc[
    groups_df["group_number"] == selected_group_num, "name_norm"
].dropna().unique().tolist()

# Filter inzendingen op groepsleden
df_group = df[df["name_norm"].isin(group_members_norm)].copy()

st.info(
    f"Je stemt binnen **{selected_group_label}** "
    f"(nr. {selected_group}). "
    f"Aantal groepsleden met inzendingen: {df_group['name_norm'].nunique()} "
    f"(inzendingen: {len(df_group)})"
)

if df_group.empty:
    st.warning("Er zijn nog geen inzendingen van mensen in jouw groep.")
    st.stop()

vote_data = fetch_votes()

# =======================
# Polariteit per tekst uit submissions (van jouw groep)
# =======================
text_posneg_map = {}
if {"text", "posneg"}.issubset(df_group.columns):
    tmp = df_group.copy()
    tmp["text_norm"] = tmp["text"].map(norm_text)
    sub_agg = (
        tmp.groupby("text_norm", dropna=False)["posneg"]
        .apply(majority_posneg)
        .reset_index(name="posneg_majority")
    )
    text_posneg_map = {
        r["text_norm"]: int(r["posneg_majority"]) if pd.notna(r["posneg_majority"]) else 0
        for _, r in sub_agg.iterrows() if r["text_norm"] != ""
    }

# =======================
# Effectgroepen bouwen
# =======================
effect_groups = []
domains = sorted([d for d in df_group["domain"].dropna().unique().tolist() if str(d).strip() != ""])

for dom in domains:
    df_dom = df_group[df_group["domain"] == dom].copy()
    if df_dom.empty:
        continue

    if "posneg" not in df_dom.columns:
        df_dom["posneg"] = 0

    grouped_indices = group_similar_effects(df_dom, similarity_threshold=0.6)

    for idx, group in enumerate(grouped_indices):
        rows = df_dom.loc[group]
        texts = [str(t) for t in rows["text"].tolist() if str(t).strip() != ""]
        authors = rows["name"].dropna().unique().tolist()

        merged_text = " / ".join(texts) if texts else "(geen tekst)"
        group_id = f"{SESSION}_{selected_group}_{slugify(str(dom))}_{idx}"

        # votes ophalen
        total_votes = 0
        if not vote_data.empty:
            try:
                total_votes = int(vote_data[vote_data["group_id"] == group_id]["votes"].sum())
            except Exception:
                total_votes = 0

        # posneg majority over component-teksten in deze groep
        text_norms = [norm_text(t) for t in texts]
        component_posnegs = [text_posneg_map.get(tn, 0) for tn in text_norms if tn != ""]
        posneg_val = majority_posneg(pd.Series(component_posnegs, dtype="float"))
        posneg_val = int(posneg_val) if pd.notna(posneg_val) else 0

        effect_groups.append({
            "text": merged_text,
            "group_id": group_id,
            "votes": total_votes,
            "authors": authors,
            "domain": dom,
            "posneg": posneg_val,  # -1/0/1
        })

# =======================
# Stemmen registreren (incl. posneg én group)
# =======================
def register_vote(group_id, value, text, domein, posneg):
    # clamp posneg naar {-1,0,1}
    try:
        p = int(posneg)
        posneg_clean = p if p in (-1, 0, 1) else 0
    except Exception:
        posneg_clean = 0

    try:
        r = requests.post(
            f"{st.secrets['supabase_url']}/rest/v1/effect_votes",
            headers={**HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"},
            json={
                "session": SESSION,
                "group": selected_group_label,          # ✅ voeg groep toe aan kolom 'group'
                "group_id": group_id,
                "votes": int(value),
                "text": text,
                "domein": domein,
                "posneg": posneg_clean,                 # ✅ stuur posneg mee
                "last_updated": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
            timeout=15,
        )
        if r.status_code not in (200, 201):
            st.error(f"Kon stem niet registreren: {r.status_code} {r.text}")
            return
    except Exception as e:
        st.error(f"Kon stem niet registreren: {e}")
        return

    st.session_state.voted_ids.add(group_id)

def vote_buttons(effect):
    # Niet op eigen effect stemmen
    if normalize_name(st.session_state.name) in [normalize_name(a) for a in effect.get("authors", [])]:
        st.info("Je kunt niet stemmen op je eigen effect.")
        return

    # Niet dubbel stemmen
    if effect["group_id"] in st.session_state.voted_ids:
        st.caption("✅ Stem geregistreerd voor dit effect.")
        return

    vote_cols = st.columns(2)
    with vote_cols[0]:
        if st.button("➕", key=f"plus_{effect['group_id']}"):
            if st.session_state.upvotes_used < MAX_UPVOTES:
                register_vote(effect["group_id"], +1, effect["text"], effect["domain"], effect.get("posneg", 0))
                st.session_state.upvotes_used += 1
                st.rerun()
            else:
                st.warning("Max upvotes bereikt.")
    with vote_cols[1]:
        if st.button("➖", key=f"minus_{effect['group_id']}"):
            if st.session_state.downvotes_used < MAX_DOWNVOTES:
                register_vote(effect["group_id"], -1, effect["text"], effect["domain"], effect.get("posneg", 0))
                st.session_state.downvotes_used += 1
                st.rerun()
            else:
                st.warning("Max downvotes bereikt.")

# =======================
# UI
# =======================
st.subheader("🗳️ Stem op effecten!")
st.markdown(
    f"Stemmen gebruikt: ➕ {st.session_state.upvotes_used} / {MAX_UPVOTES} "
    f" |  ➖ {st.session_state.downvotes_used} / {MAX_DOWNVOTES}"
)
st.markdown(f"Je stemt binnen **{selected_group_label}** (nr. {selected_group}).")

# Shuffle + filter (niet op eigen/zijn al gestemd)
effect_groups_shuffled = [
    e for e in effect_groups
    if e["group_id"] not in st.session_state.voted_ids
    and normalize_name(st.session_state.name) not in [normalize_name(a) for a in e.get("authors", [])]
]
random.shuffle(effect_groups_shuffled)

if not effect_groups_shuffled:
    st.success("Niets meer om op te stemmen binnen je groep. 🎉")
else:
    # Grid layout (3 per rij)
    cols = st.columns(3)
    for idx, effect in enumerate(effect_groups_shuffled):
        with cols[idx % 3]:
            with st.container(border=True):
                st.markdown(f"**{effect['text']}**")
                posneg_label = "Positief" if effect.get("posneg", 0) == 1 else "Negatief" if effect.get("posneg", 0) == -1 else "Onbekend"
                st.caption(f"Domein: {effect['domain']} • {posneg_label}")
                vote_buttons(effect)

st.divider()
col1, col2 = st.columns(2)
with col1:
    if st.button("➡️ Klik hier om de groepsvragen in te vullen"):
        st.session_state["group_question_filler"] = True
        st.session_state["selected_group"] = selected_group
        st.switch_page("pages/12_gezamenlijke opdracht.py")

with col2:
    if st.button("📄 Klik hier als iemand anders de groepsvragen namens je groep invult"):
        st.session_state["group_question_filler"] = False
        st.session_state["selected_group"] = selected_group
        st.switch_page("pages/13_meekijken.py")
