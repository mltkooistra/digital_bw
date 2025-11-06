# effect_page.py
import streamlit as st
import requests
import uuid
import pandas as pd
from urllib.parse import quote  # for URL-safe name filter

def render_effect_page(*, domain: str, domain_index: int, next_domain: str):
    st.set_page_config(page_title=f"Effect op {domain}", layout="wide")
    st.title(f"Effect op {domain}")

    # --- Controle sessie ---
    required_vars = ["access_code", "info", "description", "prov", "name"]
    for v in required_vars:
        if v not in st.session_state:
            st.error(f"Sessiestatus '{v}' ontbreekt. Ga terug naar startpagina.")
            st.stop()

    current_name = str(st.session_state.name)

    # --- Unieke submission_id ---
    if "submission_id" not in st.session_state or not st.session_state["submission_id"]:
        st.session_state["submission_id"] = str(uuid.uuid4())

    # --- Config / constants ---
    BASE = f"{st.secrets['supabase_url']}/rest/v1/submissions"

    # --- Headers helper ---
    def headers(return_representation: bool = True):
        prefer = "return=representation" if return_representation else ""
        return {
            "apikey": st.secrets["supabase_key"],
            "Authorization": f"Bearer {st.secrets['supabase_key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": prefer,
        }

    # --- Nieuwe entry helper ---
    def _new_entry(direction: str, text: str = "", mode: str = "edit"):
        direction = "pos" if direction not in ("pos", "neg") else direction
        return {
            "id": str(uuid.uuid4()),
            "text": text,
            "score": 1,  # always 1, not shown
            "direction": direction,
            "mode": mode,
            "row_id": None,
        }

    # --- State initialiseren ---
    if domain not in st.session_state:
        st.session_state[domain] = {"positive": [], "negative": [], "loaded": False}

    # --- Laden van bestaande effecten (alleen van deze persoon) ---
    if not st.session_state[domain]["loaded"]:
        try:
            # URL-safe name for filters
            name_eq = quote(current_name, safe="")

            q = (
                f"?select=id,text,score,direction,posneg,submission_id,session,domain,name"
                f"&submission_id=eq.{st.session_state.submission_id}"
                f"&domain=eq.{domain}"
                f"&name=eq.{name_eq}"  # filter by same person
            )
            r = requests.get(BASE + q, headers=headers(), timeout=10)
            rows = r.json() if r.ok else []

            if not rows:
                # fallback: filter by current session + domain + name
                q2 = (
                    f"?select=id,text,score,direction,posneg,submission_id,session,domain,name"
                    f"&session=eq.{st.session_state.access_code}"
                    f"&domain=eq.{domain}"
                    f"&name=eq.{name_eq}"  # filter by same person
                )
                r2 = requests.get(BASE + q2, headers=headers(), timeout=10)
                rows = r2.json() if r2.ok else []

            # Extra safety: client-side filter by exact name
            rows = [row for row in rows if str(row.get("name", "")) == current_name]

            for row in rows:
                # Prefer 'direction'; fallback to legacy 'posneg'
                dir_val = row.get("direction")
                if not dir_val:
                    pn = row.get("posneg", None)
                    if pn is not None:
                        try:
                            dir_val = "pos" if int(pn) == 1 else "neg"
                        except Exception:
                            dir_val = "pos"
                    else:
                        dir_val = "pos"
                etype = "positive" if dir_val == "pos" else "negative"

                st.session_state[domain][etype].append({
                    "id": str(uuid.uuid4()),
                    "text": row.get("text", ""),
                    "score": 1,  # force 1 locally even if DB has something else
                    "direction": dir_val,
                    "mode": "view",
                    "row_id": row.get("id"),
                })
            st.session_state[domain]["loaded"] = True
        except Exception as e:
            st.warning(f"Kon eerdere antwoorden niet laden: {e}")

    # --- Domeininformatie laden ---
    try:
        info_df = pd.read_excel("domein_info.xlsx")
        info = info_df[info_df["domein"] == domain]
        info_text = info["introductietekst"].iloc[0]
        questions = info["hulpvragen"].iloc[0].split("-")
        question_list = "\n".join([f"- {q.strip()}" for q in questions if q.strip()])
        question_text = "<br>".join([q.strip() for q in questions])
        link = info["link_GR"].iloc[0] if st.session_state.prov == "GR" else info["link_DR"].iloc[0]
    except Exception:
        info_text, question_list, link = "", "", "#"

    # --- Info UI ---
    st.markdown(
        f"""
        <div style="position: absolute; top: 0; right: 0;">
          <a href="{link}" target="_blank"
             style="background-color:#f0f2f6;padding:6px 12px;border-radius:6px;
             text-decoration:none;color:#3366cc;font-weight:bold;font-size:14px;">
             Meer informatie over {domain}
          </a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        We zijn benieuwd naar de mogelijke effecten van **{st.session_state.description}** op **{domain}**.

        Klik op de blauwe tekst voor meer informatie

        <details>
        <summary style="cursor: pointer; font-weight: bold; color: #0b74de;">
            Waar gaat het domein {domain} over?
        </summary>
        <div style="margin-top: 8px;">
            {info_text}
        </div>
        </details>

        <details>
        <summary style="cursor: pointer; font-weight: bold; color: #0b74de;">
            Voorbeeldonderwerpen bij {domain}
        </summary>
        <div style="margin-top: 8px;">
            {question_text}
        </div>
        </details>
        """,
        unsafe_allow_html=True,
    )

    # =======================================================
    #  CRUD FUNCTIES
    # =======================================================
    def save_effect(effect):
        """Upsert; schrijft 'direction' (pos/neg) i.p.v. 'posneg'."""
        direction = effect.get("direction", "pos")
        if direction not in ("pos", "neg"):
            direction = "pos"

        data = {
            "submission_id": str(st.session_state.get("submission_id")),
            "domain": str(domain),
            "text": (effect.get("text") or " ").strip(),
            "score": 1,  # always 1 in DB
            "direction": direction,  # new field used
            "session": str(st.session_state.get("access_code", "")),
        }
        if st.session_state.get("name"):
            data["name"] = str(st.session_state["name"])

        try:
            # --- Lookup of er al iets bestaat ---
            row_id = effect.get("row_id")
            if not row_id:
                q = (
                    f"?select=id"
                    f"&submission_id=eq.{data['submission_id']}"
                    f"&domain=eq.{data['domain']}"
                    f"&text=eq.{quote(data['text'], safe='')}"
                )
                r_lookup = requests.get(BASE + q, headers=headers(False), timeout=10)
                if r_lookup.ok:
                    rows = r_lookup.json()
                    if isinstance(rows, list) and rows:
                        row_id = rows[0].get("id")
                        effect["row_id"] = row_id

            # --- PATCH of POST ---
            if row_id:
                url = f"{BASE}?id=eq.{row_id}"
                r = requests.patch(url, headers=headers(True), json=data, timeout=10)
            else:
                r = requests.post(BASE, headers=headers(True), json=data, timeout=10)

            r.raise_for_status()
            res = r.json()
            if isinstance(res, list) and res:
                effect["row_id"] = res[0].get("id")
            elif isinstance(res, dict) and "id" in res:
                effect["row_id"] = res["id"]

            st.toast("✅ Opgeslagen", icon="💾")
            return True
        except Exception as e:
            st.error(f"❌ Opslaan mislukt: {e}")
            return False

    def delete_effect(effect):
        """Verwijder effect uit Supabase."""
        if not effect.get("row_id"):
            return
        try:
            url = f"{BASE}?id=eq.{effect['row_id']}"
            r = requests.delete(url, headers=headers(False), timeout=10)
            r.raise_for_status()
            st.success("Verwijderd uit database.")
        except Exception as e:
            st.error(f"⚠️ Verwijderen mislukt: {e}")

    # =======================================================
    #  RENDER FUNCTIE
    # =======================================================
    def render_effect(effect, etype, idx):
        with st.container(border=True):
            if effect.get("mode") == "edit":
                effect["text"] = st.text_area(
                    "Beschrijf het effect",
                    value=effect.get("text", ""),
                    key=f"{etype}_txt_{effect['id']}",
                    height=100,
                )
                if st.button("💾 Opslaan", key=f"{etype}_save_{effect['id']}", use_container_width=True):
                    # ensure direction matches column type
                    effect["direction"] = "pos" if etype == "positive" else "neg"
                    effect["score"] = 1  # always 1 locally too
                    if save_effect(effect):
                        effect["mode"] = "view"
                        st.rerun()
            else:
                c1, c2 = st.columns([7, 1])
                with c1:
                    st.markdown(effect.get("text") or "_(geen tekst)_")
                with c2:
                    col_e, col_d = st.columns([1, 1])
                    with col_e:
                        if st.button("✏️", key=f"{etype}_edit_{effect['id']}"):
                            effect["mode"] = "edit"
                            st.rerun()
                    with col_d:
                        if st.button("🗑️", key=f"{etype}_del_{effect['id']}"):
                            delete_effect(effect)
                            st.session_state[domain][etype] = [
                                e for e in st.session_state[domain][etype] if e["id"] != effect["id"]
                            ]
                            st.rerun()

    # =======================================================
    #  UI
    # =======================================================
    col_pos, col_neg = st.columns(2)

    with col_pos:
        st.header("✅ Positieve effecten")
        for i, e in enumerate(st.session_state[domain]["positive"]):
            render_effect(e, "positive", i)
        if st.button("➕ Voeg positief effect toe"):
            st.session_state[domain]["positive"].append(_new_entry("pos"))
            st.rerun()

    with col_neg:
        st.header("❌ Negatieve effecten")
        for i, e in enumerate(st.session_state[domain]["negative"]):
            render_effect(e, "negative", i)
        if st.button("➕ Voeg negatief effect toe"):
            st.session_state[domain]["negative"].append(_new_entry("neg"))
            st.rerun()

    st.divider()
    st.info("Je kunt elk effect afzonderlijk opslaan of verwijderen.", icon="💡")

    if st.button(f"➡️ Ga door naar het volgende domein: {next_domain}"):
        st.switch_page(f"pages/{domain_index + 1}_{next_domain}.py")
