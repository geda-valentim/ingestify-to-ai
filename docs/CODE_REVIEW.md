# Code Review — Ingestify

> Revisão técnica do estado do repositório em **2026-08-24** (branch `main`, commit `b7bf521`).
> Escopo: arquitetura, god files, dívida técnica, segurança, testes e documentação.
> Método: inspeção estática do código-fonte (20.214 LOC em Python/TS, excluindo `node_modules`).
>
> **Status (2026-08-26):** todo o P0 e parte do P1 já foram corrigidos — ver § 9 e § 11.
> Os achados abaixo estão preservados como escritos; o que mudou está marcado ✅ no plano.

---

## 1. Sumário executivo

O projeto funciona e tem uma arquitetura de jobs hierárquicos bem pensada, mas acumulou
dívida em três eixos que se reforçam:

| Eixo | Estado | Impacto |
|---|---|---|
| **Arquitetura** | Duas arquiteturas coexistem; a "oficial" (Clean Arch) é código morto | Alto |
| **God files** | 4 arquivos concentram ~26% do código-fonte | Alto |
| **Testes** | Nenhum teste automatizado executável; `make test` quebrado | Crítico |
| **Segurança** | 4 achados exploráveis (1 IDOR, CORS, admin, segredos default) | Crítico |
| **Documentação** | 14 docs desatualizados desde 2025-10-20; descrevem código que não existe | Médio |

**Prioridade recomendada:** § 5 (segurança) → § 4 (testes) → § 2 (arquitetura duplicada) → § 3 (god files).

---

## 2. Achado estrutural nº 1 — Clean Architecture é código morto

O `CLAUDE.md` e o `backend/docs/CLEAN_ARCHITECTURE.md` afirmam que o backend segue Clean
Architecture com `domain/ → application/ → infrastructure/ → presentation/`.

**A realidade:**

```
backend/api/main.py  →  include_router(api.routes)        ← 100% do tráfego passa aqui
                        include_router(api.auth_routes)
                        include_router(api.apikey_routes)
                        include_router(api.admin_routes)
```

`backend/presentation/` **nunca é importado** por nenhum módulo fora dele mesmo:

```bash
$ grep -rn "presentation" backend --include=*.py -l
backend/presentation/api/controllers/conversion_controller.py   # só ele mesmo
```

São **47 arquivos** em `domain/`, `application/`, `infrastructure/` e `presentation/`
(entities, value objects, ports, use cases, DI container, 3 repositórios MySQL, 3 adapters)
que nunca executam em produção. `backend/infrastructure/di_container.py` nunca é instanciado.

### Consequências

- **Duplicação de modelos em 3 camadas:** `shared/schemas.py` (27 classes),
  `presentation/schemas/` (8 classes), `application/dto/` (7 classes) modelam os mesmos conceitos.
- **Documentação enganosa:** quem lê o `CLAUDE.md` procura a lógica em `use_cases/` e a encontra
  em `api/routes.py`.
- **Custo de manutenção invisível:** toda alteração de regra teria que ser feita 2× para manter
  a paridade — e não é, então as camadas já divergiram.
- Único ponto de contato real: `infrastructure/adapters/celery_queue_adapter.py` importa tasks
  reais do `workers/tasks.py`, mas o adapter em si não tem chamador.

### Decisão necessária (é uma decisão, não uma tarefa)

| Opção | Esforço | Quando escolher |
|---|---|---|
| **A. Deletar** `domain/`, `application/`, `infrastructure/`, `presentation/` e assumir a arquitetura em camadas simples (`api/` + `workers/` + `shared/`) | Baixo | Se o time é pequeno e o domínio é estável |
| **B. Migrar** os 14 endpoints de `api/routes.py` para os controllers/use cases e deletar `api/routes.py` | Alto | Se há intenção real de trocar infra (MySQL→X, Celery→Y) ou testar domínio isolado |
| **C. Manter as duas** | — | **Não é opção.** É o estado atual e é a origem da maior parte da dívida abaixo |

