from __future__ import annotations

from typing import Any, Optional, Protocol, TypeAlias


class NLPModel(Protocol):
    def __call__(self, text: str) -> Any:
        ...


NLPModelType: TypeAlias = Optional[NLPModel]
