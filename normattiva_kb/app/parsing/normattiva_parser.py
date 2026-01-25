from __future__ import annotations

from lxml import etree
from typing import Iterable

from app.core.utils_ids import canonical_doc_id, sha256_text
from app.core.utils_text import text_hash
from app.parsing.hierarchy_builder import build_sort_key, canonical_path
from app.parsing.node_text import clean_text, extract_text
from app.parsing.references import extract_references
from app.parsing.canonicalize import canonical_node


def parse_normattiva(tree: etree._ElementTree) -> dict:
    root = tree.getroot()
    meta = root.find("meta")
    doc_type = (meta.findtext("doc_type") if meta is not None else "altro").lower()
    number = meta.findtext("number") if meta is not None else None
    year = meta.findtext("year") if meta is not None else None
    title = meta.findtext("title") if meta is not None else None
    canonical_doc = canonical_doc_id(doc_type, number, year)

    doc = {
        "canonical_doc": canonical_doc,
        "doc_type": doc_type,
        "number": int(number) if number and number.isdigit() else None,
        "year": int(year) if year and year.isdigit() else None,
        "title": title,
    }

    nodes: list[dict] = []

    preambolo = root.find("preambolo")
    if preambolo is not None:
        text_raw = extract_text(preambolo)
        node_path = canonical_path(["atto", "preambolo"])
        nodes.append(_build_node("atto_preambolo", "Preambolo", node_path, text_raw))

    for articolo in root.findall("articolo"):
        art_id = articolo.get("id") or "1"
        art_label = f"Art. {art_id}"
        art_path = canonical_path([f"art:{art_id}"])
        heading = articolo.findtext("rubrica")
        text_raw = extract_text(articolo.find("testo"))
        nodes.append(
            _build_node("articolo", art_label, art_path, text_raw, heading=heading)
        )
        for comma in articolo.findall("comma"):
            comma_id = comma.get("id") or "1"
            comma_label = f"comma {comma_id}"
            comma_path = canonical_path([f"art:{art_id}", f"c:{comma_id}"])
            comma_text = extract_text(comma)
            nodes.append(_build_node("comma", comma_label, comma_path, comma_text))
            for lettera in comma.findall("lettera"):
                letter_id = lettera.get("id") or "a"
                letter_label = f"lett. {letter_id}"
                letter_path = canonical_path([f"art:{art_id}", f"c:{comma_id}", f"lett:{letter_id}"])
                letter_text = extract_text(lettera)
                nodes.append(_build_node("lettera", letter_label, letter_path, letter_text))
                for numero in lettera.findall("numero"):
                    num_id = numero.get("id") or "1"
                    num_label = f"num. {num_id}"
                    num_path = canonical_path([f"art:{art_id}", f"c:{comma_id}", f"lett:{letter_id}", f"num:{num_id}"])
                    num_text = extract_text(numero)
                    nodes.append(_build_node("numero", num_label, num_path, num_text))

    for allegato in root.findall("allegato"):
        allegato_id = allegato.get("id") or "A"
        allegato_label = f"Allegato {allegato_id}"
        allegato_path = canonical_path([f"allegato:{allegato_id}"])
        text_raw = extract_text(allegato)
        nodes.append(_build_node("allegato", allegato_label, allegato_path, text_raw))
        for tabella in allegato.findall("tabella"):
            tabella_id = tabella.get("id") or "1"
            tabella_label = f"Tabella {tabella_id}"
            tabella_path = canonical_path([f"allegato:{allegato_id}", f"tabella:{tabella_id}"])
            tabella_text = extract_text(tabella)
            nodes.append(_build_node("tabella", tabella_label, tabella_path, tabella_text))

    for nota in root.findall("nota"):
        nota_id = nota.get("id") or "1"
        nota_label = f"nota {nota_id}"
        nota_path = canonical_path([f"nota:{nota_id}"])
        nota_text = extract_text(nota)
        nodes.append(_build_node("nota", nota_label, nota_path, nota_text))

    for node in nodes:
        node["sort_key"] = build_sort_key(node["canonical_path"])

    return {"doc": doc, "nodes": nodes}


def _build_node(node_type: str, label: str, path: str, text_raw: str, heading: str | None = None) -> dict:
    text_clean = clean_text(text_raw)
    return {
        "node_type": node_type,
        "label": label,
        "canonical_path": path,
        "heading": heading,
        "text_raw": text_raw,
        "text_clean": text_clean,
        "text_hash": text_hash(text_raw),
        "metadata_json": {},
    }
