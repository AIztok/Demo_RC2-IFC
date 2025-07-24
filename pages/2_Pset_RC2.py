# pages/2_🛠️_Pset_RC2.py
"""
• Button 1 → builds an editable Streamlit sheet (st.data_editor)  
  - guid  | Position_1 | Menge_1 | Position_2 | Menge_2 | …  
  - pre-filled from the IFC model (classifications + GrossVolume)  
  - user can overwrite any cell

• Button 2 → writes the edited table back into the IFC
  - every row updates / creates PropertySet `OEBBset_RC2`
  - Pruefung column optional (default TRUE)
  - re-uses helper functions from helpers.py
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st
import ifcopenshell
import ifcopenshell.guid

from helpers import (
    get_classification_strings,
    _get_gross_volume,            # <- already in helpers.py
)

###############################################################################
# ------------------------- util: build initial DF ---------------------------
###############################################################################


def build_rc2_dataframe(model: ifcopenshell.file) -> pd.DataFrame:
    """Return a DataFrame with guid + dynamic Position_n / Menge_n columns."""
    records: List[Dict] = []
    max_n = 0

    for el in model.by_type("IfcProduct"):
        if not getattr(el, "GlobalId", None):
            continue

        cls_list = get_classification_strings(el)
        gross_vol = _get_gross_volume(el)
        row: Dict = {"guid": el.GlobalId, "Pruefung": False}

        for idx, cls in enumerate(cls_list, start=1):
            row[f"Position_{idx}"] = cls
            row[f"Menge_{idx}"] = gross_vol
        max_n = max(max_n, len(cls_list))
        records.append(row)

    # make sure every Position_n/Menge_n column exists even if NaN
    cols = ["guid", "Pruefung"]
    for i in range(1, max_n + 1):
        cols += [f"Position_{i}", f"Menge_{i}"]

    df = pd.DataFrame(records)[cols]
    return df


###############################################################################
# ------------- util: write DF values back to the IFC model ------------------
###############################################################################


def upsert_single_value(
    model: ifcopenshell.file,
    pset,
    name: str,
    value,
    ifc_type: str,
):
    """Add or update a property named `name` in `pset`."""
    existing = next((p for p in pset.HasProperties if p.Name == name), None)
    if existing:
        existing.NominalValue.wrappedValue = value
    else:
        prop = model.createIfcPropertySingleValue(
            Name=name,
            Description=None,
            NominalValue=model.create_entity(ifc_type, value),
            Unit=None,
        )
        pset.HasProperties = pset.HasProperties + (prop,)


def sync_rc2_to_ifc(model: ifcopenshell.file, df: pd.DataFrame):
    """Iterate DataFrame rows and push values into Pset OEBBset_RC2."""
    guid_index = {el.GlobalId: el for el in model.by_type("IfcProduct")}

    # regex to capture Position_n / Menge_n
    pos_pat = re.compile(r"Position_(\d+)")
    men_pat = re.compile(r"Menge_(\d+)")

    for _, row in df.iterrows():
        guid = row["guid"]
        el = guid_index.get(guid)
        if not el:
            continue  # GUID disappeared

        # find or create P-set
        pset = None
        for rel in el.IsDefinedBy or []:
            if rel.is_a("IfcRelDefinesByProperties"):
                obj = rel.RelatingPropertyDefinition
                if obj.is_a("IfcPropertySet") and obj.Name == "OEBBset_RC2":
                    pset = obj
                    break

        if pset is None:
            pset = model.createIfcPropertySet(
                GlobalId=ifcopenshell.guid.new(),
                OwnerHistory=None,
                Name="OEBBset_RC2",
                Description=None,
                HasProperties=(),
            )
            model.createIfcRelDefinesByProperties(
                GlobalId=ifcopenshell.guid.new(),
                OwnerHistory=None,
                Name=None,
                Description=None,
                RelatedObjects=[el],
                RelatingPropertyDefinition=pset,
            )

        # --- Pruefung -------------------------------------------------------
        pruefung_value = bool(row.get("Pruefung", True))
        upsert_single_value(model, pset, "Pruefung", pruefung_value, "IfcBoolean")

        # --- dynamic Position_n / Menge_n ----------------------------------
        for col in df.columns:
            if m := pos_pat.fullmatch(col):
                idx = m.group(1)
                val = row[col]
                if pd.notna(val) and val != "":
                    upsert_single_value(
                        model, pset, f"Position_{idx}", str(val), "IfcLabel"
                    )
            elif m := men_pat.fullmatch(col):
                idx = m.group(1)
                val = row[col]
                if pd.notna(val):
                    upsert_single_value(
                        model, pset, f"Menge_{idx}", float(val), "IfcVolumeMeasure"
                    )


###############################################################################
# ------------------------------ Streamlit UI --------------------------------
###############################################################################
st.header("🛠️ Pset OEBBset_RC2 editor")

if "model" not in st.session_state:
    st.error("Bitte laden und extrahieren Sie zuerst eine IFC unter **📥 Lesen & Schreiben CSV**.")
    st.stop()

model: ifcopenshell.file = st.session_state.model
default_name = Path(st.session_state.ifc_name).stem + "_RC2.ifc"

# 1) Build / show editable sheet ------------------------------------------------
if st.button("🔄 Bearbeitbare Tabelle erzeugen"):
    st.session_state.rc2_df = build_rc2_dataframe(model)

if "rc2_df" in st.session_state:
    edited_df = st.data_editor(
        st.session_state.rc2_df,
        num_rows="dynamic",
        use_container_width=True,
        height=600,
        key="rc2_editor",
    )
    # keep latest edits in session
    st.session_state.rc2_df = edited_df
else:
    st.info("Klicken Sie auf **Bearbeitbare Tabelle erzeugen** um zu starten.")

# 2) Write back & offer download ------------------------------------------------
if "rc2_df" in st.session_state and st.button("💾 In IFC speichern & herunterladen"):
    with st.spinner("Schreiben IFC …"):
        sync_rc2_to_ifc(model, st.session_state.rc2_df)

        # temp-file path for this session
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc")
        tmp_path = tmp.name
        tmp.close()
        model.write(tmp_path)

    with open(tmp_path, "rb") as f:
        st.download_button(
            label=f"⬇️ Modifizierte IFC herunterladen ({default_name})",
            data=f,
            file_name=default_name,
            mime="application/octet-stream",
        )
    st.success("Fertig! Laden Sie Ihre IFC oben herunter.")
