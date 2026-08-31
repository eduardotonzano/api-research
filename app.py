"""App web local (Flask): formulário ticker + tópico -> busca de verdade -> relatório.

Sem servidor externo, sem chave paga — roda 100% na sua máquina/Codespace.
A busca acontece de verdade a cada envio do formulário (sob demanda, sempre
atual — não é um job em background).

Uso:
    python3 app.py
Depois abre http://localhost:5000 (ou a porta encaminhada, no Codespaces).
"""

from __future__ import annotations

from urllib.parse import quote

from flask import Flask, redirect, render_template_string, request

from date_utils import filter_recent_items
from db.connection import init_db
from db.queries import get_latest_search_news, list_searched_pairs, lookup_company_id, lookup_topic_id
from report_html import STYLE, render_group_html, render_report_page
from run_search import DEFAULT_MAX_AGE_DAYS, run_search

app = Flask(__name__)

PAGE_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de Notícias</title>
{{ style|safe }}
<style>
form { margin-bottom: 28px; display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
label { display: flex; flex-direction: column; font-size: 0.85rem; color: var(--muted); gap: 4px; }
input { padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px;
        background: var(--card-bg); color: var(--text); font-size: 0.95rem; }
button { padding: 9px 18px; border: none; border-radius: 6px; background: var(--accent);
         color: #fff; font-size: 0.95rem; cursor: pointer; }
button:hover { opacity: 0.9; }
.pairs { list-style: none; padding: 0; }
.pairs li { margin-bottom: 6px; }
.pairs a { color: var(--accent); text-decoration: none; }
.pairs a:hover { text-decoration: underline; }
.status { color: var(--muted); font-size: 0.85rem; margin-bottom: 20px; }
</style>
</head>
<body>
<h1>Monitor de Notícias Financeiras</h1>

<form method="post" action="/buscar">
  <label>Empresa <input name="company" placeholder="Petrobras" required></label>
  <label>Ticker <input name="ticker" placeholder="PETR4 (opcional)"></label>
  <label>Tópico <input name="topic" placeholder="resultados" required></label>
  <button type="submit">Buscar</button>
</form>

{% if status %}<div class="status">{{ status }}</div>{% endif %}

{% if pairs %}
<h2>Pares já buscados</h2>
<ul class="pairs">
{% for company_name, topic_name in pairs %}
  <li><a href="/ver?company={{ company_name|urlencode }}&topic={{ topic_name|urlencode }}">
      {{ company_name }} + {{ topic_name }}</a></li>
{% endfor %}
</ul>
{% endif %}

{% if report_body %}
<hr>
{{ report_body|safe }}
{% endif %}

</body>
</html>
"""


def _searched_pairs_names(conn) -> list[tuple[str, str]]:
    return [(company_name, topic_name) for _, company_name, _, topic_name in list_searched_pairs(conn)]


def _current_snapshot_html(conn, company_name: str, topic_name: str) -> str | None:
    """Retrato atual (não o diff) pra um par já buscado. None se o par não existe."""
    company_id = lookup_company_id(conn, company_name)
    topic_id = lookup_topic_id(conn, topic_name) if company_id is not None else None
    if company_id is None or topic_id is None:
        return None

    items = get_latest_search_news(conn, company_id, topic_id)
    items = filter_recent_items(items, max_age_days=DEFAULT_MAX_AGE_DAYS)
    group = render_group_html(company_name, topic_name, items)
    return render_report_page([group], title=f"{company_name} + {topic_name}")


@app.route("/", methods=["GET"])
def index():
    conn = init_db()
    try:
        pairs = _searched_pairs_names(conn)
    finally:
        conn.close()
    return render_template_string(PAGE_TEMPLATE, style=STYLE, pairs=pairs, status=None, report_body=None)


@app.route("/buscar", methods=["POST"])
def buscar():
    company = (request.form.get("company") or "").strip()
    ticker = (request.form.get("ticker") or "").strip() or None
    topic = (request.form.get("topic") or "").strip()

    if not company or not topic:
        return redirect("/")

    conn = init_db()
    try:
        stats = run_search(conn, company, topic, ticker=ticker)
    finally:
        conn.close()

    return redirect(
        f"/ver?company={quote(company)}&topic={quote(topic)}"
        f"&found={stats['found']}&saved={stats['saved']}&summarized={stats['summarized']}"
    )


@app.route("/ver", methods=["GET"])
def ver():
    company = request.args.get("company", "")
    topic = request.args.get("topic", "")

    conn = init_db()
    try:
        pairs = _searched_pairs_names(conn)
        report_body = _current_snapshot_html(conn, company, topic)
    finally:
        conn.close()

    status = None
    if "found" in request.args:
        status = (
            f"Busca concluída: {request.args.get('found')} notícia(s) encontrada(s), "
            f"{request.args.get('saved')} salva(s), {request.args.get('summarized')} resumida(s)."
        )
    if report_body is None:
        report_body = f'<p class="empty">Empresa/tópico ainda não buscado: {company} + {topic}</p>'

    return render_template_string(
        PAGE_TEMPLATE, style=STYLE, pairs=pairs, status=status, report_body=report_body
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
