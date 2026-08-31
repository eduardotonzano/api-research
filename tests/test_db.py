import sqlite3
import threading
from pathlib import Path

import pytest

from db.connection import get_connection, init_db
from db.queries import (
    add_news,
    create_search,
    get_company_history,
    get_latest_search_news,
    get_new_since_last_search,
    get_or_create_company,
    get_or_create_topic,
    link_search_news,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path):
    connection = init_db(db_path)
    yield connection
    connection.close()


# --- Inserção básica ---


def test_insert_basic_flow(conn):
    company_id = get_or_create_company(conn, "Petrobras", "PETR4")
    topic_id = get_or_create_topic(conn, "resultados")
    search_id = create_search(conn, company_id, topic_id, source="google_news")
    news_id = add_news(
        conn,
        url="https://example.com/noticia-1",
        content_hash="hash1",
        title="Petrobras anuncia resultado",
        source="Valor Econômico",
        published_at="2026-08-20T10:00:00Z",
    )
    link_search_news(conn, search_id, news_id, relevance=0.9)

    history = get_company_history(conn, company_id)
    assert len(history) == 1
    assert history[0]["url"] == "https://example.com/noticia-1"
    assert history[0]["topic_name"] == "resultados"
    assert history[0]["relevance"] == 0.9


# --- Dedupe ---


def test_dedupe_news_by_url(conn):
    id1 = add_news(conn, url="https://example.com/a", content_hash="h1")
    id2 = add_news(conn, url="https://example.com/a", content_hash="h2-different")
    assert id1 == id2
    count = conn.execute("SELECT COUNT(*) AS c FROM news").fetchone()["c"]
    assert count == 1


def test_dedupe_news_by_content_hash_different_url(conn):
    id1 = add_news(conn, url="https://site-a.com/materia", content_hash="same-hash")
    id2 = add_news(
        conn, url="https://site-b.com/mesma-materia-republicada", content_hash="same-hash"
    )
    assert id1 == id2
    count = conn.execute("SELECT COUNT(*) AS c FROM news").fetchone()["c"]
    assert count == 1


def test_get_or_create_company_idempotent_case_insensitive(conn):
    id1 = get_or_create_company(conn, "Petrobras", "PETR4")
    id2 = get_or_create_company(conn, "petrobras")
    assert id1 == id2
    count = conn.execute("SELECT COUNT(*) AS c FROM companies").fetchone()["c"]
    assert count == 1


def test_get_or_create_topic_idempotent_case_insensitive(conn):
    id1 = get_or_create_topic(conn, "Resultados")
    id2 = get_or_create_topic(conn, "resultados")
    assert id1 == id2


def test_link_search_news_is_idempotent(conn):
    company_id = get_or_create_company(conn, "Localiza", "RENT3")
    topic_id = get_or_create_topic(conn, "frota")
    search_id = create_search(conn, company_id, topic_id)
    news_id = add_news(conn, url="https://example.com/localiza-frota")

    link_search_news(conn, search_id, news_id, relevance=0.5)
    link_search_news(conn, search_id, news_id, relevance=0.5)

    count = conn.execute("SELECT COUNT(*) AS c FROM search_results").fetchone()["c"]
    assert count == 1


# --- Queries de histórico e "novo desde a última busca" ---


def test_company_history_across_multiple_topics_and_searches(conn):
    company_id = get_or_create_company(conn, "Vale", "VALE3")
    topic_resultados = get_or_create_topic(conn, "resultados")
    topic_ma = get_or_create_topic(conn, "M&A")

    search1 = create_search(conn, company_id, topic_resultados)
    search2 = create_search(conn, company_id, topic_ma)

    news1 = add_news(conn, url="https://example.com/vale-resultado", title="Vale bate recorde")
    news2 = add_news(conn, url="https://example.com/vale-fusao", title="Vale negocia fusão")

    link_search_news(conn, search1, news1)
    link_search_news(conn, search2, news2)

    history = get_company_history(conn, company_id)
    assert len(history) == 2
    topics_found = {row["topic_name"] for row in history}
    assert topics_found == {"resultados", "M&A"}


def test_new_since_last_search_first_time_returns_everything(conn):
    company_id = get_or_create_company(conn, "Itaú", "ITUB4")
    topic_id = get_or_create_topic(conn, "dividendos")
    search_id = create_search(conn, company_id, topic_id)
    news_id = add_news(conn, url="https://example.com/itau-dividendo")
    link_search_news(conn, search_id, news_id)

    new_items = get_new_since_last_search(conn, company_id, topic_id)
    assert len(new_items) == 1
    assert new_items[0]["url"] == "https://example.com/itau-dividendo"


def test_new_since_last_search_only_returns_unseen_news(conn):
    company_id = get_or_create_company(conn, "Ambev", "ABEV3")
    topic_id = get_or_create_topic(conn, "resultados")

    search1 = create_search(conn, company_id, topic_id, searched_at="2026-08-01T09:00:00Z")
    old_news = add_news(conn, url="https://example.com/ambev-antiga")
    link_search_news(conn, search1, old_news)

    search2 = create_search(conn, company_id, topic_id, searched_at="2026-08-20T09:00:00Z")
    new_news = add_news(conn, url="https://example.com/ambev-nova")
    link_search_news(conn, search2, old_news)  # notícia antiga reapareceu na busca nova
    link_search_news(conn, search2, new_news)

    new_items = get_new_since_last_search(conn, company_id, topic_id)
    urls = {row["url"] for row in new_items}
    assert urls == {"https://example.com/ambev-nova"}


