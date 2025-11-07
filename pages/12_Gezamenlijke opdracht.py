# pages/12_Gezamenlijke opdracht.py
import streamlit as st
import pandas as pd
import numpy as np
import requests
import math
import json
from collections import Counter
import re
from urllib.parse import quote
from datetime import datetime, date, timezone

# =========================
# Page config
# =========================
st.set_page_config(page_title="Verdiepingsopdracht", layout="wide")
st.title("Verdiepingsopdracht")

# --- Quick toggle to see server responses & run a probe insert ---
diagnose = st.sidebar.checkbox("🔧 Diagnose mode (toon server-antwoorden)", value=False)

# --- Basischecks ---
if "name" not in st.session_state or "access_code" not in st.session_state:
    st.error("Naam of sessiecode ontbreekt. Ga terug naar de startpagina.")
    st.stop()
if "group_question_filler" not in st.session_state:
    st.error("Deze pagina is niet direct toegankelijk.")
    st.stop()

session_code = st.session_state.access_code     # REQUIRED by group_results
display_name = st.session_state.name

# --- Groep info ---
selected_group = str(st.session_state.get("selected_group", "1"))
group_name = f"Groep {selected_group}"         # REQUIRED by group_results
st.info(f"Je zit in **{group_name}**.")

# Headers voor Supabase
BASE_URL = st.secrets['supabase_url']
HEADERS = {
    "apikey": st.secrets["supabase_key"],
    "Authorization": f"Bearer {st.secrets['supabase_key']}",
    "Content-Type": "application/json",
    # Upsert-friendly: merge duplicates on the unique key and return rows
    "Prefer": "return=representation,resolution=merge-duplicates",
}

# =========================
# JSON sanitizers (containers first; no empty-array truthiness)
# =========================
def _is_scalar(x) -> bool:
    return np.isscalar(x) or isinstance(
        x, (str, bytes, datetime, date, pd.Timestamp, np.generic, bool)
    )

def _is_na_like(x) -> bool:
    if x is None:
        return True
    if not _is_scalar(x):
        return False
    try:
        return bool(pd.isna(x))
    except Exception:
        return False

def _to_builtin_number(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        xf = float(x)
        if math.isnan(xf) or math.isinf(xf):
            return None
        return xf
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    return x

def _to_serializable_datetime(x):
    if isinstance(x, (pd.Timestamp, datetime)):
        if isinstance(x, datetime) and x.tzinfo is None:
            x = x.replace(tzinfo=timezone.utc)
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
    # 0) dict first
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    # 1) pandas containers
    if isinstance(value, pd.Series):
        return json_safe(value.to_dict())
    if isinstance(value, pd.DataFrame):
        return [json_safe(r) for r in value.to_dict(orient="records")]
    # 2) iterables
    if isinstance(value, (np.ndarray, list, tuple, set)):
        return [json_safe(v) for v in list(value)]
    # 3) scalars
    if _is_na_like(value):
        return None
    value = _to_builtin_number(value)
    value = _to_serializable_datetime(value)
    # 4) numpy scalars
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.str_, np.bytes_)):
        return str(value)
    return value

def _assert_jsonable(payload):
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
    row = get_my_group_row(session_code, name_value, group_value)
    if row:
        return row
    base = f"{BASE_URL}/rest/v1/groups"
    payload = {"session": session_code, "name": name_value, "group": group_value, "leader": "no"}
    r = post_json(base, payload, HEADERS, timeout=10)
    if r.status_code not in (200, 201):
        st.error(f"Kon groepsrecord niet aanmaken: {r.status_code} {r.text}")
        return None
    rows = r.json() or []
    return rows[0] if rows else None

def take_over_leadership(session_code: str, name_value: str, group_value: str) -> bool:
    my_row = ensure_current_row_exists(session_code, name_value, group_value)
    if not my_row:
        return False

    base = f"{BASE_URL}/rest/v1/groups"
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

    try:
        r_patch = patch_json(f"{base}?id=eq.{my_row['id']}", {"leader": "yes"}, HEADERS, timeout=10)
        if r_patch.status_code not in (200, 204):
            st.error(f"Kon leiderschap niet overnemen: {r_patch.status_code} {r_patch.text}")
            return False
    except Exception as e:
        st.error(f"Kon leiderschap niet overnemen: {e}")
        return False

    return True

