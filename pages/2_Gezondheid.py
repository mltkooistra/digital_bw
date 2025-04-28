import streamlit as st
import requests
import uuid
import pandas as pd


# -------------- edit per page----------
domain = "Gezondheid"
domain_index = 2

next_domain = "Arbeid en vrije tijd"

#---get domain info

#---get domain info

info = pd.read_excel('domein_info.xlsx')

info = info[info['domein'] == domain]
info_text = info['introductietekst'].iloc[0]
questions = info['hulpvragen'].iloc[0].split('-')
question_list = "\n".join([f"- {question.strip()}" for question in questions if question.strip()])

link = info['link_GR'].iloc[0] if st.session_state.prov == 'GR' else info['link_DR'].iloc[0]










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


#---- information section
#more info button with link 

st.markdown(f"""
<div style="position: absolute; top: 0; right: 0;">
    <a href="{link}" target="_blank" style="background-color: #f0f2f6; padding: 6px 12px; border-radius: 6px; text-decoration: none; color: #3366cc; font-weight: bold; font-size: 14px;">
        Meer informatie over {domain}
    </a>
</div>
""", unsafe_allow_html=True)

# tekst
st.markdown(f"""
We zijn benieuwd naar de mogelijke effecten van 
<span title="{st.session_state.info}" style="border-bottom: 1px dotted #999; cursor: help;">
{st.session_state.description}
</span> 
op {domain}.

{info_text}

Denk bijvoorbeeld aan de volgende vragen:

{question_list}
""", unsafe_allow_html=True)



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
    st.button("➡️ Ga door naar het volgende domein", on_click=lambda: st.session_state.update({"go_to_next_page": True}))