> Enquanto a decisão não for tomada, `CLAUDE.md` e `backend/docs/CLEAN_ARCHITECTURE.md`
> devem ser marcados como "arquitetura-alvo, não implementada".

---

## 3. God files

### 3.1 `backend/api/routes.py` — 2.000 linhas, 14 endpoints

Concentra roteamento, validação, orquestração de Redis + MySQL + Elasticsearch + MinIO,
regras de deduplicação, autorização e montagem de resposta.

Funções mais longas:

| Linhas | Função | Responsabilidades misturadas |
|---:|---|---|
| 283 | `convert_document` (L528) | 4 tipos de source, upload, dedup, Redis, MySQL, enfileiramento |
| 267 | `transcribe_audio` (L261) | pipeline de áudio inteiro dentro do handler HTTP |
| 225 | `upload_and_convert` (L35) | ~80% duplicado de `convert_document` |
| 187 | `get_job_status` (L811) | leitura Redis + MySQL + paginação + montagem de DTO |
| 168 | `retry_failed_page` (L1713) | busca no MinIO + reenfileiramento |

**Duplicação concreta:** `upload_and_convert` e `convert_document` (source_type=file) executam
a mesma sequência — checksum → busca de duplicata → `uuid4()` → `set_job_status` → persistência
MySQL → `process_conversion.delay()` — em dois blocos de código independentes que já divergiram
(`upload_and_convert` aceita `docling_preset`, `convert_document` aceita `ConversionOptions`).

**Refatoração sugerida** (independe da decisão do § 2):

```
api/routes/
├── __init__.py          # agrega os routers
├── upload.py            # POST /upload, POST /convert
├── transcribe.py        # POST /transcribe
├── jobs.py              # GET/DELETE /jobs, /jobs/{id}, /jobs/{id}/result
├── pages.py             # /jobs/{id}/pages/**
└── search.py            # GET /search
api/deps.py              # get_owned_job(), get_owned_page()  ← ver § 5.1
services/job_service.py  # create_job_from_source() — remove a duplicação upload/convert
```

### 3.2 `backend/workers/tasks.py` — 1.225 linhas, 6 tasks

| Linhas | Task |
|---:|---|
| 390 | `process_conversion` |
| 252 | `convert_page_task` |
| 226 | `process_page` |
| 169 | `merge_pages_task` |
| 127 | `split_pdf_task` |

**`convert_page_task` (L557) e `process_page` (L809) são a mesma operação.** A diferença é a
origem do arquivo: a primeira recebe `page_file_path` (página já split), a segunda recebe
`pdf_path` (PDF inteiro) e extrai a página. Ambas convertem, gravam em Redis/MySQL/ES e
disparam `merge_pages_task`. `process_page` é usada **exclusivamente** pelo retry em
`routes.py:1851`; `convert_page_task` pelo fluxo normal e pelo `monitoring.py`.

→ Duas implementações do mesmo caminho crítico significam que uma correção de bug será
  aplicada em uma e esquecida na outra. Unificar em uma task com `source: PagePath | PdfPage`.

### 3.3 `frontend/app/jobs/[id]/page.tsx` — 911 linhas

Um único componente com 6+ `useState`, viewer de PDF dinâmico, aba de markdown, seleção
múltipla de páginas, diálogo de exclusão e polling. Deveria ser quebrado em
`<PdfPane>`, `<MarkdownPane>`, `<PageList>`, `<DeleteJobDialog>` + um hook `useJobDetail(id)`.

### 3.4 `backend/shared/redis_client.py` — 504 linhas, 32 métodos

Não é god file por tamanho, mas por escopo: acumula status de job, resultado, páginas,
propriedade (autorização), progresso e índice por usuário. As responsabilidades de
**cache** e **autorização** não deveriam morar na mesma classe (ver § 5.1).

---

## 4. Testes — achado crítico

```bash
$ ls backend/tests
ls: cannot access 'backend/tests': No such file or directory

$ grep -A2 "^test:" Makefile
test:
	@docker compose exec api pytest tests/ -v      # ← diretório não existe
```

