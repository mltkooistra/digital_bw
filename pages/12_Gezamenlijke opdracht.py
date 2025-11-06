import streamlit as st
import pandas as pd
import numpy as np
import requests
import math
import json
from collections import Counter
import re
from urllib.parse import quote
from datetime import datetime, date

# =========================
# Page config
# =========================
st.set_page_config(page_title="Verdiepingsopdracht", layout="wide")
st.title("Verdiepingsopdracht")

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
st.info(f"Je zit in **{group_name}**.")

# Headers voor Supabase
BASE_URL = st.secrets['supabase_url']
HEADERS = {
    "apikey": st.secrets["supabase_key"],
    "Authorization": f"Bearer {st.secrets['supabase_key']}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# =========================
# JSON sanitizers to avoid InvalidJSONError
# =========================
def _is_na_like(x) -> bool:
    """True for np.nan, pd.NA, pd.NaT, etc."""
    try:
        return pd.isna(x)
    except Exception:
        return False

def _to_builtin_number(x):
    # Normalize numpy/pandas numbers to Python ints/floats
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        xf = float(x)
        if math.isnan(xf) or math.isinf(xf):
            return None
        return xf
    if isinstance(x, (int,)):
        return int(x)
    if isinstance(x, (float,)):
        if math.isnan(x) or math.isinf(x):
            return None
        return float(x)
    return x

def _to_serializable_datetime(x):
    # Timestamps, dates, timedeltas
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    if isinstance(x, datetime):
        return x.isoformat()
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, (pd.Timedelta, np.timedelta64)):
        try:
            return pd.Timedelta(x).isoformat()
        except Exception:
            return str(x)
    return x

def json_safe(value):
    """
    Recursively convert a structure into JSON-safe values:
    - Replace NaN/Inf/NA/NaT with None
    - Convert numpy/pandas scalars to builtin types
    - Convert timestamps/timedeltas to strings
    """
    # None or NA-like
    if _is_na_like(value):
        return None

    # Numbers
    value = _to_builtin_number(value)

    # Datetime-like
    value = _to_serializable_datetime(value)

    # Dict
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}

    # Iterables
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]

    # Numpy scalars (after earlier conversions)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.str_, np.bytes_)):
        return str(value)

    # Everything else: str, bool, None, already-safe numbers
    return value

def _assert_jsonable(payload):
    """Validate by trying json.dumps with allow_nan=False for clearer local errors."""
    json.dumps(payload, allow_nan=False)

def post_json(url: str, body: dict, headers_: dict, timeout: int = 15):
    safe = json_safe(body)
    _assert_jsonable(safe)
    return requests.post(url, headers=headers_, json=safe, timeout=timeout)

def patch_json(url: str, body: dict, headers_: dict, timeout: int = 15):
    safe = json_safe(body)
    _assert_jsonable(safe)
    return requests.patch(url, headers=headers_, json=safe, timeout=timeout)

# =========================
# Helpers (leader control + analysis)
# =========================
def normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())

def get_my_group_row(session_code: str, name_value: str, group_value: str) -> dict | None:
    """Fetch the groups row for (session, name, group)."""
    base = f"{BASE_URL}/rest/v1/groups"
    q = (
        f"?select=id,session,name,group,leader"
        f"&session=eq.{quote(session_code)}"
        f"&name=eq.{quote(name_value)}"
        f"&group=eq.{quote(group_value)}"
        f"&limit=1"
    )
    r = requests.get(base + q, headers=HEADERS, timeout=10)
    if r.status_code != 200:
        st.error(f"Kon groepsrecord niet ophalen: {r.status_code} {r.text}")
        return None
    rows = r.json() or []
    return rows[0] if rows else None

def get_existing_leaders(session_code: str, group_value: str) -> list[dict]:
    """Fetch all rows with leader='yes' for (session, group)."""
    base = f"{BASE_URL}/rest/v1/groups"
    q = (
        f"?select=id,name,leader,group"
        f"&session=eq.{quote(session_code)}"
        f"&group=eq.{quote(group_value)}"
        f"&leader=eq.yes"
    )
    r = requests.get(base + q, headers=HEADERS, timeout=10)
    if r.status_code != 200:
        st.error(f"Kon leiderschap niet ophalen: {r.status_code} {r.text}")
        return []
    return r.json() or []

