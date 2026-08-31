"""Relatório HTML de 'notícias novas desde a última busca' (Fase 5).

HTML+CSS puro, auto-contido: sem framework, sem JS, sem dependência de rede
pra estilizar. Abre em qualquer navegador direto do arquivo local.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

_STYLE = """<style>
:root { --bg:#f7f7f5; --card-bg:#ffffff; --text:#1a1a1a; --muted:#666666; --border:#e2e2e2; --accent:#2563eb; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#15161a; --card-bg:#1f2024; --text:#e8e8e8; --muted:#9a9a9a; --border:#333333; --accent:#7aa2f7; }
}
body { margin:0; padding:24px; background:var(--bg); color:var(--text);
       font-family:-apple-system,"Segoe UI",Roboto,sans-serif; }
h1 { font-size:1.4rem; margin:0 0 4px; }
.generated-at { color:var(--muted); font-size:0.85rem; margin-bottom:24px; }
.group { margin-bottom:32px; }
.group h2 { font-size:1.1rem; border-bottom:1px solid var(--border); padding-bottom:6px; }
.empty { color:var(--muted); font-style:italic; }
.card { background:var(--card-bg); border:1px solid var(--border); border-radius:8px;
        padding:14px 16px; margin-bottom:12px; }
.card h3 { margin:0 0 6px; font-size:1rem; }
.card h3 a { color:var(--accent); text-decoration:none; }
.card h3 a:hover { text-decoration:underline; }
.meta { color:var(--muted); font-size:0.8rem; margin-bottom:8px; }
.summary { font-size:0.92rem; line-height:1.4; }
</style>"""


def _render_card(item: dict[str, Any]) -> str:
    title = escape(item.get("title") or "(sem título)")
    url = escape(item.get("url") or "", quote=True)
    meta_parts = [escape(str(v)) for v in (item.get("source"), item.get("published_at")) if v]
    meta = " · ".join(meta_parts)
    summary = escape(item["summary"]) if item.get("summary") else ""

    heading = (
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
        if url
        else title
    )

    parts = ['<div class="card">', f"<h3>{heading}</h3>"]
    if meta:
        parts.append(f'<div class="meta">{meta}</div>')
    if summary:
        parts.append(f'<div class="summary">{summary}</div>')
    parts.append("</div>")
    return "\n".join(parts)


def render_group_html(company_name: str, topic_name: str, items: list[dict[str, Any]]) -> str:
    heading = f"{escape(company_name)} + {escape(topic_name)}"
    body = (
        '<p class="empty">Nada novo desde a última busca.</p>'
        if not items
        else "\n".join(_render_card(item) for item in items)
    )
    return f'<div class="group">\n<h2>{heading}</h2>\n{body}\n</div>'


def render_report_page(groups_html: list[str], *, title: str = "Notícias novas") -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = (
        "\n".join(groups_html)
        if groups_html
        else '<p class="empty">Nenhuma busca feita ainda.</p>'
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
{_STYLE}
</head>
<body>
<h1>{escape(title)}</h1>
<div class="generated-at">Gerado em {generated_at}</div>
{body}
</body>
</html>
"""


def write_report(path: str | Path, html: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
