import streamlit as st

st.set_page_config(page_title="Brede Welvaart Werksessie", layout="centered")

st.title("Welkom bij de Brede Welvaart Werksessie")

st.markdown("""
We hebben eerst wat informatie nodig
""")

with st.form("input_form"):
    name = st.text_input("Naam")

# 👇 This must be outside markdown, and button text needs to be plain
if st.button("Klik om aan de slag te gaan"):
    st.switch_page("pages/1_effecten.py")