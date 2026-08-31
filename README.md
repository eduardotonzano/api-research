# Monitor de Notícias Financeiras

Ferramenta pessoal para acompanhar notícias por empresa + tópico, 100% gratuita
(sem APIs pagas, sem chave de cartão de crédito). Desenvolvimento em fases —
este README documenta a **Fase 1: base de dados**.

## Stack da Fase 1

- **SQLite** (`sqlite3` da stdlib do Python) — banco local, sem servidor, sem custo.
- **Migrations caseiras**: arquivos `.sql` numerados em `db/migrations/`, aplicados
  em ordem e registrados na tabela `schema_migrations`. Nunca se altera o schema
  manualmente — toda mudança vira um novo arquivo de migration.
- **pytest** para os testes automatizados (`tests/test_db.py`).

## Por que cada tabela existe

```
companies ──┐
            ├──< searches >──┐
topics ─────┘                ├──< search_results >──── news
                              (searches)
```

### `companies`
Uma linha por empresa. **`id` é a chave — não o nome nem o ticker.** Isso é o
que garante que "Petrobras", "petrobras" e "PETROBRAS S.A." nunca virem
registros diferentes: `name` tem `UNIQUE COLLATE NOCASE`, então qualquer
variação de maiúsculas/minúsculas aponta pro mesmo `id`. `ticker` é opcional
(nem toda empresa monitorada precisa ter ticker) mas também é único quando
preenchido.

### `topics`
Um tópico de busca (ex: "resultados", "M&A", "governança"), com a mesma regra
de unicidade case-insensitive do `companies`.

### `searches`
Cada linha é **uma execução de busca** para um par empresa+tópico, com data
(`searched_at`) e, opcionalmente, de onde veio (`source`). É essa tabela que
guarda o "quando eu procurei isso" — permite ter várias buscas ao longo do
tempo para o mesmo par empresa+tópico, o que é a base pra "o que é novo desde
a última busca" (Fase 4).

### `news`
Uma notícia, independente de quantas buscas a encontraram. Duas camadas de
dedupe:
- `url UNIQUE` — a mesma URL nunca é gravada duas vezes.
- `content_hash UNIQUE` — se a mesma matéria for republicada em outra URL
  (comum em agregadores), o hash do conteúdo (calculado na Fase 2, a partir do
  título+corpo) evita duplicar a notícia mesmo com URL diferente.

Campos como `published_at`, `source` e `summary` são opcionais — nem toda
fonte fornece isso de forma confiável, e a tabela precisa aceitar dado
incompleto sem quebrar.

### `search_results`
Tabela de junção N:N entre `searches` e `news`. Existe porque **a mesma
notícia pode aparecer em mais de uma busca** (empresa X + tópico "resultados"
e empresa X + tópico "M&A" acham a mesma matéria) — sem essa tabela, ou a
notícia duplicaria, ou perderíamos o vínculo com uma das buscas. `UNIQUE
(search_id, news_id)` evita linkar a mesma notícia duas vezes na mesma busca.
`relevance` é opcional e fica nesta tabela (não em `news`) porque relevância é
contextual: a mesma notícia pode ser muito relevante pra uma busca e pouco
relevante pra outra.

É esse encadeamento — `companies → searches → search_results → news` — que
permite puxar todo o histórico de uma empresa cruzando todos os tópicos e
buscas já feitos (ver `get_company_history` em `db/queries.py`).

## Integridade

- `PRAGMA foreign_keys = ON` em toda conexão — sem isso o SQLite aceita FK
  inválida silenciosamente.
- Chaves estrangeiras com `ON DELETE CASCADE`: apagar uma empresa remove suas
  buscas e os vínculos de `search_results` associados (a notícia em si
  permanece, pois pode estar linkada a outras buscas).
- Campos obrigatórios (`NOT NULL`) em tudo que não pode faltar: nome de
  empresa/tópico, `url` da notícia, chaves estrangeiras de `searches` e
  `search_results`.
- `get_or_create_company` / `get_or_create_topic` / `add_news` tentam o
  `INSERT` e, se colidir com uma `UNIQUE constraint`, buscam e devolvem o
  registro já existente — dedupe automática, sem lançar erro para o caso
  esperado de "já existe".

## Concorrência

- `PRAGMA journal_mode = WAL` — permite um escritor + múltiplos leitores
  simultâneos sem corromper o arquivo.
- `PRAGMA busy_timeout = 5000` — se duas escritas colidirem, uma espera até
  5s pela outra em vez de falhar na hora com "database is locked".
- Testado com múltiplas threads escrevendo ao mesmo tempo (`tests/test_db.py`),
  inclusive disputando o mesmo registro (mesma empresa) — sem duplicar dado e
  sem corromper o banco (`PRAGMA integrity_check`).

## Estrutura de arquivos