- **`backend/pytest.ini` existe, mas não há um único teste `pytest`.**
- O que existe são **11 scripts manuais** (`scripts/test_*.py`, `test_*.sh`, `test_conversion_flow.py`)
  que exigem a stack de pé, credenciais e inspeção visual da saída colorida. Não são
  executáveis em CI, não têm asserts, não retornam exit code confiável.
- `backend/test_clean_arch.py` (237 linhas) testa a camada que nunca roda em produção (§ 2).
- **Frontend:** nenhum teste. `package.json` tem apenas `dev`, `build`, `start`, `lint`.
- Não há CI (`.github/workflows` ausente).

### Cobertura mínima recomendada (ordem de valor)

1. `pdf_splitter.should_split_pdf` / split — puro, sem I/O, alto risco.
2. `redis_client.calculate_job_progress` — a fórmula 10/80/10 não tem nenhuma verificação.
3. `verify_job_ownership` — é o controle de acesso do sistema (§ 5.1).
4. Contratos HTTP dos 14 endpoints com `TestClient` + Redis/MySQL fakes.
5. Idempotência da deduplicação por checksum.

---

## 5. Segurança

### 5.1 🔴 IDOR em `DELETE /jobs/{job_id}` — autorização pode ser totalmente ignorada

`backend/api/routes.py:1045-1049`:

```python
if status_data and not redis_client.verify_job_ownership(job_id, current_user.id):
    raise HTTPException(403, ...)

if db_job and db_job.user_id and db_job.user_id != current_user.id:
    raise HTTPException(403, ...)
```

Ambas as verificações são **condicionais**. Existe um caminho em que nenhuma dispara:

- `status_data is None` — o status no Redis expirou (`result_ttl_seconds = 3600`), **e**
- `db_job.user_id is None` — `Job.user_id` é nullable com `ondelete="SET NULL"`
  (`backend/shared/models.py:68`), então todo job de um usuário removido vira órfão.

Resultado: **qualquer usuário autenticado pode deletar jobs órfãos de terceiros**, incluindo
os artefatos no Elasticsearch e MinIO.

**Causa raiz mais ampla:** a autorização é derivada do Redis (`verify_job_ownership`), que é um
cache com TTL. Passado o TTL, o dono legítimo recebe **403** no próprio job — e o registro
autoritativo (MySQL) só é consultado como fallback opcional.

**Correção:**

```python
# api/deps.py
def get_owned_job(job_id: str,
                  user: User = Depends(get_current_active_user),
                  db: Session = Depends(get_db)) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    if job.user_id != user.id:          # sem `and job.user_id` — None nunca autoriza
        raise HTTPException(404, "Job não encontrado")   # 404, não 403: não vaza existência
    return job
```

E aplicar como dependência nos 14 endpoints, substituindo as 7 verificações ad-hoc espalhadas
(L837, L1046, L1049, L1148, L1220, L1345, L1444, L1740). MySQL passa a ser a fonte de verdade
da autorização; Redis fica só com estado efêmero.

### 5.2 🔴 Endpoints `/admin/*` sem verificação de admin

`backend/api/admin_routes.py:38-45`:

```python
def require_admin(current_user=Depends(get_current_active_user)):
    """For now, all authenticated users are considered admins
    TODO: Add is_admin field to User model and check it here"""
    return current_user
```

Os 6 endpoints administrativos — estatísticas do sistema, jobs travados de todos os usuários,
retry em massa, `cleanup_old_jobs` (destrutivo) — estão abertos a **qualquer conta registrada**.
`POST /auth/register` é público.

**Correção:** adicionar `is_admin: bool = Column(Boolean, default=False, nullable=False)` ao
`User` (com migration Alembic) e falhar em `require_admin` quando falso. Enquanto isso não for
feito, remover `include_router(admin_router)` de `main.py:227` em qualquer deploy exposto.

### 5.3 🟠 CORS permissivo com credenciais

`backend/api/main.py:120-125`:

```python
allow_origins=["*"],       # "Configure properly in production"
allow_credentials=True,
allow_methods=["*"], allow_headers=["*"],
```

