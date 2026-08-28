"""CLI: busca notícias por empresa + tópico e salva no banco da Fase 1.

Uso:
    python run_search.py "Petrobras" "resultados" --ticker PETR4
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time

from db.connection import init_db
from db.queries import (
    add_news,
    create_search,
    get_or_create_company,
    get_or_create_topic,
    link_search_news,
)
from fetch.extractor import extract_article
from fetch.google_news import fetch_google_news
from fetch.hashing import compute_content_hash
from fetch.portal_feeds import search_portal_feeds

# Delay entre extrações de artigo (não entre a busca do RSS em si), pra não
# martelar os sites de origem com requisições em sequência.
DELAY_BETWEEN_EXTRACTIONS_SECONDS = 1.0


def run_search(
    conn: sqlite3.Connection,
    company: str,
    topic: str,
    ticker: str | None = None,
    *,
    delay_seconds: float = DELAY_BETWEEN_EXTRACTIONS_SECONDS,
) -> dict:
    company_id = get_or_create_company(conn, company, ticker)
    topic_id = get_or_create_topic(conn, topic)
    search_id = create_search(conn, company_id, topic_id, source="google_news+portais")

    try:
        rss_items = fetch_google_news(company, topic)
    except Exception as exc:
        print(f"Aviso: falha ao buscar Google News RSS: {exc}", file=sys.stderr)
        rss_items = []

    try:
        portal_items = search_portal_feeds(company, topic, ticker=ticker)
    except Exception as exc:
        print(f"Aviso: falha ao buscar feeds de portais: {exc}", file=sys.stderr)
        portal_items = []

    all_items = list(rss_items) + list(portal_items)

    saved = 0
    failed_extractions = 0

    for item in all_items:
        try:
            result = extract_article(item.link)
        except Exception:
            result = None

        final_url = item.link
        final_published_at = item.published_at
        content_hash = None

        if result is not None:
            final_url = result.final_url
            final_published_at = result.published_at or item.published_at
            content_hash = compute_content_hash(item.title, result.text)
            if result.text is None:
                failed_extractions += 1
        else:
            failed_extractions += 1

        news_id = add_news(
            conn,
            url=final_url,
            content_hash=content_hash,
            title=item.title,
            source=item.source,
            published_at=final_published_at,
        )
        link_search_news(conn, search_id, news_id)
        saved += 1

        if delay_seconds:
            time.sleep(delay_seconds)

    return {
        "search_id": search_id,
        "found": len(all_items),
        "saved": saved,
        "failed_extractions": failed_extractions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Busca notícias por empresa + tópico.")
    parser.add_argument("company", help="Nome da empresa (ex: Petrobras)")
    parser.add_argument("topic", help="Tópico de busca (ex: resultados)")
    parser.add_argument("--ticker", default=None, help="Ticker da empresa (ex: PETR4)")
    args = parser.parse_args()

    conn = init_db()
    try:
        stats = run_search(conn, args.company, args.topic, ticker=args.ticker)
    finally:
        conn.close()

    print(
        f"Busca concluída: {stats['found']} notícias encontradas, {stats['saved']} salvas "
        f"({stats['failed_extractions']} sem extração completa de texto)."
    )


if __name__ == "__main__":
    main()
