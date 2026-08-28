"""Operações de escrita/leitura sobre o schema.

Convenção de dedupe: as funções de escrita tentam o INSERT primeiro e, se colidir
com uma UNIQUE constraint, buscam e devolvem o registro já existente em vez de
lançar erro. Isso deixa o "get or create" atômico mesmo sob concorrência (duas
conexões podem tentar inserir a mesma empresa ao mesmo tempo: uma vence o INSERT,
a outra cai no except e lê o que a primeira gravou).
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def get_or_create_company(
    conn: sqlite3.Connection, name: str, ticker: str | None = None
) -> int:
    if not name or not name.strip():
        raise ValueError("name é obrigatório")
    try:
        cur = conn.execute(
            "INSERT INTO companies (name, ticker) VALUES (?, ?)", (name, ticker)
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT id FROM companies WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is None:
            raise
        return row["id"]


def get_or_create_topic(conn: sqlite3.Connection, name: str) -> int:
    if not name or not name.strip():
        raise ValueError("name é obrigatório")
    try:
        cur = conn.execute("INSERT INTO topics (name) VALUES (?)", (name,))
        return cur.lastrowid
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT id FROM topics WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is None:
            raise
        return row["id"]


def create_search(
    conn: sqlite3.Connection,
    company_id: int,
    topic_id: int,
    source: str | None = None,
    searched_at: str | None = None,
) -> int:
    if searched_at is not None:
        cur = conn.execute(
            "INSERT INTO searches (company_id, topic_id, source, searched_at) "
            "VALUES (?, ?, ?, ?)",
            (company_id, topic_id, source, searched_at),
        )
    else:
        cur = conn.execute(
            "INSERT INTO searches (company_id, topic_id, source) VALUES (?, ?, ?)",
            (company_id, topic_id, source),
        )
    return cur.lastrowid


def add_news(
    conn: sqlite3.Connection,
    url: str,
    content_hash: str | None = None,
    title: str | None = None,
    source: str | None = None,
    published_at: str | None = None,
    summary: str | None = None,
) -> int:
    if not url or not url.strip():
        raise ValueError("url é obrigatória")
    try:
        cur = conn.execute(
            "INSERT INTO news (url, content_hash, title, source, published_at, summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, content_hash, title, source, published_at, summary),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        row = conn.execute("SELECT id FROM news WHERE url = ?", (url,)).fetchone()
        if row is None and content_hash is not None:
            row = conn.execute(
                "SELECT id FROM news WHERE content_hash = ?", (content_hash,)
            ).fetchone()
        if row is None:
            raise
        return row["id"]


def link_search_news(
    conn: sqlite3.Connection,
    search_id: int,
    news_id: int,
    relevance: float | None = None,
) -> int | None:
    cur = conn.execute(
        "INSERT OR IGNORE INTO search_results (search_id, news_id, relevance) "
        "VALUES (?, ?, ?)",
        (search_id, news_id, relevance),
    )
    if cur.rowcount == 1:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM search_results WHERE search_id = ? AND news_id = ?",
        (search_id, news_id),
    ).fetchone()
    return row["id"] if row else None


def get_company_history(conn: sqlite3.Connection, company_id: int) -> list[dict[str, Any]]:
    """Todo o histórico de notícias de uma empresa, cruzando todos os tópicos e buscas já feitos."""
    rows = conn.execute(
        """
        SELECT
            n.id AS news_id,
            n.url,
            n.title,
            n.source,
            n.published_at,
            n.summary,
            n.fetched_at,
            t.id AS topic_id,
            t.name AS topic_name,
            s.id AS search_id,
            s.searched_at,
            sr.relevance
        FROM searches s
        JOIN topics t ON t.id = s.topic_id
        JOIN search_results sr ON sr.search_id = s.id
        JOIN news n ON n.id = sr.news_id
        WHERE s.company_id = ?
        ORDER BY COALESCE(n.published_at, n.fetched_at) DESC, s.searched_at DESC
        """,
        (company_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_new_since_last_search(
    conn: sqlite3.Connection, company_id: int, topic_id: int
) -> list[dict[str, Any]]:
    """Notícias trazidas pela busca mais recente de empresa+tópico que não apareceram
    em nenhuma busca anterior para esse mesmo par. Se só existir uma busca, retorna
    tudo o que ela trouxe (é a primeira vez)."""
    rows = conn.execute(
        """
        WITH pair_searches AS (
            SELECT id, searched_at
            FROM searches
            WHERE company_id = ? AND topic_id = ?
        ),
        latest AS (
            SELECT id FROM pair_searches ORDER BY searched_at DESC, id DESC LIMIT 1
        ),
        previous_news_ids AS (
            SELECT DISTINCT sr.news_id
            FROM search_results sr
            WHERE sr.search_id IN (
                SELECT id FROM pair_searches WHERE id != (SELECT id FROM latest)
            )
        )
        SELECT n.*
        FROM news n
        JOIN search_results sr ON sr.news_id = n.id
        WHERE sr.search_id = (SELECT id FROM latest)
          AND n.id NOT IN (SELECT news_id FROM previous_news_ids)
        ORDER BY COALESCE(n.published_at, n.fetched_at) DESC
        """,
        (company_id, topic_id),
    ).fetchall()
    return [dict(row) for row in rows]
