from reporting import format_new_items


def test_format_new_items_with_no_items():
    text = format_new_items("Petrobras", "resultados", [])
    assert "=== Petrobras + resultados ===" in text
    assert "Nada novo desde a última busca." in text


def test_format_new_items_includes_optional_fields_when_present():
    items = [
        {
            "title": "Petrobras anuncia lucro recorde",
            "source": "Valor Econômico",
            "published_at": "2026-08-20",
            "url": "https://example.com/petrobras-lucro",
            "summary": "Lucro líquido de R$ 30 bilhões no trimestre.",
        }
    ]
    text = format_new_items("Petrobras", "resultados", items)
    assert "- Petrobras anuncia lucro recorde" in text
    assert "fonte: Valor Econômico" in text
    assert "publicado em: 2026-08-20" in text
    assert "https://example.com/petrobras-lucro" in text
    assert "resumo: Lucro líquido de R$ 30 bilhões no trimestre." in text


def test_format_new_items_omits_missing_optional_fields():
    items = [{"title": "Notícia sem metadado extra", "url": "https://example.com/x"}]
    text = format_new_items("Vale", "M&A", items)
    assert "- Notícia sem metadado extra" in text
    assert "https://example.com/x" in text
    assert "fonte:" not in text
    assert "resumo:" not in text


def test_format_new_items_lists_multiple_items_in_order():
    items = [
        {"title": "Primeira notícia", "url": "https://example.com/1"},
        {"title": "Segunda notícia", "url": "https://example.com/2"},
    ]
    text = format_new_items("Ambev", "resultados", items)
    assert text.index("Primeira notícia") < text.index("Segunda notícia")
