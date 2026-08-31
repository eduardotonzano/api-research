from pathlib import Path

import pytest
import requests

import run_search
from db.connection import init_db
from fetch.extractor import ExtractionResult, extract_article, resolve_final_url
from fetch.google_news import RssItem, _clean_title, _parse_rss, build_query, fetch_google_news
from fetch.hashing import compute_content_hash
from fetch.portal_feeds import FeedItem, matches_keywords, search_portal_feeds
from fetch.yahoo_finance import (
    YahooNewsItem,
    fetch_yahoo_finance_news,
    normalize_ticker_for_yahoo,
    search_yahoo_finance,
)

SAMPLE_GOOGLE_NEWS_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>"petrobras resultados" - Google News</title>
    <item>
      <title>Petrobras anuncia lucro recorde no trimestre - Valor Econômico</title>
      <link>https://news.google.com/rss/articles/CBMi123abc?oc=5</link>
      <pubDate>Thu, 20 Aug 2026 10:00:00 GMT</pubDate>
      <source url="https://valor.globo.com">Valor Econômico</source>
    </item>
    <item>
      <title>Ação da Petrobras sobe após resultado - InfoMoney</title>
      <link>https://news.google.com/rss/articles/CBMi456def?oc=5</link>
      <pubDate>Thu, 20 Aug 2026 12:30:00 GMT</pubDate>
      <source url="https://infomoney.com.br">InfoMoney</source>
    </item>
    <item>
      <title>Item sem link, deve ser ignorado</title>
      <pubDate>Thu, 20 Aug 2026 13:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_PORTAL_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>InfoMoney</title>
    <item>
      <title>Petrobras (PETR4) anuncia novo plano de investimentos</title>
      <link>https://www.infomoney.com.br/petrobras-plano-investimentos/</link>
      <pubDate>Wed, 19 Aug 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Selic: o que esperar da próxima reunião do Copom</title>
      <link>https://www.infomoney.com.br/selic-copom/</link>
      <pubDate>Wed, 19 Aug 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_YAHOO_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Yahoo! Finance: PETR4.SA News</title>
    <item>
      <title>Petrobras (PETR4.SA) reports record quarterly profit</title>
      <link>https://finance.yahoo.com/news/petrobras-record-profit.html</link>
      <pubDate>Thu, 20 Aug 2026 11:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Petrobras announces new dividend policy</title>
      <link>https://finance.yahoo.com/news/petrobras-dividend-policy.html</link>
      <pubDate>Fri, 21 Aug 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_ARTICLE_HTML = """
<html><head><title>Petrobras anuncia lucro recorde no trimestre</title>
<meta property="article:published_time" content="2026-08-20T10:00:00Z">
</head><body>
<article>
<h1>Petrobras anuncia lucro recorde no trimestre</h1>
<p>A Petrobras divulgou nesta quinta-feira lucro líquido de R$ 30 bilhões no
segundo trimestre, superando as expectativas do mercado.</p>
<p>Segundo analistas, o resultado reflete o aumento do preço do petróleo.</p>
</article>
</body></html>
"""


class FakeResponse:
    def __init__(self, text: str = "", status_code: int = 200, url: str = ""):
        self.text = text
        self.status_code = status_code
        self.url = url or "https://example.com/resolved"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeSession:
    def __init__(self, response: FakeResponse | Exception):
        self._response = response

    def get(self, *args, **kwargs):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


# --- Google News RSS ---


def test_parse_rss_extracts_items_and_skips_missing_link():
    items = _parse_rss(SAMPLE_GOOGLE_NEWS_RSS)
    assert len(items) == 2
    assert items[0].title == "Petrobras anuncia lucro recorde no trimestre"
    assert items[0].source == "Valor Econômico"
    assert items[0].link.startswith("https://news.google.com/")


def test_clean_title_strips_source_suffix():
    assert (
        _clean_title("Título da matéria - Fonte X", "Fonte X") == "Título da matéria"
    )
    assert _clean_title("Título sem fonte conhecida", None) == "Título sem fonte conhecida"


def test_build_query_combines_company_and_topic():
    assert build_query("Petrobras", "resultados") == "Petrobras resultados"


def test_fetch_google_news_uses_injected_session():
    session = FakeSession(FakeResponse(text=SAMPLE_GOOGLE_NEWS_RSS))
    items = fetch_google_news("Petrobras", "resultados", session=session)
    assert len(items) == 2


def test_fetch_google_news_propagates_request_errors():
    session = FakeSession(requests.ConnectionError("sem rede"))
    with pytest.raises(requests.ConnectionError):
        fetch_google_news("Petrobras", "resultados", session=session)


