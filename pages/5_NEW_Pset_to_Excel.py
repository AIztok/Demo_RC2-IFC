# pages/5_Pset_to_Excel.py
from __future__ import annotations
from pathlib import Path
import io, math, itertools
import pandas as pd
import streamlit as st
import ifcopenshell
from helpers import load_model_from_bytes

# ───────── utilities ─────────
def is_number(x):
    return isinstance(x, (int, float)) and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))

def list_containers(model):
    psets, qtos = set(), set()
    for el in model.by_type("IfcObject"):
        for rel in getattr(el, "IsDefinedBy", []) or []:
            if not rel.is_a("IfcRelDefinesByProperties"):
                continue
            rd = rel.RelatingPropertyDefinition
            if rd.is_a("IfcPropertySet") and rd.Name:
                psets.add(rd.Name)
            elif rd.is_a("IfcElementQuantity") and rd.Name:
                qtos.add(rd.Name)
    return sorted(psets), sorted(qtos)

def collect_fields(model, kind: str, name: str):
    fields = set()
    for el in model.by_type("IfcObject"):
        for rel in getattr(el, "IsDefinedBy", []) or []:
            if not rel.is_a("IfcRelDefinesByProperties"):
                continue
            rd = rel.RelatingPropertyDefinition
            if kind == "Pset" and rd.is_a("IfcPropertySet") and rd.Name == name:
                for p in rd.HasProperties or []:
                    nm = getattr(p, "Name", None)
                    if nm:
                        fields.add(nm)
            elif kind == "Qto" and rd.is_a("IfcElementQuantity") and rd.Name == name:
                for q in rd.Quantities or []:
                    nm = getattr(q, "Name", None)
                    if nm:
                        fields.add(nm)
    return sorted(fields)

def unit_label_from_si(si_unit):
    if not si_unit:
        return ""
    name = str(getattr(si_unit, "Name", "") or getattr(si_unit, "UnitType", ""))
    table = {
        "METRE": "m", "IfcUnitEnum.LENGTHUNIT": "m",
        "SQUARE_METRE": "m²", "IfcUnitEnum.AREAUNIT": "m²",
        "CUBIC_METRE": "m³", "IfcUnitEnum.VOLUMEUNIT": "m³",
        "GRAM": "g", "KILOGRAM": "kg",
    }
    return table.get(name, "")

def read_pset_value(el, pset_name: str, prop_name: str):
    for rel in getattr(el, "IsDefinedBy", []) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if pset.is_a("IfcPropertySet") and pset.Name == pset_name:
            for p in pset.HasProperties or []:
                if p.is_a("IfcPropertySingleValue") and p.Name == prop_name and p.NominalValue:
                    return p.NominalValue.wrappedValue
    return None

def read_qto_value_and_unit(el, qto_name: str, qty_name: str):
    for rel in getattr(el, "IsDefinedBy", []) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        qset = rel.RelatingPropertyDefinition
        if qset.is_a("IfcElementQuantity") and qset.Name == qto_name:
            for q in qset.Quantities or []:
                if getattr(q, "Name", None) != qty_name:
                    continue
                for attr in ("AreaValue", "VolumeValue", "LengthValue", "CountValue", "WeightValue"):
                    if hasattr(q, attr):
                        val = getattr(q, attr)
                        return val, unit_label_from_si(getattr(q, "Unit", None))
    return None, ""

def extract_single(el, kind: str, container: str, spec: str):
    if spec == "guid":
        return getattr(el, "GlobalId", "")
    if spec == "name":
        return getattr(el, "Name", "")
    if kind == "Pset":
        return read_pset_value(el, container, spec)
    if kind == "Qto":
        if spec.endswith(" [Unit]"):
            qty_name = spec[:-8]
            _, u = read_qto_value_and_unit(el, container, qty_name)
            return u
        val, _u = read_qto_value_and_unit(el, container, spec)
        return val
    return None

def gather_values(el, kind: str, container: str, specs: list[str]):
    """Return list of values for this column for this element (one per selected spec),
       skipping None. If specs empty → return [None] (no expansion).
    """
    if not specs:
        return [None]
    out = []
    for s in specs:
        v = extract_single(el, kind, container, s)
        if v is not None and v != "":
            out.append(v)
    return out or [None]

# ───────── UI ─────────
st.header("📤 Pset/Qto → Excel (Mehrfachauswahl ⇒ mehrere Zeilen)")

if "ifc_bytes" not in st.session_state:
    st.error("Bitte laden Sie eine IFC-Datei auf der Startseite hoch.")
    st.stop()

