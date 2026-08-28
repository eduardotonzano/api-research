"""Conexão com o SQLite e runner de migrations.

Todo acesso ao banco deve passar por get_connection() (ou init_db(), que já aplica
as migrations pendentes). Isso garante que PRAGMAs de integridade e concorrência
(foreign_keys, WAL, busy_timeout) sejam aplicados sempre, em toda conexão nova.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "newsmon.db"


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Abre uma conexão com os PRAGMAs necessários. Não roda migrations."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row

    # foreign_keys é por conexão: sem isso o SQLite aceita FK inválida silenciosamente.
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL permite um escritor + múltiplos leitores concorrentes sem corromper o arquivo.
    conn.execute("PRAGMA journal_mode = WAL")
    # Em vez de falhar na hora com "database is locked", espera até 5s por um writer concorrente.
    conn.execute("PRAGMA busy_timeout = 5000")

    return conn


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def _split_sql_statements(script: str) -> list[str]:
    """Separa um script SQL em statements individuais, respeitando strings e comentários.

    Necessário porque sqlite3.Cursor.executescript() faz commit statement a statement
    (não é atômico): uma falha no meio do script deixaria o schema pela metade. Aqui
    cada statement é executado com conn.execute() dentro de uma única transação manual,
    então uma falha em qualquer statement desfaz a migration inteira.
    """
    statements = []
    current: list[str] = []
    in_single = in_double = in_line_comment = False
    i, n = 0, len(script)
    while i < n:
        ch = script[i]
        nxt = script[i + 1] if i + 1 < n else ""
        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_single:
            current.append(ch)
            if ch == "'" and nxt == "'":
                current.append(nxt)
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            current.append(ch)
            if ch == '"' and nxt == '"':
                current.append(nxt)
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "-" and nxt == "-":
            in_line_comment = True
            current.append(ch)
            i += 1
            continue
        if ch == "'":
            in_single = True
            current.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            current.append(ch)
            i += 1
            continue
        if ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Aplica, em ordem, os arquivos .sql ainda não registrados em schema_migrations.

    Retorna a lista de versões aplicadas nesta chamada (vazia se já estava tudo em dia).
    """
    applied = _applied_versions(conn)
    pending = sorted(p for p in migrations_dir.glob("*.sql") if p.stem not in applied)

    newly_applied = []
    for path in pending:
        statements = _split_sql_statements(path.read_text(encoding="utf-8"))
        conn.execute("BEGIN")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (path.stem,)
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        newly_applied.append(path.stem)

    return newly_applied


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Abre a conexão e garante que o schema está atualizado. Ponto de entrada padrão."""
    conn = get_connection(db_path)
    apply_migrations(conn)
    return conn