`allow_origins=["*"]` com `allow_credentials=True` é uma combinação que os navegadores
rejeitam — na prática o browser bloqueia requisições com credencial, o que mascara o problema
até alguém "consertar" trocando o wildcard por reflexão de origem. Deve virar uma lista de
origens vinda de `settings` (`cors_allowed_origins: list[str]`).

### 5.4 🟠 Segredos com default de produção no código

| Local | Default |
|---|---|
| `shared/config.py:85` | `jwt_secret_key = "your-secret-key-change-in-production-min-32-chars"` |
| `shared/config.py:76-77` | `minio_access_key/secret_key = "minioadmin"` |
| `docker-compose.yml:74,118,157,196` | `${MINIO_ROOT_USER:-minioadmin}` |

O `.env` local **não define `JWT_SECRET_KEY`** — ou seja, o ambiente atual assina tokens com a
chave publicada no repositório. Qualquer pessoa com acesso ao código forja um JWT válido.

**Correção:** remover os defaults e deixar o Pydantic Settings falhar na inicialização
(`jwt_secret_key: str` sem valor), documentando em `.env.example`.

> ✅ Ponto positivo: `.env` está corretamente no `.gitignore` e nenhum arquivo de segredo
> está versionado (`git ls-files | grep env` → apenas `.env.example`).

---

## 6. Dívida técnica geral

### 6.1 Gestão de sessão do banco

**37 ocorrências de `SessionLocal()` manual** (33 delas em `workers/tasks.py`), cada uma com
seu próprio `try/finally: db.close()`. Em `tasks.py` o padrão se repete até **11 vezes dentro
de uma única task** (`process_conversion`), abrindo e fechando conexões a cada etapa.

→ Extrair um `@contextmanager def db_session()` em `shared/database.py` com commit/rollback
  automático. Reduz ~120 linhas de boilerplate e elimina a classe de bug "esqueci o `finally`".

### 6.2 Tratamento de erro engolindo falhas

**172 `except Exception`** no backend. O padrão dominante é logar e continuar, o que transforma
falhas de infraestrutura (ES fora do ar, MinIO indisponível) em jobs "concluídos" com resultado
parcial. Não há exceções de domínio (`JobNotFound`, `ConversionFailed`) — tudo é `HTTPException`
levantada no meio da lógica de negócio, o que impede reuso fora do contexto HTTP.

### 6.3 `print()` em código de produção

28 `print()` fora dos scripts de teste, misturados com `logging`. Em containers, saem sem nível,
timestamp ou correlação de job.

### 6.4 Poluição da raiz do repositório

11 scripts na raiz (`start.sh`, `stop_api.sh`, `rebuild.sh`, `infra.sh`, `run_api.sh`,
`run_worker.sh`, `validate-frontend.sh`, `test_auth.sh`, `test_pagination.sh`,
`test_upload_apikey.sh`, `test_conversion_flow.py`) — funcionalidade que o `Makefile`
(44 targets) já cobre em grande parte. Mover para `scripts/` e manter o `Makefile` como
interface única.

### 6.5 Dependências

`backend/requirements.txt` mistura pins exatos (`fastapi==0.104.1`, `celery==5.3.4`) com ranges
abertos (`docling>=2.0.0,<3.0.0`, `requests>=2.32.2`). Builds não são reproduzíveis. O FastAPI
0.104.1 é de 2023 e está várias versões atrás. Não há `requirements.lock` nem Dependabot.

### 6.6 Tipagem no frontend

Apenas 8 usos de `any`/`as any` — bom. Mas o token de autenticação é lido de `localStorage`
(`frontend/lib/api.ts:23`), exposto a XSS. Considerar cookie `httpOnly` + `SameSite`.

---

## 7. Documentação

14 arquivos em `docs/`, **todos com última alteração em 2025-10-20** — mais de 10 meses atrás,
enquanto o código continuou evoluindo (MinIO, transcrição de áudio, admin routes, monitoring
não existiam ou mudaram desde então).

