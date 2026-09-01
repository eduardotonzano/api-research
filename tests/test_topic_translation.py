from topic_translation import translate_topic


def test_translate_topic_known_term():
    assert translate_topic("resultados") == "earnings"


def test_translate_topic_is_case_insensitive():
    assert translate_topic("RESULTADOS") == "earnings"
    assert translate_topic("Resultados") == "earnings"


def test_translate_topic_ignores_accents():
    assert translate_topic("fusão") == "merger"
    assert translate_topic("fusao") == "merger"
    assert translate_topic("dívida") == "debt"


def test_translate_topic_unknown_term_returns_none():
    assert translate_topic("um-topico-qualquer-inventado") is None


def test_translate_topic_empty_or_none_returns_none():
    assert translate_topic("") is None
    assert translate_topic(None) is None


def test_translate_topic_strips_whitespace():
    assert translate_topic("  resultados  ") == "earnings"
