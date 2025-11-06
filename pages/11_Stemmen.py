import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import uuid
import difflib
import re
from collections import Counter
from urllib.parse import quote

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

if "vote_map" not in st.session_state:
    st.session_state.vote_map = {}

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
    if g is None or (isinstance(g, float) and pd.isna(g)):
        return None
    if isinstance(g, (int, float)):
        return int(g)
    m = re.search(r"(\d+)", str(g))
    return int(m.group(1)) if m else None

def normalize_name(s: str) -> str:
    if not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def majority_direction(series: pd.Series) -> str:
    if series is None or len(series) == 0:
        return "unknown"
    vals = []
    for v in series.tolist():
        if pd.isna(v) or str(v).strip() == "":
            continue
        sv = str(v).strip().lower()
        if sv in ("pos", "neg"):
            vals.append(sv)
            continue
        try:
            iv = int(float(v))  # legacy safety
            vals.append("pos" if iv == 1 else "neg" if iv == -1 else None)
        except Exception:
            continue
    vals = [v for v in vals if v in ("pos", "neg")]
    if not vals:
        return "unknown"
    c_pos = vals.count("pos")
    c_neg = vals.count("neg")
    if c_pos == c_neg:
        return "unknown"
    return "pos" if c_pos > c_neg else "neg"

def group_similar_effects(df_local, similarity_threshold=0.6):
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
    if not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())

