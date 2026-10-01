# 0003 — Projetos e pastas: o Ingestify como portal de ingestão

| | |
|---|---|
| **Status** | Rascunho (v3 final — passou no portão adversarial; aguarda aprovação do dono) |
| **Autor** | Geda Valentim |
| **Criada em** | 2026-10-01 |
| **Atualizada em** | 2026-10-01 |
| **Relacionadas** | — (convive com as tags de `74fda74`) |
| **Substituída por** | — |

---

## 1. Problema

Hoje a única forma de organizar jobs é a **tag** (`job_tags`, `shared/tags.py`): rótulo
livre, minúsculo, 0..N por job, sem existência própria e sem hierarquia. Tags servem para
*filtrar*, mas não respondem à pergunta de quem abre o Ingestify: **"onde está o material do
cliente X?"**.

- `GET /jobs` é uma lista única por data que mistura as centenas de áudios/dia do cliente
  automático (`POST /transcribe`, API key, `output_format=json`, `purge_source=true`) com os
  documentos enviados à mão. Achar algo exige lembrar a tag certa.
- Tag não existe antes do primeiro upload, não tem contagem por pasta, e um job pode não ter
  nenhuma — "todo arquivo tem um lugar" não é garantido.

O dono pediu: *usuários criam **projetos** e, dentro deles, **subpastas**. **Projeto é
obrigatório**, subpasta não. O usuário indica isso no upload, podendo ser só texto, com
get-or-add de projeto e pasta. O Ingestify vai virar um portal de ingestão.*

## 2. Objetivo

Todo job MAIN pertence a exatamente um **projeto** do seu dono — escolhido **explicitamente**
no upload ou pela API key que fez o upload — e opcionalmente a uma **pasta** desse projeto;
o upload aceita ambos como texto (get-or-add); a interface filtra por projeto/pasta; e o
cliente de áudio de produção continua funcionando **sem mudar uma linha**, porque a migração
vincula a key dele a um projeto.

### Fora de escopo (desta spec inteira)

- **Compartilhamento / times / tenant.** Projeto é de um usuário (D1).
- **Pastas aninhadas.** Um nível; `/` reservado no nome da pasta (D2).
- **Projeto/pasta no caminho do MinIO** (§ 4.7).
- **Projeto implícito** ("Inbox" automático para quem não diz o projeto). Ver § 4.4 e
  Revisão 1 #1: isso seria "opcional com default", não "obrigatório".
- **Renomear a chave de um projeto** (renomear de verdade). Só rename cosmético (§ 4.1).
- **Converter tags em projetos.** Tags ficam como estão (D4).
- Jobs filhos (SPLIT/PAGE/MERGE) e crawler: só o MAIN tem projeto; filhos herdam pelo pai.
- Ideias futuras listadas em § 10 (defaults por projeto, keys restritas a projeto, aliases,
  export, webhooks…).

## 3. Critérios de aceitação (Fase 1)

**Obrigatoriedade**
- [ ] Dado um upload por JWT sem `project`/`project_id`, então `422` com mensagem em
      português e exemplo `curl` (§ 4.4). Nenhum projeto é criado, nenhum arquivo fica no disco.
- [ ] Dado um upload por API key **vinculada** a um projeto e sem `project`, então o job vai
      ao projeto da key. Com `project` explícito, o explícito vence.
- [ ] Dado um upload por API key **não vinculada** e sem `project`, então `422`.
- [ ] **Regressão do cliente de produção**: depois da migração, o request exato de hoje
      (`file`, `output_format=json`, `purge_source=true`, `X-API-Key`) devolve `200` com os
      mesmos campos e valores de hoje (+ `project`/`folder` aditivos), e o job cai no projeto
      ao qual a migração vinculou a key — o mesmo projeto dos jobs antigos, logo a
      deduplicação continua achando os arquivos já processados.
- [ ] Dado JWT **e** `X-API-Key` no mesmo request, então vale o JWT (precedência de
      `get_current_user`) e o vínculo da key **não** é aplicado.

**Get-or-add e normalização**
- [ ] `project="Cliente X"` sem equivalente → cria "Cliente X" e responde `created: true`.
- [ ] Projeto "Reunião Semanal" existente e `project="  reuniao   SEMANAL "` → mesmo projeto.
- [ ] 8 uploads concorrentes com grafias equivalentes de um nome novo → 1 projeto (idem pasta).
- [ ] `folder` sem projeto resolvido → `422`. `folder` com `/` → `422`.
- [ ] Nome > 100 caracteres, chave normalizada > 200, controle (`\x00-\x1f`) → `422`.
- [ ] `ハード` e `ハート` são projetos **diferentes**; `한국` não expande para jamo; `й` ≠ `и`
      e `ё` ≠ `е` (acentos só são ignorados sobre letras latinas).
- [ ] `project_id`/`folder_id` de outro usuário ou inexistente → `404` com a mesma mensagem.
- [ ] `folder_id` que não pertence ao projeto resolvido → `422`.

**Dados / deploy**
- [ ] O script de migração é idempotente (roda 2× sem erro), não usa `ALGORITHM=COPY` em
      `jobs` e desiste (sem travar o banco) se não obtiver o metadata lock em 5 s após N tentativas.
- [ ] Com o MariaDB acessível, a tabela `jobs` existente e `jobs.project_id` ausente, o
      processo da API **termina** (`SystemExit(1)`) qualquer que seja `ENVIRONMENT`, antes de
      `create_all`.
- [ ] Com um banco **vazio** (sem tabela `jobs`), a API sobe: `create_all` cria tudo (colunas
      e índice já declarados nos modelos) e os marcadores `0003_backfill`/`0003_tail` são
      gravados com T1 = T2 = agora.
- [ ] O backfill de cauda roda **uma vez** (marcador em `app_migrations`, inserido na mesma
      transação da cauda), só sobre linhas com `created_at <= T2` e `project_id IS NULL`; reiniciar a API não revincula keys nem recria Inbox.
- [ ] Depois do primeiro boot da versão nova, não existe job MAIN com `project_id IS NULL`
      criado antes do marcador; se aparecer algum criado depois, é logado como ERROR (não corrigido).
- [ ] Um banco novo criado por `create_all` (dev/CI) tem o mesmo índice e charset que o
      produzido pelo script.

**Navegação**
- [ ] `GET /projects?include=folders` devolve projetos + pastas + contagens.
- [ ] `GET /jobs?project_id=P&folder_id=F|root` filtra; `folder_id` alheio → `404`.
- [ ] Itens de `GET /jobs` e `GET /jobs/{id}` trazem `project` e `folder`.
- [ ] Tags continuam funcionando sem mudança e combinam com os filtros novos.
- [ ] UI: o upload não envia sem projeto, nunca pré-seleciona um projeto que o usuário não
      escolheu (só URL ou último usado por ele); a barra lateral filtra `/jobs`; a tela de API
      keys mostra e altera o projeto vinculado.

## 4. Solução proposta

### 4.1 Domínio

```
User 1───* Project 1───* Folder            (um nível)
             │ 1            │ 0..1
             └─────* Job *──┘               (só MAIN; vínculos sem FK no banco — § 4.2)
APIKey *──0..1 Project   (project_id: projeto vinculado; usado quando o request não diz)
```

- **Por usuário** (D1): `Job.user_id` é a única fronteira de autorização hoje
  (`api/deps.py`); não há tenant no modelo.
