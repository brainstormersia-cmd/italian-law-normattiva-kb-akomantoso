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
    valid_from = meta.findtext("valid_from") if meta is not None else None
    valid_to = meta.findtext("valid_to") if meta is not None else None
    source_url = meta.findtext("source_url") if meta is not None else None
    canonical_doc = canonical_doc_id(doc_type, number, year)

    doc = {
        "canonical_doc": canonical_doc,
        "doc_type": doc_type,
        "number": int(number) if number and number.isdigit() else None,
        "year": int(year) if year and year.isdigit() else None,
        "title": title,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }

    nodes: list[dict] = []

    preambolo = root.find("preambolo")
    if preambolo is not None:
        text_raw = extract_text(preambolo)
        node_path = canonical_path(["atto", "preambolo"])
        nodes.append(
            _build_node(
                "atto_preambolo",
                "Preambolo",
                node_path,
                text_raw,
                hierarchy_string="Atto > Preambolo",
                source_url=source_url,
            )
        )

    for articolo in root.findall("articolo"):
        art_id = articolo.get("id") or "1"
        art_label = f"Art. {art_id}"
        art_path = canonical_path([f"art:{art_id}"])
        heading = articolo.findtext("rubrica")
        text_raw = extract_text(articolo.find("testo"))
        comma_elements = articolo.findall("comma")
        if comma_elements:
            text_raw = ""
        nodes.append(
            _build_node(
                "articolo",
                art_label,
                art_path,
                text_raw,
                heading=heading,
                hierarchy_string=f"Articolo {art_id}",
                source_url=source_url,
            )
        )
        if not comma_elements:
            comma_path = canonical_path([f"art:{art_id}", "c:1"])
            nodes.append(
                _build_node(
                    "comma",
                    "comma 1",
                    comma_path,
                    extract_text(articolo),
                    hierarchy_string=f"Articolo {art_id} > Comma 1",
                    source_url=source_url,
                )
            )
        for comma in comma_elements:
            comma_id = comma.get("id") or "1"
            comma_label = f"comma {comma_id}"
            comma_path = canonical_path([f"art:{art_id}", f"c:{comma_id}"])
            comma_text = extract_text(comma)
            nodes.append(
                _build_node(
                    "comma",
                    comma_label,
                    comma_path,
                    comma_text,
                    hierarchy_string=f"Articolo {art_id} > Comma {comma_id}",
                    source_url=source_url,
                )
            )
            for lettera in comma.findall("lettera"):
                letter_id = lettera.get("id") or "a"
                letter_label = f"lett. {letter_id}"
                letter_path = canonical_path([f"art:{art_id}", f"c:{comma_id}", f"lett:{letter_id}"])
                letter_text = extract_text(lettera)
                nodes.append(
                    _build_node(
                        "lettera",
                        letter_label,
                        letter_path,
                        letter_text,
                        hierarchy_string=f"Articolo {art_id} > Comma {comma_id} > Lettera {letter_id}",
                        source_url=source_url,
                    )
                )
                for numero in lettera.findall("numero"):
                    num_id = numero.get("id") or "1"
                    num_label = f"num. {num_id}"
                    num_path = canonical_path([f"art:{art_id}", f"c:{comma_id}", f"lett:{letter_id}", f"num:{num_id}"])
                    num_text = extract_text(numero)
                    nodes.append(
                        _build_node(
                            "numero",
                            num_label,
                            num_path,
                            num_text,
                            hierarchy_string=(
                                f"Articolo {art_id} > Comma {comma_id} > Lettera {letter_id} > Numero {num_id}"
                            ),
                            source_url=source_url,
                        )
                    )

    for allegato in root.findall("allegato"):
        allegato_id = allegato.get("id") or "A"
        allegato_label = f"Allegato {allegato_id}"
        allegato_path = canonical_path([f"allegato:{allegato_id}"])
        text_raw = extract_text(allegato)
        nodes.append(
            _build_node(
                "allegato",
                allegato_label,
                allegato_path,
                text_raw,
                hierarchy_string=f"Allegato {allegato_id}",
                source_url=source_url,
            )
        )
        for tabella in allegato.findall("tabella"):
            tabella_id = tabella.get("id") or "1"
            tabella_label = f"Tabella {tabella_id}"
            tabella_path = canonical_path([f"allegato:{allegato_id}", f"tabella:{tabella_id}"])
            tabella_text = extract_text(tabella)
            nodes.append(
                _build_node(
                    "tabella",
                    tabella_label,
                    tabella_path,
                    tabella_text,
                    hierarchy_string=f"Allegato {allegato_id} > Tabella {tabella_id}",
                    source_url=source_url,
                )
            )

    for nota in root.findall("nota"):
        nota_id = nota.get("id") or "1"
        nota_label = f"nota {nota_id}"
        nota_path = canonical_path([f"nota:{nota_id}"])
        nota_text = extract_text(nota)
        nodes.append(
            _build_node(
                "nota",
                nota_label,
                nota_path,
                nota_text,
                hierarchy_string=f"Nota {nota_id}",
                source_url=source_url,
            )
        )

    for node in nodes:
        node["sort_key"] = build_sort_key(node["canonical_path"])

    return {"doc": doc, "nodes": nodes}


def _build_node(
    node_type: str,
    label: str,
    path: str,
    text_raw: str,
    heading: str | None = None,
    hierarchy_string: str | None = None,
    source_url: str | None = None,
) -> dict:
    text_clean = clean_text(text_raw)
    return {
        "node_type": node_type,
        "label": label,
        "canonical_path": path,
        "hierarchy_string": hierarchy_string,
        "heading": heading,
        "text_raw": text_raw,
        "text_clean": text_clean,
        "text_hash": text_hash(text_raw),
        "source_url": source_url,
        "metadata_json": {},
    }
