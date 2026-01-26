# app/parsing/akoma_parser.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import structlog
from lxml import etree

from app.core.tag_config import DEFAULT_TAG_CONFIG, TagConfig
from app.parsing.akoma_models import DocumentOut, NodeOut, ReferenceOut

logger = structlog.get_logger()

AKN_NAMESPACE = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN_NAMESPACES = {"akn": AKN_NAMESPACE}


# ----------------------------
# MODELLI INTERNI
# ----------------------------

@dataclass
class ParseState:
    nodes: list[NodeOut]


@dataclass
class _FRBRMeta:
    urn: Optional[str] = None
    work_urn: Optional[str] = None
    expression_urn: Optional[str] = None
    manifestation_urn: Optional[str] = None
    publication_date: Optional[str] = None
    version_date: Optional[str] = None


# ----------------------------
# PARSER
# ----------------------------

class AkomaNtosoParser:
    """
    Parser deterministico per documenti Akoma Ntoso.

    Fix chiave:
    - Mixed-content robusto: se un tag non è in inline_tags ma è "inoffensivo" (p, span, num, etc.)
      NON deve far perdere testo. Ora viene trattato come inline generico (si scende ricorsivamente).
    - I tag structural/container restano “boundary” (non assorbiti nel testo del padre).
    - <ref> produce ReferenceOut, e il suo testo viene incluso normalmente.
    """

    def __init__(self, tag_config: TagConfig = DEFAULT_TAG_CONFIG) -> None:
        self.tag_config = tag_config

    # ----------------------------
    # API PUBBLICA
    # ----------------------------

    def parse(self, xml_tree: etree._ElementTree) -> DocumentOut:
        root = xml_tree.getroot()
        meta = self._extract_frbr_metadata_xpath(xml_tree)

        state = ParseState(nodes=[])
        self._visit_node(root, parent_path="", level=0, state=state)

        return DocumentOut(
            urn=meta.urn,
            work_urn=meta.work_urn,
            expression_urn=meta.expression_urn,
            manifestation_urn=meta.manifestation_urn,
            publication_date=meta.publication_date,
            version_date=meta.version_date,
            nodes=state.nodes,
        )

    def parse_iter(self, path: str) -> DocumentOut:
        meta = _FRBRMeta()
        state = ParseState(nodes=[])

        stack: list[tuple[str, str | None]] = []

        context = etree.iterparse(
            path,
            events=("start", "end"),
            recover=True,
            huge_tree=True,
        )

        for event, elem in context:
            tag = self._strip_ns(elem.tag)

            if event == "start":
                e_id = elem.get("eId") or elem.get("id")
                stack.append((tag, e_id))
                continue

            self._capture_frbr_metadata_from_iter(elem, tag, stack, meta)

            if tag in self.tag_config.structural_tags:
                node_path = self._build_path_from_stack(stack)
                text, refs = self._get_clean_text(elem)

                if text.strip():
                    state.nodes.append(
                        NodeOut(
                            eId=elem.get("eId") or elem.get("id"),
                            canonical_path=node_path,
                            text_content=text.strip(),
                            text_xml_fragment=self._xml_fragment(elem),
                            level=len(stack),
                            references=refs,
                        )
                    )

            stack.pop()
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]

        return DocumentOut(
            urn=meta.urn,
            work_urn=meta.work_urn,
            expression_urn=meta.expression_urn,
            manifestation_urn=meta.manifestation_urn,
            publication_date=meta.publication_date,
            version_date=meta.version_date,
            nodes=state.nodes,
        )

    # ----------------------------
    # VISITA RICORSIVA
    # ----------------------------

    def _visit_node(self, node: etree._Element, parent_path: str, level: int, state: ParseState) -> None:
        tag = self._strip_ns(node.tag)

        if tag in self.tag_config.metadata_tags:
            return

        node_path = self._build_path(parent_path, node)
        e_id = node.get("eId") or node.get("id")

        if tag in self.tag_config.structural_tags:
            text, refs = self._get_clean_text(node)
            if text.strip():
                state.nodes.append(
                    NodeOut(
                        eId=e_id,
                        canonical_path=node_path,
                        text_content=text.strip(),
                        text_xml_fragment=self._xml_fragment(node),
                        level=level,
                        references=refs,
                    )
                )

        for child in node:
            self._visit_node(child, parent_path=node_path, level=level + 1, state=state)

    # ----------------------------
    # ESTRAZIONE TESTO + REFERENCES (FIX MIXED CONTENT)
    # ----------------------------

    def _get_clean_text(self, node: etree._Element) -> tuple[str, list[ReferenceOut]]:
        parts: list[str] = []
        refs: list[ReferenceOut] = []

        # Prendiamo TUTTO il testo del nodo e dei suoi figli (span, b, i, p, etc.)
        # saltando però i figli che sono a loro volta strutturali (altri articoli/commi)
        text = "".join(node.itertext()).strip()
        
        # Estraiamo le referenze
        for ref in node.xpath(".//akn:ref", namespaces=AKN_NAMESPACES):
            href = ref.get("href") or ""
            t = "".join(ref.itertext()).strip()
            if href or t:
                refs.append(ReferenceOut(href=href, text=t))

        return self._normalize_whitespace(text), refs
        if node.text:
            self._append_part(parts, node.text)

        for child in node:
            child_tag = self._strip_ns(child.tag)

            # 1) boundary tags: NON assorbire
            if child_tag in self.tag_config.structural_tags or child_tag in self.tag_config.container_tags:
                # niente testo del figlio nel padre
                pass

            else:
                # 2) ref: estrai ReferenceOut (anche se non è in inline_tags, per robustezza)
                if child_tag == "ref":
                    href = child.get("href") or child.get("hrefs") or ""
                    text_ref = "".join(child.itertext()).strip()
                    if href or text_ref:
                        refs.append(ReferenceOut(href=href, text=text_ref))

                # 3) inline_tags + unknown tags: assorbi ricorsivamente
                #    - inline_tags: ok
                #    - unknown tags: FIX mixed content
                child_text, child_refs = self._get_clean_text(child)
                if child_refs:
                    refs.extend(child_refs)
                if child_text:
                    self._append_part(parts, child_text)

            # tail sempre
            if child.tail:
                self._append_part(parts, child.tail)

        text = self._normalize_whitespace("".join(parts))
        return text, refs

    # ----------------------------
    # PATH / XML / NORMALIZZAZIONE
    # ----------------------------

    def _build_path(self, parent_path: str, node: etree._Element) -> str:
        tag = self._strip_ns(node.tag)
        e_id = node.get("eId") or node.get("id")
        segment = f"{tag}:{e_id}" if e_id else tag
        return f"{parent_path}/{segment}" if parent_path else segment

    def _build_path_from_stack(self, stack: list[tuple[str, str | None]]) -> str:
        segments: list[str] = []
        for tag, e_id in stack:
            if tag in self.tag_config.metadata_tags:
                continue
            segment = f"{tag}:{e_id}" if e_id else tag
            segments.append(segment)
        return "/".join(segments)

    def _strip_ns(self, tag: str) -> str:
        return tag.split("}")[-1]

    def _xml_fragment(self, node: etree._Element) -> str:
        return etree.tostring(node, encoding="unicode")

    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([\.,;:])", r"\1", text)
        return text.strip()

    def _append_part(self, parts: list[str], text: str) -> None:
        if not text:
            return
        if parts:
            prev = parts[-1]
            if prev and prev[-1].isalnum() and text[0].isalnum():
                parts.append(" ")
        parts.append(text)

    # ----------------------------
    # METADATI FRBR
    # ----------------------------

    def _extract_frbr_metadata_xpath(self, xml_tree: etree._ElementTree) -> _FRBRMeta:
        meta = _FRBRMeta()
        meta.version_date = self._xpath_text(xml_tree, "//akn:FRBRExpression/akn:FRBRdate/@date")
        meta.publication_date = self._xpath_text(xml_tree, "//akn:FRBRManifestation/akn:FRBRdate/@date")

        meta.urn = self._xpath_text(xml_tree, "//akn:FRBRWork/akn:FRBRthis/@value")
        meta.work_urn = self._xpath_text(xml_tree, "//akn:FRBRWork/akn:FRBRuri/@value")
        meta.expression_urn = self._xpath_text(xml_tree, "//akn:FRBRExpression/akn:FRBRuri/@value")
        meta.manifestation_urn = self._xpath_text(xml_tree, "//akn:FRBRManifestation/akn:FRBRuri/@value")
        return meta

    def _capture_frbr_metadata_from_iter(
        self,
        elem: etree._Element,
        tag: str,
        stack: list[tuple[str, str | None]],
        meta: _FRBRMeta,
    ) -> None:
        if not stack:
            return

        parent = stack[-2][0] if len(stack) > 1 else None

        if tag == "FRBRthis":
            value = elem.get("value")
            if not value:
                return
            if parent == "FRBRWork":
                meta.urn = value
            elif parent == "FRBRExpression":
                meta.expression_urn = value
            elif parent == "FRBRManifestation":
                meta.manifestation_urn = value

        elif tag == "FRBRuri":
            value = elem.get("value")
            if not value:
                return
            if parent == "FRBRWork":
                meta.work_urn = value
            elif parent == "FRBRExpression":
                meta.expression_urn = value
            elif parent == "FRBRManifestation":
                meta.manifestation_urn = value

        elif tag == "FRBRdate":
            value = elem.get("date")
            if not value:
                return
            if parent == "FRBRExpression":
                meta.version_date = value
            elif parent == "FRBRManifestation":
                meta.publication_date = value

    def _xpath_text(self, tree: etree._ElementTree, xpath: str) -> Optional[str]:
        result = tree.xpath(xpath, namespaces=AKN_NAMESPACES)
        if not result:
            return None
        if isinstance(result[0], str):
            return str(result[0])
        return getattr(result[0], "text", None)
