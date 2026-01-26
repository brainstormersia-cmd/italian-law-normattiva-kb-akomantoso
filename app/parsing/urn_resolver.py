from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from app.parsing.references import ALIASES, ART_PATTERN

# Regex per catturare riferimenti dinamici tipo "L. 231/2001" o "Legge n. 40 del 1998"
# Cattura gruppi: 1=Tipo, 2=Numero, 3=Anno (con supporto a 2 o 4 cifre)
DYNAMIC_LAW_PATTERN = re.compile(
    r"(?i)(legge|l\.|d\.lgs\.?|decreto legislativo|d\.l\.|decreto legge|d\.p\.r\.)"
    r"(?:\s+(?:regionale|provinciale))?"  # Opzionale: regionale/provinciale
    r"[^0-9]*?"                           # Testo in mezzo (es. "n.", "del", data)
    r"\b(\d{1,4})\b"                      # Il Numero
    r"(?:[^0-9]{1,15})?"                  # Separatore (es. "/", " del ")
    r"\b(\d{2,4})\b"                      # L'Anno
)

def _build_urn(base_urn: str, article: str | None, comma: str | None, letter: str | None, number: str | None) -> str:
    """Costruisce URN canonici. Esempio output: urn:nir:stato:legge:2001;231#art5"""
    parts = []
    if article: parts.append(f"art{article}") # Normattiva usa spesso #art5 senza ':'
    if comma: parts.append(f"com{comma}")
    if letter: parts.append(f"let{letter}")
    if number: parts.append(f"num{number}")
    
    fragment = "-".join(parts)
    if not fragment:
        return base_urn
    return f"{base_urn}#{fragment}"

def _match_alias(text: str) -> Optional[str]:
    lowered = text.lower()
    # 1. Controllo Aliases statici (es. "codice civile")
    for alias, canonical in ALIASES.items():
        if alias.lower() in lowered:
            return canonical
    return None

def _match_dynamic_law(text: str) -> Optional[str]:
    """Tenta di estrarre una URN da citazioni tipo 'Legge 231/2001'"""
    m = DYNAMIC_LAW_PATTERN.search(text)
    if not m:
        return None
    
    tipo_raw, numero, anno = m.groups()
    
    # Normalizzazione Anno (98 -> 1998, 01 -> 2001)
    if len(anno) == 2:
        anno = "20" + anno if int(anno) < 50 else "19" + anno

    # Normalizzazione Tipo Atto
    t = tipo_raw.lower()
    if "legge" in t or "l." in t:
        urn_type = "legge"
    elif "d.lgs" in t or "legislativo" in t:
        urn_type = "decreto.legislativo"
    elif "d.l" in t or "decreto legge" in t:
        urn_type = "decreto.legge"
    elif "d.p.r" in t:
        urn_type = "decreto.presidente.repubblica"
    else:
        urn_type = "legge" # Fallback
        
    # Costruzione URN NIR standard
    return f"urn:nir:stato:{urn_type}:{anno};{numero}"

class UrnResolver:
    def __init__(self, document_urn: Optional[str]) -> None:
        self.document_urn = document_urn

    # Rimosso context_text dalla cache key per evitare cache miss continui
    @lru_cache(maxsize=4096)
    def _resolve_cached(self, match_text: str, context_hash: int) -> tuple[Optional[str], float, str]:
        # Nota: context_hash è solo per la firma, il testo vero deve essere passato in altro modo
        # Per semplicità qui manteniamo la logica interna senza cache sul contesto stringa, 
        # o cachiamo solo le risoluzioni "pure" (senza contesto).
        pass

    def resolve(self, match_text: str, raw_snippet: str = "") -> tuple[Optional[str], float, str]:
        """
        Risolve un riferimento testuale in URN.
        Priorità: Explicit URN > Dynamic Law > Alias > Internal Context > Manual
        """
        # Uniamo per cercare il contesto (es. "del codice civile")
        combined = f"{match_text} {raw_snippet}".strip()
        
        # 1. URN Esplicita (massima fiducia)
        if "urn:" in match_text:
             # Estrazione grezza se il testo è sporco
            return match_text.split()[0], 1.0, "explicit"

        # Parsing dell'articolo (Art. X)
        # Usiamo search su match_text per i dati precisi dell'articolo
        art_match = ART_PATTERN.search(match_text)
        
        article, comma, letter, number = (None, None, None, None)
        if art_match:
            article, comma, letter, number = art_match.groups()

        # 2. Ricerca Dinamica (Legge n. X/YYYY)
        # Cerchiamo nel contesto combinato (es. "Art. 5 della Legge 231/2001")
        ext_law_urn = _match_dynamic_law(combined)
        if ext_law_urn:
            return _build_urn(ext_law_urn, article, comma, letter, number), 0.85, "dynamic_parsing"

        # 3. Ricerca Alias (es. "Codice Civile")
        alias_urn = _match_alias(combined)
        if alias_urn:
            return _build_urn(alias_urn, article, comma, letter, number), 0.8, "alias"

        # 4. Fallback Interno (Il riferimento è al documento stesso)
        # Solo se abbiamo trovato almeno un "Art. X" e abbiamo un documento padre
        if art_match and self.document_urn:
            return _build_urn(self.document_urn, article, comma, letter, number), 0.6, "contextual"

        # 5. Fallback Manuale (Non siamo riusciti a collegarlo)
        return None, 0.0, "unresolved"