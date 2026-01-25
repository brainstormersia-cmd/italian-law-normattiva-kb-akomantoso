from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

import structlog
from lxml import etree

from app.core.tag_config import TagConfig, DEFAULT_TAG_CONFIG
from app.parsing.akoma_models import DocumentOut, NodeOut, ReferenceOut

logger = structlog.get_logger()


@dataclass
class ParseState:
    nodes: list[NodeOut]


class AkomaNtosoParser:
    def __init__(self, tag_config: TagConfig = DEFAULT_TAG_CONFIG) -> None:
        self.tag_config = tag_config

    def parse(self, xml_tree: etree._ElementTree) -> DocumentOut:
        root = xml_tree.getroot()
        frbr = self._extract_frbr(xml_tree)
        version_date = self._xpath_text(xml_tree, "//FRBRExpression/FRBRdate/@date")
        publication_date = self._xpath_text(xml_tree, "//FRBRManifestation/FRBRdate/@date")

        state = ParseState(nodes=[])
        self._visit_node(root, "", 0, state)

        return DocumentOut(
            urn=self._xpath_text(xml_tree, "//FRBRWork/FRBRthis/@value"),
            work_urn=self._xpath_text(xml_tree, "//FRBRWork/FRBRuri/@value"),
            expression_urn=self._xpath_text(xml_tree, "//FRBRExpression/FRBRuri/@value"),
            manifestation_urn=self._xpath_text(xml_tree, "//FRBRManifestation/FRBRuri/@value"),
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
            return

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
            parts.append(node.text)

        for child in node:
            child_tag = self._strip_ns(child.tag)
            if child_tag in self.tag_config.inline_tags:
                if child_tag == "ref":
                    href = child.get("href") or child.get("hrefs") or ""
                    text = (child.text or "").strip()
                    if href or text:
                        refs.append(ReferenceOut(href=href, text=text))
                inline_text, _ = self._get_clean_text(child)
                parts.append(inline_text)
                if child.tail:
                    parts.append(child.tail)
            elif child_tag in self.tag_config.container_tags:
                if child.tail:
                    parts.append(child.tail)
            else:
                inline_text, _ = self._get_clean_text(child)
                parts.append(inline_text)
                if child.tail:
                    parts.append(child.tail)

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
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([\.,;:])", r"\1", text)
        return text.strip()

    def _xpath_text(self, tree: etree._ElementTree, xpath: str) -> Optional[str]:
        result = tree.xpath(xpath)
        if not result:
            return None
        if isinstance(result[0], str):
            return result[0]
        return getattr(result[0], "text", None)

    def _extract_frbr(self, tree: etree._ElementTree) -> dict[str, Optional[str]]:
        return {
            "work": self._xpath_text(tree, "//FRBRWork/FRBRthis/@value"),
            "expression": self._xpath_text(tree, "//FRBRExpression/FRBRthis/@value"),
            "manifestation": self._xpath_text(tree, "//FRBRManifestation/FRBRthis/@value"),
        }