def majority_direction(series: pd.Series):
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

# --- OPTIONS ---
REACH_OPTIONS = [
    "individueel/huishouden", "de buurt", "wijk/dorp", "stad of gemeente",
    "provincie", "landelijk", "internationaal",
]
WHEN_OPTIONS = ["direct", "weken", "maanden", "jaren", "meer dan 15 jaar"]

# =========================
# Feedback UI
# =========================
def feedback_ui(row, idx, label):
    st.markdown(f"### {row.get('domein','')}: {row['text']}")
    st.text_input(
        "1. Voor wie is dit effect het grootst? (bijv. huiseigenaren, mensen met een laag inkomen, ouderen, jongeren, etc.)",
        key=f"{label}_{idx}_q1"
    )
    st.multiselect(
        "2. Hoe ver reikt het effect? (meerdere antwoorden mogelijk)",
        options=REACH_OPTIONS,
        default=[],
        help="Kies alle niveaus waarop het effect relevant is.",
        key=f"{label}_{idx}_q_reikwijdte_list",
    )
    st.selectbox(
        "3. Wanneer verwacht je dat het effect zichtbaar wordt?",
        options=WHEN_OPTIONS,
        index=0,
        help="Kies de orde van grootte tot het effect zichtbaar is.",
        key=f"{label}_{idx}_q_start_cat",
    )
    if label.lower().startswith("pos"):
        q4_label = "4. Zijn er aanpassingen mogelijk om het effect te versterken? (overslaan mogelijk)"
    else:
        q4_label = "4. Zijn er aanpassingen mogelijk aan de interventie om dit effect te beperken of voorkomen?"
    st.text_input(q4_label, key=f"{label}_{idx}_q3")
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
                st.rerun()
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
        .apply(lambda s: s.dropna().tolist())
        .reset_index(name="dirs")
    )
    sub_agg["dir_maj"] = sub_agg["dirs"].apply(lambda lst: majority_direction(pd.Series(lst)))
    direction_from_sub = {r["text_norm"]: r["dir_maj"] for _, r in sub_agg.iterrows() if r["text_norm"] != ""}

# =========================
# Aggregate ALL voted items
# =========================
def _maj_dir_from_series(s):
    return majority_direction(pd.Series([v for v in s if pd.notna(v)]))

agg = (
    df_votes.groupby("group_id", dropna=False)
    .agg(
        votes=("votes", "sum"),
        text=("text", "first"),
        domein=("domein", "first"),
        direction_votes=("direction", _maj_dir_from_series),
    )
    .reset_index()
)

# Resolve direction from submissions if available
agg["text_norm"] = agg["text"].map(norm_text)
agg["direction_from_sub"] = agg["text_norm"].map(direction_from_sub)

def pick_direction(row):
    if pd.notna(row.get("direction_from_sub")):
        return row["direction_from_sub"]
    return row.get("direction_votes")

agg["direction_resolved"] = agg.apply(pick_direction, axis=1)

# =========================
# UI (render top-3 pos/neg for inputs)
# =========================
top_pos = (
    agg[agg["direction_resolved"] == "pos"]
    .sort_values("votes", ascending=False)
    .head(3).reset_index(drop=True)
)
top_neg = (
    agg[agg["direction_resolved"] == "neg"]
    .sort_values("votes", ascending=False)
    .head(3).reset_index(drop=True)
)

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
# Helpers: insert with retry if jsonb mismatch, + optional probe
# =========================
UPSERT_URL = f"{BASE_URL}/rest/v1/group_results?on_conflict=session,%22group%22,text"

