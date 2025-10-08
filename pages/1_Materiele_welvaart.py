import streamlit as st
import requests
import uuid
import pandas as pd

# -------------- edit per page----------
domain = "Materiële welvaart"
domain_index = 1
next_domain = "Gezondheid"

# --- Setup page ---
st.set_page_config(page_title=f"Effect op {domain}", layout="wide")
st.title(f"Effect op {domain}")

# --- Initialize required session variables ---
required_session_vars = ["name", "access_code", "info", "description", "prov"]
for var in required_session_vars:
    if var not in st.session_state:
        st.error(f"Sessiestatus '{var}' ontbreekt. Ga terug naar startpagina.")
        st.stop()

if "submission_id" not in st.session_state:
    st.session_state.submission_id = str(uuid.uuid4())

if domain not in st.session_state:
    st.session_state[domain] = {"positive": [], "negative": []}
    # --- Load previous answers ONLY on first run ---
    response = requests.get(
        f"{st.secrets['supabase_url']}/rest/v1/submissions?name=eq.{st.session_state.name}&session=eq.{st.session_state.access_code}&domain=eq.{domain}",
        headers={
            "apikey": st.secrets["supabase_key"],
            "Authorization": f"Bearer {st.secrets['supabase_key']}"
        }
    )

    if response.status_code == 200 and response.json():
        previous_entries = pd.DataFrame(response.json()).drop_duplicates(subset=["name", "score", "text"])

        for _, row in previous_entries.iterrows():
            effect_type = "positive" if row["posneg"] == 1 else "negative"
            st.session_state[domain][effect_type].append({
                "text": row["text"],
                "score": row["score"],
                "posneg": row["posneg"]
            })

# --- Load domain info ---
info_df = pd.read_excel("domein_info.xlsx")
info = info_df[info_df['domein'] == domain]


info_text = info['introductietekst'].iloc[0]
questions = info['hulpvragen'].iloc[0].split('-')
question_list = "\n".join([f"- {q.strip()}" for q in questions if q.strip()])
link = info['link_GR'].iloc[0] if st.session_state.prov == 'GR' else info['link_DR'].iloc[0]

# --- Info Section ---
st.markdown(f"""
<div style="position: absolute; top: 0; right: 0;">
    <a href="{link}" target="_blank" style="background-color: #f0f2f6; padding: 6px 12px; border-radius: 6px; text-decoration: none; color: #3366cc; font-weight: bold; font-size: 14px;">
        Meer informatie over {domain}
    </a>
</div>
""", unsafe_allow_html=True)



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


# --- Effect Removal Handler ---
for effect_type in ["positive", "negative"]:
    for i in range(len(st.session_state[domain][effect_type])):
        delete_key = f"delete_{effect_type}_{i}"
        if st.session_state.get(delete_key):
            del st.session_state[domain][effect_type][i]
            st.session_state.pop(delete_key)
            st.rerun()
# --- Form ---
with st.form("effects_form"):
    col_pos, col_neg = st.columns(2)

    with col_pos:
        st.header("✅ Positieve effecten")
        if st.form_submit_button("➕ Voeg positief effect toe", type="secondary"):
            st.session_state[domain]["positive"].append({"text": "", "score": 0, "posneg": 1})

        for i, entry in enumerate(st.session_state[domain]["positive"]):
            text_key = f"{domain}_positive_text_{i}"
            score_key = f"{domain}_positive_score_{i}"

            entry["text"] = st.text_area(f"Positief effect {i+1}", value=entry["text"], key=text_key)
            entry["score"] = st.slider(
                f"Hoe sterk is het effect op {domain}?",
                min_value=0,
                max_value=4,
                value=entry.get("score", 0),
                key=score_key,
                help="0 = verwaarloosbaar · 1 = beperkt · 2 = merkbaar · 3 = sterk · 4 = zeer sterk"
            )
            st.checkbox("🗑️ Verwijder", key=f"delete_positive_{i}")

    with col_neg:
        st.header("❌ Negatieve effecten")
        if st.form_submit_button("➕ Voeg negatief effect toe", type="secondary"):
            st.session_state[domain]["negative"].append({"text": "", "score": 0, "posneg": -1})

        for i, entry in enumerate(st.session_state[domain]["negative"]):
            text_key = f"{domain}_negative_text_{i}"
            score_key = f"{domain}_negative_score_{i}"

            entry["text"] = st.text_area(f"Negatief effect {i+1}", value=entry["text"], key=text_key)
            entry["score"] = st.slider(
                f"Hoe sterk is het effect op {domain}?",
                min_value=0,
                max_value=4,
                value=entry.get("score", 0),
                key=score_key,
                help="0 = verwaarloosbaar · 1 = beperkt · 2 = merkbaar · 3 = sterk · 4 = zeer sterk"
            )
            st.checkbox("🗑️ Verwijder effect", key=f"delete_negative_{i}")



    # Submit all effects
    submitted = st.form_submit_button("✅ Effecten opslaan")

# --- Save Effects to Supabase ---
if submitted and not st.session_state.get(f"submitted_{domain_index}"):
    try:
        def post_effect(content_text: str, score: int, posneg: int):
            # coerce empty/whitespace to a single space
            safe_text = content_text if content_text.strip() else " "
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
                    "text": safe_text,
                    "score": score,
                    "posneg": posneg,
                    "name": st.session_state.name,
                    "session": st.session_state.access_code
                },
                timeout=10
            )

        # If lists are empty, still save one placeholder per side
        if not st.session_state[domain]["positive"]:
            post_effect(" ", 1, 1)
        else:
            for entry in st.session_state[domain]["positive"]:
                post_effect(entry.get("text", ""), int(entry.get("score", 1)), 1)

        if not st.session_state[domain]["negative"]:
            post_effect(" ", 1, -1)
        else:
            for entry in st.session_state[domain]["negative"]:
                post_effect(entry.get("text", ""), int(entry.get("score", 1)), -1)

        st.success("Opgeslagen!")
        st.session_state[f"submitted_{domain_index}"] = True

    except Exception as e:
        st.error(f"❌ Fout bij opslaan: {e}")


# --- Next Page Button ---
if st.session_state.get(f"submitted_{domain_index}"):
    if st.button("➡️ Ga door naar het volgende domein"):
        st.session_state.go_to_next_page = True

if st.session_state.get("go_to_next_page"):
    del st.session_state["go_to_next_page"]
    st.switch_page(f"pages/{domain_index + 1}_{next_domain}.py")
