# pages/3_🧮_Autofill_Qto.py
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import streamlit as st
import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.geom
from helpers import load_model_from_bytes


# ────────────────────────── Mesh mass-properties (no extra deps) ─────────────
def tri_area(v0: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> float:
    return 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0))


def mesh_area_and_volume(verts: np.ndarray, faces: np.ndarray) -> Tuple[float, float]:
    """Return (surface_area, volume) from a triangle mesh.
    Volume via signed tetrahedra wrt origin (abs at end).
    """
    area = 0.0
    vol = 0.0
    for a, b, c in faces:
        v0, v1, v2 = verts[a], verts[b], verts[c]
        area += tri_area(v0, v1, v2)
        vol += np.dot(v0, np.cross(v1, v2)) / 6.0
    return float(area), abs(float(vol))


def bbox_longest_edge(verts: np.ndarray) -> float:
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    return float((maxs - mins).max())


# ───────────────────────────── Helpers for IFC Qto ───────────────────────────
def element_has_qto(element) -> bool:
    for rel in element.IsDefinedBy or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            if rel.RelatingPropertyDefinition.is_a("IfcElementQuantity"):
                return True
    return False


QTO_MAP: Dict[str, str] = {
    "IfcWall": "Qto_WallBaseQuantities",
    "IfcWallStandardCase": "Qto_WallBaseQuantities",
    "IfcSlab": "Qto_SlabBaseQuantities",
    "IfcBeam": "Qto_BeamBaseQuantities",
    "IfcColumn": "Qto_ColumnBaseQuantities",
    # Add more mappings here as needed…
}


def make_quantity(model: ifcopenshell.file, qtype: str, name: str, value: float):
    """Create an IfcQuantity* with the correct value attribute."""
    val_attr = {
        "IfcQuantityVolume": "VolumeValue",
        "IfcQuantityArea": "AreaValue",
        "IfcQuantityLength": "LengthValue",
        "IfcQuantityCount": "CountValue",
        "IfcQuantityWeight": "WeightValue",
    }[qtype]
    return model.create_entity(
        qtype,
        Name=name,
        Description=None,
        Unit=None,
        **{val_attr: value},
    )


def generate_qto(model: ifcopenshell.file) -> int:
    """Create missing Qto sets & quantities using tessellated geometry."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    # NOTE: By default the tessellated geometry often has openings subtracted.
    # If you want "gross" values (incl. openings), configure settings accordingly
    # for your IfcOpenShell build, or post-process as needed.

    new_count = 0

    for el in model.by_type("IfcProduct"):
        if not getattr(el, "GlobalId", None):
            continue

        if element_has_qto(el):
            continue  # keep author-supplied quantities

        try:
            shape = ifcopenshell.geom.create_shape(settings, el)
        except Exception:
            continue  # no geometry or failed BREP -> skip

        # verts: flat array [x0,y0,z0, x1,y1,z1, ...]
        verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
        faces = np.asarray(shape.geometry.faces, dtype=int).reshape(-1, 3)

        if len(verts) == 0 or len(faces) == 0:
            continue

        area, volume = mesh_area_and_volume(verts, faces)
        length = bbox_longest_edge(verts)

        # Choose Qto set name by class, else generic
        cls = el.is_a()
        qto_name = QTO_MAP.get(cls, "Qto_GenericBaseQuantities")

        qset = model.createIfcElementQuantity(
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=None,
            Name=qto_name,
            Description=None,
            MethodOfMeasurement=None,
            Quantities=(),
        )

        # Always add GrossVolume & GrossArea
        qset.Quantities = qset.Quantities + (
            make_quantity(model, "IfcQuantityVolume", "GrossVolume", volume),
            make_quantity(model, "IfcQuantityArea", "GrossArea", area),
        )

        # Length is useful for linear elements; harmless for others
        if length > 0:
            qset.Quantities = qset.Quantities + (
                make_quantity(model, "IfcQuantityLength", "Length", length),
            )

        # attach to element
        model.createIfcRelDefinesByProperties(
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=None,
            Name=None,
            Description=None,
            RelatedObjects=[el],
            RelatingPropertyDefinition=qset,
        )

        new_count += 1

    return new_count


# ─────────────────────────────── Streamlit UI ────────────────────────────────
st.header("🧮 Autofill Qto (Quantity Take-Off)")

if "ifc_bytes" not in st.session_state:
    st.error("Bitte zuerst eine IFC-Datei auf der Startseite hochladen.")
    st.stop()
if "model" not in st.session_state:
    # first time we enter this page → load IFC bytes now
    model, tmp_path = load_model_from_bytes(st.session_state.ifc_bytes)
    st.session_state.model = model
    st.session_state.ifc_path = tmp_path

model: ifcopenshell.file = st.session_state.model
default_name = Path(st.session_state.ifc_name).stem + "_with_qto.ifc"

if st.button("⚙️  Fehlende Qto automatisch erzeugen"):
    with st.spinner("Berechne Geometrie & erstelle Quantity-Sets …"):
        added = generate_qto(model)

    st.success(f"Fertig – {added} ElementQuantity-Sets neu erstellt.")

    # Write to a temp file and offer download
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc")
    tmp_path = tmp.name
    tmp.close()
    model.write(tmp_path)

    with open(tmp_path, "rb") as f:
        st.download_button(
            label=f"💾 Geänderte IFC herunterladen ({default_name})",
            data=f,
            file_name=default_name,
            mime="application/octet-stream",
        )
else:
    st.info("Drücken Sie **Fehlende Qto automatisch erzeugen**, um Mengen zu berechnen.")
