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

## Comparação de histórico / notícia nova (Fase 4)

```
reporting.py    # formata "notícias novas desde a última busca" (texto puro por enquanto)
whats_new.py      # CLI: lê o banco, não busca nada na rede
tests/
  test_reporting.py
  test_whats_new.py
```

A query em si (`get_new_since_last_search`, `db/queries.py`) já existia desde
a Fase 1. `whats_new.py` expõe ela sob demanda, sem gastar busca/cota — lê só
o que já está salvo, sem tocar em rede/RSS/LLM, útil pra conferir de novo sem
refazer a busca.

⚠️ **Ajuste pós-Fase 5**: o relatório que `run_search.py` mostra ao final de
cada busca **não** usa mais essa query — ver "Retrato atual vs. diff" logo
abaixo.

```bash
python3 whats_new.py "Petrobras" "resultados"   # um par específico
python3 whats_new.py --all                       # todos os pares já buscados
```

Diferente das Fases 2 e 3, essa é só lógica de banco — dá pra rodar e validar
de ponta a ponta mesmo sem acesso à rede externa.

## Layout de saída (Fase 5)

```
report_html.py       # gera o HTML (cards por empresa+tópico, CSS embutido)
reports/                # saída gerada (gitignored) — não é fonte, é resultado
tests/
  test_report_html.py
```

Formato escolhido: **relatório HTML**, não terminal — melhor pra folhear várias
notícias de uma vez e guardar/compartilhar depois. Sem framework/JS: HTML+CSS
puro, auto-contido, abre em qualquer navegador direto do arquivo local, com
suporte a modo escuro do sistema.

- `run_search.py` grava `reports/latest_search.html` ao final de cada busca
  (só o par empresa+tópico que acabou de rodar).
- `whats_new.py` grava `reports/whats_new.html` (um par específico ou `--all`).
- Ambos aceitam `--open` pra abrir o relatório no navegador automaticamente.
- Título, fonte e resumo vêm de fora (scraping) — tudo passa por `html.escape`
  antes de virar HTML, pra nenhum site injetar marcação quebrada.
- O terminal continua mostrando só um resumo curto (contagem + caminho do
  arquivo) — o detalhe completo fica no HTML.

## Correções depois do teste real (datas erradas + relatório confuso)

Rodando de verdade, apareceram dois problemas que não tinham como ser pegos
só com dados mockados:

**1. Data de publicação errada.** Páginas sem meta tag de data limpa faziam o
`trafilatura` (via `htmldate`) escanear todo texto solto da página como
último recurso — barra lateral, "notícias relacionadas", rodapé — e pegar
qualquer data ali como se fosse a de publicação. Corrigido em duas frentes:
`fetch/extractor.py` agora chama `extract_metadata(..., extensive=False)`
(mantém meta tags/JSON-LD limpos, corta a busca de último recurso), e
`run_search.py` inverteu a prioridade — a data que já vem estruturada do RSS
(Google News/portais/Yahoo) vale primeiro; a data "adivinhada" do HTML só
entra quando o feed não trouxe nenhuma.

**2. "Retrato atual" em vez de "diff".** O relatório que `run_search.py`
mostrava ao final de cada busca usava `get_new_since_last_search` — ou seja,
só o que mudou desde a última vez. Rodando a busca várias vezes seguidas (em
teste), quase tudo já contava como "visto", sobrando pouca coisa útil. Trocado
por `get_latest_search_news` (`db/queries.py`): mostra **tudo que a busca mais
recente encontrou**, sempre o quadro atual, não a diferença. `whats_new.py`
continua com a semântica de diff (é o que o nome promete).

**3. Filtro de recência.** Nem toda notícia que bate a palavra-chave é atual
— `date_utils.py` (`is_recent` / `filter_recent_items`) descarta do relatório
o que tem data conhecida e claramente antiga (padrão: 45 dias, ajustável via
`--max-age-days`). Notícia com data desconhecida/ilegível não é descartada
(preferimos mostrar incerto a esconder algo relevante).

## Formulário web local (Fase 6)

```
app.py              # Flask: formulário ticker/empresa + tópico -> busca -> relatório
tests/
  test_app.py
```

