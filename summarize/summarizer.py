"""Orquestra o resumo: tenta Groq primeiro, cai pro Gemini se falhar/sem chave.

Se nenhum dos dois estiver disponível, devolve None — a notícia é salva sem
resumo, mesmo padrão de degradação graciosa da Fase 2 (quando a extração de
texto falha, a notícia também não deixa de ser salva).
"""

from __future__ import annotations

from . import gemini_provider, groq_provider


def summarize_article(title: str, text: str | None) -> str | None:
    if not text or not text.strip():
        return None

    summary = groq_provider.summarize(title, text)
    if summary:
        return summary

    return gemini_provider.summarize(title, text)