# --- Feeds de portais ---


def test_search_portal_feeds_filters_by_keyword():
    session = FakeSession(FakeResponse(text=SAMPLE_PORTAL_RSS))
    items = search_portal_feeds(
        "Petrobras",
        "investimentos",
        ticker="PETR4",
        feeds={"InfoMoney": "https://www.infomoney.com.br/feed/"},
        session=session,
    )
    assert len(items) == 1
    assert "Petrobras" in items[0].title


def test_search_portal_feeds_skips_feed_on_error():
    session = FakeSession(requests.ConnectionError("feed fora do ar"))
    items = search_portal_feeds(
        "Petrobras",
        "resultados",
        feeds={"InfoMoney": "https://www.infomoney.com.br/feed/"},
        session=session,
    )
    assert items == []


def test_matches_keywords_is_case_insensitive():
    item = FeedItem(title="AÇÃO da PETROBRAS sobe", link="x", published_at=None, source="X")
    assert matches_keywords(item, ["petrobras"])
    assert not matches_keywords(item, ["vale"])


# --- Yahoo Finance ---


def test_normalize_ticker_for_yahoo_adds_sa_suffix_for_b3_tickers():
    assert normalize_ticker_for_yahoo("petr4") == "PETR4.SA"


def test_normalize_ticker_for_yahoo_respects_existing_suffix():
    assert normalize_ticker_for_yahoo("AAPL.US") == "AAPL.US"


def test_fetch_yahoo_finance_news_parses_feed():
    session = FakeSession(FakeResponse(text=SAMPLE_YAHOO_RSS))
    items = fetch_yahoo_finance_news("PETR4", session=session)
    assert len(items) == 2
    assert items[0].source == "Yahoo Finance"


def test_search_yahoo_finance_filters_by_topic():
    session = FakeSession(FakeResponse(text=SAMPLE_YAHOO_RSS))
    items = search_yahoo_finance("PETR4", "dividend", session=session)
    assert len(items) == 1
    assert "dividend policy" in items[0].title.lower()


def test_search_yahoo_finance_without_topic_returns_everything():
    session = FakeSession(FakeResponse(text=SAMPLE_YAHOO_RSS))
    items = search_yahoo_finance("PETR4", "", session=session)
    assert len(items) == 2


# --- Hash de conteúdo ---


def test_compute_content_hash_is_stable_regardless_of_case_and_spacing():
    hash1 = compute_content_hash("Título", "Corpo   da   notícia")
    hash2 = compute_content_hash("título", "corpo da notícia")
    assert hash1 == hash2


def test_compute_content_hash_differs_for_different_content():
    hash1 = compute_content_hash("Título A", "Corpo A")
    hash2 = compute_content_hash("Título B", "Corpo B")
    assert hash1 != hash2


def test_compute_content_hash_none_when_empty():
    assert compute_content_hash(None, None) is None
    assert compute_content_hash("", "") is None


# --- Extração de artigo ---


def test_resolve_final_url_follows_redirect():
    session = FakeSession(FakeResponse(url="https://valor.globo.com/artigo-final"))
    final_url = resolve_final_url("https://news.google.com/rss/articles/xyz", session=session)
    assert final_url == "https://valor.globo.com/artigo-final"


def test_resolve_final_url_falls_back_to_original_on_error():
    session = FakeSession(requests.ConnectionError("timeout"))
    original = "https://news.google.com/rss/articles/xyz"
    assert resolve_final_url(original, session=session) == original


def test_extract_article_returns_text_and_date(monkeypatch):
    monkeypatch.setattr(
        "fetch.extractor.resolve_final_url", lambda url, **kw: "https://valor.globo.com/artigo"
    )
    monkeypatch.setattr("trafilatura.fetch_url", lambda url: SAMPLE_ARTICLE_HTML)

    result = extract_article("https://news.google.com/rss/articles/xyz")
    assert result.final_url == "https://valor.globo.com/artigo"
    assert "lucro líquido" in result.text
    assert result.published_at == "2026-08-20"


def test_extract_article_handles_download_failure_gracefully(monkeypatch):
    monkeypatch.setattr(
        "fetch.extractor.resolve_final_url", lambda url, **kw: "https://bloqueado.com/artigo"
    )
    monkeypatch.setattr("trafilatura.fetch_url", lambda url: None)

    result = extract_article("https://news.google.com/rss/articles/xyz")
    assert result.text is None
    assert result.published_at is None
    assert result.final_url == "https://bloqueado.com/artigo"


# --- Pipeline completo (run_search) ---