def try_insert(payload: dict):
    """
    1) Try as-is (arrays for feedback_*).
    2) If 400/415 with json type complaints, retry once converting lists -> JSON strings.
    Returns (ok: bool, status: int, text: str)
    """
    r = post_json(UPSERT_URL, payload, HEADERS, timeout=15)
    if r.status_code in (200, 201):
        return True, r.status_code, r.text

    err_txt = (r.text or "").lower()
    needs_string_retry = ("jsonb" in err_txt or "type" in err_txt or "invalid input syntax for type" in err_txt)

    if needs_string_retry:
        payload2 = payload.copy()
        for k in ("feedback_place_impact", "feedback_distance"):
            v = payload2.get(k, [])
            if isinstance(v, list):
                payload2[k] = json.dumps(v, ensure_ascii=False)
        r2 = post_json(UPSERT_URL, payload2, HEADERS, timeout=15)
        if r2.status_code in (200, 201):
            return True, r2.status_code, r2.text
        return False, r2.status_code, r2.text

    return False, r.status_code, r.text

def probe_insert():
    """
    Insert a harmless probe row to reveal RLS / type issues up front.
    Will upsert the same key so it won't accumulate.
    """
    payload = {
        "session": session_code,
        "group": group_name,
        "text": "__probe__",
        "domein": "",
        "direction": None,
        "feedback_group_impact": "",
        "feedback_place_impact": [],     # will retry as string if needed
        "feedback_distance": [],
        "feedback_improvements": "",
        "feedback_start": "direct",
    }
    ok, status, txt = try_insert(payload)
    return ok, status, txt

# =========================
# Save EVERY effect to public.group_results via UPSERT
# (unique key: session,"group",text)
# =========================
if st.button("✅ Versturen"):
    # -- optional probe first so we fail fast with a clear message --
    if diagnose:
        pok, pstatus, ptxt = probe_insert()
        st.info(f"Probe insert -> ok={pok}, status={pstatus}")
        if not pok:
            st.error("Probe insert is mislukt. Waarschijnlijk RLS of type-mismatch.")
            if ptxt:
                st.code(ptxt, language="json")
            st.stop()

    ok = 0
    rows_debug = []

    for idx_all, row in agg.sort_values("votes", ascending=False).reset_index(drop=True).iterrows():
        # Map UI inputs if this effect was visible in the top lists
        label = None
        ui_idx = None
        for i, rpos in top_pos.iterrows():
            if rpos["text"] == row["text"]:
                label, ui_idx = "Pos", i
                break
        if label is None:
            for i, rneg in top_neg.iterrows():
                if rneg["text"] == row["text"]:
                    label, ui_idx = "Neg", i
                    break

        # Defaults if not in UI
        reach_list = []
        when_choice = WHEN_OPTIONS[0]
        q1 = ""
        q3 = ""

        if label is not None:
            reach_list = st.session_state.get(f"{label}_{ui_idx}_q_reikwijdte_list", []) or []
            when_choice = st.session_state.get(f"{label}_{ui_idx}_q_start_cat", WHEN_OPTIONS[0])
            q1 = st.session_state.get(f"{label}_{ui_idx}_q1", "") or ""
            q3 = st.session_state.get(f"{label}_{ui_idx}_q3", "") or ""

        # Safe, non-empty text to satisfy RLS WITH CHECK and upsert key
        safe_text = (row.get("text") or "").strip() or "(zonder tekst)"

        payload = {
            "session": session_code,                     # unique key part
            "group": group_name,                         # unique key part
            "text": safe_text,                           # unique key part
            "domein": row.get("domein", ""),             # requires column in table (else ignored)
            "direction": row.get("direction_resolved", None),
            "feedback_group_impact": q1,
            "feedback_place_impact": reach_list,         # json array (retry will send as string)
            "feedback_distance": reach_list,             # mirror legacy
            "feedback_improvements": q3,
            "feedback_start": when_choice,
        }

        ins_ok, status, txt = try_insert(payload)
        if diagnose:
            rows_debug.append({
                "text": safe_text,
                "status": status,
                "ok": ins_ok,
                "response": txt[:500] if isinstance(txt, str) else str(txt)
            })

        if ins_ok:
            ok += 1
        else:
            st.error(f"Opslaan mislukt voor “{safe_text}”: {status}")
            if txt:
                st.code(txt, language="json")

    if diagnose:
        st.subheader("📜 Insert log")
        if rows_debug:
            st.dataframe(pd.DataFrame(rows_debug))

    st.success(f"Feedback opgeslagen/bijgewerkt ({ok} items).")
    st.session_state["group_answers_submitted"] = True
    st.switch_page("pages/14_Rapport.py")