| Problema | Arquivo(s) |
|---|---|
| Descrevem arquitetura não implementada | `CLAUDE.md`, `backend/docs/CLEAN_ARCHITECTURE.md`, `backend/docs/README_CLEAN_ARCH.md`, `backend/docs/MIGRATION_GUIDE.md` |
| Descrevem `backend/tests/` inexistente | `CLAUDE.md`, `Makefile` |
| Snapshots de estado que envelhecem sozinhos | `docs/STATUS.md`, `docs/TASKS.md`, `docs/TEST_RESULTS.md`, `backend/docs/TEST_RESULTS.md`, `backend/docs/IMPLEMENTATION_SUMMARY.md` |
| Notas de migração já concluída | `docs/CHANGELOG_PYTHON313.md`, `docs/PYTHON_313_COMPATIBILITY.md` |
| PRD de 80 KB sem status | `docs/WEBSCRAPPING_PRD.md` |

→ Documentos de *estado* (`STATUS`, `TASKS`, `TEST_RESULTS`) devem sair do git e virar issues.
  Documentos de *decisão* devem virar specs versionadas — ver § 8.

---

## 8. Modelo de specs

Foi criado em `docs/specs/` um modelo padronizado para especificações de funcionalidade:

- **`docs/specs/README.md`** — a convenção: numeração, ciclo de vida, quando escrever uma spec.
- **`docs/specs/_TEMPLATE.md`** — o template a copiar.

O objetivo é substituir o padrão atual (PRDs monolíticos + docs de estado que apodrecem) por
uma unidade pequena, numerada e com status explícito, que registra **a decisão e o porquê** —
a única parte da documentação que o código não consegue contar sozinho.

---

## 9. Plano de ação priorizado

### P0 — Segurança ✅ concluído
- [x] IDOR do `DELETE /jobs/{id}`: `api/deps.py::get_owned_job`, MySQL como fonte da verdade, aplicado aos 7 endpoints que recebem job/page id (§ 5.1)
- [x] `User.is_admin` + migration `e399267560a7` + `require_admin` com 403; bootstrap via `scripts/make_admin.py` (§ 5.2)
- [x] `jwt_secret_key` e credenciais MinIO obrigatórios; boot falha com mensagem acionável (§ 5.4)
- [x] `CORS_ALLOWED_ORIGINS` com allowlist explícita; métodos/headers restritos ao uso real (§ 5.3)

### P1 — Rede de segurança (parcial)
- [x] `backend/tests/` criado — 48 testes cobrindo `pdf_splitter`, `redis_client` e a autorização de `deps.py` (§ 4)
- [x] `make test` consertado; a imagem da API agora inclui `tests/`
- [ ] Adicionar CI (`.github/workflows/ci.yml`): pytest + `tsc --noEmit` + `next lint`
- [ ] `@contextmanager db_session()` e migrar as 37 chamadas manuais (§ 6.1)

### P2 — Arquitetura (1 mês)
- [ ] **Decidir § 2 (A ou B)** e executar; até lá, marcar os docs de Clean Arch como "não implementado"
- [ ] Unificar `convert_page_task` / `process_page` (§ 3.2)
- [ ] Extrair `create_job_from_source()` e eliminar a duplicação `upload`/`convert` (§ 3.1)
- [ ] Quebrar `api/routes.py` em módulos por recurso (§ 3.1)

### P3 — Higiene (contínuo)
- [ ] Quebrar `frontend/app/jobs/[id]/page.tsx` em componentes + hook (§ 3.3)
- [ ] Substituir `print()` por `logging` (§ 6.3)
- [ ] Mover scripts da raiz para `scripts/` (§ 6.4)
- [ ] Pinar dependências e gerar lockfile (§ 6.5)
- [ ] Arquivar docs de estado; adotar `docs/specs/` para novas funcionalidades (§ 7, § 8)

---

## 10. Pontos positivos

Para calibrar: o que já está bem feito e deve ser preservado numa refatoração.