def test_run_search_pipeline_saves_and_dedupes(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pipeline.db"
    conn = init_db(db_path)

    rss_items = [
        RssItem(
            title="Petrobras anuncia lucro recorde no trimestre",
            link="https://news.google.com/rss/articles/abc",
            published_at="Thu, 20 Aug 2026 10:00:00 GMT",
            source="Valor Econômico",
        ),
    ]
    # a mesma notícia aparece de novo via feed de portal, com link diferente
    portal_items = [
        FeedItem(
            title="Petrobras anuncia lucro recorde no trimestre",
            link="https://www.infomoney.com.br/petrobras-lucro-recorde/",
            published_at="Thu, 20 Aug 2026 10:05:00 GMT",
            source="InfoMoney",
        ),
    ]

    monkeypatch.setattr(run_search, "fetch_google_news", lambda company, topic: rss_items)
    monkeypatch.setattr(
        run_search, "search_portal_feeds", lambda company, topic, ticker=None: portal_items
    )
    monkeypatch.setattr(
        run_search,
        "search_yahoo_finance",
        lambda ticker, topic, market_suffix=".SA": [],
    )
    monkeypatch.setattr(
        run_search,
        "extract_article",
        lambda url: ExtractionResult(
            final_url=url,
            text="A Petrobras divulgou lucro recorde no trimestre.",
            published_at="2026-08-20",
        ),
    )

    stats = run_search.run_search(
        conn, "Petrobras", "resultados", ticker="PETR4", delay_seconds=0
    )

    assert stats["found"] == 2
    assert isinstance(stats["company_id"], int)
    assert isinstance(stats["topic_id"], int)
    # mesmo conteúdo (mesmo texto extraído) em URLs diferentes -> dedupe por content_hash
    news_count = conn.execute("SELECT COUNT(*) AS c FROM news").fetchone()["c"]
    assert news_count == 1

    results_count = conn.execute("SELECT COUNT(*) AS c FROM search_results").fetchone()["c"]
    assert results_count == 1  # link_search_news também é idempotente pro mesmo search+news

    conn.close()


def test_run_search_includes_yahoo_finance_when_ticker_given(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pipeline_yahoo.db"
    conn = init_db(db_path)

    yahoo_items = [
        YahooNewsItem(
            title="Petrobras reports record quarterly profit",
            link="https://finance.yahoo.com/news/petrobras-record-profit.html",
            published_at="Thu, 20 Aug 2026 11:00:00 GMT",
        ),
    ]

    monkeypatch.setattr(run_search, "fetch_google_news", lambda company, topic: [])
    monkeypatch.setattr(
        run_search, "search_portal_feeds", lambda company, topic, ticker=None: []
    )
    monkeypatch.setattr(
        run_search,
        "search_yahoo_finance",
        lambda ticker, topic, market_suffix=".SA": yahoo_items,
    )
    monkeypatch.setattr(
        run_search,
        "extract_article",
        lambda url: ExtractionResult(final_url=url, text="lucro recorde", published_at=None),
    )

    stats = run_search.run_search(
        conn, "Petrobras", "resultados", ticker="PETR4", delay_seconds=0
    )

    assert stats["found"] == 1
    row = conn.execute("SELECT source FROM news").fetchone()
    assert row["source"] == "Yahoo Finance"

    conn.close()


def test_run_search_skips_yahoo_finance_without_ticker(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pipeline_no_ticker.db"
    conn = init_db(db_path)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("search_yahoo_finance não deveria ser chamado sem ticker")

    monkeypatch.setattr(run_search, "fetch_google_news", lambda company, topic: [])
    monkeypatch.setattr(
        run_search, "search_portal_feeds", lambda company, topic, ticker=None: []
    )
    monkeypatch.setattr(run_search, "search_yahoo_finance", fail_if_called)

    stats = run_search.run_search(conn, "Petrobras", "resultados", ticker=None, delay_seconds=0)

    assert stats["found"] == 0
    conn.close()


def test_run_search_saves_summary_when_available(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pipeline_summary.db"
    conn = init_db(db_path)

    rss_items = [
        RssItem(
            title="Petrobras anuncia lucro recorde no trimestre",
            link="https://news.google.com/rss/articles/abc",
            published_at="Thu, 20 Aug 2026 10:00:00 GMT",
            source="Valor Econômico",
        ),
    ]

    monkeypatch.setattr(run_search, "fetch_google_news", lambda company, topic: rss_items)
    monkeypatch.setattr(
        run_search, "search_portal_feeds", lambda company, topic, ticker=None: []
    )
    monkeypatch.setattr(
        run_search, "search_yahoo_finance", lambda ticker, topic, market_suffix=".SA": []
    )
    monkeypatch.setattr(
        run_search,
        "extract_article",
        lambda url: ExtractionResult(
            final_url=url, text="A Petrobras divulgou lucro recorde.", published_at="2026-08-20"
        ),
    )
    monkeypatch.setattr(run_search, "summarize_article", lambda title, text: "Resumo gerado pelo LLM.")

    stats = run_search.run_search(
        conn, "Petrobras", "resultados", ticker="PETR4", delay_seconds=0
    )

    assert stats["summarized"] == 1
    row = conn.execute("SELECT summary FROM news").fetchone()
    assert row["summary"] == "Resumo gerado pelo LLM."

    conn.close()


def test_run_search_reuses_existing_summary_instead_of_calling_llm_again(
    tmp_path: Path, monkeypatch
):
    db_path = tmp_path / "pipeline_summary_reuse.db"
    conn = init_db(db_path)

    call_count = {"n": 0}

    def fake_summarize(title, text):
        call_count["n"] += 1
        return f"Resumo #{call_count['n']}"

    monkeypatch.setattr(
        run_search, "search_yahoo_finance", lambda ticker, topic, market_suffix=".SA": []
    )
    monkeypatch.setattr(run_search, "summarize_article", fake_summarize)

    same_text = "A Petrobras divulgou lucro recorde no trimestre, superando expectativas."

    # primeira busca: notícia nova, chama o LLM
    monkeypatch.setattr(
        run_search,
        "fetch_google_news",
        lambda company, topic: [
            RssItem(
                title="Petrobras anuncia lucro recorde",
                link="https://news.google.com/rss/articles/primeira",
                published_at="Thu, 20 Aug 2026 10:00:00 GMT",
                source="Valor Econômico",
            )
        ],
    )
    monkeypatch.setattr(
        run_search, "search_portal_feeds", lambda company, topic, ticker=None: []
    )
    monkeypatch.setattr(
        run_search,
        "extract_article",
        lambda url: ExtractionResult(final_url=url, text=same_text, published_at="2026-08-20"),
    )

    run_search.run_search(conn, "Petrobras", "resultados", ticker="PETR4", delay_seconds=0)
    assert call_count["n"] == 1

    # segunda busca: mesmo conteúdo (mesmo content_hash), URL diferente -> não deve
    # chamar o LLM de novo, só reaproveitar o resumo já salvo
    monkeypatch.setattr(
        run_search,
        "fetch_google_news",
        lambda company, topic: [
            RssItem(
                title="Petrobras anuncia lucro recorde",
                link="https://outraportal.com/petrobras-lucro-recorde",
                published_at="Fri, 21 Aug 2026 08:00:00 GMT",
                source="InfoMoney",
            )
        ],
    )

    run_search.run_search(conn, "Petrobras", "resultados", ticker="PETR4", delay_seconds=0)

    assert call_count["n"] == 1  # não incrementou: reaproveitou o resumo existente

    summaries = {row["summary"] for row in conn.execute("SELECT summary FROM news").fetchall()}
    assert summaries == {"Resumo #1"}

    conn.close()


def test_run_search_continues_when_extraction_fails(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pipeline_fail.db"
    conn = init_db(db_path)

    rss_items = [
        RssItem(
            title="Notícia bloqueada por paywall",
            link="https://news.google.com/rss/articles/blocked",
            published_at="Thu, 20 Aug 2026 10:00:00 GMT",
            source="Valor Econômico",
        ),
    ]

    monkeypatch.setattr(run_search, "fetch_google_news", lambda company, topic: rss_items)
    monkeypatch.setattr(
        run_search, "search_portal_feeds", lambda company, topic, ticker=None: []
    )
    monkeypatch.setattr(
        run_search,
        "search_yahoo_finance",
        lambda ticker, topic, market_suffix=".SA": [],
    )

    def fake_extract(url):
        raise RuntimeError("paywall bloqueou o download")

    monkeypatch.setattr(run_search, "extract_article", fake_extract)

    stats = run_search.run_search(
        conn, "Petrobras", "resultados", ticker="PETR4", delay_seconds=0
    )

    assert stats["saved"] == 1
    assert stats["failed_extractions"] == 1

    row = conn.execute("SELECT title, content_hash FROM news").fetchone()
    assert row["title"] == "Notícia bloqueada por paywall"
    assert row["content_hash"] is None  # extração falhou, mas a notícia foi salva mesmo assim

    conn.close()


# --- Teste de rede real (não roda por padrão: `pytest -m network` pra validar manualmente) ---


@pytest.mark.network
def test_fetch_google_news_real_request_smoke():
    items = fetch_google_news("Petrobras", "resultados")
    assert isinstance(items, list)
