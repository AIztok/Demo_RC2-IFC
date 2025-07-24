# app.py
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
#  Page layout / title
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Demo RC2-IFC", layout="wide")
st.title("🏗️ Demo RC2-IFC")

st.markdown(
    "Upload IFC Datei. Öffnen, Lesen und CSV schreiben **📥  CSV Export** "
    "to process it, oder **🛠️ Pset RC2** um den `OEBBset_RC2` "
    "zu erstellen."
)

# ─────────────────────────────────────────────────────────────────────────────
#  File upload
# ─────────────────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload IFC",
    type=("ifc"),
    #help="The file is kept in session; processing happens on the tool pages.",
)

if uploaded is not None:
    # If the user changed the file name, reset session state
    if st.session_state.get("ifc_name") != uploaded.name:
        st.session_state.clear()

    st.session_state.ifc_name = uploaded.name
    st.session_state.ifc_bytes = uploaded.getvalue()

    st.success(
        f"Loaded **{uploaded.name}**. "
        ""
    )
else:
    st.info("👆 Upload IFC Datei.")
