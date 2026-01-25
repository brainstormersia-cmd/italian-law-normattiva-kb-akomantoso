from app.parsing.references import extract_references


def test_reference_extraction():
    text = "Ai sensi del d.lgs. 74/2000 e del DPR 917/1986, come modificato da legge 212/2000."
    refs = extract_references(text)
    targets = {ref.get("target_canonical_doc") for ref in refs if ref.get("target_canonical_doc")}
    assert "dlgs:74:2000" in targets
    assert "dpr:917:1986" in targets
    assert "l:212:2000" in targets
    relations = {ref.get("relation_type") for ref in refs}
    assert "AMENDS" in relations or "CITES" in relations
