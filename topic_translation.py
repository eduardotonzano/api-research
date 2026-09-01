"""Tradução de tópicos financeiros comuns pra inglês.

Usada só nas fontes em inglês (Google News em en-US, feeds internacionais
como Investing.com/MarketWatch/CNBC) — sem isso, buscar "resultados" nunca
bate num título tipo "Petrobras Reports Record Profit", porque a palavra em
português simplesmente não existe em texto em inglês. Não é um serviço de
tradução genérico (não tem API gratuita confiável pra isso) — é um
dicionário pequeno e explícito dos termos financeiros mais comuns. Termo
fora da lista: sem tradução, e quem chama decide o que fazer (normalmente,
cair pra buscar só a empresa).
"""

from __future__ import annotations

import unicodedata

TOPIC_TRANSLATIONS: dict[str, str] = {
    "resultados": "earnings",
    "resultado": "earnings",
    "lucro": "profit",
    "lucros": "profits",
    "prejuizo": "loss",
    "dividendos": "dividends",
    "dividendo": "dividend",
    "fusao": "merger",
    "fusoes": "mergers",
    "aquisicao": "acquisition",
    "aquisicoes": "acquisitions",
    "recompra": "buyback",
    "governanca": "governance",
    "divida": "debt",
    "dividas": "debt",
    "greve": "strike",
    "processo": "lawsuit",
    "multa": "fine",
    "acoes": "shares",
    "acao": "shares",
    "investimentos": "investments",
    "investimento": "investment",
    "expansao": "expansion",
    "demissoes": "layoffs",
    "guidance": "guidance",
    "ipo": "ipo",
}


def _normalize(text: str) -> str:
    """Minúsculo e sem acento, pra 'fusão'/'fusao' caírem na mesma chave."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def translate_topic(topic: str) -> str | None:
    """Devolve a tradução conhecida pro tópico, ou None se não tiver no
    dicionário — nunca inventa tradução pra termo desconhecido."""
    if not topic:
        return None
    return TOPIC_TRANSLATIONS.get(_normalize(topic))