- **Design de jobs hierárquicos** (MAIN → SPLIT → PAGE* → MERGE) é a decisão certa para o
  problema, permite paralelismo real e retry granular.
- **Deduplicação por checksum** no upload evita reprocessamento caro — bom instinto de produto.
- **Presets `fast`/`balanced`/`quality`** do Docling expõem o trade-off custo/qualidade ao
  usuário em vez de escondê-lo.
- **`Makefile` com 44 targets e health checks** de Redis/MySQL/ES/MinIO — boa ergonomia de dev.
- **Frontend com tipagem sólida** (apenas 8 `any` em toda a base).
- **Nenhum segredo versionado**; `.gitignore` correto.
- **Separação infra compartilhada** (`docker-compose.infra.yml`) é uma boa ideia para múltiplos
  projetos na mesma máquina.

---

## 11. Achados da rodada de correções (2026-08-26)

Itens que só apareceram ao corrigir o P0. Os três primeiros eram bugs reais em produção,
invisíveis porque estavam mascarados por `except Exception` (§ 6.2).

### 11.1 ✅ `RedisClient` não tem atributo `.redis` — cleanup nunca deletou nada

`RedisClient` guarda a conexão em `self.client` (23 usos, zero `self.redis`). Quatro call sites
usavam `redis_client.redis`:

| Local | Efeito |
|---|---|
| `api/admin_routes.py:62` | `AttributeError` engolido → `/admin/stats` sempre devolvia `redis: {error}` |
| `workers/monitoring.py:275,283,284` | **`cleanup_old_jobs` nunca apagou uma única chave** |

No `cleanup_old_jobs` o efeito era pior que um erro: cada `delete` lançava `AttributeError`, era
capturado, logado — e `cleaned_count += 1` acontecia mesmo assim. A task registrava
`"Cleanup complete: N jobs cleaned"` enquanto o Redis crescia sem limite.

Dois nomes de chave também estavam errados: o status de página vive em `job:{id}:page:{n}`
(não `:status`) e `job:{id}:child_jobs` nunca existiu — child jobs ficam dentro do JSON de status.

**Corrigido.** Também passou a limpar `job:{id}:owner` e a remover o job de `user:{id}:jobs`,
e um job cujo delete falha não é mais contado como limpo.

### 11.2 ✅ Alembic nunca foi ligado

`alembic/env.py` era o scaffolding intocado (`target_metadata = None`) e `alembic.ini` ainda tinha
`driver://user:pass@localhost/dbname`. `alembic upgrade head` não rodava de forma alguma — o
schema era criado só por `Base.metadata.create_all()`, que **não** altera tabelas existentes.

Consequência: um banco já implantado nunca ganharia a coluna `is_admin` e quebraria em runtime
assim que `require_admin` passasse a lê-la.

**Corrigido** — `env.py` importa `shared.models` e usa `settings.database_url`.

> ⚠️ **Pendência:** bancos criados via `create_all()` já têm `users.is_admin`, então
> `alembic upgrade head` falhará com coluna duplicada. Rode `alembic stamp head` neles primeiro.
> Ainda falta uma migration baseline para `users`/`api_keys`/`jobs`/`pages`.

### 11.3 ✅ `start.sh` apagava o `.env` e produção nunca era produção

- `start.sh` regenerava o `.env` inteiro com `cat > .env` a cada execução. Com o `JWT_SECRET_KEY`
  agora obrigatório, isso apagaria a chave e deixaria um clone novo sem conseguir subir.
  **Corrigido:** preserva segredos existentes, gera a chave quando ausente, e para de embutir
  `minioadmin` na chamada `mc alias`.
- `docker-compose.prod.yml` nunca sobrescrevia `ENVIRONMENT=development` do arquivo base. Em
  produção o handler global de exceções devolvia `str(exc)` cru ao cliente. **Corrigido** para
  api, worker e beat.

### 11.4 ✅ `GET /jobs/{job_id}/pages/{n}/pdf` era público — **corrigido**

