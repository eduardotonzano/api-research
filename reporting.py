"""Formatação de 'notícias novas desde a última busca' (Fase 4).

Texto puro no terminal por enquanto — a Fase 5 decide o formato definitivo
(terminal mais elaborado ou HTML). Fica separado da lógica de busca no
banco (whats_new.py) pra ser testável sem precisar de conexão SQLite.
"""

from __future__ import annotations

from typing import Any


def format_new_items(company_name: str, topic_name: str, items: list[dict[str, Any]]) -> str:
    lines = [f"=== {company_name} + {topic_name} ==="]

    if not items:
        lines.append("Nada novo desde a última busca.")
        return "\n".join(lines)

    for item in items:
        lines.append(f"- {item['title']}")
        if item.get("source"):
            lines.append(f"    fonte: {item['source']}")
        if item.get("published_at"):
            lines.append(f"    publicado em: {item['published_at']}")
        if item.get("url"):
            lines.append(f"    {item['url']}")
        if item.get("summary"):
            lines.append(f"    resumo: {item['summary']}")

    return "\n".join(lines)
