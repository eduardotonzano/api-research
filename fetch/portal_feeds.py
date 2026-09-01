"""Feeds RSS de portais financeiros brasileiros.

Diferente do Google News, esses feeds não são buscáveis por palavra-chave — eles
só trazem o que o portal publicou recentemente. Por isso filtramos os itens do
feed por menção à empresa (nome ou ticker) e ao tópico no título.

As URLs em PORTAL_FEEDS são de conhecimento público, mas portais mudam a
estrutura/endereço do RSS sem aviso — confirme que ainda respondem antes de
depender delas.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from .google_news import REQUEST_TIMEOUT, USER_AGENT

PORTAL_FEEDS = {
    "InfoMoney": "https://www.infomoney.com.br/feed/",
    "Money Times": "https://www.moneytimes.com.br/feed/",
    "Suno Notícias": "https://www.suno.com.br/noticias/feed/",
    # Investing.com não tem busca por empresa gratuita (a página de busca é
    # protegida por anti-bot) — usamos os feeds de categoria que eles mesmos
    # publicam pra sindicação, filtrados por palavra-chave como os demais.
    "Investing.com": "https://www.investing.com/rss/news.rss",
    "Investing.com - Ações": "https://www.investing.com/rss/stock_Stock-Market-News.rss",
}


@dataclass
class FeedItem:
    title: str
    link: str
    published_at: str | None
    source: str


def _parse_feed(xml_text: str, source_name: str) -> list[FeedItem]:
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
            FeedItem(
                title=(title_el.text or "").strip(),
                link=link,
                published_at=(pubdate_el.text or "").strip() if pubdate_el is not None else None,
                source=source_name,
            )
        )
    return items


def fetch_portal_feed(
    source_name: str, feed_url: str, *, session: requests.Session | None = None
) -> list[FeedItem]:
    http = session or requests
    response = http.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return _parse_feed(response.text, source_name)


def matches_keywords(
    item: FeedItem,
    *,
    company: str | None,
    ticker: str | None = None,
    topic: str | None = None,
) -> bool:
    """Um item só é relevante se citar a empresa (nome OU ticker) no título —
    isso é obrigatório, nunca opcional. Quando um tópico foi informado, o
    título também precisa citar o tópico. Antes disso era 'basta bater
    qualquer uma das três palavras', o que deixava passar notícia que só
    menciona o tópico (ex: 'resultados') sem falar da empresa nenhuma — puro
    ruído."""
    haystack = item.title.lower()

    identity_terms = [term for term in (company, ticker) if term]
    if not identity_terms or not any(term.lower() in haystack for term in identity_terms):
        return False

    topic_clean = (topic or "").strip()
    if not topic_clean:
        return True
    return topic_clean.lower() in haystack


def search_portal_feeds(
    company: str,
    topic: str,
    *,
    ticker: str | None = None,
    feeds: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> list[FeedItem]:
    """Varre os feeds fixos de portais, filtrando por empresa/ticker no
    título (obrigatório) e por tópico (se informado). Falha em um feed não
    derruba a busca nos demais."""
    feeds = feeds if feeds is not None else PORTAL_FEEDS
    matched: list[FeedItem] = []
    for source_name, feed_url in feeds.items():
        try:
            items = fetch_portal_feed(source_name, feed_url, session=session)
        except requests.RequestException:
            continue
        matched.extend(
            item
            for item in items
            if matches_keywords(item, company=company, ticker=ticker, topic=topic)
        )
    return matched
