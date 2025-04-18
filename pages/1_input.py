import streamlit as st
import requests

# Set this if not already present
if "has_submitted" not in st.session_state:
    st.session_state.has_submitted = False

st.title("📝 Werksessie brede welvaart")

with st.form("input_form"):
    name = st.text_input("Naam/functie/id")
    text = st.text_area("Effect")
    score = st.slider("Hoe positief is dit effect? (1 = negatief, 5 = positief)", 1, 5, 3)
    submitted = st.form_submit_button("Antwoord opslaan")

    if submitted:
        if text.strip() == "":
            st.warning("Vul een antwoord in.")
        else:
            response = requests.post(
                "https://tnvthmgeafgvqhzbetjz.supabase.co/rest/v1/submissions",
                headers={
                    "apikey": st.secrets["supabase_key"],
                    "Authorization": f"Bearer {st.secrets['supabase_key']}",
                    "Content-Type": "application/json"
                },
                json={
                    "name": name if name else "Anonymous",
                    "text": text,
                    "score": score
                }
            )
            if response.status_code == 201:
                st.session_state.has_submitted = True
                st.success("Bedankt voor het invullen!")

            else:
                st.error("Er ging iets mis 😕")

if st.session_state.get("has_submitted"):
    st.success("✅ Bedankt voor het invullen!")
    if st.button("➡️ Bekijk de resultaten"):
        st.switch_page("pages/2_viewresults.py")