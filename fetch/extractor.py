"""Extração de texto completo de uma notícia a partir da URL, via trafilatura.

Nunca lança erro por falha de extração (paywall, bloqueio, HTML quebrado): o
chamador (run_search) precisa poder salvar a notícia mesmo sem o texto
completo, só com os metadados que vieram do RSS — é exatamente pra isso que
news.content_hash e news.summary são nullable na Fase 1.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests
import trafilatura

from .google_news import REQUEST_TIMEOUT, USER_AGENT


@dataclass
class ExtractionResult:
    final_url: str
    text: str | None
    published_at: str | None


def resolve_final_url(url: str, *, session: requests.Session | None = None) -> str:
    """Segue redirects (comum em links do Google News) e devolve a URL final.

    Sem isso, o dedupe por URL (Fase 1) compararia o link intermediário do
    Google, não o artigo real — duas buscas diferentes que passam pelo mesmo
    redirect gerariam duas notícias em vez de uma.
    """
    http = session or requests
    try:
        with http.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True,
        ) as response:
            if response.status_code < 400:
                return response.url
    except requests.RequestException:
        pass
    return url


def extract_article(url: str, *, session: requests.Session | None = None) -> ExtractionResult:
    final_url = resolve_final_url(url, session=session)

    downloaded = trafilatura.fetch_url(final_url)
    if not downloaded:
        return ExtractionResult(final_url=final_url, text=None, published_at=None)

    text = trafilatura.extract(downloaded)
    metadata = trafilatura.extract_metadata(downloaded, default_url=final_url)
    published_at = metadata.date if metadata else None

    return ExtractionResult(final_url=final_url, text=text, published_at=published_at)
