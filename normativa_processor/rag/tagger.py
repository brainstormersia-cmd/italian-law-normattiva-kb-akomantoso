from __future__ import annotations

from normativa_processor.core.types import NLPModelType

TAG_KEYWORDS = {
    "obblighi": ["obbligo", "deve", "devono", "obbligatorio"],
    "divieti": ["vietato", "divieto", "non è consentito", "non possono"],
    "sanzioni": ["sanzione", "sanzioni", "ammenda", "multa", "pena"],
    "privacy": ["dati personali", "privacy", "gdpr", "protezione dei dati"],
    "appalti": ["appalto", "gara", "contraente", "stazione appaltante"],
    "definizioni": ["si intende", "definizione", "ai fini del presente"],
    "deroghe": ["deroga", "in deroga", "fatto salvo"],
    "entrata in vigore": ["entra in vigore", "vigore dal"],
    "competenze": ["competenza", "competenze", "attribuito"],
    "diritto del lavoro": ["lavoratore", "datore di lavoro", "lavoro"],
    "tutela ambientale": ["ambiente", "ambientale", "inquinamento"],
}


def extract_entity_tags(text: str, nlp: NLPModelType) -> list[str]:
    tags = []
    lowered = text.lower()
    if "gdpr" in lowered or "regolamento (ue) 2016/679" in lowered:
        tags.append("gdpr")
    if "sanzioni amministrative" in lowered:
        tags.append("sanzioni amministrative")
    if "datore di lavoro" in lowered:
        tags.append("obblighi datore di lavoro")
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_.lower() in {"org", "law", "event"}:
                tags.append(ent.text.lower())
    return tags


def extract_tags(text: str, nlp: NLPModelType = None) -> list[str]:
    lowered = text.lower()
    tags = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            tags.append(tag)
    tags.extend(extract_entity_tags(text, nlp))
    unique_tags = []
    for tag in tags:
        if tag not in unique_tags:
            unique_tags.append(tag)
    if len(unique_tags) < 5:
        unique_tags.append("normativa")
    return unique_tags[:10]
