from pathlib import Path
from lxml import etree

from app.parsing.normattiva_parser import parse_normattiva


def test_articoli_bis_commi_bis():
    tree = etree.parse(str(Path(__file__).parent / "fixtures" / "normattiva_sample_1.xml"))
    parsed = parse_normattiva(tree)
    labels = {node["label"] for node in parsed["nodes"]}
    assert "Art. 1-bis" in labels
    assert "comma 1-bis" in labels
