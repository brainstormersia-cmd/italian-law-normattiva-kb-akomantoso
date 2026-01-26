from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from lxml import etree

from app.core.utils_ids import canonical_doc_id, sha256_text
from app.core.utils_text import text_hash
from app.parsing.hierarchy_builder import build_sort_key, canonical_path
from app.parsing.node_text import clean_text, extract_text
from app.parsing.references import extract_references
from app.parsing.canonicalize import canonical_node

# ✅ Akoma Ntoso support
from app.parsing.akoma_parser import AkomaNtosoParser
from app.parsing.akoma_models import DocumentOut


AKN_NS_PREFIX = "http://docs.oasis-open.org/legaldocml/ns/akn/"


# ---------------------------
# ✅ HELPER: text_hash robusto
# ---------------------------

def _safe_text_hash(text: str | None) -> str:
    """
    Calcola hash del testo gestendo None e stringhe vuote.
    """
    if text is None:
        text = ""
    return text_hash(text)


# ---------------------------
# AKOMA DETECTION
# ---------------------------

def _is_akoma_tree(tree: etree._ElementTree) -> bool:
    root = tree.getroot()
    local = root.tag.split("}")[-1].lower()
    if local == "akomantoso":
        return True
    try:
        ns = etree.QName(root).namespace or ""
    except Exception:
        ns = ""
    return ns.startswith(AKN_NS_PREFIX)


def _is_akoma_path(path: Path) -> bool:
    context = etree.iterparse(str(path), events=("start",), recover=True, huge_tree=True)
    for _event, elem in context:
        local = (elem.tag or "").split("}")[-1].lower()
        if local == "akomantoso":
            return True
        try:
            ns = etree.QName(elem).namespace or ""
        except Exception:
            ns = ""
        return ns.startswith(AKN_NS_PREFIX)
    return False


# ---------------------------
# ✅ FIX REGEX URN (più flessibile)
# ---------------------------

_URN_AKOMA_RE = re.compile(
    r"""
    /akn/
    (?P<country>[a-z]{2})/
    (?P<class>act|bill|doc)/
    (?P<doc_type>[^/]+)/
    (?P<authority>[^/]+)/
    (?P<date>\d{4}-\d{2}-\d{2})/
    (?P<number>\d+)
    (?:/|$)
    """,
    re.IGNORECASE | re.VERBOSE
)


def _parse_akoma_urn(urn: str | None) -> tuple[str, str | None, str | None, str | None]:
    """
    Estrae (doc_type, number, year, authority) da URN Akoma tipico Normattiva.

    Esempio:
      /akn/it/act/decreto/MINISTERO_DELLE_FINANZE/1996-11-18/631/!main
    """
    if not urn:
        return "altro", None, None, None

    m = _URN_AKOMA_RE.search(urn)
    if m:
        doc_type = (m.group("doc_type") or "altro").lower()
        number = m.group("number")
        year = (m.group("date") or "")[:4] or None
        authority = m.group("authority")
        return doc_type, number, year, authority

    # fallback: mantieni qualcosa anche su URN strani
    return "altro", None, None, None


# ---------------------------
# AKOMA -> SHAPE COMUNE usando _build_node
# ---------------------------

def _map_akoma_output(doc: DocumentOut, path: Path | None = None) -> dict:
    doc_type, number, year, authority = _parse_akoma_urn(doc.urn)

    if doc.urn:
        canonical_doc = doc.urn.split("/")[-1]
    elif path:
        canonical_doc = path.stem
    else:
        canonical_doc = canonical_doc_id(doc_type, number, year)

    nodes: list[dict] = []
    for n in doc.nodes:
        cpath = n.canonical_path
        node_type = cpath.split("/")[-1].split(":")[0]
        text_raw = n.text_content or ""

        # ✅ Consolidamento: usa sempre la stessa _build_node finale
        node = _build_node(
            node_type=node_type,
            label=cpath.split("/")[-1],
            path=cpath,
            text_raw=text_raw,
            heading=None,
            hierarchy_string=cpath.replace("/", " > "),
            source_url=None,
        )
        node["metadata_json"] = {
            **(node.get("metadata_json") or {}),
            "akn": {
                "urn": doc.urn,
                "work_urn": doc.work_urn,
                "expression_urn": doc.expression_urn,
                "manifestation_urn": doc.manifestation_urn,
                "publication_date": doc.publication_date,
                "version_date": doc.version_date,
                "authority": authority,
                "eId": getattr(n, "eId", None),
                "level": getattr(n, "level", None),
                "references": [r.model_dump() for r in (n.references or [])],
            },
        }

        nodes.append(node)

    for node in nodes:
        node["sort_key"] = build_sort_key(node["canonical_path"])

    doc_payload = {
        "canonical_doc": canonical_doc,
        "doc_type": doc_type,
        "number": int(number) if number and str(number).isdigit() else None,
        "year": int(year) if year and str(year).isdigit() else None,
        "title": None,
        "valid_from": None,
        "valid_to": None,
        "version_tag": doc.expression_urn or (f"v:{path.name}" if path else doc.version_date),
        "metadata_json": {
            "urn": doc.urn,
            "work_urn": doc.work_urn,
            "expression_urn": doc.expression_urn,
            "manifestation_urn": doc.manifestation_urn,
            "publication_date": doc.publication_date,
            "version_date": doc.version_date,
            "authority": authority,
        },
    }

    return {"doc": doc_payload, "nodes": nodes}


# ---------------------------
# ✅ ENTRY: parse_normattiva + iter (auto Akoma)
# ---------------------------

