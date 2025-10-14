# effect_page.py
import streamlit as st
import requests
import uuid
import pandas as pd

def render_effect_page(*, domain: str, domain_index: int, next_domain: str):
    st.set_page_config(page_title=f"Effect op {domain}", layout="wide")
    st.title(f"Effect op {domain}")

    # --- Controle sessie ---
    required_vars = ["access_code", "info", "description", "prov"]
    for v in required_vars:
        if v not in st.session_state:
            st.error(f"Sessiestatus '{v}' ontbreekt. Ga terug naar startpagina.")
            st.stop()

    # --- Unieke submission_id ---
    if "submission_id" not in st.session_state or not st.session_state["submission_id"]:
        st.session_state["submission_id"] = str(uuid.uuid4())

    # --- Config / constants ---
    BASE = f"{st.secrets['supabase_url']}/rest/v1/submissions"
    SCORE_MIN, SCORE_MAX = 1, 5
    SCORE_HELP = "1 = verwaarloosbaar · 2 = beperkt · 3 = merkbaar · 4 = sterk · 5 = zeer sterk"

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
    def _new_entry(posneg: int, text: str = "", score: int = SCORE_MIN, mode: str = "edit"):
        return {
            "id": str(uuid.uuid4()),
            "text": text,
            "score": score,
            "posneg": posneg,
            "mode": mode,
            "row_id": None,
        }

    # --- State initialiseren ---
    if domain not in st.session_state:
        st.session_state[domain] = {"positive": [], "negative": [], "loaded": False}

    # --- Laden van bestaande effecten ---
    if not st.session_state[domain]["loaded"]:
        try:
            q = (
                f"?select=id,text,score,posneg,submission_id,session,domain"
                f"&submission_id=eq.{st.session_state.submission_id}"
                f"&domain=eq.{domain}"
            )
            r = requests.get(BASE + q, headers=headers(), timeout=10)
            rows = r.json() if r.ok else []
            if not rows:
                q2 = (
                    f"?select=id,text,score,posneg,submission_id,session,domain"
                    f"&session=eq.{st.session_state.access_code}"
                    f"&domain=eq.{domain}"
                )
                r2 = requests.get(BASE + q2, headers=headers(), timeout=10)
                rows = r2.json() if r2.ok else []
            for row in rows:
                etype = "positive" if int(row.get("posneg", 0)) == 1 else "negative"
                st.session_state[domain][etype].append({
                    "id": str(uuid.uuid4()),
                    "text": row.get("text", ""),
                    "score": int(row.get("score", SCORE_MIN)),
                    "posneg": int(row.get("posneg", 0)),
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
        We zijn benieuwd naar de mogelijke effecten van 
        <span title="{st.session_state.info}"
              style="border-bottom:1px dotted #999;cursor:help;">
        {st.session_state.description}</span> 
        op {domain}.

        {info_text}

        Denk bijvoorbeeld aan de volgende vragen:

        {question_list}
        """,
        unsafe_allow_html=True,
    )

    # =======================================================
    #  CRUD FUNCTIES
    # =======================================================
    def save_effect(effect):
        """Upsert zonder on_conflict; altijd geldige score binnen 1–5."""
        score_val = int(effect.get("score", SCORE_MIN))
        score_val = max(SCORE_MIN, min(SCORE_MAX, score_val))

        data = {
            "submission_id": str(st.session_state.get("submission_id")),
            "domain": str(domain),
            "text": (effect.get("text") or " ").strip(),
            "score": score_val,
            "posneg": int(effect.get("posneg", 0)),
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
                    f"&text=eq.{data['text']}"
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
                c1, c2 = st.columns([3, 1])
                with c1:
                    effect["text"] = st.text_area(
                        "Beschrijf het effect",
                        value=effect.get("text", ""),
                        key=f"{etype}_txt_{effect['id']}",
                        height=100,
                    )
                with c2:
                    start_score = int(effect.get("score", SCORE_MIN))
                    start_score = max(SCORE_MIN, min(SCORE_MAX, start_score))
                    effect["score"] = st.slider(
                        "Hoe sterk?", SCORE_MIN, SCORE_MAX, start_score,
                        key=f"{etype}_score_{effect['id']}", help=SCORE_HELP
                    )
                    if st.button("💾 Opslaan", key=f"{etype}_save_{effect['id']}", use_container_width=True):
                        if save_effect(effect):
                            effect["mode"] = "view"
                            st.rerun()
            else:
                c1, c2, c3 = st.columns([6, 1, 1])
                with c1:
                    st.markdown(f"**Score {effect['score']}** – {effect['text'] or '_(geen tekst)_'}")
                    if effect.get("row_id"):
                        st.caption(f"Row ID: `{effect['row_id']}`")
                with c2:
                    if st.button("✏️", key=f"{etype}_edit_{effect['id']}"):
                        effect["mode"] = "edit"
                        st.rerun()
                with c3:
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
            st.session_state[domain]["positive"].append(_new_entry(1))
            st.rerun()

    with col_neg:
        st.header("❌ Negatieve effecten")
        for i, e in enumerate(st.session_state[domain]["negative"]):
            render_effect(e, "negative", i)
        if st.button("➕ Voeg negatief effect toe"):
            st.session_state[domain]["negative"].append(_new_entry(-1))
            st.rerun()

    st.divider()
    st.info("Je kunt elk effect afzonderlijk opslaan of verwijderen.", icon="💡")

    if st.button("➡️ Ga door naar het volgende domein"):
        st.switch_page(f"pages/{domain_index + 1}_{next_domain}.py")
