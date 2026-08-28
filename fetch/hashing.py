"""Hash de conteúdo usado pra dedupe de notícia (Fase 1: news.content_hash)."""

from __future__ import annotations

import hashlib
import re


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def compute_content_hash(title: str | None, body: str | None) -> str | None:
    """Hash sha256 de título+corpo normalizados (espaços colapsados, minúsculo).

    Serve pra identificar a mesma notícia republicada em URLs diferentes. Retorna
    None quando não há conteúdo suficiente pra hashear (ex: extração de texto
    falhou e só temos o título vazio) — nesse caso o dedupe cai só na URL.
    """
    normalized = _normalize_text(f"{title or ''} {body or ''}")
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