# === NEW: check if another leader already exists for this group ===
def fetch_existing_leaders(*, session_code: str, group_value: str) -> list[dict]:
    """
    Returns rows with leader='yes' for (session, group).
    """
    base = f"{st.secrets['supabase_url']}/rest/v1/groups"
    q = (
        f"?select=id,name,group,leader&session=eq.{quote(session_code)}"
        f"&group=eq.{quote(group_value)}&leader=eq.yes"
    )
    try:
        r = requests.get(base + q, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            st.error(f"Kon leiders niet ophalen: {r.status_code} {r.text}")
            return []
        return r.json() or []
    except Exception as e:
        st.error(f"Fout bij ophalen leiders: {e}")
        return []

# === NEW: helper to set leader='yes' when user chooses to fill group questions ===
def set_group_leader_yes(*, session_code: str, name_value: str, group_value: str) -> bool:
    """
    Upsert leader='yes' into groups for the unique combination (session, name, group).
    Has a guard: if someone ELSE already has leader='yes', it refuses.
    """
    # Guard against races: check first
    leaders = fetch_existing_leaders(session_code=session_code, group_value=group_value)
    for row in leaders:
        if normalize_name(row.get("name", "")) != normalize_name(name_value):
            st.warning(f"Iemand anders ({row.get('name')}) is al als groepsleider gemarkeerd.")
            return False

    base = f"{st.secrets['supabase_url']}/rest/v1/groups"
    try:
        # 1) lookup existing row for (session, name, group)
        q = (
            f"?select=id&session=eq.{quote(session_code)}"
            f"&name=eq.{quote(name_value)}"
            f"&group=eq.{quote(group_value)}"
        )
        r_get = requests.get(base + q, headers=HEADERS, timeout=10)
        if r_get.status_code != 200:
            st.error(f"Kon groep niet ophalen: {r_get.status_code} {r_get.text}")
            return False
        rows = r_get.json() or []

        if rows:
            # 2) PATCH existing
            row_id = rows[0].get("id")
            r_patch = requests.patch(
                f"{base}?id=eq.{row_id}",
                headers={**HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"},
                json={"leader": "yes"},
                timeout=10,
            )
            if r_patch.status_code not in (200, 204):
                st.error(f"Kon leider niet bijwerken: {r_patch.status_code} {r_patch.text}")
                return False
            return True
        else:
            # 3) POST new
            r_post = requests.post(
                base,
                headers={**HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"},
                json={
                    "session": session_code,
                    "name": name_value,
                    "group": group_value,
                    "leader": "yes",
                },
                timeout=10,
            )
            if r_post.status_code not in (200, 201):
                st.error(f"Kon leider niet registreren: {r_post.status_code} {r_post.text}")
                return False
            return True
    except Exception as e:
        st.error(f"Fout bij instellen groepsleider: {e}")
        return False

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
    return pd.DataFrame(data) if data else pd.DataFrame()

@st.cache_data(ttl=15)
def fetch_votes():
    url = (
        f"{st.secrets['supabase_url']}/rest/v1/effect_votes"
        f"?select=session,text,domein,direction,votes&session=eq.{SESSION}"
    )
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return pd.DataFrame(columns=["text","domein","direction","votes"])
    data = r.json()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=["text","domein","direction","votes"])

@st.cache_data(ttl=15)
def fetch_groups_for_session():
    url = (
        f"{st.secrets['supabase_url']}/rest/v1/groups"
        f"?select=session,name,group,leader&session=eq.{SESSION}"
    )
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return pd.DataFrame(columns=["session", "name", "group", "leader"])
    data = r.json()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=["session", "name", "group", "leader"])

# =======================
# Ophalen + GROEP VIA NAAM (uit groups)
# =======================
df_submissions_all = fetch_submissions()
df = (
    df_submissions_all.drop_duplicates(subset=["name", "domain", "score", "text"])
    if not df_submissions_all.empty else pd.DataFrame()
)

if df.empty:
    st.info("Nog geen inzendingen.")
    st.stop()

groups_df = fetch_groups_for_session()
if groups_df.empty:
    st.error("Geen groepsindeling gevonden. Vraag de organisator om je in een groep te plaatsen.")
    st.stop()

# Normaliseer namen voor matching
df["name_norm"] = df["name"].astype(str).apply(normalize_name)
groups_df["name_norm"] = groups_df["name"].astype(str).apply(normalize_name)
current_user_norm = normalize_name(USERNAME)

# Bepaal groepnummer en label
groups_df["group_number"] = groups_df["group"].apply(parse_group_number)

my_row = groups_df.loc[groups_df["name_norm"] == current_user_norm].head(1)
if my_row.empty or pd.isna(my_row.iloc[0]["group_number"]):
    st.error("Je hebt geen groep toegewezen.")
    with st.expander("🔎 Debug: groups-gegevens"):
        st.write(groups_df)
    st.stop()

selected_group_num = int(my_row.iloc[0]["group_number"])
selected_group_label = (
    str(my_row.iloc[0]["group"])
    if "group" in my_row.columns and pd.notna(my_row.iloc[0]["group"])
    else f"Groep {selected_group_num}"
)

# Use the stored name from the groups row to avoid case/spacing mismatches
stored_name = str(my_row.iloc[0].get("name", USERNAME))

# --- Determine leader situation for your group ---
leaders_rows = fetch_existing_leaders(session_code=SESSION, group_value=selected_group_label)
leader_names_norm = {normalize_name(r.get("name", "")) for r in leaders_rows}
current_is_leader = current_user_norm in leader_names_norm
someone_else_is_leader = len(leader_names_norm - {current_user_norm}) > 0
someone_else_display = ", ".join(sorted({r.get("name","") for r in leaders_rows if normalize_name(r.get("name","")) != current_user_norm})) or None

# -----------------------
# Filter inzendingen op groepsleden
# -----------------------
groups_min = groups_df[["name_norm", "group_number", "group"]].drop_duplicates()
df_with_groups = df.merge(groups_min, on="name_norm", how="inner")

df_group = df_with_groups.loc[
    df_with_groups["group_number"] == selected_group_num
].copy()

# Zorg voor 'direction' met fallback op legacy 'posneg'
if "direction" not in df_group.columns:
    df_group["direction"] = None
if "posneg" in df_group.columns:
    df_group.loc[df_group["direction"].isna(), "direction"] = (
        df_group["posneg"].apply(lambda x: "pos" if pd.notna(x) and str(x).strip() not in ("", "0") and int(float(x)) == 1
                                 else ("neg" if pd.notna(x) and str(x).strip() != "" and int(float(x)) == -1
                                       else None))
    )
df_group["direction"] = df_group["direction"].fillna("unknown")

# UI: status & tellingen
st.info(f"Je stemt binnen **{selected_group_label}**.")
st.text(
    f"Aantal groepsleden met inzendingen: {df_group['name_norm'].nunique()} \n"
    f"Aantal inzendingen: {len(df_group)}"
)

if someone_else_is_leader and someone_else_display:
    st.warning(f"📌 {someone_else_display} is al groepsleider voor **{selected_group_label}**.")

if df_group.empty:
    st.warning("Wacht op inzendingen")
    with st.expander("🔎 Debug: mogelijke naam-mismatches"):
        group_members_norm = groups_df.loc[
            groups_df["group_number"] == selected_group_num, "name_norm"
        ].dropna().unique().tolist()
        submitters_norm = df["name_norm"].dropna().unique().tolist()
        missing_submitters = sorted(set(group_members_norm) - set(submitters_norm))
        st.write({"groep_leden_zonder_inzending": missing_submitters})
    st.stop()

vote_data = fetch_votes()  # rows unique per (session, text, domein, direction)

# =======================
# Polariteit per tekst (direction) uit submissions (van jouw groep)
# =======================
text_direction_map = {}
if {"text", "direction"}.issubset(df_group.columns):
    tmp = df_group.copy()
    tmp["text_norm"] = tmp["text"].map(norm_text)
    sub_agg = (
        tmp.groupby("text_norm", dropna=False)["direction"]
        .apply(majority_direction)
        .reset_index(name="direction_majority")
    )
    text_direction_map = {
        r["text_norm"]: (r["direction_majority"] or "unknown")
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

    if "direction" not in df_dom.columns:
        df_dom["direction"] = "unknown"

    grouped_indices = group_similar_effects(df_dom, similarity_threshold=0.6)

    for idx, group in enumerate(grouped_indices):
        rows = df_dom.loc[group]
        texts = [str(t) for t in rows["text"].tolist() if str(t).strip() != ""]
        authors = rows["name"].dropna().unique().tolist()

        merged_text = " / ".join(texts) if texts else "(geen tekst)"
        group_id = f"{SESSION}_{selected_group_num}_{slugify(str(dom))}_{idx}"

        # majority direction for this merged item
        text_norms = [norm_text(t) for t in texts]
        component_dirs = [text_direction_map.get(tn, "unknown") for tn in text_norms if tn != ""]
        dir_majority = majority_direction(pd.Series(component_dirs, dtype="object"))

        # read total votes by unique key (session, text, domein, direction)
        total_votes = 0
        if not vote_data.empty:
            mask = (
                (vote_data["text"] == merged_text) &
                (vote_data["domein"] == dom) &
                (vote_data["direction"] == dir_majority)
            )
            try:
                total_votes = int(pd.to_numeric(vote_data.loc[mask, "votes"]).sum())
            except Exception:
                total_votes = 0

        effect_groups.append({
            "text": merged_text,
            "group_id": group_id,          # only for UI de-dupe per user
            "votes": total_votes,
            "authors": authors,
            "domain": dom,
            "direction": dir_majorority if (dir_majorority := dir_majority) else "unknown",
        })

# =======================
# Atomic-ish vote upsert (unique by session,text,domein,direction)
# =======================
def upsert_increment_vote(*, text: str, domein: str, direction: str, delta: int, group_label: str, group_id: str):
    """
    1) Try to find existing row for (session,text,domein,direction)
    2) If found -> PATCH votes = current + delta
    3) If not found -> POST new row with votes = delta
    Note: This is read-modify-write; for heavy concurrency, prefer a SQL RPC.
    """
    d = (direction or "").strip().lower()
    if d not in ("pos", "neg"):
        d = "unknown"

    base = f"{st.secrets['supabase_url']}/rest/v1/effect_votes"
    q = (
        f"?session=eq.{quote(SESSION)}"
        f"&text=eq.{quote(text)}"
        f"&domein=eq.{quote(domein)}"
        f"&direction=eq.{quote(d)}"
        f"&select=id,votes"
    )

    # 1) lookup
    try:
        r_get = requests.get(base + q, headers=HEADERS, timeout=10)
        if r_get.status_code != 200:
            st.error(f"Kon stemmen niet ophalen: {r_get.status_code} {r_get.text}")
            return False
        rows = r_get.json() or []
    except Exception as e:
        st.error(f"Kon stemmen niet ophalen: {e}")
        return False

    now_iso = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    if rows:
        # 2) PATCH existing
        row = rows[0]
        row_id = row.get("id")
        current = 0
        try:
            current = int(row.get("votes") or 0)
        except Exception:
            current = 0
        new_votes = current + int(delta)

        try:
            r_patch = requests.patch(
                f"{base}?id=eq.{row_id}",
                headers={**HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"},
                json={"votes": new_votes, "last_updated": now_iso},
                timeout=10,
            )
            if r_patch.status_code not in (200, 204):
                st.error(f"Kon stem niet bijwerken: {r_patch.status_code} {r_patch.text}")
                return False
        except Exception as e:
            st.error(f"Kon stem niet bijwerken: {e}")
            return False
    else:
        # 3) POST new
        try:
            r_post = requests.post(
                base,
                headers={**HEADERS, "Content-Type": "application/json", "Prefer": "return=representation"},
                json={
                    "session": SESSION,
                    "group": selected_group_label,
                    "group_id": group_id,    # for UI/debug; not part of uniqueness
                    "text": text,
                    "domein": domein,
                    "direction": d,
                    "votes": int(delta),
                    "last_updated": now_iso,
                },
                timeout=10,
            )
            if r_post.status_code not in (200, 201):
                st.error(f"Kon stem niet registreren: {r_post.status_code} {r_post.text}")
                return False
        except Exception as e:
            st.error(f"Kon stem niet registreren: {e}")
            return False

    return True

# Wrapper used by UI
def register_vote(effect, delta: int):
    ok = upsert_increment_vote(
        text=effect["text"],
        domein=effect["domain"],
        direction=effect.get("direction", "unknown"),
        delta=delta,
        group_label=selected_group_label,
        group_id=effect["group_id"],
    )
    if ok:
        st.session_state.voted_ids.add(effect["group_id"])
    return ok

# =======================
# Vote buttons (Belangrijk / Onbelangrijk)
# =======================
def vote_buttons(effect):
    # Niet op eigen effect stemmen
    if normalize_name(st.session_state.name) in [normalize_name(a) for a in effect.get("authors", [])]:
        st.info("Je kunt niet stemmen op je eigen effect.")
        return

    # Niet dubbel stemmen
    if effect["group_id"] in st.session_state.voted_ids:
        st.caption("✅ Stem geregistreerd voor dit effect.")
        return

    # Style
    st.markdown(
        """
        <style>
        div.small-vote-button > button {
            font-size: 0.85rem !important;
            padding: 0.25rem 0.6rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    vote_cols = st.columns(2)

    # Belangrijk = +1
    with vote_cols[0]:
        st.markdown('<div class="small-vote-button">', unsafe_allow_html=True)
        if st.button("Belangrijk", key=f"up_{effect['group_id']}"):
            if st.session_state.upvotes_used < MAX_UPVOTES:
                if register_vote(effect, +1):
                    st.session_state.upvotes_used += 1
                    st.session_state.vote_map[effect["group_id"]] = "up"
                    st.rerun()
            else:
                st.warning("Max upvotes bereikt.")
        st.markdown('</div>', unsafe_allow_html=True)

    # Onbelangrijk = -1
    with vote_cols[1]:
        st.markdown('<div class="small-vote-button">', unsafe_allow_html=True)
        if st.button("Onbelangrijk", key=f"down_{effect['group_id']}"):
            if st.session_state.downvotes_used < MAX_DOWNVOTES:
                if register_vote(effect, -1):
                    st.session_state.downvotes_used += 1
                    st.session_state.vote_map[effect["group_id"]] = "down"
                    st.rerun()
            else:
                st.warning("Max downvotes bereikt.")
        st.markdown('</div>', unsafe_allow_html=True)

#_____________
# UI
# =======================

st.markdown(
    """
    <style>
    div.stButton > button[data-testid="baseButton-secondary"]{
        font-size: 0.85rem;
        padding: 0.25rem 0.55rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.subheader("🗳️ Stem op effecten!")
st.markdown(
    f"Stemmen gebruikt: Belangrijk {st.session_state.upvotes_used} / {MAX_UPVOTES} "
    f" |  Onbelangrijk {st.session_state.downvotes_used} / {MAX_DOWNVOTES}"
)
st.markdown(f"Je stemt binnen **{selected_group_label}**.")

# Huidige lijst (niet eigen / niet al gestemd)
effect_groups_shuffled = [
    e for e in effect_groups
    if e["group_id"] not in st.session_state.voted_ids
    and normalize_name(st.session_state.name) not in [normalize_name(a) for a in e.get("authors", [])]
]

if not effect_groups_shuffled:
    st.success("Niets meer om te stemmen binnen je groep. 🎉")
else:
    cols = st.columns(3)
    for idx, effect in enumerate(effect_groups_shuffled):
        with cols[idx % 3]:
            with st.container(border=True):
                st.markdown(f"**{effect['text']}**")
                dir_label = (
                    "Positief" if effect.get("direction") == "pos"
                    else "Negatief" if effect.get("direction") == "neg"
                    else "Onbekend"
                )
                st.caption(f"Domein: {effect['domain']} • {dir_label}")
                vote_buttons(effect)

# =======================
# Navigatie naar groepsopdracht
# =======================
st.divider()
col1, col2 = st.columns(2)

# Show only "meekijken" if another leader exists.
if someone_else_is_leader and not current_is_leader:
    with col2:
        if st.button("📄 Bekijk de vragen voor de groepsopdracht"):
            st.session_state["group_question_filler"] = False
            st.session_state["selected_group"] = selected_group_num
            st.switch_page("pages/13_meekijken.py")
else:
    # Either no leader yet, or YOU are the leader → show both buttons
    with col1:
        if st.button("➡️ Klik hier om de groepsvragen in te vullen"):
            ok = set_group_leader_yes(
                session_code=SESSION,
                name_value=stored_name,
                group_value=selected_group_label
            )
            if ok:
                st.session_state["group_question_filler"] = True
                st.session_state["selected_group"] = selected_group_num
                st.switch_page("pages/12_Gezamenlijke opdracht.py")
            else:
                st.warning("Kon je niet als groepsleider registreren. Kies 'meekijken' of probeer opnieuw.")
    with col2:
        if st.button("📄 Klik hier als iemand anders de groepsvragen namens je groep invult"):
            st.session_state["group_question_filler"] = False
            st.session_state["selected_group"] = selected_group_num
            st.switch_page("pages/13_Meekijken.py")

# =======================
# JE STEMMEN (undo = tegenovergestelde delta)
# =======================
st.divider()
st.subheader("🧾 Je stemmen")

def remove_vote(effect_obj: dict):
    effect_id = effect_obj["group_id"]
    vote_kind = st.session_state.vote_map.get(effect_id)

    # Reverse the previous action on the same unique key
    delta = -1 if vote_kind == "up" else +1 if vote_kind == "down" else 0
    if delta != 0:
        upsert_increment_vote(
            text=effect_obj["text"],
            domein=effect_obj["domain"],
            direction=effect_obj.get("direction", "unknown"),
            delta=delta,
            group_label=selected_group_label,
            group_id=effect_id,
        )

    # Update lokale UI-state
    if vote_kind == "up" and st.session_state.upvotes_used > 0:
        st.session_state.upvotes_used -= 1
    elif vote_kind == "down" and st.session_state.downvotes_used > 0:
        st.session_state.downvotes_used -= 1

    if effect_id in st.session_state.voted_ids:
        try:
            st.session_state.voted_ids.remove(effect_id)
        except Exception:
            st.session_state.voted_ids = {vid for vid in st.session_state.voted_ids if vid != effect_id}

    if effect_id in st.session_state.vote_map:
        del st.session_state.vote_map[effect_id]

voted_effects = [e for e in effect_groups if e["group_id"] in st.session_state.voted_ids]

if not voted_effects:
    st.info("Je hebt nog geen stemmen uitgebracht.")
else:
    cols = st.columns(3)
    for idx, e in enumerate(voted_effects):
        with cols[idx % 3]:
            with st.container(border=True):
                st.markdown(f"**{e['text']}**")
                dir_label = (
                    "Positief" if e.get("direction") == "pos"
                    else "Negatief" if e.get("direction") == "neg"
                    else "Onbekend"
                )

                my_vote = st.session_state.vote_map.get(e["group_id"], "?")
                my_vote_label = "Belangrijk" if my_vote == "up" else "Onbelangrijk" if my_vote == "down" else "Nog niet beoordeeld"

                st.caption(f"🗳️ {my_vote_label} • Domein: {e['domain']} • {dir_label}")

                if st.button("Stem verwijderen", key=f"unvote_{e['group_id']}"):
                    remove_vote(e)
                    st.rerun()
