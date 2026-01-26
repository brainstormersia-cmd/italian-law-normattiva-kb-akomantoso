from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class TagConfig:
    structural_tags: frozenset[str]
    container_tags: frozenset[str]
    inline_tags: frozenset[str]
    metadata_tags: frozenset[str]

# CONFIGURAZIONE OTTIMIZZATA PER NORMATTIVA/AKOMA NTOSO
# Risolve il problema "0 Nodi" sbloccando il flusso del testo
DEFAULT_TAG_CONFIG = TagConfig(
    structural_tags=frozenset({
        # UNITA' GERARCHICHE: Definiscono l'identità di un nodo nel DB
        "article", "articolo", "paragraph", "comma", "clause", "section", 
        "part", "chapter", "book", "annex", "allegato", "item", "point", "list"
    }),
    container_tags=frozenset({
        # WRAPPER: Organizzano la struttura ma non bloccano né contengono testo proprio
        "akomaNtoso", "act", "body", "mainBody", "preamble", "preambolo", 
        "preface", "conclusions", "meta", "formula", "citations", "hcontainer", 
        "attachment", "attachments", "quotedStructure"
    }),
    inline_tags=frozenset({
        # CONTENUTI: Tag che portano la "carne" del testo normativo
        "p", "content", "num", "heading", "subheading", "intro", "alinea",
        "letter", "subpoint", "ins", "del", "mod", "ref", "quotedText", 
        "span", "b", "i", "u", "sub", "sup"
    }),
    metadata_tags=frozenset({
        # METADATI: Tag tecnici da saltare durante il parsing del corpo
        "meta", "identification", "publication", "classification", "lifecycle", 
        "analysis", "references", "proprietary", "eli", "rdf", "FRBRWork", 
        "FRBRExpression", "FRBRManifestation", "FRBRthis", "FRBRuri", 
        "FRBRalias", "FRBRdate", "FRBRauthor", "FRBRcountry", "FRBRlanguage"
    }),
)