from relevance import compute_relevance


def test_compute_relevance_full_match_scores_highest():
    score = compute_relevance(
        "Petrobras (PETR4) anuncia resultados do trimestre",
        "Petrobras",
        "resultados",
        ticker="PETR4",
        published_at="2026-08-20",
    )
    assert score == 1.0


def test_compute_relevance_identity_only_without_date():
    score = compute_relevance("Petrobras anuncia novo diretor", "Petrobras", "resultados")
    assert score == 0.6


def test_compute_relevance_identity_with_known_date_gets_bonus():
    score = compute_relevance(
        "Petrobras anuncia novo diretor", "Petrobras", "resultados", published_at="2026-08-20"
    )
    assert score == 0.7


def test_compute_relevance_topic_only_scores_lower_than_identity_match():
    """Bater só no tópico, sem citar a empresa, ainda pontua (pode ser uma
    matéria legítima que o Google News achou por relevância geral), mas
    pontua bem menos que citar a empresa — reflete o mesmo espírito da
    correção do filtro AND: tópico sozinho é um sinal fraco."""
    topic_only_score = compute_relevance(
        "Selic: o que esperar da próxima reunião do Copom sobre resultados fiscais",
        "Petrobras",
        "resultados",
    )
    identity_only_score = compute_relevance(
        "Petrobras anuncia novo diretor", "Petrobras", "resultados"
    )
    assert topic_only_score == 0.3
    assert topic_only_score < identity_only_score


def test_compute_relevance_is_case_insensitive():
    score = compute_relevance("PETROBRAS ANUNCIA RESULTADOS", "petrobras", "RESULTADOS")
    assert score == 0.9


def test_compute_relevance_ticker_alone_counts_as_identity():
    score = compute_relevance("PETR4 dispara na bolsa", "Petrobras", "", ticker="PETR4")
    assert score == 0.6


def test_compute_relevance_without_topic_still_scores_identity():
    score = compute_relevance("Petrobras anuncia recompra de ações", "Petrobras", "")
    assert score == 0.6


def test_compute_relevance_unknown_date_gets_no_bonus():
    score = compute_relevance(
        "Petrobras anuncia resultados", "Petrobras", "resultados", published_at=None
    )
    assert score == 0.9