# Load model
if "model" not in st.session_state:
    model, _ = load_model_from_bytes(st.session_state.ifc_bytes)
    st.session_state.model = model
else:
    model = st.session_state.model

# 1) Source container
psets, qtos = list_containers(model)
choices = [f"Pset: {n}" for n in psets] + [f"Qto: {n}" for n in qtos]
if not choices:
    st.warning("Keine PropertySets oder ElementQuantity-Sets gefunden.")
    st.stop()

default_choice = next((c for c in choices if c.lower().startswith("pset: oebbset_rc2_ke")), choices[0])
picked = st.selectbox("Quelle auswählen", choices, index=choices.index(default_choice))
kind = "Pset" if picked.startswith("Pset: ") else "Qto"
container_name = picked.split(": ", 1)[1]

# 2) Template (headers)
tpl = st.file_uploader("Excel/CSV-Template mit Spaltenköpfen (nur Kopfzeile nötig)",
                       type=("xlsx", "xls", "csv"))
if not tpl:
    st.info("Bitte Template hochladen.")
    st.stop()

df_tpl = pd.read_excel(tpl, header=0) if tpl.name.lower().endswith(("xlsx","xls")) else pd.read_csv(tpl)
headers = list(df_tpl.columns)
if not headers:
    st.error("Im Template wurden keine Spaltenköpfe gefunden.")
    st.stop()

# 3) Build options (fields)
available_fields = ["guid", "name"] + collect_fields(model, kind, container_name)
if kind == "Qto":
    available_fields += [f"{n} [Unit]" for n in available_fields if n not in ("guid", "name")]

# Heuristic defaults: match header if same name
lower_to_field = {f.lower(): f for f in available_fields}
suggested = {h: ([lower_to_field[h.lower()]] if h.lower() in lower_to_field else []) for h in headers}

st.markdown("#### Spalten-Mapping (Mehrfachauswahl je Spalte ⇒ mehrere Zeilen)")
map_rows = []
for h in headers:
    map_rows.append(
        {
            "Excel-Spalte": h,
            "Quelle(n)": st.multiselect(
                f"Quelle für **{h}**",
                options=available_fields,
                default=suggested[h],
                key=f"map_{h}",
            )
        }
    )
map_df = pd.DataFrame(map_rows)

sum_same_name = st.checkbox("🔢 Zusätzlich: Gleiche Elemente summiert (nach Ifc-Name)", value=True)

# NEW: let the user choose which columns to group by (from your template headers)
group_keys = []
if sum_same_name:
    group_keys = st.multiselect(
        "Nach welchen Spalten zusammenfassen? (z. B. Klassifikation, Einheit, …)",
        options=headers,           # use only the mapped/export headers
        default=[],                # no default; user decides
        help="Zeilen mit identischen Werten in diesen Spalten werden zu einer Zeile zusammengefasst."
    )

