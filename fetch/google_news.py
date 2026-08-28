"""Busca de notícias via Google News RSS — gratuito, sem chave de API.

Formato de URL: https://news.google.com/rss/search?q=...&hl=pt-BR&gl=BR&ceid=BR:pt-BR
O <link> de cada item costuma ser um redirect do Google (news.google.com/rss/articles/...),
por isso a resolução da URL final fica a cargo de fetch.extractor.resolve_final_url.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

RSS_BASE_URL = "https://news.google.com/rss/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15


@dataclass
class RssItem:
    title: str
    link: str
    published_at: str | None
    source: str | None


def build_query(company: str, topic: str) -> str:
    return f"{company} {topic}".strip()


def _clean_title(raw_title: str, source: str | None) -> str:
    """O <title> do Google News costuma vir como 'Título da matéria - Nome da Fonte'."""
    if source and raw_title.endswith(f" - {source}"):
        return raw_title[: -(len(source) + 3)].strip()
    return raw_title.strip()


def _parse_rss(xml_text: str) -> list[RssItem]:
    root = ET.fromstring(xml_text)
    items = []
    for item_el in root.findall("./channel/item"):
        title_el = item_el.find("title")
        link_el = item_el.find("link")
        pubdate_el = item_el.find("pubDate")
        source_el = item_el.find("source")

        link = (link_el.text or "").strip() if link_el is not None else ""
        if title_el is None or not link:
            continue  # item sem link não serve pra nada (não dá pra extrair/dedupe)

        source_name = (source_el.text or "").strip() if source_el is not None else None
        title = _clean_title((title_el.text or "").strip(), source_name)

        items.append(
            RssItem(
                title=title or link,
                link=link,
                published_at=(pubdate_el.text or "").strip() if pubdate_el is not None else None,
                source=source_name,
            )
        )
    return items


def fetch_google_news(
    company: str, topic: str, *, session: requests.Session | None = None
) -> list[RssItem]:
    """Busca notícias no Google News RSS pra empresa+tópico.

    Lança requests.RequestException em caso de falha de rede/HTTP — quem chama
    decide se trata (ex: run_search segue com os outros feeds) ou deixa propagar.
    """
    query = build_query(company, topic)
    params = {"q": query, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-BR"}
    http = session or requests
    response = http.get(
        RSS_BASE_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return _parse_rss(response.text)
