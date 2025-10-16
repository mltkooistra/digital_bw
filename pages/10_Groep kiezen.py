import streamlit as st
import requests

st.set_page_config(page_title="Kies je groep", layout="wide")
st.title("👥 Kies je groep")

# --- Basischecks ---
if "name" not in st.session_state or "access_code" not in st.session_state:
    st.error("Naam of sessiecode ontbreekt. Ga terug naar de startpagina.")
    st.stop()

session_code = st.session_state.access_code
display_name = st.session_state.name

# --- Aantal groepen ophalen uit meta ---
def fetch_n_groups():
    try:
        r = requests.get(
            f"{st.secrets['supabase_url']}/rest/v1/meta?select=n_groups&session=eq.{session_code}",
            headers={
                "apikey": st.secrets["supabase_key"],
                "Authorization": f"Bearer {st.secrets['supabase_key']}",
            },
            timeout=10,
        )
        if r.status_code == 200 and r.json():
            return int(r.json()[0].get("n_groups") or 1)
    except Exception:
        pass
    return int(st.session_state.get("n_groups", 1))

n_groups = max(1, fetch_n_groups())
st.info(f"Deze sessie heeft **{n_groups}** groep(en).")

# --- Keuze UI ---
group_options = [f"Groep {i}" for i in range(1, n_groups + 1)]

chosen = st.radio(
    "Kies jouw groep:",
    options=group_options,
    index=None,        # geen vooraf geselecteerde groep
    horizontal=True,
)

st.caption("Tip: spreek met je tafelgenoten af welke groepnummers jullie nemen.")

# --- Supabase helpers ---
HEADERS_JSON = {
    "apikey": st.secrets["supabase_key"],
    "Authorization": f"Bearer {st.secrets['supabase_key']}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def upsert_group_choice(session_code: str, username: str, group_name: str) -> bool:
    """
    Upsert into 'groups' so that if (session, name) already exists,
    the 'group' column is overwritten with the new value.
    Requires a UNIQUE constraint on (session, name) in the 'groups' table.
    """
    url_base = f"{st.secrets['supabase_url']}/rest/v1/groups"
    # Upsert via PostgREST: on_conflict + Prefer: resolution=merge-duplicates
    url = f"{url_base}?on_conflict=session,name"

    payload = {
        "session": session_code,
        "name": username,
        "group": group_name,
    }
    headers = {
        "apikey": st.secrets["supabase_key"],
        "Authorization": f"Bearer {st.secrets['supabase_key']}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            return True

        # Optional fallback if UNIQUE (session,name) isn’t set: do an update instead
        if resp.status_code == 409:
            patch_url = f"{url_base}?session=eq.{session_code}&name=eq.{username}"
            patch_headers = {
                "apikey": st.secrets["supabase_key"],
                "Authorization": f"Bearer {st.secrets['supabase_key']}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            }
            patch_resp = requests.patch(patch_url, headers=patch_headers, json={"group": group_name}, timeout=10)
            return patch_resp.status_code in (200, 204)
    except Exception:
        pass
    return False

# --- Doorgaan ---
if st.button("➡️ Doorgaan"):
    if chosen is None:
        st.warning("Kies eerst een groep voordat je verdergaat.")
    else:
        group_num = chosen.split()[-1]           # b.v. "Groep 3" -> "3"
        st.session_state["selected_group"] = group_num

        ok = upsert_group_choice(session_code, display_name, chosen)  # schrijft naar 'groups'
        if not ok:
            st.warning("Kon je keuze niet opslaan in de database. Probeer het later nog eens.")
        else:
            st.success(f"Je keuze is opgeslagen: **{chosen}**.")
            st.switch_page("pages/11_stemmen.py")
