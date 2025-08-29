# pages/4_Mapping_Qto.py
"""
Mapping-driven quantity take-off + OEBBset_RC2_KE writer

• Upload IFC on the main page
• Upload Mapping (CSV / XLSX) – columns:
      A  classification  (number)
      B  title           (free text)
      C  –               (ignored / reserved)
      D  prop_template   (ignored here)
      E  quantity_type   (VOLUME_GROSS, COUNT_STK, …)
      F  unit_hint       (m³, Stk, …)
  (If your sheet has more columns, they are ignored here.)

• Press  ⚙️  button → quantities are generated, written to Qto set and
  OEBBset_RC2_KE properties, tables appear, and two download buttons
  (Excel + IFC) stay visible on re-runs.
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import streamlit as st
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.guid

from helpers import load_model_from_bytes, get_classification_strings

# ───────────────────────── geometry helpers ─────────────────────────
def tri_area(v0, v1, v2):
    return 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0))

def mesh_area_and_volume(verts, faces) -> Tuple[float, float]:
    area = vol = 0.0
    for a, b, c in faces:
        v0, v1, v2 = verts[a], verts[b], verts[c]
        area += tri_area(v0, v1, v2)
        vol += np.dot(v0, np.cross(v1, v2)) / 6.0
    return area, abs(vol)

def bbox_longest_edge(v):  return float((v.max(0) - v.min(0)).max())
def bbox_height(v):        return float(v[:, 2].ptp())
def bbox_diag_xy(v):       return float(np.linalg.norm(v[:, :2].ptp(0)))

def area_bottom(v, f):
    down = np.array([0, 0, -1.0]); a = 0.0
    for i, j, k in f:
        n = np.cross(v[j]-v[i], v[k]-v[i]); n /= np.linalg.norm(n) + 1e-12
        if np.dot(n, down) > .8: a += tri_area(v[i], v[j], v[k])
    return a

def area_side_max(v, f):
    up = np.array([0, 0, 1.0]); areas=[]
    for i,j,k in f:
        n = np.cross(v[j]-v[i], v[k]-v[i]); n/=np.linalg.norm(n)+1e-12
        if abs(np.dot(n, up))<.2: areas.append(tri_area(v[i],v[j],v[k]))
    return max(areas, default=0.0)

def compute_quantity(key, v, f):
    area, vol = mesh_area_and_volume(v, f)
    return {
        "VOLUME_NET": vol,
        "VOLUME_GROSS": vol,
        "AREA_SURF_TOTAL": area,
        "AREA_BOTTOM": area_bottom(v, f),
        "AREA_SIDE_MAX": area_side_max(v, f),
        "LENGTH_LONGEST": bbox_longest_edge(v),
        "LENGTH_XY": bbox_diag_xy(v),
        "HEIGHT_Z": bbox_height(v),
    }.get(key)

# ───────────────────────── IFC helpers ─────────────────────────
def get_project_unit(model, unit_type):
    """Return first IfcUnit of given UnitType; fall back to simple SI."""
    ua = model.by_type("IfcUnitAssignment")
    if ua:
        for u in ua[0].Units:
            if getattr(u, "UnitType", "") == unit_type:
                return u
    # create minimal SI unit if missing
    si_map = {
        "LENGTHUNIT": ("METRE", "IfcUnitEnum.LENGTHUNIT"),
        "AREAUNIT": ("SQUARE_METRE", "IfcUnitEnum.AREAUNIT"),
        "VOLUMEUNIT": ("CUBIC_METRE", "IfcUnitEnum.VOLUMEUNIT"),
    }
    if unit_type in si_map:
        name, ut = si_map[unit_type]
        return model.create_entity(
            "IfcSIUnit",
            UnitType=ut,
            Name=getattr(ifcopenshell.util.unit, name),
            Prefix=None,
        )
    return None  # count/unitless

def upsert_qto_set(model, el, name):
    for r in el.IsDefinedBy or []:
        if r.is_a("IfcRelDefinesByProperties"):
            q = r.RelatingPropertyDefinition
            if q.is_a("IfcElementQuantity") and q.Name == name:
                return q
    q = model.createIfcElementQuantity(
        GlobalId=ifcopenshell.guid.new(), Name=name, Quantities=()
    )
    model.createIfcRelDefinesByProperties(
        GlobalId=ifcopenshell.guid.new(), RelatedObjects=[el], RelatingPropertyDefinition=q
    )
    return q

def upsert_pset(model, el, name="OEBBset_RC2_KE"):
    for r in el.IsDefinedBy or []:
        if r.is_a("IfcRelDefinesByProperties"):
            p = r.RelatingPropertyDefinition
            if p.is_a("IfcPropertySet") and p.Name == name:
                return p
    p = model.createIfcPropertySet(
        GlobalId=ifcopenshell.guid.new(), Name=name, HasProperties=()
    )
    model.createIfcRelDefinesByProperties(
        GlobalId=ifcopenshell.guid.new(), RelatedObjects=[el], RelatingPropertyDefinition=p
    )
    return p

def upsert_single_value(model, pset, name, value, ifc_type="IfcReal", unit=None):
    ex = next((p for p in pset.HasProperties if p.Name == name), None)
    if ex:
        # allow None for numeric placeholders
        if ex.NominalValue is not None and hasattr(ex.NominalValue, "wrappedValue"):
            ex.NominalValue.wrappedValue = value
        else:
            ex.NominalValue = model.create_entity(ifc_type, value) if value is not None else None
        ex.Unit = unit
        return
    pset.HasProperties += (
        model.createIfcPropertySingleValue(
            Name=name,
            Description=None,
            NominalValue=(model.create_entity(ifc_type, value) if value is not None else None),
            Unit=unit,
        ),
    )

def upsert_quantity(model, qset, qtype: str, name: str, unit, value_attr: str, value):
    """Find quantity with same Name & type; update or append."""
    for q in qset.Quantities or ():
        if q.is_a(qtype) and getattr(q, "Name", None) == name:
            setattr(q, value_attr, value)
            q.Unit = unit
            return q
    qty = model.create_entity(
        qtype,
        Name=name,
        Description=None,
        Unit=unit,
        **{value_attr: value},
    )
    qset.Quantities = (qset.Quantities or ()) + (qty,)
    return qty

# ───────────────────────── Streamlit UI ─────────────────────────
st.header("🧮 Mapping-gesteuertes Quantity Take-Off")

if "ifc_bytes" not in st.session_state:
    st.error("Bitte auf der Startseite eine IFC-Datei hochladen.")
    st.stop()

upload_map = st.file_uploader(
    "Mapping-Tabelle (CSV/XLSX)",
    type=("csv", "xls", "xlsx"),
    help="A=classification • B=title • D=prop_template(ignoriert) • E=quantity_type • F=unit_hint",
)

# clear cached outputs if new IFC or new mapping file
if (
    ("cached_ifc_name" in st.session_state and st.session_state.cached_ifc_name != st.session_state.ifc_name)
    or ("mapping_filename" in st.session_state and upload_map and upload_map.name != st.session_state.mapping_filename)
):
    for k in ("qto_detailed_df", "qto_summary_df", "qto_ifc_path"):
        st.session_state.pop(k, None)

# show cached tables/downloads if available
if "qto_detailed_df" in st.session_state:
    det, summ = st.session_state.qto_detailed_df, st.session_state.qto_summary_df
    st.dataframe(det, use_container_width=True, height=400)
    st.markdown("### Zusammenfassung")
    st.dataframe(summ, use_container_width=True, height=300)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        summ.to_excel(w, index=False, sheet_name="Summary")
        det.to_excel(w, index=False, sheet_name="Detailed")
    st.download_button(
        "📥 XLSX herunterladen",
        buf.getvalue(),
        file_name="quantities_summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="xlsx_dl",
    )
    with open(st.session_state.qto_ifc_path, "rb") as f:
        st.download_button(
            "💾 Geänderte IFC herunterladen",
            f.read(),
            file_name=Path(st.session_state.ifc_name).stem + "_mapped_qto.ifc",
            mime="application/octet-stream",
            key="ifc_dl",
        )
    st.stop()

if upload_map is None:
    st.info("Bitte Mapping-Datei hochladen.")
    st.stop()

# robust mapping reader: keep only A..F, ignore extras; normalize
raw = (
    pd.read_excel(upload_map, header=0)
    if upload_map.name.lower().endswith(("xls", "xlsx"))
    else pd.read_csv(upload_map)
)
NEEDED = 6  # A..F
if raw.shape[1] < NEEDED:
    for i in range(NEEDED - raw.shape[1]):
        raw[f"_pad{i}"] = None

df_map = raw.iloc[:, :NEEDED].copy()
df_map.columns = ["classification", "title", "_", "prop_template", "quantity_type", "unit_hint"]

# normalize + filter
df_map["classification"] = df_map["classification"].astype(str).str.strip()
df_map["title"]          = df_map["title"].astype(str).str.strip()
df_map["quantity_type"]  = df_map["quantity_type"].astype(str).str.strip().str.upper()
df_map["unit_hint"]      = df_map["unit_hint"].astype(str).str.strip()
df_map = df_map.replace({"": pd.NA})
df_map = df_map.dropna(subset=["classification", "quantity_type"])

if st.button("⚙️ Mengen nach Mapping generieren"):
    # load or reuse model
    if "model" not in st.session_state:
        model, _ = load_model_from_bytes(st.session_state.ifc_bytes)
        st.session_state.model = model
    else:
        model = st.session_state.model

    st.session_state.cached_ifc_name = st.session_state.ifc_name
    st.session_state.mapping_filename = upload_map.name

    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    unit_len  = get_project_unit(model, "LENGTHUNIT")
    unit_area = get_project_unit(model, "AREAUNIT")
    unit_vol  = get_project_unit(model, "VOLUMEUNIT")

    # map for quick row access
    map_dict = {str(r.classification): r for r in df_map.itertuples(index=False)}

    QTO_MAP = {
        "IfcWall": "Qto_WallBaseQuantities",
        "IfcWallStandardCase": "Qto_WallBaseQuantities",
        "IfcSlab": "Qto_SlabBaseQuantities",
        "IfcBeam": "Qto_BeamBaseQuantities",
        "IfcColumn": "Qto_ColumnBaseQuantities",
    }

    processed = []

    for el in model.by_type("IfcProduct"):
        if not getattr(el, "GlobalId", None):
            continue

        # unique classification numbers per element (preserve order)
        seen, uniq_nums = set(), []
        for c in get_classification_strings(el):
            num = c.split(":")[-1].strip() if ":" in c else c.strip()
            if num in map_dict and num not in seen:
                seen.add(num)
                uniq_nums.append(num)
        if not uniq_nums:
            continue

        # geometry
        try:
            sh = ifcopenshell.geom.create_shape(settings, el)
        except Exception:
            continue
        v = np.asarray(sh.geometry.verts, float).reshape(-1, 3)
        f = np.asarray(sh.geometry.faces, int).reshape(-1, 3)

        # target pset
        pset = upsert_pset(model, el, "OEBBset_RC2_KE")

        # write once-per-element keys
        el_name = getattr(el, "Name", "") or ""
        upsert_single_value(model, pset, "10_Vorhabenteil", el_name, ifc_type="IfcLabel")
        upsert_single_value(model, pset, "11_Kommentar", "ND", ifc_type="IfcText")

        # per classification
        for idx, num in enumerate(uniq_nums, 1):
            row = map_dict[num]

            # compute value + select unit object + label
            if row.quantity_type == "COUNT_STK":
                val, unit_obj, unit_label = 1.0, None, (row.unit_hint or "Stk" or "Stk")
            elif row.quantity_type.startswith("VOLUME"):
                val = compute_quantity(row.quantity_type, v, f)
                unit_obj = unit_vol
                unit_label = row.unit_hint or "m³"
            elif row.quantity_type.startswith("AREA"):
                val = compute_quantity(row.quantity_type, v, f)
                unit_obj = unit_area
                unit_label = row.unit_hint or "m²"
            else:
                val = compute_quantity(row.quantity_type, v, f)
                unit_obj = unit_len
                unit_label = row.unit_hint or "m"

            if val is None:
                continue

            # QTO upsert
            qto = upsert_qto_set(model, el, QTO_MAP.get(el.is_a(), "Qto_GenericBaseQuantities"))
            if row.quantity_type == "COUNT_STK":
                qtype, attr = "IfcQuantityCount", "CountValue"
            elif row.quantity_type.startswith("VOLUME"):
                qtype, attr = "IfcQuantityVolume", "VolumeValue"
            elif row.quantity_type.startswith("AREA"):
                qtype, attr = "IfcQuantityArea", "AreaValue"
            else:
                qtype, attr = "IfcQuantityLength", "LengthValue"

            upsert_quantity(model, qset=qto, qtype=qtype, name=row.quantity_type,
                            unit=unit_obj, value_attr=attr, value=val)

            # ── OEBBset_RC2_KE numbering: 21–25 for first class, 31–35 for second, etc.
            base = 20 + 10 * (idx - 1)
            # 21/31/… Elementbezeichnung
            upsert_single_value(model, pset, f"{base+1}_Elementbezeichnung",
                                str(row.title), ifc_type="IfcText")
            # 22/32/… Menge (IfcReal) + keep IFC Unit
            upsert_single_value(model, pset, f"{base+2}_Menge",
                                float(val), ifc_type="IfcReal", unit=unit_obj)
            # 23/33/… Einheit (label)
            upsert_single_value(model, pset, f"{base+3}_Einheit",
                                unit_label, ifc_type="IfcLabel")
            # 24/34/… Element-Kennnummer (mapping column A)
            upsert_single_value(model, pset, f"{base+4}_Element-Kennnummer",
                                str(num), ifc_type="IfcLabel")
            # 25/35/… Dichte = "ND" (store as text placeholder)
            upsert_single_value(model, pset, f"{base+5}_Dichte",
                                "ND", ifc_type="IfcText")

            processed.append(
                dict(
                    guid=el.GlobalId,
                    name=el_name,
                    classification_no=num,
                    title=row.title,
                    quantity_type=row.quantity_type,
                    unit=unit_label,
                    value=val,
                )
            )

    if not processed:
        st.warning("Keine passenden Elemente/Zeilen gefunden.")
        st.stop()

    det = pd.DataFrame(processed)
    st.dataframe(det, use_container_width=True, height=400)

    summ = (
        det.groupby(["classification_no", "title", "quantity_type", "unit"], as_index=False)["value"]
        .sum()
        .sort_values(["classification_no", "quantity_type"])
    )
    st.markdown("### Zusammenfassung")
    st.dataframe(summ, use_container_width=True, height=300)

    # cache outputs
    st.session_state.qto_detailed_df = det
    st.session_state.qto_summary_df = summ

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc")
    model.write(tmp.name)
    st.session_state.qto_ifc_path = tmp.name

    # downloads
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        summ.to_excel(w, index=False, sheet_name="Summary")
        det.to_excel(w, index=False, sheet_name="Detailed")
    st.download_button(
        "📥 XLSX herunterladen",
        buf.getvalue(),
        file_name="quantities_summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="xlsx_dl_gen",
    )
    with open(st.session_state.qto_ifc_path, "rb") as f:
        st.download_button(
            "💾 Geänderte IFC herunterladen",
            f.read(),
            file_name=Path(st.session_state.ifc_name).stem + "_mapped_qto.ifc",
            mime="application/octet-stream",
            key="ifc_dl_gen",
        )
else:
    st.info("Mapping laden und auf **Mengen nach Mapping generieren** klicken.")