def parse_normattiva(tree: etree._ElementTree) -> dict:
    if _is_akoma_tree(tree):
        akn_doc = AkomaNtosoParser().parse(tree)
        return _map_akoma_output(akn_doc, path=None)

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
    # ✅ TRUCCO: Invece di usare lo streaming che cancella i dati, 
    # carichiamo il file ed usiamo il parser in memoria.
    if _is_akoma_path(path):
        tree = etree.parse(str(path))
        # Usiamo .parse() invece di .parse_iter()
        akn_doc = AkomaNtosoParser().parse(tree)
        return _map_akoma_output(akn_doc, path=path)

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

    for _event, elem in context:
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

    for node in nodes:
        node["sort_key"] = build_sort_key(node["canonical_path"])

    return {"doc": doc, "nodes": nodes}


# ---------------------------
# RESTO: invariato
# ---------------------------

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
    text_raw = extract_text(preambolo) or ""  # ✅ Garantisce stringa non-None
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
    
    # Pulizia della rubrica (spesso ha spazi o a capo inutili)
    raw_heading = articolo.findtext("rubrica")
    heading = clean_text(raw_heading) if raw_heading else None
    
    # ✅ RAG BOOSTER: Creiamo un contesto ricco per i figli
    # Se c'è una rubrica, la aggiungiamo alla gerarchia visibile ai figli.
    # Esempio: "Articolo 5 (Disposizioni Penali)"
    context_prefix = f"Articolo {art_id}"
    if heading:
        context_prefix += f" ({heading})"

    # --- Nodo Padre (Articolo) ---
    testo_elem = articolo.find("testo")
    text_raw = extract_text(testo_elem) if testo_elem is not None else ""
    
    comma_elements = articolo.findall("comma")
    # Se ci sono commi, il testo dell'articolo è spesso vuoto o introduttivo,
    # ma lo teniamo per sicurezza. Se c'è solo testo senza commi, è fondamentale.
    if comma_elements:
        text_raw = text_raw or "" 
    
    nodes.append(
        _build_node(
            "articolo",
            art_label,
            art_path,
            text_raw,
            heading=heading,
            hierarchy_string=context_prefix, # Il padre ha se stesso come gerarchia
            source_url=source_url,
        )
    )
    
    # --- Caso Articolo senza Commi (testo diretto) ---
    if not comma_elements:
        # A volte il testo è diretto nell'articolo ma strutturalmente è un "comma 1 implicito"
        # Se abbiamo già salvato il testo nel nodo articolo, qui stiamo creando un duplicato logico?
        # Normattiva a volte mette il testo misto.
        # Strategia: Se non ci sono commi espliciti, il nodo 'articolo' sopra basta.
        # Ma se vuoi atomicità, creiamo un finto comma 1 solo se c'è testo residuo non catturato.
        pass 

    # --- Parsing Figli (Commi) ---
    for comma in comma_elements:
        comma_id = comma.get("id") or "1"
        comma_label = f"comma {comma_id}"
        comma_path = canonical_path([f"art:{art_id}", f"c:{comma_id}"])
        comma_text = extract_text(comma) or ""
        
        # ✅ RAG BOOSTER: Il figlio eredita la "Rubrica del Padre" nella gerarchia
        nodes.append(
            _build_node(
                "comma",
                comma_label,
                comma_path,
                comma_text,
                hierarchy_string=f"{context_prefix} > Comma {comma_id}",
                source_url=source_url,
            )
        )
        
        # --- Parsing Nipoti (Lettere) ---
        for lettera in comma.findall("lettera"):
            letter_id = lettera.get("id") or "a"
            letter_label = f"lett. {letter_id}"
            letter_path = canonical_path([f"art:{art_id}", f"c:{comma_id}", f"lett:{letter_id}"])
            letter_text = extract_text(lettera) or ""
            
            nodes.append(
                _build_node(
                    "lettera",
                    letter_label,
                    letter_path,
                    letter_text,
                    hierarchy_string=f"{context_prefix} > Comma {comma_id} > Lettera {letter_id}",
                    source_url=source_url,
                )
            )
            
            # --- Parsing Pronipoti (Numeri) ---
            for numero in lettera.findall("numero"):
                num_id = numero.get("id") or "1"
                num_label = f"num. {num_id}"
                num_path = canonical_path([f"art:{art_id}", f"c:{comma_id}", f"lett:{letter_id}", f"num:{num_id}"])
                num_text = extract_text(numero) or ""
                
                nodes.append(
                    _build_node(
                        "numero",
                        num_label,
                        num_path,
                        num_text,
                        hierarchy_string=(
                            f"{context_prefix} > Comma {comma_id} > Lettera {letter_id} > Numero {num_id}"
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
    text_raw = extract_text(allegato) or ""  # ✅ Garantisce stringa
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
        tabella_text = extract_text(tabella) or ""  # ✅ Garantisce stringa
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
    nota_text = extract_text(nota) or ""  # ✅ Garantisce stringa
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
    """
    ✅ VERSIONE CORRETTA:
    - Garantisce che text_raw sia sempre una stringa (mai None)
    - Calcola text_hash su text_clean (più consistente)
    - Usa _safe_text_hash per robustezza extra
    """
    # Normalizza input: garantisce che text_raw sia stringa
    if text_raw is None:
        text_raw = ""
    
    text_cleaned = clean_text(text_raw)
    
    # ✅ FIX PRINCIPALE: Calcola hash su text_clean (non text_raw)
    # e usa la versione safe che gestisce None
    computed_hash = _safe_text_hash(text_cleaned)
    
    return {
        "node_type": node_type,
        "label": label,
        "canonical_path": path,
        "hierarchy_string": hierarchy_string,
        "heading": heading,
        "text_raw": text_raw,
        "text_clean": text_cleaned,
        "text_hash": computed_hash,  # ✅ Ora sempre presente e valido
        "source_url": source_url,
        "metadata_json": {},
    }