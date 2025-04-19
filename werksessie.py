import streamlit as st
import streamlit as st

# Set your desired code
ACCESS_CODE = "test2"

# Check session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Ask for the code if not authenticated
if not st.session_state.authenticated:
    st.title("🔐 Toegang vereist")
    code_input = st.text_input("Voer toegangscode in", type="password")

    if code_input == ACCESS_CODE:
        st.session_state.authenticated = True
        st.session_state.access_code = code_input

        st.success("✅ Toegang verleend")
        st.rerun()
    elif code_input:
        st.error("❌ Onjuiste code")
    st.stop()
st.set_page_config(page_title="Brede Welvaart Werksessie", layout="centered")

st.title("Welkom bij de Brede Welvaart Werksessie")

st.markdown("""
We hebben eerst wat informatie nodig
""")
if "name" not in st.session_state:
    st.session_state.name = ""

# Ask for name once
if not st.session_state.name:
    name_input = st.text_input("Wat is je naam of code?")
    if name_input:
        st.session_state.name = name_input
        st.success(f"Welkom, {name_input}!")
        st.rerun()
else:
    st.success(f"Je bent ingelogd als: **{st.session_state.name}**")


# 👇 This must be outside markdown, and button text needs to be plain
if st.button("Klik om aan de slag te gaan"):
    st.switch_page("pages/1_effecten.py")