`routes.py` estava deliberadamente sem autenticação (documentado como "NO AUTH REQUIRED") e
redirecionava para uma URL pública do MinIO. Quem obtivesse ou adivinhasse um UUID de job lia o
PDF de qualquer usuário.

O buraco maior estava uma camada abaixo: `MinIOClient._set_public_read_policies()` aplicava uma
policy anônima de `s3:GetObject` em `uploads`, `pages` e `results` a **cada** inicialização do
cliente. Os documentos originais e os markdowns convertidos eram legíveis por qualquer um em
`http://<minio>:9000/<bucket>/<path>`, com caminho previsível
(`pages/{job_id}/page_{n:04d}.pdf`). Autenticar só o endpoint teria sido cosmético.

**Corrigido:**
- o endpoint usa `get_owned_job` (via `get_owned_page_or_none`) — MySQL como fonte da verdade,
  404 para job de terceiro;
- responde JSON com uma URL pré-assinada (TTL de 15 min) e seu `expires_at`, em vez de um 307
  (um redirect não carrega o `Authorization` do chamador até o MinIO, e o cliente precisa saber
  quando a URL morre);
- os quatro buckets passam a ter a policy **apagada** no startup — remover o código não revoga a
  policy já gravada num MinIO em execução;
- a URL é assinada para o endpoint que o **navegador** usa (`MINIO_PUBLIC_ENDPOINT`, ou o host da
  requisição + porta 9000). A assinatura SigV4 cobre o header `Host`: assinar para `minio:9000` e
  buscar em outro host devolveria 403 em todo PDF.

O frontend passou a buscar a URL de forma autenticada e a renová-la ao trocar de página, ao voltar
para a aba PDF depois do TTL, e quando o viewer falha com uma URL expirada.

**Limitação conhecida:** o esquema (http/https) da URL assinada vem de `MINIO_SECURE`, que também
governa a conexão interna. Um deploy que termine TLS na frente do MinIO e fale HTTP por dentro
precisaria de um flag separado.

### 11.5 🟠 `calculate_job_progress` não é o que a documentação diz

`CLAUDE.md` e § 2 do `SPECS.md` descrevem uma ponderação 10% split / 80% páginas / 10% merge.
A implementação (`redis_client.py:255`) é uma razão simples `completed / total * 100`. Os testes
fixam o comportamento **real**; ou a documentação ou o código precisa mudar — decisão de produto.

### 11.6 🟠 Dívidas menores identificadas e não corrigidas

- **`Page.page_job_id` sem índice** (`shared/models.py`) — a resolução de dono de child job faz
  lookup nessa coluna a cada request de página. Precisa de índice + migration.
- **`Job.user_id` com `ondelete="SET NULL"`** contradiz o `cascade="all, delete-orphan"` já
  declarado em `User.jobs`. É a origem dos jobs órfãos que habilitaram o IDOR do § 5.1. Alinhar
  para `CASCADE` eliminaria a classe inteira de problema.
- **`GET /jobs` lista a partir do set Redis `user:{id}:jobs`** (TTL de 30 dias), não do MySQL.
  Usuários perdem visibilidade de jobs antigos silenciosamente. Não é segurança, é correção.
- **`redis_client.verify_job_ownership`** ficou sem uso. Deve ser removida — é uma primitiva de
  autorização baseada em cache e não deve voltar a ser usada.
- **`scripts/init_db.py` e `scripts/check_db_sync.py`** só inserem a raiz do repo no `sys.path`,
  mas os módulos importam como `shared.*`; dependem de um `PYTHONPATH=backend` externo.

### 11.7 Verificação

- 48 testes passam no host e dentro de `ingestify-to-ai-api:latest` (Python 3.13, dependências reais).
- `import api.main` funciona na imagem, com a allowlist de CORS aplicada no startup.
- Sem `JWT_SECRET_KEY` o processo aborta com instrução de como gerar a chave.
- `docker compose config -q` passa para base, infra e prod.
- **Teste de mutação:** revertendo a guarda de autorização para a forma permissiva original,
  falham exatamente os 4 casos de job órfão/ciclo — a suíte de fato pega a regressão.