def ensure_current_row_exists(session_code: str, name_value: str, group_value: str) -> dict | None:
    """Ensure a groups row exists for (session, name, group); create if needed (leader defaults to 'no')."""
    row = get_my_group_row(session_code, name_value, group_value)
    if row:
        return row
    base = f"{BASE_URL}/rest/v1/groups"
    payload = {
        "session": session_code,
        "name": name_value,
        "group": group_value,
        "leader": "no",
    }
    r = post_json(base, payload, HEADERS, timeout=10)
    if r.status_code not in (200, 201):
        st.error(f"Kon groepsrecord niet aanmaken: {r.status_code} {r.text}")
        return None
    rows = r.json() or []
    return rows[0] if rows else None

def take_over_leadership(session_code: str, name_value: str, group_value: str) -> bool:
    """
    Make current user leader='yes' for (session, name, group).
    Also (softly) demote other leaders to 'no' for the same session+group.
    """
    # 0) Ensure our row exists
    my_row = ensure_current_row_exists(session_code, name_value, group_value)
    if not my_row:
        return False

    base = f"{BASE_URL}/rest/v1/groups"

    # 1) Demote others (optional but keeps a single leader for the group)
    try:
        r_demote = patch_json(
            f"{base}"
            f"?session=eq.{quote(session_code)}"
            f"&group=eq.{quote(group_value)}"
            f"&leader=eq.yes"
            f"&name=neq.{quote(name_value)}",
            {"leader": "no"},
            HEADERS,
            timeout=10
        )
        if r_demote.status_code not in (200, 204):
            st.warning(f"Kon eerdere leider(s) niet terugzetten naar 'no': {r_demote.status_code} {r_demote.text}")
    except Exception as e:
        st.warning(f"Kon eerdere leider(s) niet terugzetten: {e}")

    # 2) Set ourselves to leader='yes'
    try:
        r_patch = patch_json(
            f"{base}?id=eq.{my_row['id']}",
            {"leader": "yes"},
            HEADERS,
            timeout=10
        )
        if r_patch.status_code not in (200, 204):
            st.error(f"Kon leiderschap niet overnemen: {r_patch.status_code} {r_patch.text}")
            return False
    except Exception as e:
        st.error(f"Kon leiderschap niet overnemen: {e}")
        return False

    return True

def majority_direction(series: pd.Series):
    """Return majority 'pos' or 'neg' from series; tie -> None."""
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

REACH_OPTIONS = [
    "-- geen antwoord --", "individueel/huishouden", "de buurt", "wijk/dorp", "stad of gemeente",
    "provincie", "landelijk", "internationaal",
]

def feedback_ui(row, idx, label):
    st.markdown(f"### {row.get('domein','')}: {row['text']}")
    st.text_input("1. Op welke groepen is het effect het grootst?", key=f"{label}_{idx}_q1")
    st.text_input("2. Op welke gebied(en) is het effect het grootst?", key=f"{label}_{idx}_q2")
    st.selectbox("3. Hoe ver reikt het effect?", options=REACH_OPTIONS, index=0, key=f"{label}_{idx}_q_reikwijdte")
    st.slider("4. Wanneer verwacht je dat het effect zichtbaar wordt?", min_value=0, max_value=50, value=0, step=1,
              format="%d jaar", help="0 = meteen vanaf de start, 50 = pas over 50 jaar of later",
              key=f"{label}_{idx}_q_start_year")
    st.text_input("5. Zijn er aanpassingen aan de interventie mogelijk of nodig?", key=f"{label}_{idx}_q3")
    st.markdown("---")

# =========================
# Determine leadership state
# =========================
my_row = get_my_group_row(session_code, display_name, group_name)
leaders = get_existing_leaders(session_code, group_name)

current_is_leader = bool(my_row and str(my_row.get("leader", "")).strip().lower() == "yes")
someone_else_is_leader = any(normalize_name(r.get("name", "")) != normalize_name(display_name) for r in leaders)

if not current_is_leader:
    if someone_else_is_leader:
        other_names = ", ".join(sorted({r.get("name", "") for r in leaders if normalize_name(r.get("name", "")) != normalize_name(display_name)})) or "iemand anders"
        st.warning(f"📌 {other_names} is momenteel groepsleider voor **{group_name}**.")
    else:
        st.info(f"Er is nog geen groepsleider ingesteld voor **{group_name}**.")

    with st.expander("Wil je de groepsleider wijzigen? ⚠️ Let op"):
        st.markdown(
            "- **Waarschuwing:** bij het wijzigen van de groepsleider kunnen **(gedeeltelijke) antwoorden** van de groepsopdracht **vervangen of niet meer zichtbaar** worden voor anderen.\n"
            "- Ga alleen verder als je dit met je groep hebt afgestemd."
        )
        confirm = st.checkbox("Ik begrijp dat sommige antwoorden mogelijk verloren gaan of overschreven worden.")
        takeover = st.button("✅ Neem leiderschap over")

        if takeover:
            if not confirm:
                st.error("Bevestig eerst de waarschuwing hierboven om door te gaan.")
                st.stop()
            if take_over_leadership(session_code, display_name, group_name):
                st.success("Je bent nu groepsleider. Deze pagina wordt herladen.")
                st.experimental_rerun()
            else:
                st.error("Overnemen van leiderschap is mislukt. Probeer opnieuw of neem contact op met de organisator.")
                st.stop()

    st.info("Je kunt deze feedbackpagina pas invullen als je groepsleider bent.")
    st.stop()