def test_new_since_last_search_no_searches_returns_empty(conn):
    company_id = get_or_create_company(conn, "Weg", "WEGE3")
    topic_id = get_or_create_topic(conn, "governanca")
    assert get_new_since_last_search(conn, company_id, topic_id) == []


def test_get_latest_search_news_returns_everything_from_most_recent_search(conn):
    company_id = get_or_create_company(conn, "Ambev", "ABEV3")
    topic_id = get_or_create_topic(conn, "resultados")

    search1 = create_search(conn, company_id, topic_id, searched_at="2026-08-01T09:00:00Z")
    old_news = add_news(conn, url="https://example.com/ambev-antiga", title="Notícia antiga")
    link_search_news(conn, search1, old_news)

    search2 = create_search(conn, company_id, topic_id, searched_at="2026-08-20T09:00:00Z")
    new_news = add_news(conn, url="https://example.com/ambev-nova", title="Notícia nova")
    link_search_news(conn, search2, old_news)  # a mesma notícia antiga reapareceu
    link_search_news(conn, search2, new_news)

    # diferente de get_new_since_last_search: aqui queremos TUDO da busca mais
    # recente, mesmo notícias que já tinham aparecido antes.
    items = get_latest_search_news(conn, company_id, topic_id)
    titles = {item["title"] for item in items}
    assert titles == {"Notícia antiga", "Notícia nova"}


def test_get_latest_search_news_no_searches_returns_empty(conn):
    company_id = get_or_create_company(conn, "Weg", "WEGE3")
    topic_id = get_or_create_topic(conn, "governanca")
    assert get_latest_search_news(conn, company_id, topic_id) == []


# --- Dados malformados / propositalmente inválidos ---


def test_missing_url_raises(conn):
    with pytest.raises(ValueError):
        add_news(conn, url="")


def test_missing_company_name_raises(conn):
    with pytest.raises(ValueError):
        get_or_create_company(conn, "")


def test_search_with_nonexistent_company_raises_foreign_key_error(conn):
    topic_id = get_or_create_topic(conn, "resultados")
    with pytest.raises(sqlite3.IntegrityError):
        create_search(conn, company_id=99999, topic_id=topic_id)


def test_search_with_nonexistent_topic_raises_foreign_key_error(conn):
    company_id = get_or_create_company(conn, "Raia Drogasil", "RADL3")
    with pytest.raises(sqlite3.IntegrityError):
        create_search(conn, company_id=company_id, topic_id=99999)


def test_duplicate_topic_name_different_case_via_raw_insert_conflicts(conn):
    conn.execute("INSERT INTO topics (name) VALUES (?)", ("Resultados",))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO topics (name) VALUES (?)", ("resultados",))


def test_link_search_news_with_nonexistent_ids_raises(conn):
    with pytest.raises(sqlite3.IntegrityError):
        link_search_news(conn, search_id=99999, news_id=99999)


# --- Migrations ---


def test_migrations_are_recorded_and_not_reapplied(db_path):
    conn1 = init_db(db_path)
    applied_versions = conn1.execute("SELECT version FROM schema_migrations").fetchall()
    assert len(applied_versions) == 1
    conn1.close()

    conn2 = init_db(db_path)
    applied_versions_again = conn2.execute("SELECT version FROM schema_migrations").fetchall()
    assert len(applied_versions_again) == 1
    conn2.close()


# --- Concorrência ---


def test_concurrent_writes_do_not_corrupt_database(db_path):
    init_db(db_path).close()  # aplica schema uma vez, fora das threads

    errors = []
    n_threads = 8
    inserts_per_thread = 20

    def worker(thread_index: int) -> None:
        try:
            local_conn = get_connection(db_path)
            for i in range(inserts_per_thread):
                get_or_create_company(local_conn, f"Empresa Concorrente {thread_index}-{i}")
            local_conn.close()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []

    check_conn = get_connection(db_path)
    count = check_conn.execute("SELECT COUNT(*) AS c FROM companies").fetchone()["c"]
    integrity = check_conn.execute("PRAGMA integrity_check").fetchone()[0]
    check_conn.close()

    assert count == n_threads * inserts_per_thread
    assert integrity == "ok"


def test_concurrent_writes_same_company_do_not_duplicate(db_path):
    init_db(db_path).close()

    errors = []

    def worker() -> None:
        try:
            local_conn = get_connection(db_path)
            get_or_create_company(local_conn, "Empresa Disputada", "DISP3")
            local_conn.close()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []

    check_conn = get_connection(db_path)
    count = check_conn.execute(
        "SELECT COUNT(*) AS c FROM companies WHERE name = 'Empresa Disputada'"
    ).fetchone()["c"]
    check_conn.close()
    assert count == 1
