"""Pontuação simples e transparente de relevância de uma notícia.

Usada só pra ORDENAR o relatório (nunca pra descartar — quem decide o que
sai do relatório é date_utils.is_recent/DEFAULT_MAX_AGE_DAYS). Regra
explicável, não uma caixa-preta: citar a empresa/ticker no título é o sinal
mais forte de que a notícia é sobre ela de verdade; citar o tópico buscado é
um reforço; ter uma data conhecida é um desempate leve.
"""

from __future__ import annotations

IDENTITY_MATCH_SCORE = 0.6
TOPIC_MATCH_SCORE = 0.3
KNOWN_DATE_SCORE = 0.1


def compute_relevance(
    title: str,
    company: str,
    topic: str,
    *,
    ticker: str | None = None,
    published_at: str | None = None,
) -> float:
    haystack = (title or "").lower()
    score = 0.0

    identity_terms = [term for term in (company, ticker) if term]
    if identity_terms and any(term.lower() in haystack for term in identity_terms):
        score += IDENTITY_MATCH_SCORE

    topic_clean = (topic or "").strip()
    if topic_clean and topic_clean.lower() in haystack:
        score += TOPIC_MATCH_SCORE

    if published_at:
        score += KNOWN_DATE_SCORE

    return round(score, 2)
