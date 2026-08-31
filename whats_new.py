"""CLI: mostra notícias novas desde a última busca, sem buscar de novo na rede.

Só lê o que já está salvo no banco (Fase 1) — útil pra conferir o que apareceu
de novo entre duas buscas sem gastar cota de RSS/extração/resumo de novo.
Gera um relatório HTML (Fase 5); o terminal só mostra o caminho do arquivo.

Uso:
    python3 whats_new.py "Petrobras" "resultados"   # um par específico
    python3 whats_new.py --all                       # todos os pares já buscados
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import webbrowser
from html import escape
from pathlib import Path

from db.connection import init_db
from db.queries import get_new_since_last_search
from report_html import render_group_html, render_report_page, write_report
from reporting import format_new_items

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "reports" / "whats_new.html"


def _list_searched_pairs(conn: sqlite3.Connection) -> list[tuple[int, str, int, str]]:
    """Todos os pares (empresa, tópico) que já tiveram pelo menos uma busca."""
    rows = conn.execute(
        """
        SELECT DISTINCT c.id AS company_id, c.name AS company_name,
               t.id AS topic_id, t.name AS topic_name
        FROM searches s
        JOIN companies c ON c.id = s.company_id
        JOIN topics t ON t.id = s.topic_id
        ORDER BY c.name, t.name
        """
    ).fetchall()
    return [(r["company_id"], r["company_name"], r["topic_id"], r["topic_name"]) for r in rows]


def _lookup_company_id(conn: sqlite3.Connection, company_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM companies WHERE name = ? COLLATE NOCASE", (company_name,)
    ).fetchone()
    return row["id"] if row is not None else None


def _lookup_topic_id(conn: sqlite3.Connection, topic_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM topics WHERE name = ? COLLATE NOCASE", (topic_name,)
    ).fetchone()
    return row["id"] if row is not None else None


def get_new_for_pair(
    conn: sqlite3.Connection, company_name: str, topic_name: str
) -> tuple[bool, str]:
    """Retorna (encontrado, texto formatado). encontrado=False quando a empresa
    ou o tópico nunca foram buscados antes (não dá pra comparar o que nunca existiu)."""
    company_id = _lookup_company_id(conn, company_name)
    if company_id is None:
        return False, f"Empresa '{company_name}' nunca foi buscada."

    topic_id = _lookup_topic_id(conn, topic_name)
    if topic_id is None:
        return False, f"Tópico '{topic_name}' nunca foi buscado."

    items = get_new_since_last_search(conn, company_id, topic_id)
    return True, format_new_items(company_name, topic_name, items)


def get_new_for_all_pairs(conn: sqlite3.Connection) -> str:
    pairs = _list_searched_pairs(conn)
    if not pairs:
        return "Nenhuma busca feita ainda."

    blocks = []
    for company_id, company_name, topic_id, topic_name in pairs:
        items = get_new_since_last_search(conn, company_id, topic_id)
        blocks.append(format_new_items(company_name, topic_name, items))
    return "\n\n".join(blocks)


def build_report_html_for_pair(
    conn: sqlite3.Connection, company_name: str, topic_name: str
) -> tuple[bool, str]:
    """Mesma lógica de get_new_for_pair, mas devolvendo a página HTML (Fase 5)."""
    company_id = _lookup_company_id(conn, company_name)
    if company_id is None:
        message = f"Empresa '{company_name}' nunca foi buscada."
        page = render_report_page([f'<p class="empty">{escape(message)}</p>'])
        return False, page

    topic_id = _lookup_topic_id(conn, topic_name)
    if topic_id is None:
        message = f"Tópico '{topic_name}' nunca foi buscado."
        page = render_report_page([f'<p class="empty">{escape(message)}</p>'])
        return False, page

    items = get_new_since_last_search(conn, company_id, topic_id)
    group = render_group_html(company_name, topic_name, items)
    page = render_report_page([group], title=f"Novidades: {company_name} + {topic_name}")
    return True, page


def build_report_html_for_all(conn: sqlite3.Connection) -> str:
    pairs = _list_searched_pairs(conn)
    groups = [
        render_group_html(
            company_name, topic_name, get_new_since_last_search(conn, company_id, topic_id)
        )
        for company_id, company_name, topic_id, topic_name in pairs
    ]
    return render_report_page(groups, title="Novidades — todos os pares")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mostra notícias novas desde a última busca (sem buscar de novo na rede)."
    )
    parser.add_argument("company", nargs="?", help="Nome da empresa (omita com --all)")
    parser.add_argument("topic", nargs="?", help="Tópico (omita com --all)")
    parser.add_argument("--all", action="store_true", help="Roda pra todos os pares já buscados")
    parser.add_argument(
        "--open", action="store_true", help="Abre o relatório no navegador ao final"
    )
    args = parser.parse_args()

    conn = init_db()
    try:
        if args.all:
            html = build_report_html_for_all(conn)
            found = True
        else:
            if not args.company or not args.topic:
                parser.error("informe empresa e tópico, ou use --all")
            found, html = build_report_html_for_pair(conn, args.company, args.topic)

        report_path = write_report(DEFAULT_REPORT_PATH, html)
        print(f"Relatório: {report_path}")
        if not found:
            print("(empresa ou tópico nunca foram buscados — veja o relatório pra detalhes)")

        if args.open:
            try:
                webbrowser.open(report_path.resolve().as_uri())
            except Exception as exc:
                print(
                    f"Aviso: não consegui abrir o navegador automaticamente: {exc}",
                    file=sys.stderr,
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
