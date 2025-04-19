import streamlit as st
import requests
import uuid

if "submission_id" not in st.session_state:
    st.session_state.submission_id = str(uuid.uuid4())

st.set_page_config(page_title="Brede Welvaart Werksessie", layout="centered")

# Set initial state
if "has_submitted" not in st.session_state:
    st.session_state.has_submitted = False

if "domain_inputs" not in st.session_state:
    st.session_state.domain_inputs = {}

st.title("Werksessie Brede Welvaart")

name = st.text_input("Naam (optioneel)")

domains = [
    "Materiële welvaart", "Gezondheid", "Arbeid en vrije tijd", "Wonen",
    "Sociaal", "Veiligheid", "Milieu", "Welzijn"
]

# Initialize domain_inputs if not already set
for domain in domains:
    if domain not in st.session_state.domain_inputs:
        st.session_state.domain_inputs[domain] = []

with st.form("input_form"):
    st.markdown("### Klik op een domein om effecten toe te voegen:")

    for domain in domains:
        with st.expander(f"➕ {domain}"):
            st.markdown(f"*Wat voor effect(en) heeft de interventie op* **{domain}?**")

            if st.form_submit_button(f"➕ Voeg effect toe aan {domain}", type="secondary"):
                st.session_state.domain_inputs[domain].append({"text": "", "score": 0})

            for i, entry in enumerate(st.session_state.domain_inputs[domain]):
                text_key = f"{domain}_text_{i}"
                score_key = f"{domain}_score_{i}"

                entry["text"] = st.text_area(f"Effect {i+1}", value=entry["text"], key=text_key)
                entry["score"] = st.radio(
                    f"Score voor effect {i+1}",
                    options=[-2, -1, 0, 1, 2],
                    format_func=lambda x: {
                        -2: "Heel negatief", -1: "Negatief", 0: "Neutraal", 1: "Positief", 2: "Heel positief"
                    }[x],
                    key= score_key,
                    index=2 #neutral default optie
                )

    submitted = st.form_submit_button("✅ Alles opslaan")

# Save to Supabase after form submission
if submitted:
    try:
        for domain, entries in st.session_state.domain_inputs.items():
            for entry in entries:
                if entry["text"].strip():
                    response = requests.post(
                        f"{st.secrets['supabase_url']}/rest/v1/submissions",
                        headers={
                            "apikey": st.secrets["supabase_key"],
                            "Authorization": f"Bearer {st.secrets['supabase_key']}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "submission_id": st.session_state.submission_id,
                            "name": name if name else "Anonymous",
                            "domain": domain,
                            "text": entry["text"],
                            "score": entry["score"]
                        }
                    )
        st.session_state.has_submitted = True
        st.success("✅ Bedankt voor het invullen!")
    except Exception as e:
        st.error("Oeps! Er ging iets mis bij het opslaan.")
        st.write(e)

# ✅ Show navigation button to results
if st.session_state.get("has_submitted"):
    if st.button("Bekijk de resultaten"):
        st.switch_page("pages/2_resultaten.py")
