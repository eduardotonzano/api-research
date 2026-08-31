"""CLI: busca notícias por empresa + tópico e salva no banco da Fase 1.

Uso:
    python run_search.py "Petrobras" "resultados" --ticker PETR4
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
import webbrowser
from pathlib import Path

from db.connection import init_db
from date_utils import filter_recent_items
from db.queries import (
    add_news,
    create_search,
    get_existing_summary,
    get_latest_search_news,
    get_or_create_company,
    get_or_create_topic,
    link_search_news,
)
from fetch.extractor import extract_article
from fetch.google_news import fetch_google_news
from fetch.hashing import compute_content_hash
from fetch.portal_feeds import search_portal_feeds
from fetch.yahoo_finance import search_yahoo_finance
from report_html import render_group_html, render_report_page, write_report
from summarize import summarize_article

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "reports" / "latest_search.html"

# Delay entre extrações de artigo (não entre a busca do RSS em si), pra não
# martelar os sites de origem com requisições em sequência.
DELAY_BETWEEN_EXTRACTIONS_SECONDS = 1.0

# Notícia mais velha que isso não aparece no relatório de "atual" — evita que
# uma matéria de meses atrás, achada só por coincidência de palavra-chave,
# polua o que deveria ser um retrato do que é relevante agora.
DEFAULT_MAX_AGE_DAYS = 45


def run_search(
    conn: sqlite3.Connection,
    company: str,
    topic: str,
    ticker: str | None = None,
    *,
    yahoo_market_suffix: str = ".SA",
    delay_seconds: float = DELAY_BETWEEN_EXTRACTIONS_SECONDS,
) -> dict:
    company_id = get_or_create_company(conn, company, ticker)
    topic_id = get_or_create_topic(conn, topic)
    search_id = create_search(conn, company_id, topic_id, source="google_news+portais+yahoo")

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

    yahoo_items = []
    if ticker:
        try:
            yahoo_items = search_yahoo_finance(
                ticker, topic, market_suffix=yahoo_market_suffix
            )
        except Exception as exc:
            print(f"Aviso: falha ao buscar Yahoo Finance: {exc}", file=sys.stderr)
    else:
        print(
            "Aviso: sem ticker informado, pulando Yahoo Finance (a busca lá é por ticker).",
            file=sys.stderr,
        )

    all_items = list(rss_items) + list(portal_items) + list(yahoo_items)
    total_items = len(all_items)
    print(f"{total_items} notícia(s) encontrada(s), processando uma por uma...")

    saved = 0
    failed_extractions = 0
    summarized = 0

    for index, item in enumerate(all_items, start=1):
        print(f"[{index}/{total_items}] {item.title}")
        try:
            result = extract_article(item.link)
        except Exception:
            result = None

        final_url = item.link
        final_published_at = item.published_at
        content_hash = None
        summary = None

        if result is not None:
            final_url = result.final_url
            # A data do feed (RSS) é estruturada e vem da própria fonte — mais
            # confiável que a data "adivinhada" a partir do HTML da página pelo
            # trafilatura. Só usamos a data extraída do HTML quando o feed não
            # trouxe nenhuma.
            final_published_at = item.published_at or result.published_at
            content_hash = compute_content_hash(item.title, result.text)
            if result.text is None:
                failed_extractions += 1
            else:
                summary = get_existing_summary(conn, final_url, content_hash)
                if not summary:
                    try:
                        summary = summarize_article(item.title, result.text)
                    except Exception as exc:
                        print(f"Aviso: falha ao resumir '{item.title}': {exc}", file=sys.stderr)
                if summary:
                    summarized += 1
        else:
            failed_extractions += 1

        news_id = add_news(
            conn,
            url=final_url,
            content_hash=content_hash,
            title=item.title,
            source=item.source,
            published_at=final_published_at,
            summary=summary,
        )
        link_search_news(conn, search_id, news_id)
        saved += 1

        if delay_seconds:
            time.sleep(delay_seconds)

    return {
        "search_id": search_id,
        "company_id": company_id,
        "topic_id": topic_id,
        "found": len(all_items),
        "saved": saved,
        "failed_extractions": failed_extractions,
        "summarized": summarized,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Busca notícias por empresa + tópico.")
    parser.add_argument("company", help="Nome da empresa (ex: Petrobras)")
    parser.add_argument("topic", help="Tópico de busca (ex: resultados)")
    parser.add_argument("--ticker", default=None, help="Ticker da empresa (ex: PETR4)")
    parser.add_argument(
        "--yahoo-market-suffix",
        default=".SA",
        help="Sufixo de bolsa pro Yahoo Finance (padrão .SA, da B3; use vazio pra tickers dos EUA)",
    )
    parser.add_argument(
        "--open", action="store_true", help="Abre o relatório no navegador ao final"
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help=f"Idade máxima (em dias) pra uma notícia aparecer no relatório (padrão {DEFAULT_MAX_AGE_DAYS})",
    )
    args = parser.parse_args()

    conn = init_db()
    try:
        stats = run_search(
            conn,
            args.company,
            args.topic,
            ticker=args.ticker,
            yahoo_market_suffix=args.yahoo_market_suffix,
        )

        print(
            f"Busca concluída: {stats['found']} notícias encontradas, {stats['saved']} salvas "
            f"({stats['failed_extractions']} sem extração completa de texto, "
            f"{stats['summarized']} resumidas)."
        )

        current_items = get_latest_search_news(conn, stats["company_id"], stats["topic_id"])
        current_items = filter_recent_items(current_items, max_age_days=args.max_age_days)
        group_html = render_group_html(args.company, args.topic, current_items)
        page_html = render_report_page(
            [group_html], title=f"{args.company} + {args.topic}"
        )
        report_path = write_report(DEFAULT_REPORT_PATH, page_html)
        print(f"Relatório: {report_path}")

        if args.open:
            try:
                webbrowser.open(report_path.resolve().as_uri())
            except Exception as exc:
                print(f"Aviso: não consegui abrir o navegador automaticamente: {exc}", file=sys.stderr)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
