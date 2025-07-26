# helpers.py
import tempfile
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid
import pandas as pd


# ---------- classification ----------
def get_classification_strings(element):
    out = []
    for rel in element.HasAssociations or []:
        if rel.is_a("IfcRelAssociatesClassification"):
            cls = rel.RelatingClassification
            if not cls:
                continue
            bits = []
            for attr in ("ReferencedSource", "ClassificationSource"):
                src = getattr(cls, attr, None)
                if src and getattr(src, "Name", None):
                    bits.append(src.Name)
            if getattr(cls, "Name", None):
                bits.append(cls.Name)
            if getattr(cls, "Identification", None):
                bits.append(cls.Identification)
            if bits:
                out.append(" : ".join(bits))
    return out


# ---------- quantities ----------
def get_quantity_dict(element):
    q = {}
    for rel in element.IsDefinedBy or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        qset = rel.RelatingPropertyDefinition
        if qset and qset.is_a("IfcElementQuantity"):
            for quantity in qset.Quantities:
                for attr in ("AreaValue", "VolumeValue", "LengthValue", "CountValue", "WeightValue"):
                    if hasattr(quantity, attr):
                        val = getattr(quantity, attr)
                        if val is not None:
                            q[quantity.Name] = val
                        break
    return q


# ---------- custom P-set harvest ----------
def get_pset_dict(element, pset_name):
    out = {}
    for rel in element.IsDefinedBy or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if pset and pset.is_a("IfcPropertySet") and pset.Name == pset_name:
            for prop in pset.HasProperties:
                if prop.is_a("IfcPropertySingleValue"):
                    val = prop.NominalValue
                    out[prop.Name] = val.wrappedValue if val else None
    return out


# ---------- FULL extraction → DataFrame ----------
def extract_ifc_to_dataframe(model, pset_name, split_classifications=False):
    rows = []
    quantity_keys = set()
    pset_keys = set()
    max_cls = 0

    for element in model.by_type("IfcProduct"):
        if not getattr(element, "GlobalId", None):
            continue

        cls_list = get_classification_strings(element)
        if split_classifications:
            max_cls = max(max_cls, len(cls_list))

        row = {
            "guid": element.GlobalId,
            "class": element.is_a(),
            "name": getattr(element, "Name", "") or "",
            "classification": "; ".join(cls_list) if not split_classifications else cls_list,
        }

        qdict = get_quantity_dict(element)
        row.update(qdict)
        quantity_keys.update(qdict.keys())

        pdict = get_pset_dict(element, pset_name)
        row.update(pdict)
        pset_keys.update(pdict.keys())

        rows.append(row)

    if split_classifications:
        cls_cols = [f"classification_{i+1}" for i in range(max_cls)]
        for r in rows:
            values = r.pop("classification")
            for i, val in enumerate(values):
                r[f"classification_{i+1}"] = val
        base_cols = ["guid", "class", "name"] + cls_cols
    else:
        base_cols = ["guid", "class", "name", "classification"]

    header = base_cols + sorted(quantity_keys) + sorted(pset_keys)
    df = pd.DataFrame(rows)
    # ensure all header columns exist
    for col in header:
        if col not in df.columns:
            df[col] = None
    df = df[header]
    return df


# ---------- Write uploaded bytes to temp & load ----------
def load_model_from_bytes(byte_data) -> ifcopenshell.file:
    # we must write to disk; IfcOpenShell cannot open from raw bytes directly (unless using io in newer builds)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc")
    tmp.write(byte_data)
    tmp.flush()
    tmp.close()
    return ifcopenshell.open(tmp.name), tmp.name



def _get_gross_volume(element):
    """Return GrossVolume if present, else None."""
    for rel in element.IsDefinedBy or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        qset = rel.RelatingPropertyDefinition
        if qset and qset.is_a("IfcElementQuantity"):
            for q in qset.Quantities:
                if q.Name.lower() == "grossvolume" and hasattr(q, "VolumeValue"):
                    return q.VolumeValue
    return None


def add_rc2_pset(model, prüfung_flag: bool = True):
    """
    Adds / updates P‑set **Oebb_RC2** on every physical element.

    • Pruefung      (BOOLEAN)   ← prüfung_flag
    • Position_1..n (LABEL)     ← classification strings
    • Menge_1..n    (VOLUME)    ← GrossVolume value (copied)

    """
    PSET_NAME = "Oebb_RC2"

    for elem in model.by_type("IfcProduct"):
        if not getattr(elem, "GlobalId", None):
            continue

        # --------------------- find or create the P‑set ---------------------
        pset = None
        for rel in elem.IsDefinedBy or []:
            if rel.is_a("IfcRelDefinesByProperties"):
                obj = rel.RelatingPropertyDefinition
                if obj.is_a("IfcPropertySet") and obj.Name == PSET_NAME:
                    pset = obj
                    break

        if pset is None:
            pset = model.createIfcPropertySet(
                GlobalId=ifcopenshell.guid.new(),
                OwnerHistory=None,
                Name=PSET_NAME,
                Description=None,
                HasProperties=(),
            )
            model.createIfcRelDefinesByProperties(
                GlobalId=ifcopenshell.guid.new(),
                OwnerHistory=None,
                Name=None,
                Description=None,
                RelatedObjects=[elem],
                RelatingPropertyDefinition=pset,
            )

        # helper to add / update a single property in that P‑set
        def upsert(name: str, nominal_value):
            existing = next((p for p in pset.HasProperties if p.Name == name), None)
            if existing:
                existing.NominalValue.wrappedValue = nominal_value
            else:
                new_prop = model.createIfcPropertySingleValue(
                    Name=name,
                    Description=None,
                    NominalValue=nominal_value,
                    Unit=None,
                )
                # tuples are immutable → re‑assign
                pset.HasProperties = pset.HasProperties + (new_prop,)

        # --------------------- 1) boolean Pruefung --------------------------
        upsert(
            "Pruefung",
            model.create_entity("IfcBoolean", prüfung_flag),
        )

        # --------------------- 2) classifications → Position_n --------------
        cls_list = get_classification_strings(elem)
        gross_vol = _get_gross_volume(elem)

        for idx, cls_txt in enumerate(cls_list, start=1):
            upsert(
                f"Position_{idx}",
                model.create_entity("IfcLabel", cls_txt),
            )
            upsert(
                f"Menge_{idx}",
                model.create_entity("IfcVolumeMeasure", gross_vol if gross_vol is not None else 0.0),
            )

    return model
