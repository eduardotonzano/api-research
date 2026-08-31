from pathlib import Path

import pytest

import app as app_module
from db.connection import get_connection, init_db
from db.queries import (
    add_news,
    create_search,
    get_or_create_company,
    get_or_create_topic,
    link_search_news,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "app_test.db"
    init_db(db_path).close()

    # o app abre suas próprias conexões via init_db(); aponta pro banco de teste
    monkeypatch.setattr(app_module, "init_db", lambda *a, **kw: get_connection(db_path))

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client, db_path


def test_index_shows_form_and_no_pairs_when_db_is_empty(client):
    test_client, _ = client
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"Buscar" in response.data
    assert b"Pares j\xc3\xa1 buscados" not in response.data


def test_index_lists_previously_searched_pairs(client):
    test_client, db_path = client
    conn = get_connection(db_path)
    company_id = get_or_create_company(conn, "Petrobras", "PETR4")
    topic_id = get_or_create_topic(conn, "resultados")
    create_search(conn, company_id, topic_id)
    conn.close()

    response = test_client.get("/")
    assert b"Petrobras" in response.data
    assert b"resultados" in response.data


def test_ver_shows_current_snapshot_for_existing_pair(client):
    test_client, db_path = client
    conn = get_connection(db_path)
    company_id = get_or_create_company(conn, "Petrobras", "PETR4")
    topic_id = get_or_create_topic(conn, "resultados")
    search_id = create_search(conn, company_id, topic_id)
    news_id = add_news(
        conn,
        url="https://example.com/petrobras-1",
        title="Petrobras anuncia lucro recorde",
        source="Valor",
        published_at="2026-08-20",
        summary="Resumo de teste.",
    )
    link_search_news(conn, search_id, news_id)
    conn.close()

    response = test_client.get("/ver?company=Petrobras&topic=resultados")
    assert response.status_code == 200
    assert b"Petrobras anuncia lucro recorde" in response.data
    assert b"Resumo de teste." in response.data


def test_ver_shows_message_for_pair_never_searched(client):
    test_client, _ = client
    response = test_client.get("/ver?company=Empresa+Nova&topic=algo")
    assert response.status_code == 200
    assert "ainda não buscado".encode("utf-8") in response.data


def test_buscar_runs_search_and_redirects_to_current_snapshot(client, monkeypatch):
    test_client, _ = client

    def fake_run_search(conn, company, topic, ticker=None, **kwargs):
        topic_id = get_or_create_topic(conn, topic)
        company_id = get_or_create_company(conn, company, ticker)
        search_id = create_search(conn, company_id, topic_id)
        news_id = add_news(
            conn, url="https://example.com/vale-1", title="Vale negocia fusão", source="Teste"
        )
        link_search_news(conn, search_id, news_id)
        return {
            "search_id": search_id,
            "company_id": company_id,
            "topic_id": topic_id,
            "found": 1,
            "saved": 1,
            "failed_extractions": 0,
            "summarized": 0,
        }

    monkeypatch.setattr(app_module, "run_search", fake_run_search)

    response = test_client.post(
        "/buscar", data={"company": "Vale", "ticker": "VALE3", "topic": "M&A"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Vale negocia fus\xc3\xa3o" in response.data
    assert b"Busca conclu\xc3\xadda" in response.data


def test_buscar_without_company_or_topic_redirects_home(client):
    test_client, _ = client
    response = test_client.post("/buscar", data={"company": "", "topic": ""})
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
