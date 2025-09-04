# pages/0_🔍_AutoClassify.py
from __future__ import annotations

import re, unicodedata, tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from rapidfuzz import process, fuzz
import ifcopenshell, ifcopenshell.guid

from helpers import load_model_from_bytes

# ───────── text helpers ─────────
def normalize(txt: str) -> str:
    nfkd = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", nfkd.lower()).strip()

def build_keyword_dict(df: pd.DataFrame):
    """classification → {'title': str, 'keywords': [kw1, kw2, ...]}"""
    out = {}
    for r in df.itertuples(index=False):
        kws = [normalize(str(r.title))]
        if len(r) >= 7 and pd.notna(getattr(r, "keywords", None)) and str(r.keywords).strip():
            kws += [normalize(k) for k in str(r.keywords).split(";") if k.strip()]
        out[str(r.classification)] = {"title": str(r.title), "keywords": list(dict.fromkeys(kws))}
    return out

# ───────── IFC helper ─────────
def element_has_scheme(el, scheme_name: str) -> bool:
    """Return True if element already has an association under the given scheme."""
    for assoc in el.HasAssociations or []:
        if assoc.is_a("IfcRelAssociatesClassification"):
            ref = assoc.RelatingClassification
            rs = getattr(ref, "ReferencedSource", None)
            if rs and getattr(rs, "Name", "") == scheme_name:
                return True
            # fallback – some models store scheme name directly on the reference
            if getattr(ref, "Name", "") == scheme_name:
                return True
    return False

def has_scheme_identification(el, scheme_root, ident: str) -> bool:
    """Check if element already has this Identification under the scheme."""
    for assoc in el.HasAssociations or []:
        if assoc.is_a("IfcRelAssociatesClassification"):
            ref = assoc.RelatingClassification
            rs = getattr(ref, "ReferencedSource", None)
            if (rs and getattr(rs, "Name", "") == scheme_root.Name) or getattr(ref, "Name", "") == scheme_root.Name:
                if getattr(ref, "Identification", "") == ident:
                    return True
    return False

# ───────── UI ─────────
st.header("🔍 Auto-Classification (Keyword + Fuzzy, Mehrfachwahl pro Element)")

if "ifc_bytes" not in st.session_state:
    st.error("Bitte zuerst eine IFC-Datei hochladen.")
    st.stop()

up_map = st.file_uploader(
    "Mapping (CSV/XLSX) – Spalten A=class • B=title • G=keywords(optional, ';' getrennt)",
    type=("csv", "xls", "xlsx"),
)
if up_map is None:
    st.info("Bitte Mapping-Datei hochladen.")
    st.stop()

# Read mapping
df_map = pd.read_excel(up_map, header=0) if up_map.name.lower().endswith(("xls", "xlsx")) else pd.read_csv(up_map)
if len(df_map.columns) < 7:
    df_map = df_map.reindex(columns=list(df_map.columns) + ["keywords"])
df_map.columns = ["classification", "title", "_c", "_d", "_e", "_f", "keywords"][: len(df_map.columns)]

kw_dict = build_keyword_dict(df_map)

# Flat keyword → class map
kw2num = {kw: num for num, data in kw_dict.items() for kw in data["keywords"]}
kw_list = list(kw2num.keys())
options_full = [f"{num} - {v['title']}" for num, v in kw_dict.items()]

# Parameters
pset_name  = st.text_input("Property-Set zum Durchsuchen", value="OEBBset_Semantik_Topologie")
scheme_name = st.text_input("Name des Klassifikationsschemas", value="RC2")
threshold  = st.slider("Fuzzy-Treffer-Schwelle (%)", 20, 100, 80, 5)

# Load IFC
if "model" not in st.session_state:
    model, _ = load_model_from_bytes(st.session_state.ifc_bytes)
    st.session_state.model = model
else:
    model = st.session_state.model

# Build suggestions + keep a GUID -> element map for later write
rows = []
guid_to_element = {}

for el in model.by_type("IfcProduct"):
    if not getattr(el, "GlobalId", None):
        continue
    guid_to_element[el.GlobalId] = el

    if element_has_scheme(el, scheme_name):
        continue

    texts = [str(getattr(el, "Name", ""))]
    for rel in el.IsDefinedBy or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            pset = rel.RelatingPropertyDefinition
            if pset.is_a("IfcPropertySet") and pset.Name == pset_name:
                for p in pset.HasProperties:
                    if p.is_a("IfcPropertySingleValue") and p.NominalValue:
                        texts.append(str(p.NominalValue.wrappedValue))
    blob = normalize(" ".join(texts))

    best_kw, best_score = "", 0
    if blob:
        m = process.extractOne(blob, kw_list, scorer=fuzz.token_set_ratio)
        if m:
            best_kw, best_score = m[0], m[1]

    best_num = kw2num.get(best_kw, "")
    suggested = f"{best_num} - {kw_dict[best_num]['title']}" if best_num and best_score >= threshold else ""

    rows.append(
        dict(
            guid=el.GlobalId,
            name=getattr(el, "Name", ""),
            blob_text=" | ".join(texts)[:150],
            matched_kw=best_kw,
            score=int(best_score if suggested else 0),
            suggestion=suggested,
        )
    )

df = pd.DataFrame(rows)
if df.empty:
    st.info("Keine klassifizierbaren Elemente gefunden.")
    st.stop()

st.dataframe(
    df[["guid", "name", "suggestion", "score", "matched_kw", "blob_text"]],
    use_container_width=True,
    height=400,
)

# Per-row multiselect widgets (like your example)
st.markdown("### Zuweisungen (Mehrfachauswahl pro Element)")
selections = {}
for i, row in df.iterrows():
    default = [row["suggestion"]] if row["suggestion"] else []
    label = f"Klassen wählen – {row['name'] or row['guid'][:10]}"
    selections[row["guid"]] = st.multiselect(
        label=label,
        options=options_full,
        default=default,
        key=f"ms_{row['guid']}",
    )

# Write classifications
if st.button("✍️ Klassifikationen schreiben"):
    scheme_root = next((c for c in model.by_type("IfcClassification") if c.Name == scheme_name), None)
    if scheme_root is None:
        scheme_root = model.createIfcClassification(Name=scheme_name, Source="AutoClass")

    written = 0
    for guid, choices in selections.items():
        if not choices:
            continue
        el = guid_to_element.get(guid)
        if el is None:
            continue

        for choice in choices:
            try:
                num, title = choice.split(" - ", 1)
            except ValueError:
                num, title = choice, ""  # tolerate raw code
            if has_scheme_identification(el, scheme_root, num):
                continue
            cls_ref = model.createIfcClassificationReference(
                Identification=num, Name=title, ReferencedSource=scheme_root
            )
            model.createIfcRelAssociatesClassification(
                GlobalId=ifcopenshell.guid.new(),
                RelatedObjects=[el],
                RelatingClassification=cls_ref,
            )
            written += 1

    if not written:
        st.warning("Keine neuen Klassifikationen geschrieben.")
        st.stop()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc")
    model.write(tmp.name)
    with open(tmp.name, "rb") as f:
        st.download_button(
            "💾 IFC herunterladen",
            f.read(),
            file_name=Path(st.session_state.ifc_name).stem + f"_{scheme_name}.ifc",
            mime="application/octet-stream",
        )
    st.success(f"{written} Klassifikationen geschrieben.")


