"""Busca de notícias via Google News RSS — gratuito, sem chave de API.

Formato de URL: https://news.google.com/rss/search?q=...&hl=pt-BR&gl=BR&ceid=BR:pt-BR
O <link> de cada item costuma ser um redirect do Google (news.google.com/rss/articles/...),
por isso a resolução da URL final fica a cargo de fetch.extractor.resolve_final_url.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from topic_translation import translate_topic

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
    company: str,
    topic: str,
    *,
    hl: str = "pt-BR",
    gl: str = "BR",
    ceid: str = "BR:pt-BR",
    session: requests.Session | None = None,
) -> list[RssItem]:
    """Busca notícias no Google News RSS pra empresa+tópico, numa região/idioma.

    Lança requests.RequestException em caso de falha de rede/HTTP — quem chama
    decide se trata (ex: run_search segue com os outros feeds) ou deixa propagar.
    """
    query = build_query(company, topic)
    params = {"q": query, "hl": hl, "gl": gl, "ceid": ceid}
    http = session or requests
    response = http.get(
        RSS_BASE_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return _parse_rss(response.text)


# pt-BR primeiro (mercado principal do projeto), en-US depois — é a busca em
# inglês que traz cobertura de Bloomberg/Reuters/MarketWatch/WSJ quando o
# Google News já indexou essas fontes pra empresa buscada. Não existe API
# gratuita da Bloomberg em si (busca por empresa é paga) — isso aqui é o
# proxy gratuito mais confiável que existe pra esse tipo de cobertura.
DEFAULT_LOCALES: list[tuple[str, str, str]] = [
    ("pt-BR", "BR", "BR:pt-BR"),
    ("en-US", "US", "US:en"),
]


def _normalize_title_for_dedupe(title: str) -> str:
    return " ".join(title.lower().split())


def _dedupe_rss_items(items: list[RssItem]) -> list[RssItem]:
    """Duas consultas por região podem trazer a mesma matéria com um link de
    redirect diferente (o link do Google News é por região) — por isso o
    dedupe é por link exato OU por título normalizado, não só por link."""
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    deduped: list[RssItem] = []
    for item in items:
        normalized_title = _normalize_title_for_dedupe(item.title)
        if item.link in seen_links or normalized_title in seen_titles:
            continue
        seen_links.add(item.link)
        seen_titles.add(normalized_title)
        deduped.append(item)
    return deduped


def fetch_google_news_multi_locale(
    company: str,
    topic: str,
    *,
    locales: list[tuple[str, str, str]] | None = None,
    session: requests.Session | None = None,
) -> list[RssItem]:
    """Consulta o Google News RSS uma vez por região (pt-BR + en-US por
    padrão) e devolve a união deduplicada. Uma região fora do ar não derruba
    as demais — mesmo padrão de fetch_portal_feed em fetch/portal_feeds.py.

    Mudar só hl/gl/ceid não basta pra achar cobertura em inglês: se o tópico
    foi digitado em português (ex: "resultados"), essa palavra nunca aparece
    numa matéria da Bloomberg/Reuters (que escrevem "earnings"). Por isso,
    em toda região que não seja a do Brasil, a busca usa a tradução conhecida
    do tópico (topic_translation.py); sem tradução conhecida, busca só a
    empresa — melhor trazer notícia geral em inglês (a relevância depois
    ordena) do que mandar uma palavra que nunca vai bater.
    """
    locales = locales if locales is not None else DEFAULT_LOCALES
    all_items: list[RssItem] = []
    for hl, gl, ceid in locales:
        query_topic = topic if gl == "BR" else (translate_topic(topic) or "")
        try:
            all_items.extend(
                fetch_google_news(company, query_topic, hl=hl, gl=gl, ceid=ceid, session=session)
            )
        except requests.RequestException:
            continue
    return _dedupe_rss_items(all_items)
