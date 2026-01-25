from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import structlog
from lxml import etree

from app.core.tag_config import TagConfig, DEFAULT_TAG_CONFIG
from app.parsing.akoma_models import DocumentOut, NodeOut, ReferenceOut

logger = structlog.get_logger()

AKN_NAMESPACE = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN_NAMESPACES = {"akn": AKN_NAMESPACE}


@dataclass
class ParseState:
    nodes: list[NodeOut]


class AkomaNtosoParser:
    def __init__(self, tag_config: TagConfig = DEFAULT_TAG_CONFIG) -> None:
        self.tag_config = tag_config

    def parse(self, xml_tree: etree._ElementTree) -> DocumentOut:
        root = xml_tree.getroot()
        version_date = self._xpath_text(xml_tree, "//akn:FRBRExpression/akn:FRBRdate/@date")
        publication_date = self._xpath_text(xml_tree, "//akn:FRBRManifestation/akn:FRBRdate/@date")

        state = ParseState(nodes=[])
        self._visit_node(root, "", 0, state)

        return DocumentOut(
            urn=self._xpath_text(xml_tree, "//akn:FRBRWork/akn:FRBRthis/@value"),
            work_urn=self._xpath_text(xml_tree, "//akn:FRBRWork/akn:FRBRuri/@value"),
            expression_urn=self._xpath_text(xml_tree, "//akn:FRBRExpression/akn:FRBRuri/@value"),
            manifestation_urn=self._xpath_text(xml_tree, "//akn:FRBRManifestation/akn:FRBRuri/@value"),
            publication_date=publication_date,
            version_date=version_date,
            nodes=state.nodes,
        )

    def parse_iter(self, path: str) -> DocumentOut:
        version_date = None
        publication_date = None
        urn = None
        work_urn = None
        expression_urn = None
        manifestation_urn = None

        state = ParseState(nodes=[])
        stack: list[tuple[str, str | None]] = []

        context = etree.iterparse(path, events=("start", "end"), recover=True, huge_tree=True)
        for event, elem in context:
            tag = self._strip_ns(elem.tag)
            if event == "start":
                e_id = elem.get("eId") or elem.get("id")
                stack.append((tag, e_id))
                continue

            if tag == "FRBRthis" and stack:
                parent = stack[-2][0] if len(stack) > 1 else None
                value = elem.get("value")
                if parent == "FRBRWork":
                    urn = value
                elif parent == "FRBRExpression":
                    expression_urn = value
                elif parent == "FRBRManifestation":
                    manifestation_urn = value
            if tag == "FRBRuri" and stack:
                parent = stack[-2][0] if len(stack) > 1 else None
                value = elem.get("value")
                if parent == "FRBRWork":
                    work_urn = value
                elif parent == "FRBRExpression":
                    expression_urn = expression_urn or value
                elif parent == "FRBRManifestation":
                    manifestation_urn = manifestation_urn or value
            if tag == "FRBRdate" and stack:
                parent = stack[-2][0] if len(stack) > 1 else None
                value = elem.get("date")
                if parent == "FRBRExpression":
                    version_date = value
                elif parent == "FRBRManifestation":
                    publication_date = value

            if tag in self.tag_config.container_tags or tag in self.tag_config.structural_tags:
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

            if event == "end":
                stack.pop()
                elem.clear()
                while elem.getprevious() is not None:
                    del elem.getparent()[0]

        return DocumentOut(
            urn=urn,
            work_urn=work_urn,
            expression_urn=expression_urn,
            manifestation_urn=manifestation_urn,
            publication_date=publication_date,
            version_date=version_date,
            nodes=state.nodes,
        )

    def _visit_node(self, node: etree._Element, parent_path: str, level: int, state: ParseState) -> None:
        tag = self._strip_ns(node.tag)
        if tag in self.tag_config.metadata_tags:
            return

        node_path = self._build_path(parent_path, node)
        e_id = node.get("eId") or node.get("id")

        if tag in self.tag_config.container_tags:
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
            self._visit_node(child, node_path, level + 1, state)

    def _get_clean_text(self, node: etree._Element) -> tuple[str, list[ReferenceOut]]:
        parts: list[str] = []
        refs: list[ReferenceOut] = []

        if node.text:
            self._append_part(parts, node.text)

        for child in node:
            child_tag = self._strip_ns(child.tag)
            if child_tag in self.tag_config.inline_tags:
                if child_tag == "ref":
                    href = child.get("href") or child.get("hrefs") or ""
                    text = (child.text or "").strip()
                    if href or text:
                        refs.append(ReferenceOut(href=href, text=text))
                inline_text, _ = self._get_clean_text(child)
                self._append_part(parts, inline_text)
                if child.tail:
                    self._append_part(parts, child.tail)
            elif child_tag in self.tag_config.container_tags:
                if child.tail:
                    self._append_part(parts, child.tail)
            else:
                inline_text, _ = self._get_clean_text(child)
                self._append_part(parts, inline_text)
                if child.tail:
                    self._append_part(parts, child.tail)

        text = self._normalize_whitespace("".join(parts))
        return text, refs

    def _build_path(self, parent_path: str, node: etree._Element) -> str:
        tag = self._strip_ns(node.tag)
        e_id = node.get("eId") or node.get("id")
        segment = f"{tag}:{e_id}" if e_id else tag
        return f"{parent_path}/{segment}" if parent_path else segment

    def _strip_ns(self, tag: str) -> str:
        return tag.split("}")[-1]

    def _xml_fragment(self, node: etree._Element) -> str:
        return etree.tostring(node, encoding="unicode")

    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([\.,;:])", r"\1", text)
        return text.strip()

    def _xpath_text(self, tree: etree._ElementTree, xpath: str) -> Optional[str]:
        parts = xpath.split("/")
        fixed_parts = []
        for part in parts:
            if not part:
                fixed_parts.append(part)
                continue
            if part.startswith("@") or part.startswith("akn:"):
                fixed_parts.append(part)
                continue
            fixed_parts.append(f"akn:{part}")
        fixed_xpath = "/".join(fixed_parts)
        result = tree.xpath(fixed_xpath, namespaces=AKN_NAMESPACES)
        if not result:
            return None
        if isinstance(result[0], str):
            return result[0]
        return getattr(result[0], "text", None)

    def _build_path_from_stack(self, stack: list[tuple[str, str | None]]) -> str:
        segments = []
        for tag, e_id in stack:
            if tag in self.tag_config.metadata_tags:
                continue
            segment = f"{tag}:{e_id}" if e_id else tag
            segments.append(segment)
        return "/".join(segments)

    def _append_part(self, parts: list[str], text: str) -> None:
        if not text:
            return
        if parts:
            prev = parts[-1]
            if prev and prev[-1].isalnum() and text[0].isalnum():
                parts.append(" ")
        parts.append(text)