```
db/
  connection.py       # abre conexão (PRAGMAs) + roda migrations pendentes
  queries.py           # operações de escrita/leitura (get_or_create, dedupe, histórico)
  migrations/
    0001_init.sql       # schema inicial
tests/
  test_db.py            # pytest: inserção, dedupe, histórico, concorrência, dados malformados
data/                    # banco SQLite local (gitignored)

fetch/
  google_news.py         # busca via Google News RSS (sem chave)
  portal_feeds.py         # feeds fixos (InfoMoney, Money Times, Suno, Investing.com), filtrados por palavra-chave
  yahoo_finance.py         # RSS do Yahoo Finance por ticker, filtrado por tópico
  extractor.py               # resolve redirect + extrai texto/data com trafilatura
  hashing.py                  # content_hash usado no dedupe da Fase 1
run_search.py                 # CLI: empresa + tópico -> busca -> extrai -> grava no banco
tests/
  test_fetch.py               # pytest: parsing, dedupe, extração e pipeline (tudo mockado)
```

### Fontes de notícia

| Fonte | Como busca | Observação |
|---|---|---|
| Google News RSS | palavra-chave livre (empresa + tópico) | a mais flexível, cobre qualquer termo |
| Portais (InfoMoney, Money Times, Suno) | feed fixo, filtrado por palavra-chave no título | não é busca de verdade — só pega o que estiver no feed recente |
| **Investing.com** | feed de categoria (`/rss/news.rss`, `/rss/stock_Stock-Market-News.rss`), filtrado por palavra-chave | ⚠️ não existe API/busca gratuita por empresa no Investing.com — a página de busca é protegida por anti-bot (Cloudflare). Uso os feeds RSS que eles mesmos publicam pra sindicação, no mesmo esquema dos outros portais. Cobertura menor que uma busca dedicada |
| **Yahoo Finance** | RSS por ticker, filtrado por tópico no título | precisa de `ticker` (é pulado se a empresa não tiver um). Tickers da B3 (ex: PETR4) recebem sufixo `.SA` automaticamente — ajustável via `--yahoo-market-suffix` |

## Rodando os testes

```bash
pip install -r requirements.txt
python3 -m pytest tests/ -v          # não bate rede real (marker "network" fica de fora)
python3 -m pytest tests/ -m network  # só o smoke test contra o Google News de verdade
```

## Rodando uma busca (Fase 2)

```bash
python3 run_search.py "Petrobras" "resultados" --ticker PETR4
```

⚠️ **Limite descoberto durante a Fase 2**: esta sessão remota (sandbox) só tem
saída de rede liberada pra um allowlist de hosts de desenvolvimento (PyPI,
GitHub, APIs da Anthropic) — `news.google.com` e os feeds de portais retornam
403 no proxy daqui. Não tem alternativa gratuita que resolva isso *dentro
desta sessão*: o código foi escrito e testado com HTTP/trafilatura mockados
(cobrindo parsing, dedupe e falha de extração), mas a validação contra a
internet real precisa ser feita na sua máquina/ambiente, onde a rede não é
restrita. Se algo no formato real do RSS do Google News divergir do que
mockei nos testes, é o primeiro lugar pra olhar.

## Resumo automático (Fase 3)

```
summarize/
  groq_provider.py    # LLM gratuito, sem cartão — fonte primária
  gemini_provider.py   # Google Gemini (AI Studio), fallback gratuito se a Groq falhar
  summarizer.py          # tenta Groq, cai pro Gemini, senão devolve None
tests/
  test_summarize.py       # pytest: providers e orquestração, tudo com HTTP mockado
```

Configure as chaves (nenhuma exige cartão de crédito):

```bash
cp .env.example .env   # preencha GROQ_API_KEY e, opcionalmente, GEMINI_API_KEY
set -a; source .env; set +a
python3 run_search.py "Petrobras" "resultados" --ticker PETR4
```

- **Ordem**: tenta a Groq primeiro; se não tiver chave, estourar rate limit (HTTP 429,
  com retry/backoff respeitando `Retry-After`) ou falhar, cai pro Gemini.
- **Sem nenhuma das duas chaves, ou se ambas falharem**: a notícia é salva do
  mesmo jeito, só com `summary = NULL` — mesmo padrão de degradação graciosa
  da extração de texto (Fase 2). Nunca trava a busca.
- **Cota**: antes de chamar o LLM, `get_existing_summary` (`db/queries.py`)
  confere se aquela notícia (por `url` ou `content_hash`) já foi resumida numa
  busca anterior — evita gastar cota resumindo a mesma matéria de novo.
- ⚠️ Os limites de rate limit do free tier (requisições/minuto, tokens/minuto)
  mudam com frequência em ambos os provedores. Confira o valor atual antes de
  rodar em volume: [Groq](https://console.groq.com/settings/limits) /
  [Gemini](https://ai.google.dev/gemini-api/docs/rate-limits).

## Próximas fases (não iniciadas)

4. Comparação de histórico / detecção de notícia nova (via `get_new_since_last_search`).
5. Layout de saída (terminal ou HTML).

Cada fase só começa após aprovação explícita e com os testes da fase anterior
passando.
