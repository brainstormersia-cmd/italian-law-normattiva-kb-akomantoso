from pathlib import Path
from lxml import etree

from app.parsing.normattiva_parser import parse_normattiva


def test_allegati_tabelle():
    tree = etree.parse(str(Path(__file__).parent / "fixtures" / "normattiva_sample_1.xml"))
    parsed = parse_normattiva(tree)
    types = [node["node_type"] for node in parsed["nodes"]]
    assert "allegato" in types
    assert "tabella" in types