Em vez de digitar comando no terminal toda vez, um formulário local:

```bash
python3 app.py
```

Abre `http://localhost:5000` (no Codespaces, a porta é encaminhada
automaticamente — aba "Ports"). Digita empresa, ticker (opcional) e tópico,
aperta **Buscar** — roda a busca de verdade (mesmo `run_search.run_search`
das fases anteriores, reaproveitado, não duplicado) e mostra o relatório na
mesma página. Sob demanda: não roda sozinho em background, sempre traz o
que há de mais atual no momento em que você pede.

A página inicial também lista todos os pares empresa+tópico já buscados, com
link direto pro "retrato atual" de cada um (sem precisar buscar de novo).

## Visualizando o banco direto no VS Code

Instala a extensão **"SQLite Viewer"** (gratuita) no VS Code/Codespace,
clica com o botão direito em `data/newsmon.db` no explorador de arquivos, e
abre uma visão de tabela (tipo planilha) com `companies`, `topics`,
`searches`, `news` e `search_results` — sem precisar rodar script nenhum só
pra olhar os dados.

## Cobertura internacional + qualidade do filtro

Depois de mais um teste real, dois problemas novos: "não tem mídia
internacional (Bloomberg, Investing.com etc)" e "o filtro ainda está muito
ruim" (notícia sem nenhuma relação com a empresa aparecendo no relatório).

**Cobertura internacional — `fetch/google_news.py`**
- ⚠️ **Bloomberg não tem API pública nem RSS gratuito pra busca por
  empresa** — não existe caminho gratuito pra puxar Bloomberg diretamente,
  isso não é algo que dá pra resolver sem pagar.
- O proxy gratuito mais confiável: `fetch_google_news_multi_locale` agora
  consulta o Google News **duas vezes** — uma em pt-BR (como sempre foi) e
  outra em en-US — e junta o resultado, deduplicado por link e por título
  normalizado. A busca em inglês é o que traz Bloomberg/Reuters/MarketWatch/
  WSJ *quando o Google já indexou* essas fontes pra empresa buscada. Uma
  região fora do ar não derruba a outra.

**Filtro AND (empresa E tópico) — `fetch/portal_feeds.py`**
- Antes: `matches_keywords` aceitava um item se ele batesse **ou** na
  empresa, **ou** no ticker, **ou** no tópico — uma notícia só sobre o
  tópico (ex: "resultados"), sem citar a empresa, passava. Era a causa
  principal do "filtro muito ruim".
- Agora: citar a empresa (nome ou ticker) no título é **obrigatório**;
  citar o tópico também é obrigatório quando um tópico foi informado.

**Relevância deixou de ser sempre `NULL` — `relevance.py` (novo) + `run_search.py` + `db/queries.py`**
- A coluna `search_results.relevance` existia desde a Fase 1 mas nunca era
  preenchida. `compute_relevance` calcula uma pontuação simples e explicável
  (citar empresa/ticker no título pesa mais que citar o tópico, que pesa mais
  que só ter uma data conhecida) — nunca é usada pra descartar notícia, só
  pra ordenar.
- `get_latest_search_news` e `get_new_since_last_search` (`db/queries.py`)
  agora ordenam por relevância primeiro, depois por data — antes era só
  cronológico.

**Não gastar resumo (LLM) com notícia já velha — `run_search.py`**
- O filtro de idade (`is_recent`/`--max-age-days`) agora também roda **antes**
  da extração/resumo, não só na hora de montar o relatório — uma notícia
  claramente velha é salva com os metadados do RSS, mas não gasta tempo nem
  cota de Groq/Gemini sendo resumida à toa. O filtro no relatório continua
  existindo (cobre o caso de ver uma notícia salva há semanas).
- Stats novo: `skipped_stale`, mostrado na mensagem final do terminal.

## Próximas fases

Nenhuma fase planejada restante — a base (Fase 1), busca (Fase 2), resumo
(Fase 3), comparação de histórico (Fase 4) e layout (Fase 5) foram
implementadas, testadas, e ajustadas depois de dois testes reais (datas +
"retrato atual" + formulário web; cobertura internacional + filtro +
relevância, acima). Próximos ajustes a partir daqui são sob demanda.
