"""Resumo via Google Gemini (AI Studio) — fallback gratuito quando a Groq falha.

Free tier sem cartão de crédito, cadastro em https://aistudio.google.com/apikey.
Assim como a Groq, o limite de requisições/dia e por minuto muda com frequência
por modelo — confira em https://ai.google.dev/gemini-api/docs/rate-limits.
"""

from __future__ import annotations

import os
import time

import requests

API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-2.0-flash"
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
    """Resume um artigo com o Gemini. Mesmo contrato do groq_provider.summarize:
    nunca lança erro, retorna None em qualquer falha (sem chave, HTTP, formato
    de resposta inesperado)."""
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key or not text or not text.strip():
        return None

    url = API_URL_TEMPLATE.format(model=model)
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {"parts": [{"text": f"Título: {title}\n\nTexto:\n{text[:MAX_INPUT_CHARS]}"}]}
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    http = session or requests

    for attempt in range(MAX_RETRIES):
        try:
            response = http.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            return None

        if response.status_code == 429:
            wait_seconds = float(response.headers.get("Retry-After", 2 * (attempt + 1)))
            time.sleep(wait_seconds)
            continue

        if response.status_code >= 400:
            return None

        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, ValueError, TypeError):
            return None

    return None