st.divider()
if st.button("📄 Vorschau erzeugen"):
    elements = [el for el in model.by_type("IfcObject") if getattr(el, "GlobalId", None)]
    out_rows = []

    # Prepare order of columns
    col_specs = {h: list(specs) for h, specs in zip(map_df["Excel-Spalte"], map_df["Quelle(n)"])}

    for el in elements:
        # Gather list of values per header
        lists_per_col = {}
        for h, specs in col_specs.items():
            lists_per_col[h] = gather_values(el, kind, container_name, specs)

        # Decide if we should output any rows for this element:
        # if all lists are [None], skip this element entirely
        has_any_value = any(any(v is not None and v != "" for v in vals) for vals in lists_per_col.values())
        if not has_any_value:
            continue

        # # Expand rows by Cartesian product across columns
        # # For columns with [None] we won't expand (single None keeps product size)
        # col_order = headers[:]  # preserve template order
        # product_lists = [lists_per_col[h] for h in col_order]
        # for combo in itertools.product(*product_lists):
        #     # Skip row that is entirely None (shouldn't happen due to has_any_value)
        #     if all(v is None or v == "" for v in combo):
        #         continue
        #     row = {h: v for h, v in zip(col_order, combo)}
        #     # Add hidden Ifc name for grouping preview/export
        #     row["__IFC_NAME__"] = getattr(el, "Name", "")
        #     out_rows.append(row)
        # NEW (PAIR BY INDEX): create one row per index across columns
        col_order = headers[:]  # preserve template order

        # how many rows do we need for this element?
        max_len = max(len(vals) for vals in lists_per_col.values())

        for k in range(max_len):
            row = {}
            for h in col_order:
                vals = lists_per_col[h]
                # take kth value if present, otherwise leave empty for that column
                row[h] = vals[k] if k < len(vals) else None
            # add hidden IFC name for optional grouping
            row["__IFC_NAME__"] = getattr(el, "Name", "")
            # skip fully empty rows (shouldn’t happen due to has_any_value, but safe)
            if any(v not in (None, "") for v in row.values()):
                out_rows.append(row)


    if not out_rows:
        st.warning("Keine Werte gefunden für die aktuelle Zuordnung.")
        st.stop()

    result = pd.DataFrame(out_rows)
    # Ensure all template headers exist as columns (even if empty)
    for h in headers:
        if h not in result.columns:
            result[h] = None
    result = result[headers + ["__IFC_NAME__"]]

    st.success(f"{len(result)} Zeilen erzeugt.")
    st.markdown("**Vorschau (Einzeln, mit Mehrfachauswahl → mehrere Zeilen):**")
    st.dataframe(result.head(200), use_container_width=True, height=380)

    # Download single
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        result[headers].to_excel(w, index=False, sheet_name="Export")
    st.download_button(
        "⬇️ Excel (Einzeln) herunterladen",
        buf.getvalue(),
        file_name=f"{Path(st.session_state.get('ifc_name','export')).stem}_{kind}_{container_name}_einzeln.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_export_single",
    )

    # # Optional grouped export by Ifc Name
    # if sum_same_name:
    #     # Try to treat numeric columns as sum, others as first
    #     agg = {}
    #     for h in headers:
    #         # Attempt to coerce to numeric for this column
    #         numeric_series = pd.to_numeric(result[h], errors="coerce")
    #         if numeric_series.notna().any():
    #             agg[h] = "sum"
    #         else:
    #             agg[h] = "first"

    #     grouped = (
    #         result.groupby("__IFC_NAME__", as_index=False)
    #         .agg(agg)
    #         .rename(columns={"__IFC_NAME__": "Name"})
    #     )

    #     st.markdown("**Vorschau (Gleiche Elemente summiert nach Ifc-Name):**")
    #     st.dataframe(grouped.head(200), use_container_width=True, height=380)

    #     buf2 = io.BytesIO()
    #     with pd.ExcelWriter(buf2, engine="xlsxwriter") as w:
    #         grouped.to_excel(w, index=False, sheet_name="Export_Summe")
    #     st.download_button(
    #         "⬇️ Excel (Summiert) herunterladen",
    #         buf2.getvalue(),
    #         file_name=f"{Path(st.session_state.get('ifc_name','export')).stem}_{kind}_{container_name}_summiert.xlsx",
    #         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    #         key="dl_export_grouped",
    #     )
    # ───────── Summed/grouped export by user-chosen keys ─────────
    if sum_same_name:
        if not group_keys:
            st.info("Bitte wählen Sie mindestens eine Spalte zum Zusammenfassen aus "
                    "oder deaktivieren Sie die Summen-Option.")
        else:
            # Work only with the export headers (ignore hidden helper column)
            df_in = result[headers].copy()

            # Detect numeric columns (that are NOT grouping keys)
            can_be_num = {c: pd.to_numeric(df_in[c], errors="coerce").notna().any() for c in headers}
            numeric_cols = [c for c, ok in can_be_num.items() if ok and c not in group_keys]

            # Aggregation: sum numeric columns, take first for others (excluding group keys themselves)
            agg = {c: ("sum" if c in numeric_cols else "first") for c in headers if c not in group_keys}

            grouped = (
                df_in
                .groupby(group_keys, dropna=False, as_index=False)  # keep NaN groups too
                .agg(agg)
            )

            st.markdown("**Vorschau (Summiert nach ausgewählten Spalten):**")
            st.dataframe(grouped.head(200), use_container_width=True, height=380)

            buf2 = io.BytesIO()
            with pd.ExcelWriter(buf2, engine="xlsxwriter") as w:
                grouped.to_excel(w, index=False, sheet_name="Export_Summe")

            suffix = "_by_" + "_".join(group_keys).replace(" ", "_") if group_keys else ""
            st.download_button(
                "⬇️ Excel (Summiert) herunterladen",
                buf2.getvalue(),
                file_name=f"{Path(st.session_state.get('ifc_name','export')).stem}_{kind}_{container_name}_summiert{suffix}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_export_grouped",
            )
else:
    st.info("Wählen Sie oben die Quelle (Pset/Qto), laden Sie Ihr Template und mappen Sie die Spalten. "
            "Bei Mehrfachauswahl pro Spalte werden mehrere Zeilen erzeugt. "
            "Klicken Sie danach auf **Vorschau erzeugen**.")
