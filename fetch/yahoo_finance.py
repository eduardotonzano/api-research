"""Notícias por ticker via RSS do Yahoo Finance — gratuito, sem chave.

Diferente do Google News, aqui a busca já vem escopada por ticker (o feed traz
as notícias recentes daquele papel). O filtro por tópico é o mesmo esquema de
fetch.portal_feeds: por palavra-chave no título, já que o feed em si não é
buscável por assunto.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from .google_news import REQUEST_TIMEOUT, USER_AGENT

YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"


@dataclass
class YahooNewsItem:
    title: str
    link: str
    published_at: str | None
    source: str = "Yahoo Finance"


def normalize_ticker_for_yahoo(ticker: str, *, market_suffix: str = ".SA") -> str:
    """Tickers da B3 (ex: PETR4, VALE3) precisam do sufixo .SA no Yahoo Finance.
    Se o ticker já tiver um ponto (ex: AAPL.US, PETR4.SA), respeita o que veio."""
    ticker = ticker.strip().upper()
    if "." in ticker:
        return ticker
    return f"{ticker}{market_suffix}"


def _parse_feed(xml_text: str) -> list[YahooNewsItem]:
    root = ET.fromstring(xml_text)
    items = []
    for item_el in root.findall("./channel/item"):
        title_el = item_el.find("title")
        link_el = item_el.find("link")
        pubdate_el = item_el.find("pubDate")

        link = (link_el.text or "").strip() if link_el is not None else ""
        if title_el is None or not link:
            continue

        items.append(
            YahooNewsItem(
                title=(title_el.text or "").strip(),
                link=link,
                published_at=(pubdate_el.text or "").strip() if pubdate_el is not None else None,
            )
        )
    return items


def fetch_yahoo_finance_news(
    ticker: str, *, market_suffix: str = ".SA", session: requests.Session | None = None
) -> list[YahooNewsItem]:
    """Busca o RSS de notícias do Yahoo Finance pra um ticker.

    Lança requests.RequestException em caso de falha de rede/HTTP — quem chama
    decide se trata ou deixa propagar (run_search segue com as outras fontes).
    """
    yahoo_ticker = normalize_ticker_for_yahoo(ticker, market_suffix=market_suffix)
    http = session or requests
    response = http.get(
        YAHOO_RSS_URL,
        params={"s": yahoo_ticker, "region": "US", "lang": "en-US"},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return _parse_feed(response.text)


def search_yahoo_finance(
    ticker: str,
    topic: str,
    *,
    market_suffix: str = ".SA",
    session: requests.Session | None = None,
) -> list[YahooNewsItem]:
    """Busca notícias do ticker no Yahoo Finance e filtra pelo tópico no título."""
    items = fetch_yahoo_finance_news(ticker, market_suffix=market_suffix, session=session)
    topic_lower = topic.lower().strip()
    if not topic_lower:
        return items
    return [item for item in items if topic_lower in item.title.lower()]
