"""Parsing e checagem de recência de datas de publicação.

news.published_at guarda formatos diferentes dependendo da fonte: RFC 822
("Thu, 20 Aug 2026 10:00:00 GMT", como vem no RSS) ou ISO ("2026-08-20" ou
"2026-08-20T10:00:00Z", como vem do trafilatura). As duas rotas de parsing
abaixo cobrem os dois casos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def parse_published_at(value: str | None) -> datetime | None:
    """Converte published_at pra datetime com timezone. None se não der pra
    entender o formato — tratado como 'data desconhecida', não como erro."""
    if not value or not value.strip():
        return None
    value = value.strip()

    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_recent(value: str | None, *, max_age_days: int) -> bool:
    """True se a notícia é recente o suficiente, OU se a data é desconhecida/
    ilegível — preferimos mostrar uma notícia de data incerta a esconder algo
    relevante por causa de um formato estranho vindo da fonte."""
    dt = parse_published_at(value)
    if dt is None:
        return True
    age_days = (datetime.now(timezone.utc) - dt).days
    return age_days <= max_age_days


def filter_recent_items(items: list[dict], *, max_age_days: int) -> list[dict]:
    """Filtra uma lista de notícias (dicts com 'published_at'), descartando só
    as que têm data conhecida e claramente antiga — evita que uma matéria de
    meses atrás, encontrada por coincidência de palavra-chave, polua o
    relatório do que é relevante agora."""
    return [item for item in items if is_recent(item.get("published_at"), max_age_days=max_age_days)]
