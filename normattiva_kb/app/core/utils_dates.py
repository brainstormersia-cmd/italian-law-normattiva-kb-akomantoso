from __future__ import annotations

import datetime as dt
import re
from typing import Optional

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
    re.compile(
        r"\b(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
        r"agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
]

MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}


def parse_date(text: str) -> Optional[dt.date]:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        day, month, year = match.groups()
        if month.isdigit():
            month_num = int(month)
        else:
            month_num = MONTHS.get(month.lower(), 0)
        if month_num == 0:
            continue
        try:
            return dt.date(int(year), month_num, int(day))
        except ValueError:
            return None
    return None
