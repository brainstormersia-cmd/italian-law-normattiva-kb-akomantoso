from __future__ import annotations

from lxml import etree
from pathlib import Path


def read_xml(path: Path) -> etree._ElementTree:
    parser = etree.XMLParser(resolve_entities=False, recover=True)
    return etree.parse(str(path), parser=parser)
