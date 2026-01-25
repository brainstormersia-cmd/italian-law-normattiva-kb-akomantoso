from __future__ import annotations

from lxml import etree
from pathlib import Path
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
    version_tag = meta.findtext("version_tag") if meta is not None else None
    canonical_doc = canonical_doc_id(doc_type, number, year)

    doc = {
        "canonical_doc": canonical_doc,
        "doc_type": doc_type,
        "number": int(number) if number and number.isdigit() else None,
        "year": int(year) if year and year.isdigit() else None,
        "title": title,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "version_tag": version_tag,
    }

    nodes = _parse_nodes(root, source_url)

    for node in nodes:
        node["sort_key"] = build_sort_key(node["canonical_path"])

    return {"doc": doc, "nodes": nodes}


def parse_normattiva_iter(path: Path) -> dict:
    context = etree.iterparse(str(path), events=("end",), recover=True)
    meta_data: dict[str, str | None] = {
        "doc_type": None,
        "number": None,
        "year": None,
        "title": None,
        "valid_from": None,
        "valid_to": None,
        "source_url": None,
        "version_tag": None,
    }
    nodes: list[dict] = []

    for event, elem in context:
        tag = elem.tag.split("}")[-1]
        if tag == "meta":
            meta_data["doc_type"] = elem.findtext("doc_type")
            meta_data["number"] = elem.findtext("number")
            meta_data["year"] = elem.findtext("year")
            meta_data["title"] = elem.findtext("title")
            meta_data["valid_from"] = elem.findtext("valid_from")
            meta_data["valid_to"] = elem.findtext("valid_to")
            meta_data["source_url"] = elem.findtext("source_url")
            meta_data["version_tag"] = elem.findtext("version_tag")
        if tag in {"preambolo", "articolo", "allegato", "nota"}:
            nodes.extend(_parse_fragment(elem, meta_data["source_url"]))
            _clear_element(elem)
    doc_type = (meta_data["doc_type"] or "altro").lower()
    canonical_doc = canonical_doc_id(doc_type, meta_data["number"], meta_data["year"])
    doc = {
        "canonical_doc": canonical_doc,
        "doc_type": doc_type,
        "number": int(meta_data["number"]) if meta_data["number"] and str(meta_data["number"]).isdigit() else None,
        "year": int(meta_data["year"]) if meta_data["year"] and str(meta_data["year"]).isdigit() else None,
        "title": meta_data["title"],
        "valid_from": meta_data["valid_from"],
        "valid_to": meta_data["valid_to"],
        "version_tag": meta_data["version_tag"],
    }
    return {"doc": doc, "nodes": nodes}


def _clear_element(elem: etree._Element) -> None:
    elem.clear()
    while elem.getprevious() is not None:
        del elem.getparent()[0]


def _parse_nodes(root: etree._Element, source_url: str | None) -> list[dict]:
    nodes: list[dict] = []

    preambolo = root.find("preambolo")
    if preambolo is not None:
        nodes.extend(_parse_preambolo(preambolo, source_url))

    for articolo in root.findall("articolo"):
        nodes.extend(_parse_articolo(articolo, source_url))

    for allegato in root.findall("allegato"):
        nodes.extend(_parse_allegato(allegato, source_url))

    for nota in root.findall("nota"):
        nodes.extend(_parse_nota(nota, source_url))

    return nodes


def _parse_fragment(element: etree._Element, source_url: str | None) -> list[dict]:
    tag = element.tag.split("}")[-1]
    if tag == "preambolo":
        return _parse_preambolo(element, source_url)
    if tag == "articolo":
        return _parse_articolo(element, source_url)
    if tag == "allegato":
        return _parse_allegato(element, source_url)
    if tag == "nota":
        return _parse_nota(element, source_url)
    return []


def _parse_preambolo(preambolo: etree._Element, source_url: str | None) -> list[dict]:
    text_raw = extract_text(preambolo)
    node_path = canonical_path(["atto", "preambolo"])
    return [
        _build_node(
            "atto_preambolo",
            "Preambolo",
            node_path,
            text_raw,
            hierarchy_string="Atto > Preambolo",
            source_url=source_url,
        )
    ]


def _parse_articolo(articolo: etree._Element, source_url: str | None) -> list[dict]:
    nodes: list[dict] = []
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
    return nodes


def _parse_allegato(allegato: etree._Element, source_url: str | None) -> list[dict]:
    nodes: list[dict] = []
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
    return nodes


def _parse_nota(nota: etree._Element, source_url: str | None) -> list[dict]:
    nota_id = nota.get("id") or "1"
    nota_label = f"nota {nota_id}"
    nota_path = canonical_path([f"nota:{nota_id}"])
    nota_text = extract_text(nota)
    return [
        _build_node(
            "nota",
            nota_label,
            nota_path,
            nota_text,
            hierarchy_string=f"Nota {nota_id}",
            source_url=source_url,
        )
    ]


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
