# pages/1_📥_CSV_export.py
import io
from pathlib import Path
import streamlit as st

from helpers import load_model_from_bytes, extract_ifc_to_dataframe

st.header("📥 Lesen & Schreiben CSV")

if "ifc_bytes" not in st.session_state:
    st.error("Bitte laden Sie eine IFC-Datei auf der Startseite hoch.")
    st.stop()

# User options
pset_name = st.text_input("P-set zu lesen (optional)", value="OEBBset_Semantik_Topologie")
split_cls = st.checkbox("IfcClassifications in getrennten Spalten", value=True)

read_btn = st.button("Lesen der Daten")

if read_btn:
    with st.spinner("Laden IFC…"):
        model, tmp_path = load_model_from_bytes(st.session_state.ifc_bytes)
        st.session_state.model = model   # store for Page 2
        st.session_state.ifc_path = tmp_path

    with st.spinner("Extrahiere…"):
        df = extract_ifc_to_dataframe(model, pset_name, split_classifications=split_cls)
        st.session_state.df = df

if "df" in st.session_state:
    df = st.session_state.df
    st.success(f"Extrahiert {len(df)} Elemente • {len(df.columns)} Spalten.")
    st.dataframe(df.head(200), use_container_width=True, height=500)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    default_name = f"{Path(st.session_state.ifc_name).stem}_export.csv"
    st.download_button(
        label="💾 CSV herunterladen",
        data=csv_bytes,
        file_name=default_name,
        mime="text/csv",
    )
else:
    st.info("Klicken Sie auf **Lesen der Daten** um die hochgeladene IFC-Datei zu verarbeiten.")
