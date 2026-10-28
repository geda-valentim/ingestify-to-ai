# Changelog - Hierarquia de Jobs Implementada

> **Registro histórico (2025-10).** Não é mantido; para mudanças posteriores use `git log`. Observação: `workers/tasks_old.py`, citado abaixo, não existe (há um `workers/tasks.py.backup`). Exceção: mudanças de comportamento intencionais que uma spec manda registrar aqui entram na seção abaixo.

## 2026-10: códigos próprios nas recusas do controle de engines e opt-in do desligamento por ociosidade (API 1.15.0)

**Por que é minor:** há códigos de erro novos que o cliente pode tratar e um campo opcional
novo no perfil de execução local. Nenhum campo ou endpoint existente é removido; uma resposta
de erro muda de `code` (abaixo, com a migração).

**Mudança de comportamento: recusas do controle de engines (#126, spec 0007)**
- As rotas de admin de engine respondiam toda recusa do controle de engines como 409
  `VERSION_CONFLICT`, com o motivo só no texto. Agora o 409 traz o `code` do motivo:
  `RUNTIME_OPERATION_REQUIRED` (salve um perfil de execução e execute um plano),
  `CLEANUP_CREDENTIAL_REQUIRED` (confirme o cooldown antes de trocar ou remover credenciais) e
  `OPERATION_CONFLICT` (o recurso está sob uma operação ativa ou incerta).
- `POST /admin/engines/{id}/reset-health` deixava a recusa escapar como **500** sem `code`;
  agora responde o mesmo 409 com `code`.
- **Migração:** quem lia o prefixo do texto de um `VERSION_CONFLICT` deve ler o `code`. O
  `VERSION_CONFLICT` continua valendo para conflito de versão de verdade. O front não dependia
  do formato antigo.

**Novo (spec 0007)**
- **Opt-in do desligamento por ociosidade (#130):** o perfil de execução local de transcrição
  e de visão aceita `idle_cooldown` (booleano, padrão `false`). Quem liga precisa poder
  planejar, desligar e iniciar a engine, porque as operações automáticas rodam com o acesso
  dele. Neste release o campo só é validado e gravado: a política que desliga e religa a
  engine sozinha vem num release seguinte. Códigos novos:
  - `IDLE_COOLDOWN_NOT_SUPPORTED` (422): engine não local, ou feature fora de transcrição e
    visão;
  - `IDLE_COOLDOWN_PERMISSION_REQUIRED` (403): falta uma das permissões acima;
  - `AUTOMATIC_EFFECT_NOT_APPLIED` e `IDLE_POLICY_NOT_OPTED_IN`: resultado de operações
    automáticas, que aparecem no histórico de operações.

**Correções**
- **Drenagem com processo morto (#129):** o ticket de admissão de uma task cujo processo
  morreu (OOM, SIGKILL, restart do container) ficava aberto, e toda drenagem daquele recurso
  esperava até o timeout. A drenagem agora libera os tickets de processos encerrados. Os
  tickets passam a registrar o pid e o nó de quem os pegou.
- **Índice dos tickets de admissão (#127):** consultas de tickets abertos e da última
  liberação por recurso usam um índice novo `(resource_key, released_at)`.
- **Deploy e registro do host com profiles do compose (#118–#121):** `make deploy BUILD_LIVE=1`
  constrói e acompanha o `worker-live` mesmo sem o profile `live` ativo; o deploy avisa quando
  o `compose build` pularia um serviço sem `build:`; o registro do host aceita `worker-live`,
  `worker-dispatch` e `worker-remote` com os profiles deles e recusa `--use-built-image` para
  o que o deploy não constrói; o agente do host passa o `--profile` explícito.
- **Token do host (#122, #123):** o arquivo de configuração do host, que guarda o token de
  máquina, nasce com modo 0600; um registro que falha no meio não deixa configuração nem
  token órfãos.
- **Frontend (#125, #128):** configuração do ESLint (o lint roda na checagem, não no build da
  imagem) e limpeza dos erros e avisos que ela apontou. Sem mudança de comportamento.

**Correções deste CHANGELOG**
- No 1.14.0, o limite de janela que impede os serviços de subir é o **maior ou igual** a
  `CELERY_VISIBILITY_TIMEOUT_SECONDS`.
- No 1.14.0, `make deploy BUILD_LIVE=1` não construía o `worker-live` quando o profile `live`
  não estava ativo; o #118 corrige isso.

**Rollout**
- **Imagens:** o frontend precisa de rebuild (`package.json` e o OpenAPI embutido mudaram).
  API e workers não mudaram de dependência; o `make deploy` os recria.
- **Migration (#127):** em instalação existente, rode de novo o `upgrade(engine)` do controle
  de engines (passo 1 de `docs/runbooks/engine-control-bootstrap.md`) e confira o índice
  `ix_control_admissions_resource_released`. Nada avisa a falta dele. O DDL espera no máximo
  30 s pelo lock de metadados; se desistir, rode de novo.
- **Agente do host:** o `make deploy` não o reinicia. Depois do deploy:
  `systemctl restart ingestify-engine-host-agent` (#121).
- **Tickets antigos (#129):** tickets gravados antes deste release têm holder `task:<id>` sem
  pid nem nó e não são liberados automaticamente. Depois do deploy, rode a consulta só de
  leitura do runbook de bootstrap (seção "Drenagem que termina em `DRAIN_TIMEOUT`"); libere
  à mão só depois do inspect por nó. O próprio deploy pode criar tickets assim.
- **Serviços gerenciados:** se o compose ou as imagens deles mudaram, re-registre o host com
  `register_engine_host.py --use-built-image` e rode `apply_profile`.
- **Modal:** nenhum arquivo do fingerprint mudou; não há redeploy.

## 2026-10: telemetria e reciclagem do Docling, pré-carga do pipeline e /api-keys sem barra (API 1.14.0)

**Por que é minor:** as linhas de `GET /admin/docling/cold-starts` ganham campos opcionais.
Nenhum campo, código de erro ou endpoint existente muda; o resto são correções e preparação.

**Novo**
- **Telemetria de conversão do Docling (#102):** as linhas de `GET /admin/docling/cold-starts`
  trazem `conversions_first`/`conversions_warm`, `conversions_first_process`,
  `conversions_failed`, `convert_seconds_first`/`convert_seconds_warm`,
  `pages_ok`/`pages_failed` e `docling_version`. O worker registra uma linha
  `docling.conversion` por conversão.
- **Motivo da reciclagem (#108, #109):** o mesmo endpoint diz por que os processos filhos
  saíram (`recycle_memory_limit`, `recycle_max_tasks`, `recycle_shutdown`, `recycle_unknown`),
  quantos sumiram sem encerrar (`processes_vanished`, ex.: OOM do cgroup), `last_exitcode`, os
  limites do pool (`max_memory_per_child_kb`, `max_tasks_per_child`), `peak_rss_pct_of_limit`
  e a memória do cgroup (`cgroup_oom_kill`, `cgroup_memory_peak_kb`, `cgroup_memory_max_kb`).
- **Pré-carga do pipeline (#110):** `DOCLING_INIT_PIPELINE=true` carrega os pesos do PDF ao
  construir o conversor, e a primeira conversão deixa de pagar por isso. Padrão `false`. As
  linhas ganham `wrapper_seconds_total`, `pipeline_init_seconds_total` e
  `pipeline_init_ok`/`pipeline_init_failed`/`pipeline_init_unavailable`.

**Correções**
- **`/api-keys` sem barra final (#115):** `POST` e `GET /api-keys` respondem também sem a
  barra. Antes, o redirect 307 perdia o prefixo do proxy e o navegador saía da API (405 ao
  criar uma key, HTML no lugar da lista). O caminho com barra continua valendo.
- **Memória do cache de conversores (#110):** o conversor mais antigo é descartado antes de
  construir o novo, então dois conjuntos de pesos nunca ficam carregados ao mesmo tempo.
- **Versões do Docling fixadas (#100):** docling 2.87.0, docling-core 2.104.0,
  docling-parse 5.11.0 e docling-ibm-models 3.15.0, as do worker de produção. Um rebuild não
  troca mais o pipeline de conversão por baixo.

**Preparação (spec 0022, ainda sem efeito)**
- Variáveis só lidas e validadas, sem nada que as use: `DOCLING_PAGE_WINDOW`,
  `DOCLING_WINDOW_TIME_LIMIT_SECONDS` (#104), `ADMISSION_MAX_PAGES_PER_PDF`,
  `ADMISSION_MAX_PAGES_PER_CLIENT`, `ADMISSION_MAX_WAITING_PER_CLIENT` e
  `ADMISSION_GLOBAL_SLOTS` (#106). **Não defina nenhuma:** `0` num `ADMISSION_*` ou um limite
  de janela maior ou igual a `CELERY_VISIBILITY_TIMEOUT_SECONDS` impedem os serviços de subir. O
  heartbeat do worker publica a `concurrency` (#105).
- Operação: `make deploy` (#107, #111; runbook em `docs/runbooks/deploy.md`, #112) e benchmark
  HTTP do Docling (#114).

**Rollout**
- **Imagens:** api e worker precisam de rebuild (`requirements-base.txt` mudou); depois,
  confira que o worker continua no docling 2.87.0. O frontend também (o OpenAPI embutido nas
  páginas de docs mudou). O `worker-live` não é reconstruído por padrão: use
  `make deploy BUILD_LIVE=1`, re-registre o host e rode `apply_profile`.
- **Compose:** o `worker` recebe `DOCLING_INIT_PIPELINE` e precisa ser recriado.
- **Serviços gerenciados pelo engine control:** re-registre com
  `register_engine_host.py --use-built-image` e rode `apply_profile`.
- **Primeiro `make deploy`:** sem o marcador `.git/deploy-last-success`, o script para com
  `no deploy marker`; passe `DEPLOY_BASE=<commit hoje em produção>` ou `FORCE_REBUILD=1`.
- **Sem migration.** Nenhuma variável obrigatória nova.
- **Modal:** nenhum arquivo do fingerprint mudou; não há redeploy.

## 2026-10: controle de cold start do Docling e correções de configuração (API 1.13.0)

**Por que é minor:** há um endpoint novo de administração, `GET /admin/docling/cold-starts`.
O resto são correções; nenhum campo, código de erro ou endpoint existente muda.

**Novo**
- **Cold starts do Docling (#97):** cada processo do worker de conversão recarrega os pesos
  (~10 s). Agora isso é medido e controlável:
  - `GET /admin/docling/cold-starts` (permissão `platform.monitoring.read`): últimas 24 h por
    hora e por worker, com motivo (`process_start`, `new_options`, `evicted`), segundos,
    processos iniciados e parados, pico de memória e cold starts por 100 conversões;
  - WARNING no log quando um worker passa de `DOCLING_COLD_START_WARN_PER_HOUR` (padrão 6);
  - `DOCLING_MAX_MEMORY_PER_CHILD_KB` (padrão 5000000) define quando o processo é reciclado
    no overlay GPU; com 3 GB (valor anterior, local) um processo ocioso de ~2,5 GB era
    reciclado a cada ~2 páginas;
  - `DOCLING_CONVERTER_CACHE_SIZE` (padrão 3, antes 2 fixo).

**Correções**
- **Tela do job (#94):** enquanto um PDF dividido converte, `/jobs/<id>` mostra as páginas já
  prontas em ordem, sob um cabeçalho de progresso fixo com a trilha de páginas.
- **Preset no upload (#95):** a tela de conversão sempre envia o preset escolhido. Antes,
  "Fast" ia como ausência de preset e, em URL/Drive/Dropbox, o servidor aplicava
  `DOCLING_ENABLE_*`. Efeito colateral: o primeiro reenvio pela tela de um arquivo
  convertido antes sem preset é processado de novo uma vez.
- **Configuração do compose (#93, #96):**
  - `worker`/`worker-audio` recebem `WHISPER_MODEL`, `WHISPER_DEVICE` e
    `WHISPER_COMPUTE_TYPE`; no overlay GPU, `WHISPER_DEVICE=cpu` tira o áudio da placa
    (sem a variável continua cuda). Um float16 explícito em CPU vira int8 com aviso;
  - `worker-vision` consome `${VISION_QUEUE}` e recebe `REDIS_PASSWORD`;
  - `ELASTICSEARCH_USER`, `ELASTICSEARCH_PASSWORD` e `ELASTICSEARCH_VERIFY_CERTS` chegam aos
    serviços que usam o Elasticsearch.

**Rollout**
- **Imagens:** só o frontend precisa de rebuild (tela do job e preset). API e workers usam o
  código montado: basta recriar, porque o compose mudou (env e `command` do worker).
- **Sem migration.** Nenhuma variável obrigatória nova; todas têm padrão.
- **Antes do deploy neste servidor:** descartar a mudança local de
  `docker-compose.gpu.yml` (`--max-memory-per-child=5000000`), agora versionada como
  `DOCLING_MAX_MEMORY_PER_CHILD_KB`, senão o `git pull --ff-only` falha.
- **Modal:** nenhum arquivo do fingerprint mudou neste release (o redeploy pendente do
  1.12.0 continua valendo).
- **Trocar `VISION_QUEUE`:** esvazie a fila antiga antes e recrie api, worker, beat,
  worker-remote e worker-vision juntos.

## 2026-10: correções de segurança e de confiabilidade (API 1.12.0)

**Por que é minor e não patch:**
- há um código novo que o cliente pode tratar, `AUDIO_SAMPLE_RATE_UNSUPPORTED`;
- a transcrição local passa a recusar áudio acima de `MAX_AUDIO_DURATION_SECONDS`, o que
  antes era aceito.

O resto são correções. Os códigos de erro existentes não mudam.

**Segurança**
- **Dependências de parsing:** python-multipart 0.0.6 → 0.0.31, Starlette 1.3.1 e FastAPI
  0.104.1 → 0.136.3. Um `Content-Type` malicioso em `/auth/login` travava a API antes do rate
  limit (CVE-2024-24762); também ficam corrigidos os DoS posteriores de multipart e de
  formulário urlencoded.
  - Formulários passam a ter limite de 1000 campos e 1 MB por parte que não é arquivo;
    acima disso a resposta é **400**, com `detail` em texto e sem `code`.
  - Um JSON enviado sem `Content-Type` continua aceito.
  - No OpenAPI, os campos de arquivo passam de `format: binary` para `contentMediaType`
    (estilo 3.1), e `ValidationError` documenta `input`/`ctx`. Os itens do 422 deixam de
    trazer o `url` do pydantic, que nunca foi documentado.
- **Drive/Dropbox:** o download é gravado em disco por streaming e para no
  `MAX_FILE_SIZE_MB`. Um arquivo acima do limite falha uma vez só, como `FILE_TOO_LARGE`,
  sem novas tentativas. A fonte por URL também.
- **Áudio:** a decodificação conta as amostras e para no limite de duração, sem confiar
  nos metadados do arquivo. **Mudança de comportamento:** a transcrição local com
  faster-whisper/openai-whisper passa a respeitar `MAX_AUDIO_DURATION_SECONDS` (padrão
  3600 s); antes não havia limite. O WhisperX segue com o próprio limite (7200 s).
  - Áudio acima do limite: `AUDIO_DURATION_LIMIT_EXCEEDED`, e a mensagem informa o limite
    em minutos.
  - Taxa de amostragem abaixo de 8 kHz: o código novo `AUDIO_SAMPLE_RATE_UNSUPPORTED`.
  - Nenhum dos dois casos tem nova tentativa.
  - **Onde o código aparece:** no caminho roteado (fila de engines), em `error` do
    `GET /jobs/{id}` (`CODE: mensagem`) e em `data.error.code` do webhook. No caminho local
    não roteado, o job leva só a mensagem do catálogo, sem código. No Modal, a recusa vira
    `INPUT_REJECTED`, e o limite fica em 3600 s mesmo que `MAX_AUDIO_DURATION_SECONDS` seja
    maior.
- **Datalakes:** respostas de S3/MinIO são limitadas a `DATALAKE_MAX_RESPONSE_BYTES`
  (8 MiB) antes de ir para a memória. Redirects e `Retry-After` não são seguidos, e corpo
  comprimido é recusado. Cada rota responde com o seu 502 que já existia (por exemplo
  `DATALAKE_DISCOVER_FAILED` no discover, `DATALAKE_DESTINATION_UNREACHABLE` no destino de
  imagens).

**Correções**
- **`POST /upload`:** um `docling_preset` desconhecido dá **422 `VALIDATION_ERROR`**, igual
  ao `/convert`. Antes o job era criado com 200 e convertido com os padrões do servidor.
  Campo vazio continua valendo o padrão.
- **CORS:** passa a aceitar `Idempotency-Key`; com UI e API em origens diferentes, as
  operações de imagens e de controle de engines eram bloqueadas no preflight.
- **Event loop:** autenticação, polling de `GET /jobs/{id}` (`/pages`, `/transcript/partial`),
  upload ao MinIO e as leituras de banco do relay ao vivo saem do event loop. O `/health`
  ganha cache de 5 s, chamada única por vez e um 503 de verdade. Travamentos que derrubavam
  sessões ao vivo com `LIVE_BACKPRESSURE`.
- **Retry de página:** o documento é concluído quando a página retentada termina. A
  tentativa antiga saía do MySQL mas continuava na lista do Redis, e o merge nunca começava.
  O merge passa a decidir e a ler as páginas pelo MySQL, e o resultado atrasado de uma
  tentativa substituída é ignorado.
- **Resultado de página expirado:** o merge reconstrói a página a partir do MySQL em vez de
  publicar um documento incompleto como concluído. Quando não dá, o que acontece em jobs com
  assets ou figuras (que só existem no cache), nada é publicado: as páginas perdidas viram
  FAILED ("page result expired; retry the page") e o job fica **PARTIAL**.
- **Retry de Drive/Dropbox:** reutiliza o arquivo já baixado. O token continua sendo apagado
  logo após o download, e o retry não falha mais por falta dele.
- **Transcrição parcial:** o polling não se sobrepõe mais; segmentos não se repetem nem
  somem.

**Interface:** o Live passa para o menu **Labs** (mesma URL `/live`).

**Rollout**
- **Imagens:** precisam de rebuild:
  - API e workers, por causa das dependências novas;
  - worker-live, porque leva o código dentro da imagem;
  - frontend, por causa do menu Labs.
- **Sem pendências de banco ou de configuração:** nenhuma migration e nenhuma variável de
  ambiente obrigatória nova (`DATALAKE_MAX_RESPONSE_BYTES` tem padrão).
- **Áudio acima de 1 h:** passa a falhar no faster-whisper/openai-whisper. Ajuste
  `MAX_AUDIO_DURATION_SECONDS` se isso for necessário.
- **Modal:** precisa de redeploy, porque `whisper_core` faz parte do fingerprint.
- **Exceção na atualização de segurança:** a imagem live-whisperx mantém o próprio lock
  (fastapi 0.116.1, starlette 0.47.3). Ela só serve um WebSocket interno protegido por
  `LIVE_INTERNAL_TOKEN`.

## 2026-10: health check não congela mais a API (API 1.11.1)

- Correção, sem mudança de contrato. `GET /health` e `GET /admin/health/monitoring` eram
  `async def`, mas consultam os workers Celery com uma chamada bloqueante de 1–2 s. A cada
  healthcheck do container a API inteira parava; uma transcrição ao vivo em andamento
  recebia o áudio represado de uma vez e caía com `LIVE_BACKPRESSURE` ou `LIVE_FRAME_RATE`.
  Os dois endpoints passam a rodar fora do event loop.

## 2026-10: API bilíngue, inglês por padrão — parte 4 (API 1.11.0)

- Última parte: administração (`/admin/*`), engines, roteamento, controle de engines, perfis
  de execução, acesso e IAM seguem o `Accept-Language` (inglês por padrão, `pt`/`pt-BR`). Os
  63 códigos de engine/IAM que só tinham português ganharam texto em inglês; não resta
  nenhum código sem os dois idiomas (o teste não aceita mais lista de pendências).
- **`detail` em texto vira objeto** `{"code", "message", "next_steps"}` (o `code` é novo; o
  `message` segue o idioma). Quem casava o texto deve casar `detail.code`:
  - `/admin/*` (monitoramento): 403 `ADMIN_REQUIRED` (era "Acesso negado: privilégios de
    administrador necessários"); 500 `ADMIN_STATS_FAILED`, `STUCK_JOBS_LIST_FAILED`,
    `STUCK_JOBS_RECOVER_FAILED`, `PAGES_RETRY_FAILED`, `CLEANUP_FAILED`,
    `HEALTH_CHECK_FAILED`; 404 `ADMIN_JOB_NOT_FOUND`; fila do broker: 409
    `BROKER_MESSAGE_NOT_ORPHANED`, `BROKER_NO_WORKER_ANSWERED`, `BROKER_TASK_RUNNING` e 404
    `BROKER_MESSAGE_GONE`.
  - Sessão e permissões (todas as rotas que usam `require(...)`): 403 `ADMIN_REQUIRED`, 403
    `LOGIN_SESSION_REQUIRED` (era "...requires a login session (JWT)...", agora um texto
    único), 401/403 `USER_INACTIVE` (era "Inactive user") e `ACCESS_DENIED` (era "Acesso
    negado").
  - `/admin/engines*`: 404 `ENGINE_NOT_FOUND`; 403 `CURRENT_PASSWORD_REQUIRED`; 409
    `VERSION_CONFLICT`, `ENGINE_NO_CREDENTIALS`, `ENGINE_SECRETS_KEY_MISSING`,
    `REMOTE_WORKER_NOT_RUNNING`, `LOCAL_ENGINE_NO_SPEND`, `REMOTE_CAPACITY_EXCEEDED`,
    `ENGINE_NOT_ACTIVATABLE` (mantém `problems`), `ENGINE_STATE_CONFLICT`; 422
    `CAPACITY_EXCEEDED` (mantém `vram`), `INVALID_BUDGET`, `INVALID_CREDENTIAL_FIELDS`,
    `CREDENTIALS_NOT_SUPPORTED`, `INVALID_CONFIGURATION`; 504 `REMOTE_WORKER_TIMEOUT`. O texto
    técnico original (sempre em inglês) vai em `technical`.
  - `/admin/routing/*`: 403 `CURRENT_PASSWORD_REQUIRED`; 409 `VERSION_CONFLICT`; 404
    `ROUTE_NOT_FOUND`; `ROUTE_REJECTED` (o status de antes, em geral 422).
  - `/internal/engine-hosts/.../operations`: o 403 sem corpo vira `HOST_OPERATION_MISMATCH`.
  - IAM: `message` e `next_steps` vêm do catálogo no idioma pedido; o texto específico
    (por exemplo o papel desconhecido) fica em `technical`.
- Os textos de engine-control que voltam em corpos de `GET` (`setup`, `reason`/`message` das
  ações) também seguem o idioma da requisição. `code` e `next_steps` são os mesmos nos dois.
- Interface de administração: as telas de controle de engines, perfis, acesso e IAM seguem em
  português e enviam `Accept-Language: pt-BR`; as telas de computação (engines, GPUs, rotas,
  status) são em inglês e usam o padrão. `ENGINE_SECRETS_KEY_MISSING` ganhou o próximo passo
  `set_server_secret`; a falta de worker-remote ao salvar uma rota responde
  `REMOTE_WORKER_NOT_RUNNING` (409).
- Fora do escopo do P-13: OpenAPI/Swagger, a mensagem de validação do FastAPI e as
  descrições de figuras ([features/languages.md](features/languages.md)).

## 2026-10: API bilíngue, inglês por padrão — parte 3 (API 1.10.0)

- Datalake e imagens passam a responder no idioma pedido em `Accept-Language` (inglês por
  padrão; `pt-BR` mantém a redação anterior). O `code`/`error_code` não muda. Mesmo contrato
  da parte 1; ver [features/languages.md](features/languages.md).
- **Mudança de comportamento: `detail` em texto vira objeto** (`{"code", "message"}`) nas
  recusas de `POST /datalakes/discover`, `/datalakes/buckets`, `/datalakes/partition-preview`,
  `POST/PATCH/DELETE /datalakes` e `/datalakes/{id}/*` (provedor, credenciais, bucket,
  nome, conexão vinculada/desativada, 502 de provedor), de `POST /jobs/{id}/datalake/retry`
  (`DATALAKE_JOB_NOT_COMPLETED` 409, `DATALAKE_DESTINATION_MISSING` 404), da validação de
  destino/particionamento (`DATALAKE_*`, `PARTITION_*`) e das recusas de
  `mode=full` e do upload facial, que agora usam o envelope de `/images/*`
  (abaixo): `IMAGE_IDEMPOTENCY_KEY_REQUIRED` 422, `IMAGE_IDEMPOTENCY_KEY_REUSED` 409,
  `IMAGE_JOB_DELETED` 410, `FLORENCE_NOT_READY` 503, `IMAGE_SUBMISSION_CONFLICT` 503,
  `IMAGE_PERSIST_FAILED` 503, `FACE_UPLOAD_FIELDS_INVALID` 422, `FACE_REQUEST_INVALID` 422,
  e os do destino de datalake (`DATALAKE_NOT_FOUND` 404, `DATALAKE_*` 422). Quem casava o
  texto deve ler `detail.error_code` (em `/images/*`) ou `detail.code` (demais rotas).
- **`/images/*` mantém `error_code` em toda parte:** todas as recusas dessas rotas (inclusive
  `mode=full`, `/images/faces/*` e o destino de datalake) respondem
  `{"detail": {"error_code", "message", "job_id"}}`, inclusive `VISION_TIMEOUT` com
  `poll_url`/`result_url`, `FACE_UNAVAILABLE` com `stages` e `VISION_ENGINE_UNAVAILABLE` com
  `retry_after`; só `message` segue o idioma. Dentro de `/images/*`, a conexão de datalake
  inexistente é `DATALAKE_NOT_FOUND` nesse envelope. Os 404 que não revelam o que existe
  continuam texto, localizado, só em `POST /images/{id}/cancel` (Full Analysis) e nas rotas
  `/datalakes*` (conexão). Mensagens de validação do Pydantic do datalake (`ConnectionConfig`, partições)
  seguem o idioma pedido, no formato de 422 de validação.
- `GET /images/capabilities` devolve `reason` no idioma pedido quando a API não vê worker de
  visão; o `reason` que o worker publica, e o `detail` de falha devolvido pelo worker de
  visão, continuam em inglês.
- Mensagens de `workers/vision` (`VisionError`): inglês, como sempre; as checagens de imagem
  feitas pela API (base64, tamanho, formato) agora saem também em português com `pt-BR`.
  O texto de falha de entrega ao datalake gravado pelo worker (`destination.error` em
  `GET /jobs/{id}/datalake`) sai em inglês (`DATALAKE_DELIVERY_FAILED`); os já gravados
  continuam em português.
- No 422 de validação do FastAPI, o `ctx.error` de um erro de datalake (`DatalakeError`)
  passa a serializar como `{"code", "params"}`; `msg` continua o texto no idioma pedido.

## 2026-10: API bilíngue, inglês por padrão — parte 2 (API 1.9.0)

- Mesma regra da parte 1 (`Accept-Language`, padrão inglês, `code` estável) para as demais
  rotas de job, a autenticação, os limites 429 e a criação de API keys. Restam datalake,
  imagens, admin, engines e IAM (partes 3 e 4), que seguem em português.
- **`detail` em texto vira objeto `{"code", "message"}`** (o status HTTP não muda; quem lia
  o texto passa a ler `detail.message`, ou melhor, ramificar por `detail.code`):
  - `GET /jobs/{id}/result`: 400 `TRANSCRIPT_NOT_PUBLISHED`, 400 `LIVE_SESSION_NOT_COMPLETED`,
    400 `JOB_NOT_FINISHED`, 500 `JOB_FAILED`, 404 `RESULT_NOT_FOUND`,
    404 `TRANSCRIPT_FORMAT_UNAVAILABLE`, 503 `IMAGE_REPORT_PENDING`, 503 `IMAGE_REPORT_UNAVAILABLE`.
  - `GET /jobs/{id}/pages`: 404 `JOB_NO_PAGES`. `GET /jobs/{id}/pages/{n}/status` e `.../result`:
    404 `PAGE_NOT_FOUND_IN_JOB`, 404 `PAGE_STATUS_NOT_FOUND`, 404 `PAGE_RESULT_NOT_FOUND`,
    400 `PAGE_NOT_FINISHED`, 500 `PAGE_FAILED`. `GET .../pages/{n}/pdf`: 404 `PAGE_NOT_FOUND`,
    404 `PAGE_PDF_NOT_FOUND`, 503 `FILE_STORAGE_UNAVAILABLE`.
  - `POST /jobs/{id}/pages/{n}/retry`: 400 `PAGE_NOT_FAILED`, 400 `PAGE_RETRY_LIMIT`,
    404 `MAIN_JOB_NOT_FOUND`, 404 `PAGE_NOT_FOUND_IN_JOB`, 503 `QUEUE_UNAVAILABLE`,
    500 `PAGE_RETRY_FAILED`; o 503 que era `{"code": "DATABASE_UNAVAILABLE"}` sem texto agora traz `message`.
  - `DELETE /jobs/{id}`: 500 `JOB_DELETE_DB_FAILED`. `DELETE /jobs/{id}/source`: 404 `SOURCE_NOT_FOUND`.
  - `GET /jobs`: 422 `JOB_STATUS_INVALID`, 422 `JOB_KIND_INVALID`, 422 `FOLDER_ROOT_NEEDS_PROJECT`,
    422 `FOLDER_NOT_IN_PROJECT`. `GET /search`: 500 `SEARCH_FAILED`.
  - `POST /auth/register`: 400 `EMAIL_ALREADY_REGISTERED`, `USERNAME_TAKEN`, `EMAIL_OR_USERNAME_EXISTS`.
    `POST /auth/login`: 401 `INVALID_CREDENTIALS` (com `WWW-Authenticate: Bearer`), 400 `USER_INACTIVE`.
    `POST /auth/refresh`: 401 `SESSION_INVALID`. Qualquer rota autenticada: 401 `NOT_AUTHENTICATED`
    (com `WWW-Authenticate: Bearer`) e 400 `USER_INACTIVE`. O status 401 não muda, então a
    interface continua encerrando a sessão por ele.
  - 429 `REQUEST_RATE_LIMITED` (limite por IP) e `LOGIN_RATE_LIMITED` (bloqueio de conta), ambos com `Retry-After`.
  - `POST /api-keys`: 422 `LOCATION_PROJECT_AND_ID` e os erros de nome de projeto
    (`PROJECT_NAME_EMPTY`, `PROJECT_NAME_CONTROL_CHARS`, `NAME_TOO_LONG`, `NAME_KEY_TOO_LONG`).
- Continuam **texto**, só que no idioma pedido: os 404 de job (`Job not found`), de job
  expirado (`Job not found or expired`, só para quem é dono), de projeto, pasta e API key.
- Textos de corpo 200 também seguem o idioma: `message` de `POST /upload|/convert|/transcribe`
  (job enfileirado, arquivo já processado, notas de `purge_source`, reprocessamento em outro
  projeto) e de `DELETE /jobs/{id}` e do retry de página.
- Não mudou: o 503 de `GET /health` (corpo de status, sem texto), a validação 422 do FastAPI e
  os `error_message` de páginas gravados pelos workers.

## 2026-10: API bilíngue, inglês por padrão — parte 1 (API 1.8.0)

- O texto legível (`message`) segue o header `Accept-Language`: inglês (padrão) ou
  português (`pt`, `pt-BR`). O `code` não muda. Toda resposta traz `Content-Language` e
  `Vary: Accept-Language`. Detalhes em [features/languages.md](features/languages.md).
- **Mudança de comportamento: o padrão passou de português para inglês.** Clientes sem
  `Accept-Language` (curl, SDKs, scripts) passam a receber mensagens em inglês; para manter
  o português, enviem `Accept-Language: pt-BR`. Quem casava texto deve casar `detail.code`.
- Esta parte cobre as recusas de `/upload`, `/convert` e `/transcribe`, projeto/pasta
  (também em `/images/*` e o 422 de `POST /api-keys`), tags, sessões ao vivo e os 404 de
  job/projeto/pasta/API key (continuam texto, no idioma pedido). As demais rotas (auth, API keys, datalake, imagens, admin, engines, IAM) migram
  nas partes seguintes e seguem em português até lá.
- Sessões ao vivo: os 503 de `POST /transcribe/live/sessions` e o `message` de
  `GET /transcribe/live/sessions/availability` (1.6.0) seguem o idioma pedido; `Retry-After`
  continua. `GET /search` 503 (`SEARCH_UNAVAILABLE`, 1.6.1) e o 422 `INVALID_CALLBACK_URL` (1.7.0)
  também.
- Mensagens de erro de job gravadas pelos workers (`error`) passam a sair em inglês; as já
  gravadas continuam como estão. Mensagens do OpenAPI, validação do FastAPI e descrições de
  figuras não são traduzidas.

## 2026-10: Webhook de conclusão de job (API 1.7.0)

- `POST /upload`, `POST /convert` e `POST /transcribe` aceitam `callback_url` (https). Quando
  o job principal termina, a plataforma envia um `POST` assinado (HMAC-SHA256,
  `X-Ingestify-Signature: t=<unix>,v1=<hex>`) com `job.completed`, `job.failed` ou
  `job.partial`: só metadados, nunca o Markdown. Falhas de rede e 5xx/408/429 são repetidas
  até 6 vezes; 3xx e outros 4xx não. Contrato completo em `docs/features/webhooks.md`.
- Novo `GET /webhooks/signing-secret` (o segredo é por usuário, derivado de
  `WEBHOOK_SIGNING_SECRET` ou, se vazio, de `JWT_SECRET_KEY`). `GET /jobs/{job_id}` ganha o
  bloco `webhook` (host, estado e tentativas da entrega).
- Novo 422 `INVALID_CALLBACK_URL` (URL http, local, privada, com credenciais ou longa demais).
- Colunas novas em `jobs`: `callback_url` e `webhook_state` (alembic `e5c90026a7d3`; também
  criadas no boot). O antigo `callback_url` de `ConvertRequest` e `send_callback`, que nenhuma
  rota usava, foram removidos. Retrocompatível.

## 2026-10: Sem sucesso silencioso (API 1.6.1)

- `GET /search` responde `503` com `{"detail": {"code": "SEARCH_UNAVAILABLE", "message"}}`
  quando o Elasticsearch falha. Antes respondia `200` com `results: []`, indistinguível de
  "nenhum documento encontrado".
- Worker sem Docling instalado **falha** a conversão (`Docling is not available in this
  worker: <erro de import>`, com as retentativas de sempre). Documento único termina
  `failed`; PDF dividido (2 ou mais páginas) divide normalmente, cada página falha após
  as retentativas e o job termina `partial` (`PAGES_FAILED`) com o erro em cada página.
  Antes o job era marcado `completed` com um Markdown de exemplo (Lorem ipsum).

## 2026-10: Disponibilidade da transcrição ao vivo (API 1.6.0)

- `GET /transcribe/live/sessions/availability` diz, sem reservar vaga, se uma sessão
  seria aceita agora: `{"available", "code", "message", "diarization": {...}}`, com os
  mesmos códigos que o `POST` responderia (`LIVE_DISABLED`, `LIVE_NOT_READY`,
  `LIVE_CAPACITY_FULL`, `LIVE_DIARIZATION_NOT_READY`).
- A página `/live` consulta ao abrir e a cada 5 s parada: com o worker fora do ar, avisa
  antes e desabilita "Iniciar microfone"; a identificação de falantes fica desabilitada
  quando não está pronta.
- Os 503 de `POST /transcribe/live/sessions` passam a trazer `message` junto do `code`.

## 2026-10: Códigos de erro na criação de jobs (API 1.5.0)

- Toda recusa de `POST /upload`, `POST /convert` e `POST /transcribe` traz
  `{"detail": {"code", "message"}}`, e o Swagger lista os códigos de cada status
  (*Responses*). Códigos: `INVALID_FILE_FORMAT` (novo: o conteúdo contradiz a extensão,
  ex.: HTML salvo como `.pdf`, que antes era aceito e falhava no worker), `FILE_EMPTY`,
  `FILE_TOO_LARGE`, `FOLDER_LIMIT`, `PROJECT_LIMIT`, `PROJECT_REQUIRED`,
  `PROJECT_ARCHIVED`, `INVALID_LOCATION`, `INVALID_TAGS`, `INVALID_SOURCE_TYPE`,
  `FILE_REQUIRED`, `SOURCE_REQUIRED`, `SOURCE_TOKEN_REQUIRED`, `INVALID_OUTPUT_FORMAT`,
  `UNSUPPORTED_MEDIA_FORMAT`, `TRANSCRIPTION_DISABLED`, `QUEUE_UNAVAILABLE`,
  `DATABASE_UNAVAILABLE` (ganhou `message`), `JOB_CREATE_FAILED`.
- O 422 de validação do FastAPI (todas as rotas) mantém `detail` como lista e ganha `code`
  no topo: `FILE_MISSING` quando o campo `file` não chegou (em geral um upload cortado),
  `VALIDATION_ERROR` nos demais.
- `MAX_FOLDERS_PER_PROJECT` passa de 500 para 10000; `0` nele ou em
  `MAX_PROJECTS_PER_USER` desliga o limite.
- Nas rotas `/images/*`, o limite de pastas/projetos responde `error_code: FOLDER_LIMIT` /
  `PROJECT_LIMIT` (antes `INVALID_LOCATION`), no envelope de sempre.
- Tags inválidas: `INVALID_TAGS` em todas as rotas que aceitam `tags`; em `/images/*` e
  `/images/faces` como `error_code`, no envelope delas.
- **Mudança de comportamento: `detail` em texto vira objeto.** Os erros acima, e os 422 de
  tags em `PUT /jobs/{job_id}/tags` e nas sessões ao vivo, respondiam `{"detail": "texto"}`. Clientes que
  liam `detail` como texto devem ler `detail.message` (a interface web foi ajustada). Os
  404 de projeto/pasta e os 401/403 de autenticação não mudam.

## 2026-10: Saída em Markdown nas rotas de imagem (API 1.4.0)

- As oito rotas de imagem (`/images/describe`, `/images/ocr`, `/images/analyze`,
  `/images/faces` e as variantes `/upload`) aceitam `output_format`: `json` (padrão, o
  corpo de sempre, byte a byte) ou `markdown`. Com `markdown`, a resposta síncrona de
  sucesso (200) é `text/markdown; charset=utf-8`; 202 (enfileirado), 504 e erros
  continuam JSON. Valor fora de `json|markdown` responde 422.
- O formato fica gravado no job (`configuration.options.output_format`, só quando
  `markdown`) e é o padrão de `GET /jobs/{job_id}/result`; `?format=json` ou
  `?format=markdown` escolhem na leitura. Em full/faces, `?format=json` continua sendo o
  relatório sem envelope. Formatos de transcrição num job de imagem respondem 422
  `IMAGE_RESULT_FORMAT_UNSUPPORTED`; formato desconhecido, `RESULT_FORMAT_INVALID`.
- `output_format` não entra na Idempotency-Key de full/faces: repetir a chave com outro
  formato devolve o mesmo job, apenas renderizado no formato pedido.
- Renderização em `backend/shared/vision_markdown.py` (determinística; o texto do modelo
  é escapado e nunca abre HTML nem estrutura Markdown; nunca inclui `image_base64`).
- Interface: o job de imagem tem "Download Markdown" / "Download JSON" com o resultado
  servido pela API.
- **Mudança de comportamento: `?format=markdown` em jobs de imagem.** Até a API 1.3.0,
  `GET /jobs/{job_id}/result?format=markdown` de um job de imagem (describe, ocr, analyze,
  full, faces) devolvia o envelope JSON padrão; agora devolve o Markdown renderizado
  (`text/markdown; charset=utf-8`). Afeta clientes que mandavam `?format=markdown` a jobs
  de imagem e liam a resposta como JSON (a interface web fazia isso e foi ajustada).
  Migração: use `?format=json` (em describe/ocr/analyze, o mesmo envelope; em full/faces,
  o relatório sem envelope, como antes) ou omita `?format=` num job criado sem
  `output_format=markdown` para receber o envelope padrão. Transcrições e documentos não
  mudam.
- **Mudança de comportamento: `?format=` inválido.** Um formato desconhecido em
  `GET /jobs/{job_id}/result` (qualquer tipo de job) responde 422 com o objeto do catálogo
  de erros (`detail: {code: "RESULT_FORMAT_INVALID", message, next_steps}`) em vez de uma
  string em `detail`. Clientes que liam `detail` como texto devem ler `detail.message`.

## 2026-10: Descrição e OCR das figuras no Markdown (API 1.3.0)

- `POST /upload` e `POST /convert` aceitam `describe_images` e `ocr_images` (padrão
  `false`): cada figura do documento é descrita (Florence-2, **em inglês**) e/ou tem o
  texto lido (`<OCR>`) no worker de visão, e o texto entra no Markdown num blockquote
  logo depois da figura (`> **Figure (description, English):** …`,
  `> **Text in figure (OCR):** …`). Só figuras, nunca páginas renderizadas; imagens
  iguais são analisadas uma vez; limites `CONVERSION_FIGURE_MAX_COUNT`,
  `CONVERSION_FIGURE_TIMEOUT_SECONDS`, `CONVERSION_FIGURE_STALL_SECONDS`.
- Nova etapa depois da conversão/merge (`workers/figure_tasks.py`), sem nenhum worker de
  conversão esperando pela visão; o job fica `processing` (90–99%) até o texto entrar e o
  `purge_source` só roda depois disso. Falha de uma figura não derruba o job.
- Resultado: `figures_described`, `figures_ocr`, `figures_skipped`; `assets[].description`
  e `assets[].ocr_text`. As opções entram no `operation_key` só quando `true`.
- `POST /convert` aceita `docling_preset`. `/convert` (interface) reúne todas as opções de
  PDF num grupo "PDF options".
- Robustez da etapa: marcador durável `jobs.figures_stage`/`figures_stage_at` (migração
  `d4b80025f6c2`) que o monitor de jobs travados respeita (um job na etapa é completado,
  nunca falhado); figuras com prioridade 9 na fila de visão (as rotas interativas saem
  antes) e no máximo `CONVERSION_FIGURE_WINDOW` por job em voo, colocadas na rota de
  visão na hora do envio, com backoff; finalize que falha completa com placeholders;
  saídas públicas de página sem marcadores; limite de figuras temporárias por documento.

## 2026-10: PDFs com avisos do qpdf não falham mais na divisão

- O qpdf sai com código 3 quando conclui com avisos (ex.: tabela de referências cruzadas
  danificada que ele reconstrói). O divisor tratava isso como falha e o job terminava com
  `SPLIT_FAILED`. Agora todas as chamadas usam `--warning-exit-0` (avisos vão para o log),
  a contagem e a extração caem para PyPDF2 quando o qpdf falha de verdade, e cada página
  extraída é validada (abre e tem exatamente 1 página).
- A mensagem de `SPLIT_FAILED` deixou de pedir para reenviar o mesmo arquivo.

## 2026-10: Pool de conexões do banco esgotava sob carga (correção)

- Rotas de imagem com `wait=true` (`/images/describe`, `/images/ocr`, `/images/analyze` e
  `/images/faces`, inclusive `mode=full`) seguravam uma conexão do pool durante toda a
  espera pelo Celery (até `VISION_REQUEST_TIMEOUT_SECONDS`). Uma rajada de chamadas
  esgotava as 15 conexões da API e o resto do app travava esperando (`QueuePool limit ...
  reached`). Agora a sessão é fechada antes da espera, e a análise completa/faces consulta
  o job com sessões curtas fora do event loop.
- Pool configurável por processo: `DB_POOL_SIZE` (20), `DB_MAX_OVERFLOW` (20),
  `DB_POOL_TIMEOUT` (15 s). O MariaDB do dev foi para `max_connections=500`.

## 2026-10: Páginas públicas de funcionalidades (/features)

- Novas páginas públicas em inglês: `/features` (índice), `/features/documents`,
  `/features/audio-video` e `/features/images`, com metadata (title, description,
  canonical, OpenGraph `en_US`), exemplo `curl` com os endpoints e campos reais e links
  para os tópicos de `/docs` via `docsHref`.
- Conteúdo derivado do código e de `docs/features/*`: presets Docling (`fast`/`balanced`/
  `quality` só em `/upload`), páginas de PDF e retry, `image_mode`/`page_images`,
  `purge_source`, dedup; `POST /transcribe` (faster-whisper `turbo` por padrão, formatos
  markdown/srt/vtt/txt/json, live e diarização apenas quando habilitados); as 15 tarefas
  Florence-2 de `GET /images/capabilities`, `wait`, Full Analysis, faces (desligado por
  padrão) e entrega em datalake só para Full Analysis/faces.
- Header público ganha o link **Features**; `app/sitemap.ts` lista as quatro rotas.
- Testes: `frontend/tests/feature-pages.test.cjs` (slugs de docs, tarefas iguais a
  `vision_capabilities.py`, header e sitemap) e `public-navigation-browser.py` estendido.

## 2026-10: Imagens da conversão na interface e no portal /docs

- `/convert`: documentos ganham "Extract images" (`image_mode=referenced`) e "Render each
  page as an image" (`page_images=true`, com a orientação de usar em slides, escaneados e
  páginas que são uma imagem só), nas quatro abas, e o aviso de retenção ligado a "Don't
  keep the original file after converting" (as imagens ficam `ASSET_RETENTION_SECONDS`, ou
  até "Delete original files"). As abas URL / Google Drive / Dropbox deixam de mostrar
  "coming soon" e enviam para `POST /convert`; `jobsApi.convert` manda o token do provedor
  no header `X-Source-Token` (o campo `auth_token` que enviava era ignorado pela API) e as
  opções de imagem.
- Página do job: aba "Images" com miniaturas carregadas com a credencial da sessão (o
  mesmo loader do Markdown, agora `hooks/use-asset-url.ts`), página/tipo/dimensões/tamanho,
  download de cada PNG, "Download all (.zip)" (ZIP sem compressão gerado no navegador),
  `assets_expire_at`, figuras puladas (`assets_skipped`) e o estado de apagadas (410). O
  botão "Delete original files" e a confirmação dizem que as imagens extraídas também são
  apagadas; depois que o original já foi apagado, o botão vira "Delete extracted images"
  enquanto `assets_available`. Um PDF `partial` deixa de aparecer como "Waiting in the
  queue…".
- Portal /docs (pt/en): campos de `assets[]` lidos do schema OpenAPI, `assets_available` /
  `assets_expire_at` em "Acompanhar o job", ETag/304/404/410/503 da rota de assets, retenção,
  `DELETE /jobs/{id}/source` apagando as imagens (`assets_deleted`), erros novos, a receita
  "PDF → imagens → descrição/OCR" com curl, deduplicação por sha256 nas rotas de imagem e
  tentativas de `Idempotency-Key`. Removidos: a seção de imagens morta de `MediaSections`
  (dizia que o resultado de visão não persistia), "trocar o preset no reenvio não força
  outra conversão" (o preset faz parte da chave) e "as abas URL/Drive/Dropbox ainda não
  concluem o envio".

## 2026-10: Imagens da conversão de documentos (API 1.2.0)

- `POST /upload` e `POST /convert` ganham `image_mode` (`none` padrão | `referenced`) e
  `page_images` (padrão `false`). `referenced` liga `generate_picture_images`, guarda cada
  figura do Docling como PNG (`assets/{job_id}/p{pág:04d}-img{idx:02d}-{sha12}.png` no bucket
  de resultados) e o Markdown a referencia (`![Image](/jobs/{job_id}/assets/{name})`, via
  `ImageRefMode.REFERENCED`); `page_images` renderiza cada página do PDF (pypdfium2).
  Com os padrões o Markdown é idêntico ao de antes.
- `GET /jobs/{id}/result`: `result.assets[]` (`name`, `kind` `picture`|`page`, `page`,
  `bbox`, `sha256`, `mime`, `width`, `height`, `size_bytes`, `url`), em ordem de página, e
  `result.assets_skipped`. PDF dividido: cada página extrai com o número absoluto, o merge
  concatena sob o job principal e aplica os limites do job.
- Nova rota `GET /jobs/{job_id}/assets/{name}` (`jobs.read`): PNG em streaming, `ETag`
  sha256, `Cache-Control: private`, `304`; só nomes do manifesto do job (`404
  ASSET_NOT_FOUND`); `410 SOURCE_PURGED` (`cause: ASSETS_PURGED`) depois de apagadas.
- `purge_source`: as imagens não são apagadas no fim do job; expiram
  `ASSET_RETENTION_SECONDS` (3600) depois, pela task `workers.image_full_tasks.reconcile`.
  `DELETE /jobs/{id}/source` as apaga na hora (`assets_deleted` na resposta) e
  `DELETE /jobs/{id}` também. `GET /jobs/{id}` informa `assets_available`/`assets_expire_at`.
- Dedup: as opções de imagem entram no `operation_key` (só quando não são o padrão).
- Novas colunas `jobs.assets_manifest`, `assets_expire_at`, `assets_deleted_at` (alembic
  `c3a70024e5b1`, também adicionadas no boot). Novas variáveis `CONVERSION_IMAGES_SCALE`,
  `CONVERSION_PAGE_IMAGE_DPI`, `CONVERSION_ASSET_MIN_PX`, `CONVERSION_ASSET_MAX_COUNT`,
  `CONVERSION_ASSET_MAX_TOTAL_MB`, `ASSET_RETENTION_SECONDS`.
- `info.version` 1.1.0 → **1.2.0** (contrato cresceu de forma compatível).
- Revisão: `image_mode=none` não muda mais a escala das figuras (`CONVERSION_IMAGES_SCALE`
  só com `referenced`); orçamento do job por PDF dividido reservado no Redis antes de
  codificar/enviar (o merge segue como autoridade); limites checados antes de codificar e
  de renderizar; job `failed`/`partial` sem manifesto lista o que existe ou apaga o
  prefixo; manifesto gravado antes de publicar (sem URL sem manifesto); expiração com lock
  Redis e adiamento de falhas; `DELETE /jobs/{id}/source` registra as imagens antes da
  origem; resultado de página só com os campos públicos; dedup ignora jobs cujas imagens
  expiram logo; a interface carrega as imagens com a credencial.
- Teste `test_compose_passes_iam_mode_wherever_engine_access_enabled_goes` considera só os
  `docker-compose*.yml` versionados (overlays locais não rastreados não o quebram mais).

## 2026-10: OpenAPI/Swagger e portal de docs atualizados (API 1.1.0)

Só documentação e metadados: nenhuma rota, status, campo ou esquema mudou
(`operationId`s e `components.schemas` idênticos).

- `info.version` 1.0.0 → **1.1.0**. Primeira mudança desde 1.0.0: o contrato só cresceu
  de forma compatível (projetos, IAM, `purge_source`, análise de imagem, live...), então
  é um *minor*; pular para outro número inventaria versões que nunca existiram. `GET /`
  passa a ecoar `app.version` em vez de um "1.0.0" fixo.
- `info.description` reescrita: visão geral, autenticação (JWT × `X-API-Key`, root e
  `GET /auth/setup`/`ROOT_SETUP_TOKEN`), permissões IAM, projetos, estados do job
  (`pending`/`queued`/`processing`/`completed`/`partial`/`failed`/`cancelled`),
  `purge_source` e `DELETE /jobs/{job_id}/source`, `Idempotency-Key` com tentativas,
  formato do corpo de erro (`code`/`message`/`next_steps`/`cause`/`technical`) e limites
  de taxa. Vive em `backend/api/openapi_docs.py`.
- `tags` declaradas (`openapi_tags`) com descrição e ordem do Swagger; nova tag `Status`
  para `GET /` (antes sem tag, no grupo "default") e `GET /health` (antes em Conversion).
- Resumos (`summary`) de todas as 138 operações em português (121 alterados).
- Descrições de `bearerAuth`/`apiKeyAuth` explicam o Authorize e quando a API key não vale.
- `docs/api-reference.md` agrupa as operações na ordem das tags e mostra a descrição de cada uma.
- Portal (`frontend/app/docs`): autenticação com root/`GET /auth/setup`; "Acompanhar o job"
  com os sete estados (lidos do enum do snapshot) e os campos `source_*`; "PDF e
  documentos", "Páginas de PDF", transcrição e os guias de imagem com `purge_source`,
  `DELETE /jobs/{id}/source`, 410 `SOURCE_PURGED`/409 `SOURCE_NOT_AVAILABLE` e as
  tentativas da `Idempotency-Key`; "Erros" com o corpo `code`/`message`/`next_steps`/
  `cause`/`technical`; "Acesso RBAC e ABAC" vira "Acesso e permissões (IAM)" (mesmo slug
  `engine-access`) com o modelo atual; "Configurações da plataforma" deixa de citar
  `/auth/registration-settings` e `/admin/settings`, que não existem; link para o ReDoc
  ao lado do Swagger e do OpenAPI JSON.
- `tests/test_openapi_metadata.py`: toda operação tem tag declarada e resumo; Swagger e
  ReDoc carregam atrás de `root_path=/api`.

## 2026-10: Raiz do repositório enxuta

- Scripts de desenvolvimento movidos para `scripts/dev/`: `start.sh`, `rebuild.sh`, `infra.sh`,
  `run_api.sh`, `run_worker.sh`, `stop_api.sh`, `validate-frontend.sh`. Os alvos do `Makefile`
  (`make start`, `make rebuild`, …) não mudam; os scripts funcionam de qualquer diretório.
- Removidos testes manuais obsoletos da raiz: `test_auth.sh`, `test_pagination.sh`,
  `test_upload_apikey.sh`, `test_conversion_flow.py` (cobertos pela suíte `pytest` e por `scripts/`).
- Os `docker-compose*.yml` ficam na raiz: o host agent fixa o caminho e o hash de cada um.

## 2026-10: `purge_source` nas rotas de imagem

- As oito rotas de imagem aceitam `purge_source` (padrão `false`): form em
  `/images/describe/upload`, `/images/ocr/upload`, `/images/analyze/upload`,
  `/images/faces/upload`; campo JSON em `/images/describe`, `/images/ocr`,
  `/images/analyze` e `/images/faces`. Está no contrato OpenAPI.
- Com `true`, toda cópia guardada da imagem original é apagada quando o job termina
  (`completed`, `failed`, `partial` ou `cancelled`): handoff local, `images/{job_id}/source`
  e prévias normalizadas da Full Analysis/rostos, e a imagem embutida no resultado
  (`image.image_base64`, que os workers já gravam como `null`). O resultado da inferência
  fica. Grava `jobs.purge_source` e `jobs.source_deleted_at` (sem migração nova).
- `GET /jobs/{id}` passa a reportar `source_available`/`source_deleted_at`/`source_deletable`
  corretamente para jobs de imagem, e `DELETE /jobs/{id}/source` funciona neles (`404` sem
  cópia, `409` em processamento).
- O valor devolvido pelas tasks de visão ao backend do Celery não carrega mais a imagem.
- Full Analysis/rostos: `purge_source` fica fora do fingerprint da `Idempotency-Key`;
  repetir a chave com outro valor devolve a tentativa existente sem alterá-la.
- Front: a opção "Don't keep the original file after processing" aparece também para imagens.
- Purge de imagem que falhou (armazenamento fora) é refeito pela task periódica
  `workers.image_full_tasks.reconcile` (até 20 jobs por minuto, idempotente).
- Worker de Full Analysis que perdeu o lease não deixa mais a prévia em tamanho real para
  trás; `source_available`/`DELETE /jobs/{id}/source` listam `images/{id}/source`,
  `images/{id}/preview/` e relatórios não selecionados, e consideram o resultado no Redis.

## 2026-10: Guardar ou apagar os arquivos de origem de documentos

- `POST /upload` e `POST /convert` aceitam `purge_source` (form, padrão `false`; mesmo
  nome e sentido do `/transcribe`). Com `true`, os **arquivos de origem** — o original
  (MinIO `uploads/…` e cópias locais, inclusive o download de URL no diretório de
  trabalho) e os PDFs por página de um PDF dividido (`pages/{job_id}/…`) — são apagados
  quando o job MAIN termina de vez: `completed`, ou `failed`/`partial` **depois de
  esgotadas as tentativas automáticas**; nunca com retry ou página pendente. O Markdown
  fica. A opção e a data ficam nas colunas `jobs.purge_source` e `jobs.source_deleted_at`
  (a opção pedida no próprio request também aparece na configuração solicitada). Falha ao
  apagar não muda o job.
- **Migração aditiva Alembic `b8f20022e1c4`** (head única; também no boot por
  `_add_missing_columns`): colunas `jobs.purge_source`, `jobs.source_deleted_at`,
  `jobs.operation_key` e índice único `uq_pages_job_page (job_id, page_number)`. A migração
  remove antes linhas de página duplicadas (fica a `COMPLETED`, senão a mais recente); o
  boot não apaga nada e pula o índice se houver duplicatas.
- Contabilidade de purge/dedup (`operation_key`, `source_deleted_at`, `purge_source` vindo
  de uma duplicata) **não aparece mais** em `GET /jobs/{id}.configuration` nem em
  "Configuração solicitada"; os campos `source_*` de `GET /jobs/{id}` continuam.
- Split que esgota as tentativas marca o job MAIN `failed` (mensagem `SPLIT_FAILED`) e
  aplica `purge_source` (antes: `processing` para sempre, `DELETE /source` 409 para
  sempre). Um retry do split reaproveita as linhas `pages` (e os page job ids) da
  tentativa anterior e não reenfileira página que já começou.
- Retry automático que não pôde ser publicado (broker fora) marca o job `failed` (ou a
  página `failed`) com `RETRY_NOT_QUEUED`, em vez de `pending` para sempre.
- Monitoramento: `detect_stuck_jobs` agora grava de fato no MySQL (antes alterava objetos
  de uma sessão fechada); página travada → `failed`, recontagem do pai (`partial`) e
  `purge_source`. `auto_retry_failed_pages` reenfileira de verdade pelo mesmo caminho do
  retry manual (antes deixava a página `pending` sem fila); job sem original é pulado.
- **Mudança de contrato:** `POST /admin/jobs/{job_id}/retry-all-failed` reenfileira cada
  página `failed` (mesmo caminho do retry manual, sob o lock do job) e põe o job em
  `processing`; resposta com `pages_retried` e `page_job_ids` (sai
  `pages_marked_for_retry`/`note`); `404` para job inexistente; `409 SOURCE_NOT_AVAILABLE`
  sem mudar nada se o original foi apagado.
- `recount_parent_pages` lê o pai com `SELECT … FOR UPDATE` e as páginas com leitura
  bloqueante: recontagens concorrentes não gravam contagens velhas.
- Frontend: a lista de páginas e o aviso de fila tratam `partial` como estado final (antes
  a página do job consultava para sempre).
- **Mudança de comportamento:** depois do apagamento o retry manual de página responde
  `409 SOURCE_NOT_AVAILABLE` sem mudar nada (antes: página presa em `pending` e `500`), e
  `GET /jobs/{id}/pages/{n}/pdf` responde `410 SOURCE_PURGED` com a data.
- Nova rota `DELETE /jobs/{job_id}/source` (`jobs.delete`): apaga os arquivos de origem
  de um job terminado (documento ou áudio) e responde `{job_id, source_deleted: true,
  source_deleted_at}`; `404` sem arquivos ou de outro usuário; `409 JOB_STILL_PROCESSING`
  enquanto o job, um retry automático ou uma página está pendente.
- `GET /jobs/{job_id}` ganha `source_available`, `source_deleted_at` e `source_deletable`
  (todos do MySQL).
- **Mudança de comportamento (status):** um PDF dividido cujas páginas terminaram todas,
  com alguma falha definitiva, passa a **`partial`** ("N de M páginas falharam…") em vez
  de ficar `processing` para sempre; o retry de página o reabre (`processing`). Entre
  tentativas automáticas, `process_conversion` deixa o job `queued` (antes `failed`), a
  página espera como `pending` (antes `failed`) e o merge mantém o job `processing`.
- **Mudança de comportamento (deduplicação):** a chave inclui a operação (preset do
  Docling numa conversão, perfil numa transcrição); jobs de imagem nunca são devolvidos;
  jobs `failed` **ou `partial`** nunca são devolvidos (reenviar é a nova tentativa). Com
  `purge_source=true` a duplicata passa a apagar a origem (na hora se já terminou); com
  `false`, uma duplicata sem origem (ou que vai apagá-la) não é reaproveitada. A resposta
  de `/upload`, `/convert` e `/transcribe` ganha `duplicate` e `source_available`.
  Consequência: `/upload` (preset padrão `fast`) e `/convert` (sem preset) **não
  deduplicam mais entre si** — o mesmo arquivo enviado aos dois cria dois jobs.
- `DELETE /jobs/{job_id}` passa a apagar o original de qualquer job no bucket certo
  (antes: só transcrições, e sempre no bucket de áudio) e os PDFs por página.
- `/transcribe` grava `purge_source` também em `job_configurations` e apaga o áudio
  também quando a transcrição falha de vez.
- **Idempotency-Key por tentativa** (`/images/analyze` `mode=full` e rostos): uma chave
  cuja última tentativa terminou `failed` cria a tentativa seguinte (job novo) em vez de
  devolver o job falho; respostas trazem `attempt`. Migração aditiva Alembic
  `a7d30021c5e9` (`image_analysis_submissions.attempt`, também em `_ADDED_COLUMNS`).
- Frontend: caixa "Don't keep the original file after converting" no formulário de
  arquivo; botão "Delete original file" habilitado por `source_deletable`; "Original files
  deleted on …"; retry de página escondido (com explicação) sem original; aviso de
  duplicata no upload. Não há a opção nas abas URL/Drive/Dropbox (não guardam original).
- `scripts/dev/start.sh` mostra o próprio caminho (`./scripts/dev/start.sh`).

## 2026-10: Spec 0020 — perfis de execução padrão na instalação

- O root cria e publica um perfil `Padrão — <modelo>` por modelo aprovado do catálogo e
  um perfil `<engine> — <feature>` por binding configurado, e vincula este último quando a
  engine/feature ainda não tem perfil desejado. Roda na criação do root, em todo boot da
  API com root, quando um host agent se registra ou volta, e por
  `scripts/seed_execution_profiles.py` / `python -m shared.access.seed` (`--dry-run`).
- **Mudança de comportamento:** engines vinculadas pela semeadura passam a "gerenciadas"
  (escritores legados de capacidade exigem operação), e engines sem atributos recebem o
  ambiente da instalação. Nada é aplicado, implantado ou reservado.
- O perfil de engine semeado antes de poder ser vinculado é conferido com a configuração
  atual da engine antes do vínculo: se só a semeadura mexeu nele, ganha revisão nova; se um
  admin mexeu, `SEEDED_PROFILE_STALE`. Perfis locais apontam para o host que serve a
  feature/GPU (`HOST_AMBIGUOUS` com mais de um); cooldown segue o `scaledown_window` da
  engine; `ENVIRONMENT` desconhecido ⇒ `ENVIRONMENT_UNKNOWN` (antes contava como
  production); a classificação da engine só é gravada junto com o vínculo.
- O cadastro do root agenda a semeadura em background (a resposta não espera o lock do
  epoch). Mudança de manifest no heartbeat re-semeia no máximo uma vez por minuto por host.
- `register_engine_host.py` valida e prepara o JSON num arquivo temporário (fsync), guarda
  `<arquivo>.bak` e reescreve o alvo no lugar (mesmo inode); arquivo novo nasce `0600`
  com `O_EXCL` (`--identities-group 10001` o deixa `0640`). A API tenta de novo uma vez
  quando lê um JSON parcial.
- **Mudança visível ao cliente (API):** `POST /admin/engines/{id}/operation-plans` com capability
  desabilitada responde `422 RUNTIME_PROFILE_REQUIRED` / `403 ACCESS_DENIED` (antes `503`);
  cooldown sem perfil desejado responde `409 NOTHING_TO_COOL_DOWN`. Nas rotas de controle,
  perfis/acesso e IAM, `detail.message` agora é sempre em português (catálogo único) e vem
  com `next_steps`; `detail.code` não mudou. Ver
  [execution-profiles](features/execution-profiles.md#corpo-de-erro).
- Sem `IAM_MODE=enforce` a semeadura não faz nada (`ACCESS_NOT_ENABLED`). Ver
  [execution-profiles](features/execution-profiles.md#perfis-padrão-da-instalação-spec-0020).

## 2026-10: Spec 0019 — usuário root na primeira inicialização

Ver a spec 0019.

- **A primeira conta cadastrada numa instalação sem nenhum usuário vira root** (`users.root_slot = 1`,
  `is_admin = true`), único por índice único e irrevogável pela aplicação. Migration
  `f1c90019d3e4` (depois de `d4e80018a2b6`); a coluna também é criada no boot.
- **Mudança de comportamento:** numa instalação **nova** (sem usuários) com
  `ENVIRONMENT=production` e sem `ROOT_SETUP_TOKEN`, o cadastro fica fechado
  (`403 ROOT_SETUP_TOKEN_REQUIRED`) até o token ser configurado. Instalações com usuários não
  mudam; designe o root com `make_admin.py --root`. O compose repassa `ROOT_SETUP_TOKEN` à API.
- `GET /auth/setup` (público, com `root_pending`), `is_root` em `/auth/me`, `make_admin.py --root`.
- `PUT /admin/access/subjects/{id}/state` recusa desativar ou rebaixar o root (`409 ROOT_IMMUTABLE`).

## 2026-10: Spec 0018 — IAM: convergência do RBAC/ABAC de engines (0009)

Ver a spec 0018 e a
[seção 6 do runbook](runbooks/execution-profiles-access.md#6-convergência-no-iam-spec-0018).

- **Grants de engines viram `iam_bindings`** da família `engines`, com o **mesmo id** do grant
  (decisões e auditoria que citam `grant_id` continuam válidas). A decisão da 0009 não muda:
  `policy.authorize`, "um grant satisfaz integralmente", vários grants do mesmo papel,
  delegação por envelope, epoch e admissão de efeito. Papéis de plataforma e de engines nunca
  se enxergam (`/iam/check`, `platform_roles` e `ROLE_ABOVE_GRANTOR` ignoram engines).
- **Migration `d4e80018a2b6`** (depois de `03e70014b8c5`): colunas `permissions`,
  `condition_ref`, `delegation`, `parent_id`, FKs e índice `ix_iam_bindings_subject_role` em
  `iam_bindings`; cópia + reconciliação + validação sob o lock do epoch; marcador
  `0018_engine_bindings`. A reconciliação roda também a cada boot da API e dos workers e só
  restringe. Gate antes do deploy: `python -m shared.iam.engine_equivalence` (ou
  `scripts/iam_engine_equivalence.py`) com 0 divergências.
- **`access_role_grants` vira espelho só-escrita** para rollback: toda concessão/revogação de
  engines grava a linha de mesmo id na mesma transação. O downgrade aplica nela o mais
  restritivo antes de apagar os bindings `engines`.
- **Flag:** `IAM_MODE=enforce` liga o acesso de engines; `ENGINE_ACCESS_ENABLED` vira alias
  depreciado que, quando definido (`true`/`false`), vence com aviso no boot; vazio = não
  definido. `ENGINE_ACCESS_ENABLED=false` continua sendo a alavanca de emergência. Os compose
  files passam `IAM_MODE` e `ENGINE_ACCESS_ENABLED` (default vazio) a todos os processos que
  decidem engines, e cada um registra `engine_access_enabled=` no boot. **Atenção:** antes
  desta release `ENGINE_ACCESS_ENABLED` ausente valia `false`; agora segue `IAM_MODE`. Uma
  instalação com `IAM_MODE=enforce` e a variável ausente (nunca ligou engines, ou desligou
  apagando a linha) passa a ligar o enforcement de engines e a exigir o esquema da 0009, e
  os grants ativos de `access_role_grants` voltam a valer: fixe `ENGINE_ACCESS_ENABLED=false`
  ou revise/revogue esses grants antes do deploy (runbook §6.1).
- **InnoDB:** as leituras com lock da família `engines` travam bindings só pela chave
  primária (sem gap): uma admissão de efeito de um filho delegado não entra mais em deadlock
  com uma concessão de plataforma ao dono do pai. Conceder e revogar papéis `engines` leem
  autoridade e delegação com lock, vendo uma revogação do pai mesmo com snapshot antigo.
  Testes opt-in em MySQL (`ENGINE_CONTROL_TEST_DATABASE_URL`) para concorrência e para o
  round trip da migração.
- **Boot:** com `IAM_MODE` diferente de `off` (inclusive `shadow` com engines desligado) ou
  engines ligado, a API não sobe sem a migração da 0018 (colunas, FKs, índice), e esta exige a
  migração da 0009 mesmo em instalações só com IAM de plataforma.
- **API:** `/admin/iam/bindings*` administra as duas famílias, com regras por família
  (corpo ganha `permissions`, `condition_ref`, `delegation`; resposta ganha `family` e
  `parent_id`). `/admin/access/grants*` ficam como aliases **depreciados** com o contrato da
  0009, só para papéis de engines.
- **Mudança intencional:** autoconcessão de papel de engines passa a ser recusada
  (`422 SELF_GRANT`) nas duas rotas.
- **Auditoria:** concessões e revogações das duas famílias gravam `iam.binding.grant` /
  `iam.binding.revoke` em `target_type="iam_binding"`; linhas antigas (`access`) intactas.
- **Frontend:** uma tela **Admin → Acesso** (`/admin/access`) com abas Concessões, Políticas,
  Atributos de engine, Recursos e Principais de instalação; `/admin/platform-access` redireciona
  para ela e o menu tem um item "Acesso".

## 2026-10: Spec 0014 — IAM: núcleo de decisão e papéis de plataforma

Ver a spec 0014.

- **`IAM_MODE`** (`off` | `shadow` | `enforce`, padrão `off`). Em `off` as rotas da API decidem
  pela regra legada (`is_effective_admin`, dono do recurso) e os bindings ficam inertes; `shadow`
  decide pelo legado e registra `iam_shadow_divergence` no log; `enforce` decide por
  `shared/iam/decide.py`. Antes de `enforce`, rodar `scripts/iam_equivalence.py` contra o
  snapshot (CA3): precisa sair com 0 divergências.
- **Migration `a1c40014e7b2` (`iam_bindings`)**: aditiva, só `CREATE TABLE iam_bindings`
  (marcador `0014_iam_bindings` em `app_migrations`). Nenhuma tabela da 0009 muda.
- **Mudança intencional (CA10):** `user_period_limit_usd` vale também em rotas com
  `remote_allowed_for=admins`, **bootstrap incluído**. Jobs de admins em rotas restritas passam a
  receber recusa `user_cap` quando o teto da rota é atingido; antes gastavam sem teto.
- **Mudança intencional (CA9):** o dispatcher decide `engines.remote.use` do dono a cada placement
  remoto em rota `admins`, em vez de confiar só no `remote_allowed` gravado no submit. Rebaixar um
  admin (ou revogar o binding) alcança páginas já enfileiradas: vão para o caminho local ou seguem
  `on_no_engine`. Isso e o CA10 **não dependem de `IAM_MODE`**: em `off` o dispatcher usa a regra
  legada, mas a cada placement.
- `/auth/me` ganha `bootstrap` e `platform_roles`; `permissions` passa a incluir as permissões de
  plataforma. Novas rotas `/iam/permissions`, `/iam/check` e `/admin/iam/bindings*`.
- Na UI de roteamento, `remote_allowed_for=admins` aparece como "restricted (needs the remote engine
  permission)".

## 2025-10-01: Job Hierarchy Architecture + CLI Tests

### ✅ Endpoint de Upload Ajustado (Adicionado)

#### Melhorias no POST /convert:

1. **Otimizações de Performance:**
   - Arquivo lido apenas 1 vez (antes: 2 vezes)
   - Uso de Path para manipulação de caminhos
   - Validação de tamanho antes de salvar

2. **Tratamento de Erros:**
   - ImportError: HTTP 503 se Celery indisponível
   - Exception: HTTP 500 com mensagem específica
   - Job marcado como "failed" no Redis em caso de erro

3. **Logging Melhorado:**
   - Log de upload (filename, size)
   - Log de MAIN JOB criado
   - Log de arquivo salvo (path)
   - Log de job enfileirado
   - Log de erros com traceback

4. **Teste Criado:**
   - scripts/test_upload_endpoint.py
   - Simula fluxo completo: MAIN → SPLIT → PAGES → MERGE
   - Resultado: ✅ PASSOU (8 jobs criados, progresso 0% → 100%)

### ✅ Testes CLI Realizados (Adicionado)

#### Scripts de Teste Criados:

1. **scripts/test_pdf_split.py** - Teste de divisão de PDF
   - Testa PDFSplitter sem Docker
   - Divide AI-50p.pdf em 50 páginas
   - Resultado: ✅ PASSOU
   - 50 arquivos criados (page_0001.pdf a page_0050.pdf)
   - Tamanho médio: 51 KB por página

2. **scripts/test_page_jobs.py** - Simulação de hierarquia de jobs
   - Simula fluxo completo MAIN → SPLIT → PAGES → MERGE
   - Cria 53 jobs (1+1+50+1)
   - Mostra progresso 0% → 100%
   - Resultado: ✅ PASSOU
   - Hierarquia demonstrada com sucesso

3. **scripts/test_cli.py** - Cliente CLI interativo
   - 7 funcionalidades testáveis
   - Menu interativo com cores
   - Requer API rodando
   - Status: ⏳ Aguardando Docker build

4. **Documentação criada:**
   - scripts/README.md - Guia do cliente CLI
   - scripts/README_TESTS.md - Resultados completos dos testes
   - TEST_RESULTS.md - Documento de validação
   - QUICK_START.md - Guia rápido

#### Resultados dos Testes:

```
TESTE 1: PDFSplitter
✓ PDF dividido: 50 páginas
✓ Arquivos criados: 2.6 MB total
✓ Overhead: 167.9% (esperado)

TESTE 2: Job Hierarchy Simulation
✓ 53 jobs criados corretamente
✓ Progresso: 0% → 10% → 20% → ... → 90% → 100%
✓ Hierarquia parent-child validada
✓ Processamento paralelo simulado (5 workers, 10 batches)
```

### ✅ Completed Implementation

#### 1. **workers/tasks.py** (anteriormente tasks_new.py)
Implementação completa da arquitetura hierárquica de jobs:

- **process_conversion** (MAIN JOB)
  - Ponto de entrada para conversões
  - Faz download do documento
  - Cria split_job se PDF multi-página
  - Converte diretamente se documento único

- **split_pdf_task** (SPLIT JOB)
  - Divide PDF em páginas individuais
  - Cria page_job para cada página
  - Lança convert_page_task em paralelo

- **convert_page_task** (PAGE JOB)
  - Converte página individual com Docling
  - Atualiza progresso do main job
  - Triggers merge_job quando todas páginas completam

- **merge_pages_task** (MERGE JOB)
  - Combina resultados de todas as páginas
  - Armazena resultado final no main job
  - Marca main job como completed
  - Limpa arquivos temporários

#### 2. **shared/redis_client.py**
Métodos de hierarquia adicionados:

- `add_child_job()` - Liga child ao parent
- `get_child_jobs()` - Retorna children do parent
- `get_page_jobs()` - Lista page job IDs
- `count_completed_page_jobs()` - Conta páginas completas
- `count_failed_page_jobs()` - Conta páginas falhas
- `all_page_jobs_completed()` - Verifica se pode fazer merge

Atualizado `set_job_status()` para incluir:
- `job_type` (main/split/page/merge)
- `parent_job_id` (para child jobs)
- `page_number` (para page jobs)
- `child_job_ids` (dict com split_job_id, page_job_ids, merge_job_id)

#### 3. **api/routes.py**
Endpoints atualizados para suportar hierarquia:

**GET /jobs/{job_id}** - Retorna status de qualquer tipo de job
- Detecta job_type automaticamente
- Para MAIN: retorna child_jobs, total_pages, pages_completed
- Para PAGE: retorna page_number, parent_job_id
- Para SPLIT/MERGE: retorna parent_job_id

**GET /jobs/{job_id}/result** - Resultado de main ou page individual
- MAIN jobs: retorna resultado merged (armazenado pelo merge job)
- PAGE jobs: retorna resultado individual da página
- Inclui page_number e parent_job_id para page jobs

**GET /jobs/{job_id}/pages** - Lista page jobs com IDs individuais
- Retorna `PageJobInfo` com:
  - `page_number`: número da página
  - `job_id`: UUID do page job
  - `status`: status do page job
  - `url`: endpoint para consultar resultado (`/jobs/{page_job_id}/result`)

#### 4. **shared/schemas.py**
Schemas atualizados:

- `JobType` enum: MAIN, SPLIT, PAGE, MERGE, DOWNLOAD
- `JobStatus` enum: QUEUED, PROCESSING, COMPLETED, FAILED, CANCELLED
- `ChildJobs`: model para child job relationships
- `PageJobInfo`: informação de page job individual com URL
- `JobStatusResponse`: updated com type, parent_job_id, child_jobs
- `JobResultResponse`: updated com type, page_number, parent_job_id

### Fluxo Completo

```
1. POST /convert
   └─> Cria MAIN JOB
       └─> Lança process_conversion task
           ├─> Download (10-20%)
           └─> Se PDF multi-página:
               └─> Cria SPLIT JOB
                   └─> split_pdf_task
                       ├─> Divide PDF
                       └─> Cria PAGE JOBS
                           ├─> page_job_1 (convert_page_task)
                           ├─> page_job_2 (convert_page_task)
                           └─> page_job_N (convert_page_task)
                               └─> Última página triggers:
                                   └─> Cria MERGE JOB
                                       └─> merge_pages_task
                                           ├─> Combina resultados
                                           ├─> Armazena em MAIN
                                           └─> Marca MAIN como completed

2. GET /jobs/{main_job_id}
   └─> Retorna status com:
       - type: "main"
       - child_jobs: {split_job_id, page_job_ids[], merge_job_id}
       - total_pages, pages_completed, pages_failed
       - progress: calculado baseado em páginas

3. GET /jobs/{main_job_id}/pages
   └─> Retorna lista de PageJobInfo:
       [{page_number: 1, job_id: "page_job_uuid_1", url: "/jobs/page_job_uuid_1/result"}, ...]

4. GET /jobs/{page_job_id}/result
   └─> Retorna resultado individual da página com page_number

5. GET /jobs/{main_job_id}/result
   └─> Retorna resultado merged (armazenado pelo merge job)
```

### Cálculo de Progresso

- **Download**: 10-20%
- **Pages**: 20-90% (70% dividido pelo número de páginas)
- **Merge**: 90-100%

Fórmula em `convert_page_task`:
```python
pages_progress = int((completed_pages / total_pages) * 70)
main_progress = 20 + pages_progress
```

### Rastreabilidade Completa

Agora é possível:
1. ✅ Consultar status de qualquer job (main, split, page, merge)
2. ✅ Obter resultado de qualquer page individualmente
3. ✅ Ver hierarquia completa de jobs (parent/child relationships)
4. ✅ Rastrear progresso granular por página
5. ✅ Retry individual de qualquer operação

### Arquivos Modificados

- `workers/tasks.py` (renomeado de tasks_new.py)
- `workers/tasks_old.py` (backup do arquivo antigo)
- `shared/redis_client.py` (métodos de hierarquia)
- `api/routes.py` (endpoints atualizados)
- `shared/schemas.py` (já estava atualizado)

### Próximos Passos para Testes

1. Rebuild Docker containers (demora devido ao PyTorch no Docling)
2. Testar fluxo completo:
   - Upload de PDF multi-página
   - Verificar split job criado
   - Verificar page jobs executando em paralelo
   - Consultar resultados individuais de páginas
   - Verificar merge job ao final
   - Consultar resultado final merged

### Como Testar

```bash
# 1. Upload PDF multi-página
curl -X POST http://localhost:8080/convert \
  -F "source_type=file" \
  -F "file=@sample.pdf"

# Response: {"job_id": "main-job-uuid", ...}

# 2. Consultar status do main job (ver child jobs)
curl http://localhost:8080/jobs/{main-job-uuid}

# 3. Listar page jobs
curl http://localhost:8080/jobs/{main-job-uuid}/pages

# 4. Consultar resultado de página individual
curl http://localhost:8080/jobs/{page-job-uuid}/result

# 5. Consultar resultado final merged
curl http://localhost:8080/jobs/{main-job-uuid}/result
```
