-- 0001_init.sql
-- Schema inicial: empresas, tópicos, buscas, notícias e o vínculo entre busca e notícia.

CREATE TABLE companies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    ticker      TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (name COLLATE NOCASE),
    UNIQUE (ticker)
);

CREATE TABLE topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (name COLLATE NOCASE)
);

-- Cada linha representa uma execução de busca (empresa + tópico) em um momento no tempo.
CREATE TABLE searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   INTEGER NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    topic_id     INTEGER NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    searched_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    source       TEXT
);

CREATE INDEX idx_searches_company_topic ON searches (company_id, topic_id, searched_at);

-- Uma notícia é única por URL e, quando o hash de conteúdo é conhecido, também por hash
-- (evita duplicar a mesma matéria republicada em outra URL).
CREATE TABLE news (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL,
    content_hash  TEXT,
    title         TEXT,
    source        TEXT,
    published_at  TEXT,
    summary       TEXT,
    fetched_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (url),
    UNIQUE (content_hash)
);

-- Vínculo N:N entre buscas e notícias: a mesma notícia pode aparecer em mais de uma busca
-- (empresas/tópicos diferentes achando a mesma matéria), e uma busca traz várias notícias.
CREATE TABLE search_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id   INTEGER NOT NULL REFERENCES searches (id) ON DELETE CASCADE,
    news_id     INTEGER NOT NULL REFERENCES news (id) ON DELETE CASCADE,
    relevance   REAL,
    UNIQUE (search_id, news_id)
);

CREATE INDEX idx_search_results_news ON search_results (news_id);
