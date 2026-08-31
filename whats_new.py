"""CLI: mostra notícias novas desde a última busca, sem buscar de novo na rede.

Só lê o que já está salvo no banco (Fase 1) — útil pra conferir o que apareceu
de novo entre duas buscas sem gastar cota de RSS/extração/resumo de novo.

Uso:
    python3 whats_new.py "Petrobras" "resultados"   # um par específico
    python3 whats_new.py --all                       # todos os pares já buscados
"""

from __future__ import annotations

import argparse
import sqlite3

from db.connection import init_db
from db.queries import get_new_since_last_search
from reporting import format_new_items


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


def get_new_for_pair(
    conn: sqlite3.Connection, company_name: str, topic_name: str
) -> tuple[bool, str]:
    """Retorna (encontrado, texto formatado). encontrado=False quando a empresa
    ou o tópico nunca foram buscados antes (não dá pra comparar o que nunca existiu)."""
    row = conn.execute(
        "SELECT id FROM companies WHERE name = ? COLLATE NOCASE", (company_name,)
    ).fetchone()
    if row is None:
        return False, f"Empresa '{company_name}' nunca foi buscada."
    company_id = row["id"]

    row = conn.execute(
        "SELECT id FROM topics WHERE name = ? COLLATE NOCASE", (topic_name,)
    ).fetchone()
    if row is None:
        return False, f"Tópico '{topic_name}' nunca foi buscado."
    topic_id = row["id"]

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mostra notícias novas desde a última busca (sem buscar de novo na rede)."
    )
    parser.add_argument("company", nargs="?", help="Nome da empresa (omita com --all)")
    parser.add_argument("topic", nargs="?", help="Tópico (omita com --all)")
    parser.add_argument("--all", action="store_true", help="Roda pra todos os pares já buscados")
    args = parser.parse_args()

    conn = init_db()
    try:
        if args.all:
            print(get_new_for_all_pairs(conn))
        else:
            if not args.company or not args.topic:
                parser.error("informe empresa e tópico, ou use --all")
            _, text = get_new_for_pair(conn, args.company, args.topic)
            print(text)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