# ---- Vanaf hier: alleen zichtbaar voor (huidige) leider ----
st.success(f"✅ Jij bent groepsleider voor **{group_name}**.")

# =========================
# DATA: votes
# =========================
r_votes = requests.get(
    f"{BASE_URL}/rest/v1/effect_votes?select=*",
    headers=HEADERS, timeout=15,
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

# =========================
# DATA: submissions (bron voor direction)
# =========================
r_sub = requests.get(
    f"{BASE_URL}/rest/v1/submissions?select=text,direction,session,group_id,domein",
    headers=HEADERS, timeout=15,
)
df_sub = pd.DataFrame(r_sub.json()) if r_sub.status_code == 200 else pd.DataFrame()
if not df_sub.empty:
    if "session" in df_sub.columns:
        df_sub = df_sub[df_sub["session"] == session_code].copy()
    if "group_id" in df_sub.columns:
        df_sub = df_sub[df_sub["group_id"].astype(str).str.startswith(prefix, na=False)].copy()

# =========================
# Polarity mapping per TEXT
# =========================
direction_from_sub = {}
if not df_sub.empty and {"text", "direction"}.issubset(df_sub.columns):
    df_sub["text_norm"] = df_sub["text"].map(norm_text)
    sub_agg = (
        df_sub.groupby("text_norm", dropna=False)["direction"]
        .apply(majority_direction)
        .reset_index(name="dir_maj")
    )
    direction_from_sub = {r["text_norm"]: r["dir_maj"] for _, r in sub_agg.iterrows() if r["text_norm"] != ""}

# =========================
# Aggregate ALL voted items
# =========================
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

# =========================
# Top 3 positief en top 3 negatief
# =========================
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

# =========================
# UI
# =========================
st.header("Top 3 Positieve effecten (meeste stemmen)")
if top_pos.empty:
    st.info("Geen positieve effecten gevonden.")
else:
    for i, row in top_pos.iterrows():
        feedback_ui(row, i, "Pos")

st.header("Top 3 Negatieve effecten (meeste stemmen)")
if top_neg.empty:
    st.info("Geen negatieve effecten gevonden.")
else:
    for i, row in top_neg.iterrows():
        feedback_ui(row, i, "Neg")

# =========================
# Opslaan (JSON-safe payloads)
# =========================
if st.button("✅ Versturen"):
    ok = 0
    base = f"{BASE_URL}/rest/v1/group_results?on_conflict=group,text"

    for label, group_df in [("Pos", top_pos), ("Neg", top_neg)]:
        for idx, row in group_df.iterrows():
            dir_to_save = row.get("direction_from_sub") or row.get("direction_votes")

            # group_id might not be present in agg; guard NaN -> None if present
            gid = row.get("group_id", None)
            if _is_na_like(gid):
                gid = None

            payload = {
                "session": session_code,
                "group": group_name,
                "text": row["text"],
                "domein": row.get("domein", ""),
                "direction": dir_to_save,
                "feedback_group_impact": st.session_state.get(f"{label}_{idx}_q1", ""),
                "feedback_place_impact": st.session_state.get(f"{label}_{idx}_q2", ""),
                "feedback_distance": st.session_state.get(f"{label}_{idx}_q_reikwijdte", ""),
                "feedback_improvements": st.session_state.get(f"{label}_{idx}_q3", ""),
                "feedback_start": st.session_state.get(f"{label}_{idx}_q_start_year", 0),
                "group_id": gid,
            }

            r = post_json(base, payload, HEADERS, timeout=15)
            if r.status_code in (200, 201):
                ok += 1
            else:
                st.error(f"Opslaan mislukt voor “{row['text']}”: {r.status_code} {r.text}")

    st.success(f"Feedback opgeslagen ({ok} items).")
    st.session_state["group_answers_submitted"] = True
    st.switch_page("pages/14_Rapport.py")
