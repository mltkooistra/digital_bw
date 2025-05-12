import streamlit as st
import requests
import uuid

# -------------- edit per page----------
domain = "Welzijn"
domain_index = 8

next_domain = 'resultaten'

info_text = f'introductie tekst over {domain}'

# --- Setup ---
if "submission_id" not in st.session_state:
    st.session_state.submission_id = str(uuid.uuid4())

#--------NEXT PAGE BUTTON SETUP
if st.session_state.get("go_to_next_page"):
    del st.session_state["go_to_next_page"]  # clean up
    st.switch_page(f"pages/{domain_index + 1}_{next_domain}.py")

#----------page name-----------
st.set_page_config(page_title=f"Effect op {domain}", layout="wide")
st.title(f"Effect op {domain}")


# --- Access check ---
if "name" not in st.session_state or not st.session_state.name.strip():
    st.warning("⚠️ Vul eerst een code en/of gebruikersnaam in op de startpagina.")
    st.stop()

# --- Session state init ---
if domain not in st.session_state:
    st.session_state[domain] = {"positive": [], "negative": []}

st.markdown(f"""
 {info_text}
""")

# --- Form ---
with st.form("effects_form"):
    col_pos, col_neg = st.columns(2)

    with col_pos:
        st.header("✅ Positieve effecten")
        if st.form_submit_button("➕ Voeg positief effect toe", type="secondary"):
            st.session_state[domain]["positive"].append({"text": "", "score": 1, "posneg": 1})

        for i, entry in enumerate(st.session_state[domain]["positive"]):
            text_key = f"{domain}_positive_text_{i}"
            score_key = f"{domain}_positive_score_{i}"

            entry["text"] = st.text_area(f"Positief effect {i+1}", value=entry["text"], key=text_key)
            entry["score"] = st.slider(
                f"Hoe sterk is het effect op {domain}",
                min_value=1,
                max_value=5,
                value=entry["score"],
                key=score_key
            )

    with col_neg:
        st.header("❌ Negatieve effecten")
        if st.form_submit_button("➕ Voeg negatief effect toe", type="secondary"):
            st.session_state[domain]["negative"].append({"text": "", "score": 1, "posneg": -1})

        for i, entry in enumerate(st.session_state[domain]["negative"]):
            text_key = f"{domain}_negative_text_{i}"
            score_key = f"{domain}_negative_score_{i}"

            entry["text"] = st.text_area(f"Negatief effect {i+1}", value=entry["text"], key=text_key)
            entry["score"] = st.slider(
                f"Hoe sterk is het effect op {domain}",
                min_value=1,
                max_value=5,
                value=entry["score"],
                key=score_key
            )

    # Submit all effects
    submitted = st.form_submit_button("✅ Effecten opslaan")

# --- Save to Supabase ---
if submitted and not st.session_state.get(f"submitted_{domain_index}"):
    try:
        for effect_type in ["positive", "negative"]:
            for entry in st.session_state[domain][effect_type]:
                if entry["text"].strip():
                    requests.post(
                        f"{st.secrets['supabase_url']}/rest/v1/submissions",
                        headers={
                            "apikey": st.secrets["supabase_key"],
                            "Authorization": f"Bearer {st.secrets['supabase_key']}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "submission_id": st.session_state.submission_id,
                            "domain": domain,
                            "text": entry["text"],
                            "score": entry["score"],
                            "posneg": entry["posneg"],
                            "name": st.session_state.name,
                            "session": st.session_state.access_code
                        }
                    )
        st.success("Opgeslagen")
        st.session_state[f"submitted_{domain_index}"] = True
    except Exception as e:
        st.error(f"❌ Fout bij opslaan: {e}")

if st.session_state.get(f"submitted_{domain_index}"):
    st.button("➡️ Ga door naar de resultaten", on_click=lambda: st.session_state.update({"go_to_next_page": True}))