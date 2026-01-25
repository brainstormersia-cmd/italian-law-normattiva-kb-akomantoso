from pathlib import Path
from lxml import etree

from app.parsing.normattiva_parser import parse_normattiva


def test_hierarchy_paths():
    tree = etree.parse(str(Path(__file__).parent / "fixtures" / "normattiva_sample_1.xml"))
    parsed = parse_normattiva(tree)
    paths = {node["canonical_path"] for node in parsed["nodes"]}
    assert "art:1-bis" in paths
    assert "art:1-bis/c:1-bis" in paths
    assert "art:1-bis/c:1-bis/lett:a" in paths
    assert "art:1-bis/c:1-bis/lett:a/num:1" in paths
    assert "allegato:A" in paths
    assert "allegato:A/tabella:1" in paths
