import requests

from summarize import gemini_provider, groq_provider
from summarize.summarizer import summarize_article


class FakeResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, responses):
        # aceita uma resposta única ou uma lista (uma por chamada, útil pra testar retry)
        self._responses = responses if isinstance(responses, list) else [responses]
        self.calls = 0

    def post(self, *args, **kwargs):
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


GROQ_SUCCESS = FakeResponse(
    status_code=200,
    json_data={"choices": [{"message": {"content": "Resumo objetivo em 3 frases."}}]},
)
GEMINI_SUCCESS = FakeResponse(
    status_code=200,
    json_data={"candidates": [{"content": {"parts": [{"text": "Resumo via Gemini."}]}}]},
)


# --- Groq ---


def test_groq_summarize_without_api_key_returns_none():
    result = groq_provider.summarize("Título", "Texto do artigo.", api_key=None)
    assert result is None


def test_groq_summarize_success_returns_content():
    session = FakeSession(GROQ_SUCCESS)
    result = groq_provider.summarize(
        "Título", "Texto do artigo.", api_key="fake-key", session=session
    )
    assert result == "Resumo objetivo em 3 frases."


def test_groq_summarize_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(groq_provider.time, "sleep", lambda s: None)
    session = FakeSession([FakeResponse(status_code=429, headers={"Retry-After": "0"}), GROQ_SUCCESS])
    result = groq_provider.summarize(
        "Título", "Texto do artigo.", api_key="fake-key", session=session
    )
    assert result == "Resumo objetivo em 3 frases."
    assert session.calls == 2


def test_groq_summarize_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(groq_provider.time, "sleep", lambda s: None)
    session = FakeSession(FakeResponse(status_code=429, headers={"Retry-After": "0"}))
    result = groq_provider.summarize(
        "Título", "Texto do artigo.", api_key="fake-key", session=session
    )
    assert result is None
    assert session.calls == groq_provider.MAX_RETRIES


def test_groq_summarize_returns_none_on_http_error():
    session = FakeSession(FakeResponse(status_code=500))
    result = groq_provider.summarize(
        "Título", "Texto do artigo.", api_key="fake-key", session=session
    )
    assert result is None


def test_groq_summarize_returns_none_on_request_exception():
    session = FakeSession(requests.ConnectionError("sem rede"))
    result = groq_provider.summarize(
        "Título", "Texto do artigo.", api_key="fake-key", session=session
    )
    assert result is None


def test_groq_summarize_returns_none_on_malformed_response():
    session = FakeSession(FakeResponse(status_code=200, json_data={"unexpected": "shape"}))
    result = groq_provider.summarize(
        "Título", "Texto do artigo.", api_key="fake-key", session=session
    )
    assert result is None


def test_groq_summarize_returns_none_for_empty_text():
    session = FakeSession(GROQ_SUCCESS)
    result = groq_provider.summarize("Título", "   ", api_key="fake-key", session=session)
    assert result is None
    assert session.calls == 0


# --- Gemini ---


def test_gemini_summarize_without_api_key_returns_none():
    result = gemini_provider.summarize("Título", "Texto do artigo.", api_key=None)
    assert result is None


def test_gemini_summarize_success_returns_content():
    session = FakeSession(GEMINI_SUCCESS)
    result = gemini_provider.summarize(
        "Título", "Texto do artigo.", api_key="fake-key", session=session
    )
    assert result == "Resumo via Gemini."


def test_gemini_summarize_returns_none_on_http_error():
    session = FakeSession(FakeResponse(status_code=403))
    result = gemini_provider.summarize(
        "Título", "Texto do artigo.", api_key="fake-key", session=session
    )
    assert result is None


# --- Orquestração (Groq primeiro, Gemini como fallback) ---


def test_summarize_article_uses_groq_when_available(monkeypatch):
    monkeypatch.setattr(groq_provider, "summarize", lambda title, text, **kw: "Resumo Groq")
    monkeypatch.setattr(
        gemini_provider,
        "summarize",
        lambda title, text, **kw: (_ for _ in ()).throw(AssertionError("Gemini não deveria ser chamado")),
    )
    result = summarize_article("Título", "Texto qualquer")
    assert result == "Resumo Groq"


def test_summarize_article_falls_back_to_gemini_when_groq_fails(monkeypatch):
    monkeypatch.setattr(groq_provider, "summarize", lambda title, text, **kw: None)
    monkeypatch.setattr(gemini_provider, "summarize", lambda title, text, **kw: "Resumo Gemini")
    result = summarize_article("Título", "Texto qualquer")
    assert result == "Resumo Gemini"


def test_summarize_article_returns_none_when_both_fail(monkeypatch):
    monkeypatch.setattr(groq_provider, "summarize", lambda title, text, **kw: None)
    monkeypatch.setattr(gemini_provider, "summarize", lambda title, text, **kw: None)
    result = summarize_article("Título", "Texto qualquer")
    assert result is None


def test_summarize_article_returns_none_for_empty_text_without_calling_providers(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("não deveria chamar provider nenhum com texto vazio")

    monkeypatch.setattr(groq_provider, "summarize", fail_if_called)
    monkeypatch.setattr(gemini_provider, "summarize", fail_if_called)
    assert summarize_article("Título", None) is None
    assert summarize_article("Título", "   ") is None