- **Pasta de um nível** (D2): get-or-add com chave única, contagem num `GROUP BY`, UI sem
  árvore. `/` proibido no nome da pasta para que caminhos possam existir no futuro.
- **Não existe projeto padrão.** Existe o projeto **"Inbox"** criado pela migração para
  guardar os jobs legados de cada usuário e ao qual as keys existentes são vinculadas — mas
  é um projeto comum, sem flag, sem comportamento especial (Revisão 1 #1, #13).

#### Nome de exibição × chave

`backend/shared/projects.py` (no estilo de `shared/tags.py`):

```python
MAX_NAME_LENGTH = 100        # exibição, em caracteres
MAX_KEY_LENGTH = 200         # chave, depois de casefold (ß→ss pode crescer)

def clean_display_name(raw: str) -> str:
    # NFC, trim, espaços internos colapsados; caixa e acentos preservados
_COMBINING_LO, _COMBINING_HI = "\u0300", "\u036f"     # Combining Diacritical Marks

def _is_latin_base(c: str) -> bool:
    o = ord(c)
    return 0x0041 <= o <= 0x024F or 0x1E00 <= o <= 0x1EFF   # Basic Latin..Latin Ext-B, Latin Ext Additional

def name_key(raw: str) -> str:
    s = unicodedata.normalize("NFD", clean_display_name(raw))
    out, base = [], ""
    for c in s:
        if _COMBINING_LO <= c <= _COMBINING_HI and _is_latin_base(base):
            continue                                   # acento sobre letra latina: ignora
        out.append(c)
        if not unicodedata.combining(c):
            base = c
    return unicodedata.normalize("NFC", "".join(out)).casefold()
```

Normalização **conservadora** (Revisões 1 #6 e 2 N8): remove marcas do bloco *Combining
Diacritical Marks* (U+0300–U+036F) **somente quando a letra-base é latina** — "Reunião" =
"reuniao", "Ação" = "acao", "Tiếng" = "tieng" — e recompõe em NFC. Assim: cirílico mantém
`й` ≠ `и` e `ё` ≠ `е` (U+0306/U+0308 sobre base cirílica não são removidos); dakuten japonês
(U+3099/309A) não é removido (`ハード` ≠ `ハート`); Hangul volta composto (não triplica); e não
há compatibilidade NFKD (`²` ≠ `2`, `Ⅳ` ≠ `iv`, ligaduras intactas). No código os limites
aparecem como escapes (`"̀"`), nunca como caracteres literais.
`casefold` (e não `lower`) é Python puro; **a UI não espelha a regra** — pergunta ao backend
(`GET /projects/resolve` e `GET /projects/{id}/folders/resolve`, § 4.6).

Validação (`422`, mensagens em português): vazio após limpeza; > 100 caracteres de exibição;
chave > 200 caracteres; caracteres de controle; `/` em nome de pasta. Campo enviado vazio
(`-F project=`) é tratado como **ausente**.

**A chave é imutável** (Revisão 1 #8). `PATCH` de nome (fase 2) só aceita um novo nome com a
**mesma chave** (corrigir caixa/acento/espaço: "cliente x" → "Cliente X"). Mudar a chave
quebraria em silêncio clientes automáticos que mandam o nome antigo por texto — eles
criariam um projeto novo no próximo upload. Rename de verdade exige aliases (§ 10).

#### Limites (configuráveis em `config.py`)

| Limite | Padrão | Ao estourar |
|---|---|---|
| `MAX_PROJECTS_PER_USER` | 200 | `422 "Limite de 200 projetos atingido"` |
| `MAX_FOLDERS_PER_PROJECT` | 500 | `422` |

O get-or-add por texto transforma typo de script em projeto novo; o limite é teto para bug
de cliente (ex.: mandar o nome do arquivo como projeto), não cota.

### 4.2 Dados

```python
class Project(Base):
    __tablename__ = "projects"
    id          = Column(String(36), primary_key=True, default=generate_uuid)
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name        = Column(String(100), nullable=False)
    name_key    = Column(KEY_TYPE, nullable=False)
    description = Column(Text)
    archived_at = Column(DateTime)                 # fase 2; coluna já nasce
    created_at, updated_at
    __table_args__ = (
        UniqueConstraint("user_id", "name_key", name="uq_projects_user_key"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_general_ci"},
    )

class Folder(Base):
    __tablename__ = "folders"
    id, project_id (FK projects CASCADE), user_id (FK users CASCADE, denormalizado p/ autorização),
    name String(100), name_key KEY_TYPE, created_at, updated_at
    __table_args__ = (
        UniqueConstraint("project_id", "name_key", name="uq_folders_project_key"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_general_ci"},
    )

class AppMigration(Base):          # marcadores de migrações de dados one-shot (§ 4.3)
    __tablename__ = "app_migrations"
    name       = Column(String(64), primary_key=True)    # ex.: "0003_backfill", "0003_tail"
    applied_at = Column(DateTime, nullable=False)        # UTC, relógio da aplicação

# KEY_TYPE: binário no MariaDB, portátil nos testes. Com mysql+pymysql o nome do dialeto
# do SQLAlchemy é "mysql" mesmo contra MariaDB, então a variante "mysql" é a que se aplica.
KEY_TYPE = String(200).with_variant(
    mysql.VARCHAR(200, charset="utf8mb4", collation="utf8mb4_bin"), "mysql")

# Job — colunas novas, SEM ForeignKey (integridade garantida pela aplicação)
project_id = Column(String(36), nullable=True)
folder_id  = Column(String(36), nullable=True)
# Job.__table_args__ ganha o índice, para create_all (dev/CI) produzir o mesmo schema do script:
Index("ix_jobs_user_type_project_folder",
      "user_id", "job_type", "project_id", "folder_id", "status", "created_at")

# APIKey — coluna nova, SEM ForeignKey
project_id = Column(String(36), nullable=True)
```

- **Banco de produção é MariaDB 10.11** (processo `mariadbd` no host, acessado por
  `host.docker.internal:3306`), não MySQL. Tudo nesta spec usa sintaxe/semântica do MariaDB
  10.11; a collation padrão do servidor é `utf8mb4_general_ci` (`utf8mb4_0900_ai_ci` não existe
  lá). As tabelas novas declaram charset/collation explícitos para não herdar o default do
  schema, seja qual for.
- **Collation binária na chave** (Revisão 1 #5b): com `utf8mb4_general_ci` o índice único
  consideraria iguais strings que `name_key` considera diferentes (a general_ci ignora caixa e
  vários acentos com regras próprias — ex.: iguala `й`/`и`), o INSERT colidiria e a releitura
  por igualdade Python não acharia a linha. Com `utf8mb4_bin` o banco compara exatamente o que
  o Python calculou. O nome de exibição usa `utf8mb4_general_ci` (ordenação natural na UI).
- **Índice declarado no modelo** (Revisão 2 N5): o script cria o mesmo índice, com o mesmo
  nome, só se `information_schema.statistics` não o tiver — um banco novo (create_all) e o de
  produção (script) convergem.
- **Sem FK em `jobs` e `api_keys`** (Revisão 1 #2, #7): `ADD FOREIGN KEY` em `jobs` com
  `foreign_key_checks=1` reconstrói a tabela (`ALGORITHM=COPY`, escrita bloqueada) — inaceitável
  com o cliente de produção enviando o dia todo — e, criada por `create_all`/`ALTER` em
  caminhos diferentes, a FK existiria em um ambiente e não no outro. Toda semântica de remoção
  é feita por **UPDATEs explícitos** na aplicação (§ 4.5); nada depende de `ON DELETE` em
  `jobs`. FKs ficam só nas tabelas novas (`projects`, `folders`), criadas inteiras de uma vez.
- **`jobs.project_id` é NULLable no banco** porque a coluna é adicionada com o código antigo
  ainda no ar (§ 4.3), que insere jobs sem projeto. O invariante "MAIN tem projeto" é da
  aplicação, estabelecido pelo backfill one-shot (§ 4.3, passos 3 e 5b) e vigiado no boot (5c).
- **Sem `is_default`** (Revisão 1 #13): não há projeto padrão a proteger.
- **Índice** `ix_jobs_user_type_project_folder (user_id, job_type, project_id, folder_id,
  status, created_at)`: cobre a agregação de contagens (`WHERE user_id AND job_type GROUP BY
  project_id, folder_id, status` + `MAX(created_at)`) e o filtro de `GET /jobs` ordenado por
  data dentro de um projeto/pasta. `api_keys` dispensa índice (dezenas de linhas).

### 4.3 Migração e deploy — DDL primeiro

Restrições reais do ambiente (Revisões 1 #2/#3 e 2 N1/N3/N4):

- O banco é **MariaDB 10.11** no host. `ALTER TABLE ... ADD COLUMN ... ALGORITHM=INSTANT`
  funciona (≥ 10.3.2 no fim da tabela; ≥ 10.4 em qualquer posição) e o MariaDB aceita
  `ALTER TABLE ... WAIT n` para limitar a espera por lock.
- `init_db()` roda `create_all()` + `_add_missing_columns()` no boot da **API**
  (`shared/database.py`), e `api/main.py` **engole** qualquer exceção de `init_db()` a menos
  que `ENVIRONMENT == "production"` — e a produção roda com `ENVIRONMENT=development`. Uma
  guarda colocada dentro de `init_db` não pararia nada.
- O Alembic de produção **não está stampado** (`docs/CODE_REVIEW.md` § 11.2): `alembic
  upgrade head` tentaria reaplicar `e399267560a7` (`is_admin` duplicada) e `7c2f4a1d9b30`
  (`job_tags` já existe) e falharia.
- `backend/shared` é **bind-mounted** (`docker-compose.yml`) na API e nos workers, inclusive
  `worker-audio-1..4`, que usam o ORM e **não** chamam `init_db`. Qualquer restart de worker
  (inclusive OOM-kill) carrega o `models.py` do disco: se ele declarar `Job.project_id` e a
  coluna não existir, todo `SELECT` em `jobs` falha e as transcrições param.
- Mesmo `INSTANT`/`INPLACE` pegam um **metadata lock exclusivo** breve em `jobs`. Se houver
  uma transação aberta tocando `jobs` (sessão de worker durante uma transcrição longa, sessão
  ociosa do pool com transação implícita aberta), o `ALTER` espera — e **todo query novo em
  `jobs` enfileira atrás dele**: API e workers congelam enquanto ele espera.

Por isso: **um único caminho em produção** — `scripts/migrate_0003_projects.py`, rodado
**diretamente** (não via Alembic). Cada passo consulta `information_schema` antes de agir, então
é idempotente. Também há uma revisão Alembic (`down_revision = 7c2f4a1d9b30`) que chama as mesmas
funções, para ambientes de dev que usam Alembic convergirem; **em produção `alembic upgrade` é
proibido** até alguém rodar `alembic stamp 7c2f4a1d9b30` conscientemente (fora desta spec).
Nada entra em `_ADDED_COLUMNS`; `create_all` encontra as tabelas já criadas e não faz nada.

**Runbook** (executado pelo dono; o script imprime cada passo e para no primeiro FAIL)

```
0. Pré-voo
   a) SELECT VERSION();                       → espera 10.11.x (MariaDB); outro valor = parar
   b) backup: mariadb-dump --single-transaction users api_keys jobs
   c) ⚠ AÇÃO DO DONO — NÃO VERIFICADO POR NINGUÉM ATÉ AGORA. Chamadores sem API key
      (Revisão 2 N7): conferir nos logs da API quem chama
      /upload|/convert|/transcribe|/images sem X-API-Key além do frontend; em especial
      `meumentor-api` (WHISPER_API_URL=http://ingestify-api:8000 com WHISPER_API_KEY vazio).
      Sem credencial ele já recebe 401 hoje (nada muda); se usar JWT, decidir antes:
      criar key vinculada para ele ou preencher UPLOAD_FALLBACK_PROJECT no deploy.
   d) janela: a hora mais quieta do cliente de áudio (medida nos logs de acesso de /transcribe
      dos últimos 7 dias; o script imprime o histograma por hora).
   e) transações longas: SELECT trx_id, trx_started, trx_mysql_thread_id
        FROM information_schema.innodb_trx WHERE trx_started < NOW() - INTERVAL 30 SECOND;
      + SHOW PROCESSLIST. Havendo alguma, esperar ou pausar as filas (ver passo 1).
1. DDL — código antigo no ar; nenhuma mudança é lida por ele. Sessão com
   SET SESSION lock_wait_timeout = 5; cada ALTER com WAIT 5:
     CREATE TABLE IF NOT EXISTS app_migrations (...), projects (...), folders (...)
       ... ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
     ALTER TABLE jobs WAIT 5 ADD COLUMN project_id VARCHAR(36) NULL,
                             ADD COLUMN folder_id  VARCHAR(36) NULL, ALGORITHM=INSTANT
     ALTER TABLE api_keys WAIT 5 ADD COLUMN project_id VARCHAR(36) NULL, ALGORITHM=INSTANT
     CREATE INDEX ix_jobs_user_type_project_folder ON jobs (...) WAIT 5
       ALGORITHM=INPLACE LOCK=NONE
   Timeout de lock → até 5 tentativas com 30 s de intervalo; esgotou → aborta limpo (nada
   pela metade: cada ALTER é atômico) e imprime as transações que estavam segurando o lock.
   Plano B se as sessões de worker forem longas: `docker compose stop worker worker-audio`
   (a fila Celery segura as tarefas), DDL, `start`. O implementador mede antes, em staging,
   quanto tempo uma task de transcrição mantém uma transação aberta em `jobs` (tasks.py usa
   SessionLocal em torno do processamento) e registra o resultado no PR.
2. Pré-voo de código: SHOW COLUMNS FROM jobs LIKE 'project_id' (e folder_id,
   api_keys.project_id) + SHOW INDEX ... → OK/FAIL. Só seguir com OK.
3. Backfill one-shot (código antigo ainda no ar), se `app_migrations` não tem "0003_backfill":
     T1 = utcnow()
     para cada user_id distinto com jobs MAIN ou api_keys:
       select-or-insert projeto name="Inbox", name_key="inbox"   (IntegrityError → reler)
     UPDATE jobs SET project_id=:inbox
       WHERE id IN (<lote de ≤1000 ids por PK: project_id IS NULL, job_type='MAIN',
                    user_id=:u, created_at <= T1>)          -- autocommit, 1 COMMIT por lote
     UPDATE api_keys SET project_id=:inbox
       WHERE user_id=:u AND project_id IS NULL AND created_at <= T1
     INSERT app_migrations ("0003_backfill", T1)
   Imprime a lista das keys vinculadas ao Inbox (usuário, nome da key, last_used_at) para o
   dono revincular conscientemente as que merecem projeto próprio (Revisão 2 N9).
4. Deploy do código novo (api + workers + frontend).
5. Boot da API (api/main.py) — FORA do try que engole erros de init_db e ANTES dele:
     a) guarda de schema, em três casos:
        - banco inacessível → comportamento de hoje (log e segue; requests falham com 503);
        - banco **vazio** (tabela `jobs` não existe: dev, CI, instalação nova) → pula a
          guarda, deixa `create_all` criar tudo (os modelos já declaram as colunas e o
          índice) e, logo depois, grava `0003_backfill` e `0003_tail` com T1 = T2 = agora —
          não há legado a migrar;
        - `jobs` existe → checa as três colunas, `app_migrations` e o marcador
          `0003_backfill` (só esse: `0003_tail` é responsabilidade do passo b). Algo
          faltando → log CRITICAL com o comando do passo 1/3 e `raise SystemExit(1)`,
          independente de ENVIRONMENT.
     b) cauda one-shot, **numa única transação**: INSERT ("0003_tail", T2=utcnow()) e, na
        mesma transação, jobs MAIN com `project_id IS NULL AND created_at <= T2` → Inbox do
        dono; api_keys com `project_id IS NULL AND created_at <= T2` → Inbox do dono; COMMIT.
        Sem limite inferior T1: `created_at` é preenchido em Python antes do INSERT ser
        commitado (routes.py), então um job "atrasado" do código antigo pode ter
        created_at < T1 e ter escapado do passo 3. Antes do código novo ninguém consegue
        deixar uma key sem projeto de propósito, então todas as NULL até T2 são legado.
        Concorrência (só em dev com `--workers N`): o segundo processo bloqueia no lock da
        PK do marcador, recebe IntegrityError quando o primeiro commita e pula. Select-or-
        insert do Inbox só para usuários com alguma dessas linhas. Feito uma vez, nunca mais.
     c) em todo boot, só leitura: COUNT de jobs MAIN com project_id NULL e created_at > T2 →
        se > 0, log ERROR "invariante violado: N jobs sem projeto" (bug a investigar). Nunca
        corrige: uma key deixada sem projeto de propósito (POST sem project / PATCH null) e
        um Inbox apagado continuam assim — o boot não recria default pela porta dos fundos.
```

Os workers não precisam de guarda própria: pelo runbook as colunas existem antes de o
`models.py` novo chegar ao disco (passo 2).

**Rollback**: código antigo ignora colunas e tabelas novas; não é preciso desfazer DDL.
`scripts/migrate_0003_projects.py --downgrade` remove índice, colunas, tabelas e marcadores
(perde a organização, não os jobs).

**Por que "Inbox" e não um projeto por key** (decisão pedida na Revisão 1): os jobs não
registram qual key os criou, então um projeto por key não teria como receber os jobs legados
— e a deduplicação (escopada por projeto, § 4.4) da key do cliente de produção deixaria de
ver os arquivos que ele já mandou, reprocessando-os na GPU. Com todas as keys e todos os jobs
legados de um usuário no mesmo "Inbox", o comportamento observável de hoje é preservado. O
dono depois cria "Transcrições automáticas", **move** os jobs (fase 2) e revincula a key.

### 4.4 Contrato de upload

Endpoints (7): `POST /upload`, `POST /convert`, `POST /transcribe`,
`POST /images/describe`, `POST /images/describe/upload`, `POST /images/ocr`,
`POST /images/ocr/upload`. Os de form recebem campos de form; os JSON, campos no corpo. Um só
helper (`api/projects_api.py::parse_location_or_422` + `resolve_upload_location`), como `tags`.

| Campo | Tipo | Significado |
|---|---|---|
| `project` | texto | Nome do projeto. **Get-or-add.** |
| `project_id` | uuid | Projeto existente. Nunca cria. |
| `folder` | texto | Nome da pasta no projeto resolvido. **Get-or-add.** |
| `folder_id` | uuid | Pasta existente. Nunca cria. Deve pertencer ao projeto resolvido. |

**Resolução do projeto**, em ordem:

```
1. project ou project_id no request                → ele   (ambos juntos → 422)
2. autenticado por API key (sem JWT) e key.project_id definido
   e o projeto existe e é do mesmo usuário         → ele
3. senão                                           → 422
```

Mensagem do `422` (texto exato no teste):

```
Informe o projeto do upload: campo 'project' (nome; é criado se não existir) ou
'project_id'. Exemplo: curl -H "X-API-Key: ..." -F "file=@arquivo.mp3" -F "project=Aulas" .../transcribe
Para não precisar enviar o projeto, vincule a API key a um projeto em /api-keys.
```

Sem `warnings`, sem header `Warning` (Revisão 1 #1): ou o projeto foi dito (pelo request ou
pela key), ou é erro.

**Válvula de emergência** `UPLOAD_FALLBACK_PROJECT` (env, **vazio por padrão**): se
preenchido, um upload sem projeto resolvido faz get-or-add desse nome em vez de `422` e loga
WARNING com `user_id` e o caminho. Existe só para o caso "um cliente que ninguém conhecia
quebrou no deploy"; liga-se sem rollback de código. Vazio = projeto obrigatório.

**Ordem no handler** (para não criar lixo nem gravar disco à toa):

```
1. parse_tags_or_422(tags); parse_location_or_422(...)    # forma: tamanhos, '/', exclusividade
2. pré-resolução sem escrita: há projeto no request ou na key? senão 422 — ANTES do stream
3. _stream_upload_to_file(...)                            # como hoje
4. location = resolve_upload_location(db, user, request.state.api_key, parsed)   # get-or-add
5. dedup (escopada por projeto) → 6. Job(..., project_id, folder_id)
```

**Get-or-add sem corrida** (`shared/projects.py`):

```python
def get_or_create_project(db, user_id, raw) -> Project:
    if db.new or db.dirty:                        # verificação explícita (assert some com -O)
        raise RuntimeError("get_or_create_project exige sessão sem escrita pendente")
    key = name_key(raw)
    try:
        for attempt in range(2):
            if p := _find(db, user_id, key):
                return p
            _enforce_limit(db, user_id)
            try:
                db.add(Project(user_id=user_id, name=clean_display_name(raw), name_key=key))
                db.commit()
                return _find(db, user_id, key)
            except IntegrityError:
                db.rollback()   # encerra a transação: a próxima leitura abre snapshot novo
    except (OperationalError, InterfaceError) as e:      # banco fora, conexão caída, lock timeout
        db.rollback()
        logger.error(f"get_or_create_project: {e}")
        raise HTTPException(503, "Banco indisponível; tente de novo em instantes")
    raise HTTPException(503, "Não foi possível criar o projeto agora; tente de novo")
```

Por que `rollback()` completo: no InnoDB (MariaDB 10.11) em `REPEATABLE READ`, reler *na mesma
transação* depois do `IntegrityError` usa o snapshot antigo e não vê a linha do outro request.
A segunda falha seguida só acontece se a chave colide sem ser igual (não deveria, com
`utf8mb4_bin`) — vira `503` limitado, nunca `None` nem loop. Mesmo padrão para pasta.

**Projetos órfãos** (Revisão 1 #11): o get-or-add commita antes do INSERT do job; se o
INSERT falhar (hoje engolido em `routes.py`, "Redis is primary"), sobra um projeto vazio.
Aceito: aparece com contagem 0 e é apagável (fase 2). Sem limpeza automática — apagar
projeto que o usuário criou de propósito antes de usar seria pior.

**Banco indisponível** (Revisão 2 N6): com projeto obrigatório a resolução precisa do
MariaDB; qualquer erro de banco no get-or-add (inclusive `OperationalError`) → `503`. Na
prática não é regressão: com o banco totalmente fora, o upload **já** falhava antes — a
autenticação por API key faz `commit` de `last_used_at` (`shared/auth.py`) e o SELECT de
deduplicação não é protegido (`routes.py`) — só que com `500`; agora é um `503` explícito.
O que **continua igual**: depois de resolvido o projeto, uma falha no INSERT do job segue
engolida como hoje ("Redis is primary"), então pode existir job no Redis/Celery sem linha no
MariaDB (e com um projeto recém-criado vazio — ver "Projetos órfãos"). Corrigir isso é outra
spec.

**Deduplicação escopada por projeto**: o filtro de duplicata ganha
`Job.project_id == location.project_id`. Mesmo arquivo em "Cliente A" e "Cliente B" = dois
jobs (dois processamentos). No mesmo projeto: devolve o existente, **não move** de pasta
(D5), soma tags como hoje. Aproveitando que o trecho é tocado, `/convert` ganha o
`Job.status != FAILED` que `/upload` e `/transcribe` já têm (Revisão 1 #14). Quando não há
duplicata no projeto mas há em outro projeto do usuário, a `message` do job novo diz:
`"Arquivo já processado no projeto 'X' (job …); processando de novo em 'Y'"` — é como o
efeito de revincular uma key aparece para quem chama.

**Resposta** (`JobCreatedResponse`, campos novos aditivos):

```jsonc
{
  "job_id": "…", "status": "queued", "created_at": "…", "message": "…",
  "project": { "id": "…", "name": "Cliente X", "created": false, "source": "request" },  // ou "api_key"
  "folder":  { "id": "…", "name": "Contratos 2026", "created": true }                    // ou null
}
```

**Erros**: `422` (forma, nome e ID juntos, `folder` sem projeto, sem projeto resolvido,
limite, pasta de outro projeto, projeto arquivado — fase 2), `404 Projeto não encontrado` /
`404 Pasta não encontrada` (ID inexistente ou alheio, mesma mensagem), `503` (banco).

### 4.5 API keys

- `get_current_user` passa a receber `request: Request` e grava
  `request.state.api_key = api_key_obj` **só** no caminho de API key; no caminho JWT grava
  `None`. Como o JWT é verificado primeiro (`shared/auth.py`), um request com os dois
  cabeçalhos é tratado como JWT e **não** usa o vínculo da key (Revisão 1 #15) — documentado
  em `/docs`.
- `GET /api-keys/` devolve `project: {id, name} | null` por key.
- `POST /api-keys/` aceita `project` (texto, get-or-add) ou `project_id`, opcionais.
- `PATCH /api-keys/{id}` `{project_id: uuid | null}` — novo; valida posse (`404`).
- No uso, o vínculo é revalidado (`project.user_id == key.user_id`, projeto existe); se não
  vale, é como se a key não tivesse vínculo (→ `422` explicando que o projeto da key sumiu).
- Apagar/arquivar um projeto vinculado a keys → `409 "Projeto usado pelas API keys: <nomes>"`
  (fase 2, junto com delete/archive).

### 4.6 API de leitura (Fase 1) e de gestão (Fase 2)

Novo router `backend/api/projects_api.py`. Tudo filtrado por `user_id` vindo do MariaDB;
recurso alheio = `404` (padrão de `api/deps.py`, que ganha `get_owned_project` e
`get_owned_folder`).

**Fase 1**

| Método | Rota | Descrição |
|---|---|---|
| GET | `/projects` | Lista + contagens; `?include=folders` |
| GET | `/projects/resolve?name=…` | Diz se o texto casa com um projeto existente, sem criar |
| GET | `/projects/{id}/folders/resolve?name=…` | Idem para pasta dentro do projeto (posse do projeto checada → `404`) |
| GET | `/jobs` | + `project_id`, `folder_id` (uuid ou `root`), ambos validados por posse |
| GET | `/jobs/{id}` | + `project`, `folder` |
| PATCH | `/api-keys/{id}` | vínculo de projeto (§ 4.5) |

```jsonc
// GET /projects?include=folders
{ "projects": [ {
    "id": "…", "name": "Cliente X", "description": null, "archived": false,
    "job_count": 412, "root_job_count": 12, "failed_count": 3, "active_count": 1,
    "last_job_at": "2026-10-01T10:22:00Z",
    "api_keys": [ { "id": "…", "name": "cliente-audio" } ],
    "folders": [ { "id": "…", "name": "Áudios", "job_count": 400 } ] } ],
  "limits": { "max_projects": 200, "max_folders_per_project": 500 } }

// GET /projects/resolve?name=reuniao
{ "valid": true, "match": { "id": "…", "name": "Reunião" } }        // ou "match": null
{ "valid": false, "error": "Nome muito longo (máximo 100 caracteres)" }

// GET /projects/{id}/folders/resolve?name=audios
{ "valid": true, "match": { "id": "…", "name": "Áudios" } }
```

Contagens: um `SELECT project_id, folder_id, status, COUNT(*), MAX(created_at) FROM jobs
WHERE user_id=:u AND job_type='MAIN' GROUP BY 1,2,3`, coberto pelo índice de § 4.2, agregado
em Python. Ordem: `last_job_at DESC`, depois nome. Itens de `GET /jobs` ganham
`project: {id,name}` e `folder: {id,name}|null` com um LEFT JOIN único (sem N+1). `folder_id`
sem `project_id` é aceito (projeto inferido da pasta, após checagem de posse).

**Fase 2 — gestão**

| Método | Rota | Descrição |
|---|---|---|
| POST | `/projects` | Get-or-add (`201` criou / `200` existia) |
| PATCH | `/projects/{id}` | `{name? (mesma chave), description?, archived?}` |
| DELETE | `/projects/{id}` | Só sem jobs e sem keys vinculadas; senão `409` dizendo o quê |
| POST | `/projects/{id}/folders` | Get-or-add de pasta |
| PATCH | `/folders/{id}` | `{name}` com a mesma chave |
| DELETE | `/folders/{id}` | Na mesma transação: `UPDATE jobs SET folder_id=NULL WHERE folder_id=:f AND user_id=:u`, depois apaga a pasta. Nunca apaga jobs |
| PATCH | `/jobs/{id}/location` | `{project|project_id, folder|folder_id|null}` |
| POST | `/jobs/move` | Lote `{job_ids ≤100, project_id, folder_id|null}`, tudo-ou-nada; algum job não possuído → `404` no lote inteiro |

Mover troca só `project_id`/`folder_id` no MariaDB (MinIO/ES não carregam projeto). Mudar de
projeto sem pasta → raiz. Upload para projeto arquivado → `422 "Projeto arquivado"` (e não
desarquiva — Revisão 1 #12); arquivar projeto vinculado a key → `409`.

### 4.7 Armazenamento e busca

- **MinIO não muda**: `uploads/{job_id}/…` e `audio/{job_id}/…`. Projeto no caminho tornaria
  mover/renomear uma cópia de objetos, e o caminho mentiria depois de cada mover.
- **Elasticsearch não muda.** Busca por conteúdo filtrada por projeto (fase 3) usa
  `terms job_id` com os IDs do MariaDB (teto de 10 000); denormalizar `project_id` no ES só se
  isso ficar lento.
- **Redis não muda.**

### 4.8 Segurança

- O get-or-add por texto é sempre `WHERE user_id = :me` — nenhum texto resolve projeto alheio.
- Todo ID recebido (upload, filtro de `GET /jobs`, vínculo de key, mover) passa por
  `get_owned_project` / `get_owned_folder` → `404` uniforme. `folder.project_id` tem de bater
  com o projeto resolvido. Nada de autorização vem do Redis.
- O vínculo de key é verificado ao gravar e ao usar.
- Limites de § 4.1 contra clientes que geram nomes aleatórios.

### 4.9 Frontend (Fase 1)

Sem dependências novas; combobox no mesmo estilo de `components/tag-input.tsx` (input +
listbox próprio com teclado).

**Upload (`/dashboard`)** — campos **Projeto** (obrigatório) e **Pasta** (opcional), acima
das tags (`components/projects/project-combobox.tsx`, `folder-combobox.tsx`):
- Opções vêm de `GET /projects?include=folders`, filtradas no cliente por substring simples
  só para **exibir**; ao digitar, `GET /projects/resolve` (ou `/projects/{id}/folders/resolve` para a pasta) com debounce decide se o texto
  casa com um existente ("usar *Reunião*") ou será criado ("criar *reuniao*" com selo
  "novo"). A regra de normalização mora só no backend (Revisão 1 #6).
- **Nunca pré-seleciona** um projeto que o usuário não escolheu: valor inicial = `?project=`
  da URL, senão o último usado *por este usuário* (`localStorage`, com try/catch), senão
  vazio. Botão "Enviar" desabilitado sem projeto, com a dica "Escolha ou crie um projeto".
- Pasta habilita depois do projeto; trocar de projeto limpa a pasta.
- Envia `project_id`/`folder_id` quando escolhidos da lista, `project`/`folder` quando
  digitados. Toast "Enviado para Cliente X › Áudios" (+ "Projeto criado" se `created`).

**Jobs (`/jobs`)** — coluna lateral (`components/projects/project-sidebar.tsx`): "Todos os
jobs", cada projeto com contagem, pastas do projeto selecionado com contagem e "Sem pasta".
Clicar grava `?project=<id>&folder=<id|root>` pelo `setParams` existente (somando-se a
`status`, `kind`, `tag`, `q`, `page`). Acima da lista, um título `Cliente X › Áudios`. Em
telas < `md` a coluna vira um `<select>` de projeto + `<select>` de pasta acima da lista (não
há `Sheet` em `components/ui`; não vale criar um na fase 1). Na visão "Todos os jobs", cada
linha mostra um chip `Projeto › Pasta`.

**API keys (`/api-keys`)** — coluna "Projeto" por key, com o combobox de projeto
(`PATCH /api-keys/{id}`); diálogo de criação ganha o mesmo campo. Texto de ajuda: "Uploads
desta key sem `project` vão para este projeto. Ao trocar, arquivos já enviados que estejam em
outro projeto serão processados de novo."

**`/docs`** — seção "Projetos e pastas": campos, obrigatoriedade, vínculo por key,
normalização, precedência JWT × key, exemplos `curl`.

**Contrato** — `types/api.ts` ganha `Project`, `Folder`; toda rota nova entra na tabela de
`test_frontend_api_contract.py`.

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Inbox implícito para quem não manda projeto (v1 desta spec) | É "opcional com default": o requisito "projeto obrigatório" vira cosmético e tudo que não é organizado acumula num balde. O vínculo por key dá a mesma compatibilidade de forma explícita. |
| Projeto por API key na migração (nome da key) | Jobs não registram a key de origem; os legados ficariam fora do projeto da key e a deduplicação do cliente de produção quebraria (reprocessamento na GPU). |
| Tags com prefixo (`project:x`) | Não garante "exatamente um", sem exibição, contagem ou vínculo de key. |
| Pastas aninhadas | Get-or-add de caminho, mover subárvore e árvore na UI triplicam o trabalho; `/` reservado deixa a porta aberta. |
| Unicidade pela collation do servidor | `utf8mb4_general_ci` (padrão do MariaDB) iguala strings que a regra Python distingue (ex.: `й`/`и`) → colisão sem releitura possível. `utf8mb4_bin` + chave Python é explícito e testável. |
| NFKD + casefold | Remove dakuten (`ハード`=`ハート`), expande Hangul e ligaduras além do tamanho da coluna, iguala `²` a `2`. |
| Normalização espelhada em TypeScript | `toLowerCase` ≠ `casefold` (ß) e as tabelas Unicode diferem por runtime; `GET /projects/resolve` elimina a divergência. |
| FKs em `jobs` com `ON DELETE SET NULL` | `ALGORITHM=COPY` na maior tabela com produção escrevendo; e existiria ou não conforme o caminho que criou o schema. |
| `_ADDED_COLUMNS` + Alembic | Dois mecanismos que se atropelam (`create_all` cria as tabelas, Alembic falha em "already exists"). Um script idempotente, DDL primeiro. |
| Rename livre na fase 1 | Clientes que mandam o nome antigo por texto criariam um projeto novo em silêncio. |
| Dedup global por usuário | O arquivo enviado a "Cliente B" devolveria o job de "Cliente A"; o usuário nunca o veria em B. |
| Projeto no caminho do MinIO | Mover/renomear viram cópia de objetos. |

## 6. Impactos

- **Compatibilidade:** clientes por API key — todas as keys existentes são vinculadas ao
  Inbox pela migração, então nada muda para elas (+ campos aditivos na resposta). Uploads por
  JWT sem projeto passam a receber `422`: o único cliente JWT conhecido é o próprio frontend,
  que passa a mandar projeto; o pré-voo 0c do runbook procura outros (ex.: `meumentor-api`). Keys criadas depois sem vínculo precisam mandar `project`.
  Dedup passa a ser por projeto (§ 4.4). Emergência: `UPLOAD_FALLBACK_PROJECT`.
- **Disponibilidade:** upload passa a exigir o MariaDB para resolver o projeto (`503` se fora);
  antes já falhava com `500` nesse caso (§ 4.4, "Banco indisponível").
- **Performance:** upload ganha 1–2 SELECTs indexados (e raramente um INSERT). `GET /projects`
  é um GROUP BY coberto. `GET /jobs` ganha dois LEFT JOINs por PK.
- **Operação:** runbook de § 4.3 (DDL antes do código, pré-voo, backfill em lotes, guarda no
  boot). Novas envs: `UPLOAD_FALLBACK_PROJECT` (vazio), `MAX_PROJECTS_PER_USER` (200),
  `MAX_FOLDERS_PER_PROJECT` (500). Log INFO quando get-or-add cria projeto/pasta, com
  `user_id` e se veio de API key — sinal de typo de cliente automático.
- **Custo:** reprocessamento quando o mesmo arquivo vai a dois projetos.

## 7. Plano de testes

SQLite + `TestClient` + override de `get_current_active_user` (como `test_job_tags.py`);
as fixtures **dos testes novos desta spec** ligam `PRAGMA foreign_keys=ON` (Revisões 1 #10 e
2 N10); a fixture compartilhada **não** muda, porque testes existentes (`test_job_tags.py`,
`test_images_endpoints.py`…) inserem jobs/keys sem linha em `users` e quebrariam. De todo modo
a semântica de remoção é por UPDATE explícito, então é testada sem depender de FK.

- **Normalização** (`test_projects_normalization.py`): tabela de casos — acentos latinos,
  caixa, espaços, `ß`, `ハード`/`ハート`, Hangul (chave em NFC, mesmo comprimento), `²`, `Ⅳ`,
  ligaduras, cirílico (`й`≠`и`, `ё`≠`е`), vietnamita (`Tiếng`→`tieng`), latinas não decomponíveis
  (`Łódź`→`łodz`, ≠ `lodz`), escrita mista (`Café Москва`→`cafe москва`); rejeições (vazio, >100, chave >200, controle, `/` em pasta).
- **Get-or-add** (`test_project_get_or_add.py`): SQLite em arquivo + 8 threads → 1 linha;
  `IntegrityError` forçado → rollback → releitura; duas falhas → `503`; `OperationalError` →
  `503`; sessão com escrita pendente → `RuntimeError`; limite → `422`.
- **Upload** (`test_upload_projects.py`), para os 7 endpoints (parametrizado): JWT sem projeto
  → `422` com a mensagem exata e nada gravado; key vinculada sem projeto → projeto da key;
  explícito vence a key; JWT+key → key ignorada; texto novo (`created`), grafia equivalente,
  ID alheio (`404`), pasta de outro projeto (`422`), nome+ID (`422`), `folder` sem projeto
  (`422`), dedup no mesmo projeto e em outro (mensagem), `/convert` não deduplica `failed`,
  `UPLOAD_FALLBACK_PROJECT` ligado.
- **Regressão do cliente de produção**: o request exato de hoje, com key vinculada ao Inbox e
  um job legado do mesmo checksum no Inbox → devolve o job existente, mesmos campos/valores.
- **Leitura** (`test_projects_api.py`): contagens, `folder_id=root`, `folder_id` alheio
  (`404`), `resolve` de projeto e de pasta (pasta de projeto alheio → `404`), `PATCH /api-keys/{id}` com projeto alheio (`404`).
- **Migração** (`test_migrate_0003.py`, SQLite): banco no schema antigo → script cria tabelas
  e colunas, um Inbox por usuário (com jobs ou keys), preenche só MAIN, vincula todas as keys;
  2ª execução não muda nada; usuário que já tem projeto "inbox" é reutilizado; a lista de
  keys vinculadas é impressa. Lock timeout simulado → retentativas → aborta sem DDL parcial.
- **Boot** (`test_boot_guard.py`): `jobs` existente sem a coluna, banco acessível →
  `SystemExit(1)` mesmo com `ENVIRONMENT=development`, e antes de `create_all`; banco
  **vazio** → sobe, `create_all` cria tabelas/colunas/índice e os dois marcadores ficam com
  T1 = T2; banco inacessível → segue como hoje; cauda pega `project_id IS NULL AND
  created_at <= T2` (inclusive um job com created_at < T1 inserido depois do passo 3) e grava
  `0003_tail` na mesma transação; marcador já existente → IntegrityError → pula sem tocar
  em linhas; segundo boot não toca em nada —
  key com `project_id` NULL criada depois de T2 continua NULL, Inbox apagado não é recriado;
  job MAIN sem projeto depois de T2 → log ERROR, linha intacta.
- **Contrato** (`test_frontend_api_contract.py`): rotas e campos novos.
- **Manual (staging)**: runbook inteiro contra uma cópia do MariaDB 10.11 de produção, medindo o
  tempo dos ALTERs e do backfill, com uma transcrição longa em andamento (para ver o
  metadata lock e o `WAIT 5` agindo); restart de um worker-audio entre os passos 2 e 4.

## 8. Plano de implementação

Estimativa honesta para uma pessoa: **Fase 1 ≈ 7–8 dias úteis** (backend ~4,5; frontend ~2;
staging/runbook ~1). Cada item cabe num PR.

**Fase 1 — projeto obrigatório de ponta a ponta**
- [ ] `shared/projects.py` (normalização, get-or-add, limites) + modelos + testes. *(1 d)*
- [ ] `scripts/migrate_0003_projects.py` (pré-voo, DDL idempotente com `WAIT`/retentativas,
      backfill em lotes, marcadores, downgrade) + guarda de boot em `main.py` + cauda
      one-shot + runbook em `docs/`. *(1,5 d)*
- [ ] `request.state.api_key`; `resolve_upload_location` em `/upload`, `/convert`,
      `/transcribe` e nos 4 de `/images` (dois JSON, dois multipart); dedup por projeto
      (+ guarda `FAILED` no `/convert`); resposta estendida; `UPLOAD_FALLBACK_PROJECT`;
      testes parametrizados. *(2 d)*
- [ ] `GET /projects`, `GET /projects/resolve`, `GET /projects/{id}/folders/resolve`, filtros e campos em `GET /jobs[/{id}]`,
      `GET/POST/PATCH /api-keys` com projeto, `get_owned_project/folder`. *(0,5 d)*
- [ ] Frontend: comboboxes no upload, barra lateral de filtro em `/jobs`, coluna de projeto
      em `/api-keys`, `/docs`, tipos + contrato. *(2 d)*
- [ ] Ensaio do runbook em staging (medir sessões de worker e tempo de lock), deploy. *(1 d)*

**Fase 2 — gestão (≈ 3 dias)**
- [ ] CRUD de projeto/pasta (§ 4.6 fase 2), rename cosmético, arquivar, apagar com `409`s.
- [ ] Mover (unitário e lote) — exige criar seleção múltipla na lista de `/jobs` (hoje não
      existe checkbox por linha) e um cartão "Local" + breadcrumb em `/jobs/[id]`.
- [ ] Página `/projects` (cartões com contagens; drop de arquivos no cartão).

**Fase 3 — sob demanda**
- [ ] Upload de vários arquivos em fila (só frontend).
- [ ] Busca por conteúdo filtrada por projeto.
- [ ] Apagar projeto com jobs (task Celery, `202`).

## 9. Questões em aberto

- [ ] **D1** Projeto por usuário (não por time)? → **Recomendado:** por usuário.
- [ ] **D2** Pastas de um nível? → **Recomendado:** sim; `/` reservado.
- [ ] **D3** Nome do projeto da migração? → **Recomendado:** "Inbox" (UI em inglês; o
      nome de exibição pode ser corrigido na fase 2 só na caixa — a chave é `inbox`).
- [ ] **D4** Tags? → **Recomendado:** coexistem como rótulos transversais; sem migração.
- [ ] **D5** Duplicata no mesmo projeto com pasta diferente: mover ou não? →
      **Recomendado:** não mover; a resposta traz a `folder` real.
- [ ] **D6** `UPLOAD_FALLBACK_PROJECT` deve existir? → **Recomendado:** sim, vazio; é
      válvula, não default.
- [ ] **D7** Acentos contam para unicidade? → **Recomendado:** acentos do bloco
      U+0300–U+036F são ignorados **só sobre letras latinas** (Reunião = Reuniao); cirílico,
      japonês, coreano etc. não são afetados (`й` ≠ `и`). Aceito também: letras latinas que
      não se decompõem em NFD continuam distintas — "Łódź" ≠ "Lodz" (ł, ø, đ, ß→ss via
      casefold é a exceção); quem quiser o mesmo projeto usa a mesma grafia ou o combobox.
- [ ] **D8** Pasta vinculada à key também? → **Recomendado:** não na fase 1; coluna
      `folder_id` em `api_keys` é trivial depois.

## 10. Trabalho futuro (não-objetivos explícitos da Fase 1)

- **Defaults por projeto**: `output_format`, `language`, `purge_source`, `docling_preset`
  guardados no projeto e aplicados quando o request não manda — o portal "configurado por
  projeto".
- **API keys restritas a um projeto** (escopo): a key só lê/escreve jobs do seu projeto.
  Diferente do vínculo desta spec, que é só destino padrão.
- **Aliases + rename de verdade** (`project_aliases (user_id, name_key) → project_id`).
- Converter tag em projeto (`POST /projects/from-tag`), cor/ícone de projeto.
- Projeto/pasta denormalizados no Elasticsearch; export zip por projeto; webhook por projeto;
  compartilhar projeto entre usuários; regras de roteamento ("arquivos `aula_*` → pasta Aulas").

## Revisão 1 — resposta ao adversário

| # | Decisão | Motivo |
|---|---|---|
| 1 | Aceito | Projeto vem do request ou do vínculo da key; senão `422` com exemplo. Sem Inbox implícito, sem `warnings`/`Warning:`; migração vincula toda key ao Inbox do dono (escolhido para preservar a dedup do cliente de produção). `PROJECT_REQUIRED` removido; sobra só a válvula `UPLOAD_FALLBACK_PROJECT`, vazia. |
| 2 | Aceito | Um só mecanismo: script idempotente (também como revisão Alembic), nada em `_ADDED_COLUMNS`; DDL aplicado antes de `create_all` ver os modelos novos; sem `ON DELETE` em `jobs`, remoção por UPDATE explícito. |
| 3 | Aceito | Runbook DDL-primeiro com pré-voo `SHOW COLUMNS` antes de o `models.py` novo chegar ao bind mount; guarda no boot da API. |
| 4 | Aceito | Backfill é pré-condição (passo 3) + cauda idempotente no boot (passo 5); não há leitura "NULL = Inbox". |
| 5 | Aceito | `utf8mb4_bin` na chave; sem lazy Inbox (some a colisão 5a); retry limitado → `503`; migração faz select-or-insert. |
| 6 | Aceito | NFD + remove só U+0300–U+036F + NFC + casefold; chave ≤ 200 validada; UI usa `GET /projects/resolve` em vez de espelhar. |
| 7 | Aceito | `ADD COLUMN ALGORITHM=INSTANT`, índice `INPLACE, LOCK=NONE`, sem FK em `jobs`/`api_keys`, backfill em lotes de 1000 por PK com commit; índice redesenhado para cobrir `job_type`/`status`. |
| 8 | Aceito | Chave imutável; rename só cosmético (mesma chave); aliases para o futuro. |
| 9 | Aceito | Fase 1 re-escopada (§ 8), ≈ 6 dias; mover/CRUD/`/projects`/seleção múltipla para a fase 2; sem `Sheet` (selects no mobile). |
| 10 | Aceito | UPDATEs explícitos + `PRAGMA foreign_keys=ON` na fixture. |
| 11 | Aceito | Órfãos reconhecidos; visíveis com contagem 0 e apagáveis na fase 2; sem limpeza automática (justificado em § 4.4). |
| 12 | Aceito | Upload para arquivado → `422`, não desarquiva; arquivar/apagar projeto vinculado a key → `409` com os nomes. |
| 13 | Aceito | `is_default` removido; não há projeto padrão. |
| 14 | Aceito | `/convert` ganha a guarda `FAILED`; reprocessamento por mudança de projeto aparece na `message`. |
| 15 | Aceito | `folder_id` em `GET /jobs` via `get_owned_folder`; precedência JWT documentada e testada. |
| 16 | Aceito | Defaults por projeto e keys escopadas em § 10; from-tag, cor e aliases saíram do núcleo. |

## Revisão 2 — resposta ao adversário

| # | Decisão | Motivo / mudança |
|---|---|---|
| N1 | Aceito | Guarda de schema sai de `init_db` e roda em `api/main.py` **antes** e **fora** do `try` que engole erros fora de `ENVIRONMENT=production`; falta de coluna com banco acessível → `SystemExit(1)` sempre (§ 4.3 passo 5a). |
| N2 | Aceito | Backfill one-shot com marcadores em `app_migrations` (`0003_backfill` = T1, `0003_tail` = T2); a cauda só toca linhas com `T1 < created_at <= T2` e roda uma vez; depois, jobs MAIN sem projeto só geram log ERROR; keys deixadas sem projeto e Inbox apagado nunca são "consertados" (passos 3, 5b, 5c). |
| N3 | Aceito | `SET SESSION lock_wait_timeout=5` + `ALTER TABLE … WAIT 5`, 5 retentativas e abort limpo; pré-voo de `innodb_trx`/`SHOW PROCESSLIST`, hora mais quieta, plano B de parar workers; medir em staging quanto tempo as sessões de worker seguram transação (passos 0d, 0e, 1). |
| N4 | Aceito | Um só caminho em produção: rodar `scripts/migrate_0003_projects.py` direto; `alembic upgrade` proibido lá (não stampado); a revisão Alembic existe só para dev e chama as mesmas funções. |
| N5 | Aceito | Índice declarado em `Job.__table_args__`; tabelas novas com `utf8mb4`/`utf8mb4_general_ci` explícitos no modelo e no DDL; script checa `information_schema` antes de criar. |
| N6 | Aceito | § 4.4 "Banco indisponível": `503` é mais limpo que o `500` que já acontecia; registrado que o INSERT do job após a resolução continua engolido como hoje. |
| N7 | Aceito | Pré-voo 0c: procurar nos logs chamadores sem API key, em especial `meumentor-api` (`WHISPER_API_KEY` vazio → hoje já leva 401); decidir key vinculada ou `UPLOAD_FALLBACK_PROJECT` antes do deploy. |
| N8 | Aceito | Acentos só são removidos sobre base latina (cirílico `й`/`и`, `ё`/`е` continuam distintos; casos na tabela de testes); limites escritos como escapes; `assert` trocado por checagem explícita; `OperationalError`/`InterfaceError` → `503`. |
| N9 | Aceito | O passo 3 imprime as keys vinculadas ao Inbox; resolver de pasta separado em `GET /projects/{id}/folders/resolve`. |
| A/#9 | Aceito | Fase 1 reestimada para 7–8 dias (upload em 7 endpoints = 2 d; migração/guarda = 1,5 d; staging = 1 d). |
| A/#10 | Aceito | `PRAGMA foreign_keys=ON` só nas fixtures dos testes novos; a fixture compartilhada não muda. |
| — | Fato novo | Produção é MariaDB 10.11.13 (não MySQL): sintaxe e collations da spec ajustadas (`utf8mb4_general_ci` como padrão, `utf8mb4_bin` na chave, `WAIT n`, `mariadb-dump`); `with_variant(..., "mysql")` vale porque o dialeto de `mysql+pymysql` se chama "mysql". |

## Revisão 3 — portão final

- **#1 (must)** Banco vazio: sem tabela `jobs` a guarda é pulada, `create_all` cria tudo e os
  dois marcadores são gravados com T1 = T2; a guarda só vale para `jobs` existente sem
  `project_id` (§ 3, § 4.3 passo 5a, teste em § 7). Aceito.
- **#2** Marcador `0003_tail` e cauda na mesma transação; concorrente bloqueia no PK e pula;
  a guarda checa só `0003_backfill`. Aceito.
- **#3** Cauda sem limite inferior: `project_id IS NULL AND created_at <= T2` para jobs e
  keys (created_at é definido antes do commit). Aceito.
- **#4** D7 aceita "Łódź" ≠ "Lodz"; casos de escrita mista na tabela de testes. Aceito.
- **#5** Limites do bloco combinante escritos como escapes no código. Aceito.
- **#6** Pré-voo 0c marcado como ação do dono, ainda não verificada. Aceito.
