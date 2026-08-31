from pathlib import Path

from report_html import render_group_html, render_report_page, write_report


def test_render_group_html_escapes_special_characters():
    items = [
        {
            "title": "Empresa <X> anuncia \"resultado\" & recorde",
            "url": "https://example.com/a?x=1&y=2",
            "source": "Fonte <Y>",
            "published_at": "2026-08-20",
            "summary": "Lucro > R$ 5bi & crescimento de 10%",
        }
    ]
    html = render_group_html("Empresa & Cia", "M&A", items)

    assert "&amp;" in html
    assert "<X>" not in html  # tag literal não deve vazar sem escape
    assert "&lt;X&gt;" in html
    assert 'href="https://example.com/a?x=1&amp;y=2"' in html
    assert "Empresa &amp; Cia" in html


def test_render_group_html_shows_empty_state_when_no_items():
    html = render_group_html("Vale", "resultados", [])
    assert "Nada novo desde a última busca." in html
    assert "Vale" in html and "resultados" in html


def test_render_group_html_omits_missing_optional_fields():
    items = [{"title": "Notícia só com título e url", "url": "https://example.com/x"}]
    html = render_group_html("Weg", "governança", items)
    assert "Notícia só com título e url" in html
    assert 'class="meta"' not in html
    assert 'class="summary"' not in html


def test_render_group_html_renders_title_without_link_when_url_missing():
    items = [{"title": "Sem URL"}]
    html = render_group_html("X", "Y", items)
    assert "Sem URL" in html
    assert "<a href=" not in html


def test_render_report_page_includes_title_and_groups():
    group = render_group_html("Petrobras", "resultados", [])
    page = render_report_page([group], title="Meu Relatório")
    assert "<title>Meu Relatório</title>" in page
    assert "Petrobras" in page
    assert "<!doctype html>" in page.lower()
    assert "Gerado em" in page


def test_render_report_page_empty_state_when_no_groups():
    page = render_report_page([])
    assert "Nenhuma busca feita ainda." in page


def test_write_report_creates_parent_dir_and_writes_content(tmp_path: Path):
    target = tmp_path / "nested" / "report.html"
    html = "<html><body>oi</body></html>"
    result_path = write_report(target, html)

    assert result_path == target
    assert target.exists()
    assert target.read_text(encoding="utf-8") == html
