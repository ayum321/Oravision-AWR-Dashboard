import streamlit as st
st.set_page_config(page_title="Test", layout="centered")
st.title("Streamlit is working ✓")
st.write("If you can read this, the server is running correctly.")
st.metric("Status", "Online")
name = st.text_input("Type something")
if name:
    st.success(f"You typed: {name}")
