"""Resumo via Groq — LLM gratuito, cadastro só por e-mail, sem cartão.

Free tier tem limite de requisições/minuto e tokens/minuto que a Groq ajusta
com frequência por modelo. Confira o valor atual em
https://console.groq.com/settings/limits antes de rodar em volume — aqui só
tratamos o 429 com backoff, não assumimos um número fixo de cota.
"""

from __future__ import annotations

import os
import time

import requests

API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
MAX_INPUT_CHARS = 6000

SYSTEM_PROMPT = (
    "Você resume notícias financeiras em português, de forma objetiva, em até "
    "3 frases. Foque em fatos e números presentes no texto. Não invente "
    "informação que não esteja nele."
)


def summarize(
    title: str,
    text: str,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    session: requests.Session | None = None,
) -> str | None:
    """Resume um artigo com a Groq. Nunca lança erro: retorna None se a chave
    não estiver configurada, a requisição falhar, ou a resposta vier num
    formato inesperado — quem chama (summarize_article) decide o fallback."""
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key or not text or not text.strip():
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Título: {title}\n\nTexto:\n{text[:MAX_INPUT_CHARS]}"},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    http = session or requests

    for attempt in range(MAX_RETRIES):
        try:
            response = http.post(API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            return None

        if response.status_code == 429:
            wait_seconds = float(response.headers.get("Retry-After", 2 * (attempt + 1)))
            time.sleep(wait_seconds)
            continue

        if response.status_code >= 400:
            return None

        try:
            return response.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError, TypeError):
            return None

    return None
