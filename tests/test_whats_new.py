from pathlib import Path

import pytest

from db.connection import init_db
from db.queries import (
    add_news,
    create_search,
    get_or_create_company,
    get_or_create_topic,
    link_search_news,
)
from whats_new import get_new_for_all_pairs, get_new_for_pair


@pytest.fixture
def conn(tmp_path: Path):
    connection = init_db(tmp_path / "whats_new.db")
    yield connection
    connection.close()


def test_get_new_for_pair_when_company_never_searched(conn):
    found, text = get_new_for_pair(conn, "Empresa Inexistente", "resultados")
    assert found is False
    assert "nunca foi buscada" in text


def test_get_new_for_pair_when_topic_never_searched(conn):
    get_or_create_company(conn, "Petrobras", "PETR4")
    found, text = get_new_for_pair(conn, "Petrobras", "tópico-inexistente")
    assert found is False
    assert "nunca foi buscado" in text


def test_get_new_for_pair_first_search_returns_everything(conn):
    company_id = get_or_create_company(conn, "Petrobras", "PETR4")
    topic_id = get_or_create_topic(conn, "resultados")
    search_id = create_search(conn, company_id, topic_id)
    news_id = add_news(conn, url="https://example.com/petrobras-1", title="Notícia 1")
    link_search_news(conn, search_id, news_id)

    found, text = get_new_for_pair(conn, "Petrobras", "resultados")
    assert found is True
    assert "Notícia 1" in text
    assert "Nada novo" not in text


def test_get_new_for_pair_second_search_shows_only_unseen(conn):
    company_id = get_or_create_company(conn, "Petrobras", "PETR4")
    topic_id = get_or_create_topic(conn, "resultados")

    search1 = create_search(conn, company_id, topic_id, searched_at="2026-08-01T09:00:00Z")
    old_news = add_news(conn, url="https://example.com/antiga", title="Notícia antiga")
    link_search_news(conn, search1, old_news)

    search2 = create_search(conn, company_id, topic_id, searched_at="2026-08-20T09:00:00Z")
    new_news = add_news(conn, url="https://example.com/nova", title="Notícia nova")
    link_search_news(conn, search2, old_news)
    link_search_news(conn, search2, new_news)

    found, text = get_new_for_pair(conn, "Petrobras", "resultados")
    assert found is True
    assert "Notícia nova" in text
    assert "Notícia antiga" not in text


def test_get_new_for_pair_with_nothing_new_since_last_search(conn):
    company_id = get_or_create_company(conn, "Vale", "VALE3")
    topic_id = get_or_create_topic(conn, "M&A")

    search1 = create_search(conn, company_id, topic_id, searched_at="2026-08-01T09:00:00Z")
    news_id = add_news(conn, url="https://example.com/vale-1", title="Notícia única")
    link_search_news(conn, search1, news_id)

    search2 = create_search(conn, company_id, topic_id, searched_at="2026-08-20T09:00:00Z")
    link_search_news(conn, search2, news_id)  # mesma notícia reapareceu, nada novo

    found, text = get_new_for_pair(conn, "Vale", "M&A")
    assert found is True
    assert "Nada novo desde a última busca." in text


def test_get_new_for_all_pairs_with_no_searches_yet(conn):
    text = get_new_for_all_pairs(conn)
    assert text == "Nenhuma busca feita ainda."


def test_get_new_for_all_pairs_covers_every_company_topic_pair(conn):
    petrobras_id = get_or_create_company(conn, "Petrobras", "PETR4")
    vale_id = get_or_create_company(conn, "Vale", "VALE3")
    resultados_id = get_or_create_topic(conn, "resultados")
    ma_id = get_or_create_topic(conn, "M&A")

    search1 = create_search(conn, petrobras_id, resultados_id)
    news1 = add_news(conn, url="https://example.com/petrobras-resultado", title="Petrobras lucro")
    link_search_news(conn, search1, news1)

    search2 = create_search(conn, vale_id, ma_id)
    news2 = add_news(conn, url="https://example.com/vale-fusao", title="Vale fusão")
    link_search_news(conn, search2, news2)

    text = get_new_for_all_pairs(conn)
    assert "=== Petrobras + resultados ===" in text
    assert "Petrobras lucro" in text
    assert "=== Vale + M&A ===" in text
    assert "Vale fusão" in text
