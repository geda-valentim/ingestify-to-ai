# Motores de execução: guia do operador

> Verificado contra o código em 2026-10-05 (spec 0003, fatias 0a a 8; a 4d, `E > 1` remoto, não
> existe ainda). Fonte da verdade:
> [backend/shared/engines/](../../backend/shared/engines/) (`routing.py`, `dispatch.py`,
> `ledger.py`, `budget.py`, `budget_watch.py`, `alerts.py`, `speed.py`, `pricing.py`,
> `capacity.py`, `features.py`, `store.py`),
> [backend/workers/engines/](../../backend/workers/engines/) (`dispatcher.py`, `lease.py`,
> `sweeper.py`, `watchdog.py`, `tasks.py`, `local.py`, `remote.py`, `remote_tasks.py`,
> `benchmark.py`, `modal_deploy.py`, `adapters/modal.py`, `modal_apps/`),
> [backend/api/routing_admin_routes.py](../../backend/api/routing_admin_routes.py),
> [backend/api/engine_admin_routes.py](../../backend/api/engine_admin_routes.py),
> [scripts/engines.py](../../scripts/engines.py).
> Desenho completo e motivos: specs/0003.

**Índice**: [Compute: o que configura](#compute-o-que-configura) · [Diagnóstico rápido](#diagnóstico-rápido) ·
[Sem rota, nada muda](#sem-rota-nada-muda) · [Conceitos](#conceitos) ·
[Do zero até rotear](#do-zero-até-rotear) · [Capacidade](#capacidade-e-vram) ·
[Rotas](#rotas) · [O caminho de um item](#o-caminho-de-um-item-com-rota) ·
[Documentos por página](#documentos-por-página-fatia-8) · [Visão](#visão-síncrona-fatia-8) ·
[Legendas ao vivo remotas](#legendas-ao-vivo-de-jobs-remotos-fatia-7) ·
[Recuperação](#liderança-recuperação-e-quedas) · [Motores remotos](#motores-remotos-modal) ·
[Orçamento e alertas](#orçamento-e-alertas) · [Velocidade e benchmark](#velocidade-aprendida-e-benchmark) ·
[Custos](#custos) · [API admin](#api-admin) · [Solução de problemas](#solução-de-problemas) ·
[Pendências com as contas reais](#a-rodar-com-as-contas-reais)

> Perfis, acesso e controle atualizados em **2026-10-06**; rollout da 0009 opt-in.

## Compute: o que configura

Compute é o conjunto de telas admin e comandos para decidir **onde os trabalhos rodam**, quantos
podem rodar ao mesmo tempo e quanto uma conta remota pode gastar. Existem dois níveis distintos:

| Configuração | Responsabilidade | Onde consultar |
|---|---|---|
| Dispositivo e bibliotecas do worker | CPU/CUDA efetivamente usado por Docling, Whisper e Florence-2 | [GPU.md](../GPU.md), [`shared/device.py`](../../backend/shared/device.py), Compose e logs |
| Motor, binding e rota | Colocação de jobs/páginas, capacidade declarada, tentativas e orçamento Modal | Este guia, `/admin/engines`, `/admin/gpus`, `/admin/routing`, `/admin/status` |

Um **provider de áudio** não é um motor: `AUDIO_TRANSCRIBER_PROVIDER` escolhe
`faster-whisper`, `openai-whisper` ou `openai-api` no worker local
([factory.py](../../backend/workers/audio/factory.py)). Os dois primeiros carregam o modelo no
processo; o terceiro envia áudio à API da OpenAI com `OPENAI_API_KEY`. Estas variáveis precisam
chegar ao environment do worker (ou à configuração do processo); o Compose base não repassa
`AUDIO_TRANSCRIBER_PROVIDER`/`OPENAI_API_KEY` automaticamente só por estarem no `.env`. O motor
`modal`, por sua vez, executa o app Whisper deployado na conta Modal. Trocar o provider local não cria uma conta
Modal, um binding nem uma rota.

O orçamento Compute cobre **motores Modal**, não cobranças de `openai-api`, eletricidade do
servidor ou outros provedores. `engine.kind=local` identifica o executor: não prova que os dados
ficaram no servidor quando o provider do worker é `openai-api`. Para processar áudio no servidor,
use um provider local. Os custos estimados neste guia são referências históricas, não preços
contratados ou garantia de latência.

### Dispositivo e declaração precisam concordar

- `DEVICE=auto|cpu|cuda|cuda:N` resolve o dispositivo geral. `WHISPER_DEVICE` não vazio prevalece
  para áudio; `WHISPER_COMPUTE_TYPE` vazio deriva `float16` em CUDA e `int8` em CPU. Confira o
  **environment final do serviço**: o overlay GPU configura `worker-audio` com `DEVICE=cpu` e
  `WHISPER_DEVICE=cuda`, enquanto `worker` e `worker-vision` usam `DEVICE=cuda`. Whisper pode
  voltar a CPU após falha CUDA pela factory; a declaração de capacidade não é recalculada.
- Um `gpu_ref` só associa o binding à placa **declarada para validar VRAM**. Não altera `DEVICE`,
  não muda a reserva NVIDIA do container nem seleciona uma GPU para a task. Em várias placas,
  o operador deve alinhar o dispositivo/reserva Docker de cada serviço com os bindings.
- O heartbeat usa `nvidia-smi` e reporta a **primeira placa visível**, com memória usada da placa
  inteira. Não mede VRAM exclusiva do modelo nem confirma qual dispositivo a inferência usou.
  Declare o UUID para casar a placa declarada com a detectada; sem UUID, `used_gb` pode ser nulo
  mesmo com GPU visível. Veja [heartbeat.py](../../backend/workers/engines/heartbeat.py).
- A factory mantém o transcriber configurado em cache **por processo**, carregado no primeiro
  uso; não há uma cópia global compartilhada entre réplicas. Mais workers podem consumir mais
  VRAM sem aumentar a vazão. O binding não escala os serviços nem aquece modelos.

As legendas parciais abaixo pertencem a uma transcrição de **arquivo já enviado**.
A captura contínua de microfone foi implementada como piloto opt-in no
[PR #22](https://github.com/geda-valentim/ingestify-to-ai/pull/22), com worker GPU e
ativação separados. Ela permanece desabilitada por padrão; os critérios de produção da
spec 0005 continuam pendentes.

## Diagnóstico rápido

A UI Compute permite configurar e operar engines pelo controlador, além de mostrar os
comandos Docker/CLI existentes. As leituras de engines e o controle usam sessão JWT. Com
acesso de engines ligado (`IAM_MODE=enforce`, ou o alias depreciado
`ENGINE_ACCESS_ENABLED=true`), usuários delegados veem apenas engines, perfis e ações
permitidos por seus bindings de engines; o servidor revalida a autorização em cada etapa. Diagnósticos
globais de GPU, routing e status continuam restritos ao administrador de bootstrap.

Configure as opções de runtime em **Compute → Perfis de execução**
(`/admin/execution-profiles`), publique uma revisão e selecione-a em
**Engine → Configuração → Perfil de execução**. Vincular altera apenas o desejado;
aplicar exige uma prévia e execução separadas. Administre papéis e escopos em
**Admin → Acesso** (`/admin/access`), a mesma tela dos papéis de plataforma desde a
spec 0018. Veja o [guia de perfis e acesso](execution-profiles.md)
e o [runbook de migração/ativação](../runbooks/execution-profiles-access.md).

| Tela | O que interpretar |
|---|---|
| `/admin/engines` e `/admin/engines/{id}` | Status/saúde, bindings, em voo, orçamento, teste e deploy; `paused` barra novas colocações |
| `/admin/execution-profiles` | Criar, revisar, publicar e vincular modelos de configuração de runtime |
| `/admin/access` | Concessões (bindings de plataforma e de engines, delegação), políticas, ambientes, consumidores de recursos e principais de instalação |
| `/admin/gpus` | VRAM orçada × usada e GPUs detectadas sem declaração; valor desconhecido não é zero |
| `/admin/routing` | Ordem dos motores e backlog de cada feature; sem rota vale a fila local habitual |
| `/admin/status` | Lease do despachante, disponibilidade do worker remoto e workers configurados × vivos |

```bash
# Leituras: substitua a URL e forneça um token JWT de admin, sem o salvar no repositório
COMPUTE_API_URL=http://localhost:8000
read -rsp 'Token JWT admin: ' COMPUTE_ADMIN_TOKEN
printf '\n'
printf 'Authorization: Bearer %s\n' "$COMPUTE_ADMIN_TOKEN" | \
  curl --fail --silent --show-error --header @- "$COMPUTE_API_URL/admin/engines/status"
printf 'Authorization: Bearer %s\n' "$COMPUTE_ADMIN_TOKEN" | \
  curl --fail --silent --show-error --header @- "$COMPUTE_API_URL/admin/gpus"
unset COMPUTE_ADMIN_TOKEN

# CLI local: não ativa motores nem muda rotas
docker compose exec api python scripts/engines.py list --json
docker compose exec api python scripts/engines.py routes show --json
# Infra e workers do deploy em uso
docker compose ps
docker compose logs --tail 50 worker-audio worker worker-vision
```

Use os mesmos arquivos `-f` do deploy GPU/produção ao operar o Compose; comandos neste guia
usam o base por brevidade. O `/health` geral não substitui o status Compute ou a confirmação de
worker na fila certa. Backlog com capacidade ocupada é espera esperada; em voo acima de workers
vivos sugere réplicas declaradas sem correspondência. Ajuste o binding **e** os serviços, e
acompanhe claim/heartbeat antes de aumentar concorrência.

Para um benchmark de áudio existente, comece pelo plano (não executa inferência remota):

```bash
docker compose --profile engines run --rm worker-remote python scripts/engines.py \
  benchmark --engine modal_1 --sample /tmp/ingestify/bench/a.mp3:240 \
  --gpus L4 --concurrency 1 --max-usd 0.30 --plan
```

Isso pressupõe conta/binding e amostra montada no caminho informado. O plano remoto estima o
custo; não mede desempenho. A execução real é descrita em [benchmark](#velocidade-aprendida-e-benchmark).
Benchmark local disputa GPU com os workers; `--pause-local` impede novas colocações roteadas,
e espera até 30 min pelo em-voo da feature registrado no ledger; não encerra esses trabalhos nem
bloqueia o caminho local **sem rota**. Confirme a atividade real da placa antes de medir.

## Sem rota, nada muda

Uma instalação **sem linha em `feature_routes`** (o padrão) se comporta exatamente como antes,
nas três features:

| Feature | Sem rota |
|---|---|
| `transcription` | `/transcribe` enfileira `process_conversion` em `ingestify-audio`; áudio em `/upload`/`/convert` transcreve no `worker`; `process_conversion` sem `usage_id` mantém o `self.retry` |
| `document_conversion` | `split_pdf_task` publica `convert_page_task.delay` por página; o retry de página (`POST /jobs/{id}/pages/{n}/retry`) publica `process_page.delay`; `task.retry` como sempre |
| `vision` | `/images/*` publica a task de visão em `ingestify-vision` e espera o resultado |

Nenhuma linha em `job_dispatches` ou `engine_usage`; `worker-dispatch` e `worker-remote` não são
necessários; nenhum processo importa `modal`. Ler a rota (cache de 5 s) com qualquer erro conta
como "sem rota". Nenhuma env var nova é obrigatória (o bloco "Execution engines" do
[.env.example](../../.env.example) é todo opcional).

## Conceitos

| Conceito | O que é |
|---|---|
| **Motor** | Linha em `engines`: `local` (semeado no startup, os workers deste servidor) ou uma conta Modal (`modal_1`…). Status `active`/`paused`, saúde, orçamento e credenciais seladas |
| **Binding** | Como uma feature roda num motor: `gpu_ref` (GPU local declarada) ou `gpu_type` (Modal), `workers`, `executions_per_worker`. **Capacidade** = `workers × executions_per_worker` |
| **Rota** | Por feature, lista ordenada de passos (motor ou grupo de motores), com condições. A ordem é a prioridade |
| **Backlog** | `job_dispatches`: itens roteados esperando colocação (FIFO durável no MySQL). Sujeito = job (transcrição) ou página (`subject_type=page`); visão não tem backlog |
| **Ledger** | `engine_usage`: uma linha por tentativa num motor. Fonte única de em-voo (capacidade) e de dinheiro |
| **Despachante** | `dispatch_tick` no `worker-dispatch`, líder único por lease com época (`dispatcher_lease`) |

## Do zero até rotear

Uma rota só com `local` não precisa de conta, chave nem `worker-remote`. O roteiro completo, com
remoto:

```bash
# 0. Despachante (necessário para qualquer rota)
docker compose --profile engines up -d worker-dispatch

# 1. GPUs locais declaradas e capacidade local por feature (veja "Capacidade e VRAM")
docker compose exec api python scripts/engines.py set-gpus gpu0:16:RTX5060Ti
docker compose exec api python scripts/engines.py set-capacity local transcription --workers 2 --gpu-ref gpu0
docker compose exec api python scripts/engines.py list

# 2. Par de chaves (uma vez). A pública vai para ENGINE_SECRETS_PUBLIC_KEY no .env (API, CLI);
#    a privada SÓ para ./secrets/engine_secrets_private (montado no worker-remote)
docker compose exec api python scripts/engines.py keygen

# 3. Contas Modal: importadas PAUSADAS, credenciais seladas com a chave pública. Sem --apply só
#    mostra o plano. Entrada: MODAL_ACCOUNT_{N}_NAME/_ID/_SECRET no stdin, ou ~/.modal.toml
docker compose exec -T api python scripts/engines.py import-env --limit-usd 30 --apply < contas.env
#    (alternativa: PUT /admin/engines/{id}/credentials com current_password)

# 4. Binding remoto: GPU e containers (E=1 até a fatia 4d)
docker compose exec api python scripts/engines.py set-capacity modal_1 transcription --workers 1 --gpu-type L4

# 5. worker-remote de pé (único com a chave privada)
docker compose --profile engines up -d --build worker-remote

# 6. Lock com hashes da imagem Modal (só fala com o PyPI) e deploy (fala com o Modal)
R="docker compose --profile engines run --rm worker-remote python scripts/engines.py"
$R modal-lock
$R modal-deploy --engine modal_1 --dry-run
$R modal-deploy --engine modal_1

# 7. Teste (sem container, grátis), orçamento e ativação
$R test --engine modal_1 --spend
docker compose exec api python scripts/engines.py budget modal_1 --limit-usd 30
docker compose exec api python scripts/engines.py activate modal_1

# 8. Rota: local primeiro, Modal sob pressão
docker compose exec api python scripts/engines.py routes set transcription \
    --step local --step "modal_1 min_wait=600"
```

### Chaves e credenciais

- A API e a CLI só **selam** (X25519 + HKDF + ChaCha20-Poly1305, presos ao `engine_id` e ao
  `key_id`); só o `worker-remote` abre. Sem chave pública, `PUT …/credentials` responde 409; sem a
  privada, nenhum motor remoto ativa.
- Rotação: gere um novo par, ponha a nova privada **antes** da antiga em
  `ENGINE_SECRETS_PRIVATE_KEYS` (ou no arquivo), troque a pública e regrave as credenciais; depois
  remova a antiga.
- Credenciais são somente escrita: as respostas trazem só `{is_set, hint, updated_at, updated_by}`.
  Logs, erros persistidos e colunas `engine_*` passam pela redação (`shared/engines/redact.py`).
- Subprocessos (deploy, relatório de gasto, benchmark) recebem um env montado do zero, com o token
  como variável e `HOME` temporário; nunca em argv, nunca em `os.environ`.
- Use um token próprio do Ingestify por conta Modal.

## Capacidade e VRAM

A capacidade do binding legado é **declarada**, não medida. Alterá-la não escala
containers Docker: a UI mostra "configurado X, vivos Y" e o comando (`scale_hint`).
Com o controle da spec 0007 habilitado, operações explícitas aplicam o perfil ao
serviço registrado pelo agente; o executor verifica réplicas e readiness antes
de atualizar o aplicado. Veja o [guia de operações](https://dev.ingestify.ai/pt/docs/engine-operations).

| Feature | Serviço local | Pegada padrão por processo (com contexto CUDA) | Como mudar réplicas |
|---|---|---|---|
| `transcription` | `worker-audio` | 3,0 GB (Whisper turbo float16) | `AUDIO_WORKER_REPLICAS=N docker compose up -d worker-audio` |
| `document_conversion` | `worker` | 1,5 GB (Docling) | `docker compose up -d --scale worker=N worker` |
| `vision` | `worker-vision` | 1,8 GB (Florence-2-base; 3,8 GB o large) | `docker compose up -d --scale worker-vision=N worker-vision` |

- **GPU local**: `set-gpus ref:vram_gb:nome[:uuid]` declara as placas. A soma, por GPU física, de
  `workers × E × pegada` de **todas** as features que a usam, mais `vram_reserve_gb` (1,0), precisa
  caber na VRAM; senão 422 com cada parcela. Bindings locais de GPU aceitam só `E=1` ("aumente as
  réplicas"); bindings sem `gpu_ref` (Docling em CPU) aceitam `E > 1` (`--concurrency` do Celery).
- **Modal**: `gpu_type` ∈ T4, L4, A10G, L40S, A100-40GB, A100-80GB, H100; `E=1` até a 4d;
  `Σ workers` da conta ≤ `account_max_gpus` (10). Mudar `gpu_type`, `workers`, `E` ou `cpu` deixa
  o motor `needs_redeploy` até o próximo `modal-deploy`. O adapter Modal só roda `transcription`.
- Heartbeats (`engines:local:{feature}:{host}`, a cada 10 s, com GPU e VRAM usada pelo
  `nvidia-smi`) decidem só **saúde**: sem nenhum worker vivo por `local_unhealthy_after_seconds`
  (180) a raia fica `unhealthy` e não recebe itens. A capacidade usa sempre o configurado.
- O benchmark local mede a pegada real e grava `vram_override_gb` com `--apply`.

## Rotas

Uma rota é, por feature, uma lista **ordenada** de passos:

| Campo do passo | Efeito |
|---|---|
| `engine_ids` | motores do passo (ids ou slugs; gravados como ids) |
| `group_strategy` | `priority`: na ordem; `fill_first`: o motor "corrente" (o elegível com a linha `kind=job` mais recente **do período**; sem nenhuma, o primeiro) primeiro. Recusa por orçamento, tamanho ou `spend_cap` ⇒ o próximo na hora; corrente **cheio** ⇒ o próximo só abre depois de `scale_out_after_seconds` (padrão 300), medido por `engine_feature_state.full_since`. Probes, benchmarks e caudas nunca mudam o corrente |
| `when.min_wait_seconds` / `when.min_backlog` | o passo só vale se o item esperou N s **ou** o backlog tem N itens |
| `spend_cap` | `{usd, window: day\|period}`: liquidado + reservado + estimativa ≤ usd (só remoto) |

Por rota: `max_attempts` (3), `on_no_engine` (`hold`/`fail` + `fail_after_seconds`),
`remote_allowed_for` (`admins`/`all`; `all` exige `current_password`, `user_period_limit_usd` e
`remote_data_notice`), `dispatcher_fallback` (`local_direct`/`hold`), `dispatcher_down_seconds`
(120).

**Desde a spec 0014** `remote_allowed_for=admins` significa "exige `engines.remote.use`"
(`shared/iam/remote.py`; em `IAM_MODE=off` continua sendo `is_effective_admin`, em `enforce`
somam-se os bindings `platform_admin`/`remote_engine_user`). `JobDispatch.remote_allowed`,
gravado no submit, é só um filtro: o dispatcher decide de novo, uma vez por usuário por tick,
antes de cada placement remoto. Uma revogação alcança o que já está na fila (páginas ainda não
colocadas vão para o caminho local ou seguem `on_no_engine`, e a reserva de skip-starvation
num motor remoto é descartada). **Mudança intencional (CA10):** `user_period_limit_usd` vale
também em rotas `admins`, bootstrap incluído. O dispatcher (`worker-dispatch`) e o `worker`
decidem essa permissão: precisam de `ADMIN_USER_IDS` e `IAM_MODE` iguais aos da `api` (o
`docker-compose.yml` repassa ambos). Divergências de shadow vindas do dispatcher saem com
`route=dispatcher`, no máximo uma a cada 10 min por usuário. O custo por tick (CA11) é medido
nos testes (`tests/test_iam_remote_engine.py`) em statements SQL (até 2 por usuário, nunca por
item) e em tempo: com 1 000 itens em backlog, o p95 do tempo gasto em `_may_use_remote` por tick
(o único trabalho que uma rota `admins` acrescenta a uma `all`) fica ≤ 5 ms (medido ~1 ms em
SQLite). A revalidação no dispatcher e o teto CA10 **não dependem de `IAM_MODE`**: em `off` a
decisão é o legado (`is_effective_admin` do dono), mas tomada a cada placement e não congelada no
submit. Logo, "`off` = legado" vale para as decisões de rota da API; no dispatcher, `off` só
desliga os bindings.

Validação: motor sem binding para a feature, motor repetido, ou passo remoto com
`remote_allowed_for=admins` sem passo local ⇒ 422; motor remoto não pronto (pausado, saúde ruim, sem
orçamento, `needs_redeploy`), `worker-remote` sem heartbeat, ou capacidade remota acima de
`REMOTE_WORKER_CONCURRENCY − 2` ⇒ 409. **`document_conversion` e `vision` só aceitam passos locais**
(nenhum adapter remoto roda Docling ou visão ainda) ⇒ 422 com motor remoto.

```bash
E="docker compose exec api python scripts/engines.py"
$E routes show
# transcrição: local primeiro, 4 contas Modal sob pressão, gastando no máximo US$ 1,50/dia
$E routes set transcription --step local --step "modal_1,modal_2,modal_3,modal_4 fill_first min_wait=600 cap=1.50/day"
# crédito da nuvem primeiro, local como reserva (com --fallback hold para obedecer a ordem mesmo com o despachante parado)
$E routes set transcription --step "modal_1,modal_2 fill_first" --step local --fallback hold
# Docling por página e visão: só local (backlog durável, capacidade respeitada, contabilidade)
$E set-capacity local document_conversion --workers 5
$E routes set document_conversion --step local
$E set-capacity local vision --workers 1 --gpu-ref gpu0
$E routes set vision --step local
$E routes delete transcription      # 202: drena o backlog de volta ao caminho de hoje
```

## O caminho de um item com rota

1. **Entrada** (`dispatch.submit`): `/transcribe`; `/upload` e `/convert` com arquivo de áudio
   (mesma lista de extensões, opções padrão de `/transcribe`); áudio que só se revela no worker
   (URL, Drive, Dropbox): `process_conversion` move o arquivo para `{TEMP}/audio/{job_id}/`, volta
   o job a `PENDING` e entrega à rota. Páginas de PDF: veja abaixo.
2. **Backlog**: linha em `job_dispatches`. Transcrição passa por `probing` (sonda de duração no
   `worker-dispatch`, no máximo `PROBE_MAX_BYTES`) e vai a `waiting`; páginas entram direto em
   `waiting` (não há duração a medir).
3. **Colocação** (`dispatch_tick`, líder único, chutado a cada entrada/settle e a cada 5 s): para
   cada candidato (cabeça de 20 + cabeça de 20 elegíveis a remoto), percorre os passos; num motor
   elegível, sob o lock da linha do motor, `em_voo < capacidade` (e, no remoto, o orçamento) ⇒
   grava `engine_usage(reserved)`, faz `waiting → assigned` (CAS com `version`) e só depois do
   commit publica a task na fila da feature com `usage_id`.
4. **Execução local**: o worker faz o *claim* `reserved → running` antes de qualquer trabalho
   (perdeu ⇒ ack e sai sem rodar), renova `heartbeat_at` a cada 15 s e liquida: sucesso ⇒
   `settled/succeeded`; exceção ⇒ `settled/failed` e o item volta à cabeça do backlog com
   `not_before = 60 · 2^(n−1)` s até `max_attempts`, nunca `self.retry`.

Estados do job: no backlog fica `PENDING` com `started_at` nulo; `PROCESSING` quando o worker
começa; `FAILED` só no settle terminal. `GET /jobs/{id}` (só o dono) ganha
`engine: {kind: local|cloud}` e `queue_reason: in_queue|starting`. O detector de jobs travados
ignora jobs com tentativa viva no ledger ou com itens abertos no backlog.

## Documentos por página (fatia 8)

Com rota de `document_conversion`, a unidade roteada é a **página** (`subject_type=page`,
`subject_id` = page job id, `job_id` = job pai):

- `split_pdf_task` cria as linhas `Page` como sempre, registra cada page job no Redis do pai e
  entrega cada página a `dispatch.submit` (payload com allowlist: `page_job_id`, `parent_job_id`,
  `page_number`, caminho da página e só a opção `docling_preset`).
- O despachante publica `convert_page_task(..., usage_id)` na fila `ingestify` (`worker`) até a
  capacidade local de `document_conversion`. A página faz claim, converte e liquida; a última
  página dispara o merge, como hoje.
- Falha: a **página** volta ao backlog (`Page.status=PENDING`, page job `queued` no Redis) com
  backoff; depois de `max_attempts` falhas contadas, **só a página** fica `FAILED` (o pai continua
  `PROCESSING` e `pages_failed` é recontado), exatamente como uma página que esgota os retries hoje.
- O retry manual (`POST /jobs/{id}/pages/{n}/retry`) também passa pela rota (`source_pdf_path`).
- Job apagado no meio: o claim da página encontra o pai fechado e liquida `cancelled` sem rodar.

## Visão (síncrona, fatia 8)

Visão não tem backlog: quem chama está segurando a conexão. Com rota de `vision`,
`/images/describe|ocr` chama `dispatch.place_now` **dentro da requisição**:

1. percorre os passos; no primeiro motor elegível com vaga (sob o lock da linha do motor) grava
   `engine_usage(reserved, subject_type=vision_request)` e publica a task com `usage_id`;
2. nada cabe **e a rota tem passo local** ⇒ fila `ingestify-vision` como hoje (nunca recusa);
3. nada cabe e não há passo local ⇒ **503** `VISION_ENGINE_UNAVAILABLE` com `Retry-After: 30`.

Um motor remoto só seria elegível quente (sem cold start dentro da requisição); como nenhum
adapter remoto roda visão nesta fatia, hoje só vagas locais são colocadas. O worker de visão faz
claim, heartbeat e settle; se a reserva caducou (o sweeper a liberou) ou a mensagem é uma
reentrega, ele **responde mesmo assim**, fora da contabilidade — não há backlog para onde devolver.
Reserva nunca publicada (a API caiu entre reservar e publicar) é liberada pelo sweeper em 60 s.

## Legendas ao vivo de jobs remotos (fatia 7)

O job page mostra o texto enquanto a transcrição acontece, lendo
`GET /jobs/{id}/transcript/partial` (lista Redis `job:{id}:transcript:partial`). No local quem
escreve é o callback de progresso do `worker-audio`; no remoto (protocolo 3 do app Modal):

- o pedido leva `live: true`; o container empurra os segmentos decodificados, em lotes a cada 2 s,
  para a `modal.Queue` `ingestify-whisper-live` da conta, **partição = `attempt_key`** (uma por
  tentativa). Limites: 2.000 lotes por tentativa, 500 segmentos por lote, `put` não bloqueante,
  TTL da partição 1 h; fila cheia ou com erro ⇒ o container para de empurrar, a transcrição segue;
- o `worker-remote` espera a chamada em fatias de 3 s (o heartbeat continua a cada 15 s), drena a
  partição a cada fatia, **valida** cada lote (`protocol.parse_live_batch`) e acrescenta à mesma
  lista Redis; ao fim da tentativa apaga a partição; `finish_transcription` apaga a lista;
- tentativa nova (spawn) começa com a lista vazia; um `worker-remote` que assume uma chamada em
  andamento (resume) mantém o texto e drena só o que sobrou na partição;
- nenhuma mudança no caminho local nem no frontend.

## Liderança, recuperação e quedas

- **Lease com época** (`dispatcher_lease`): um líder por vez; assumir incrementa a época, e toda
  colocação relê a época em modo compartilhado e aborta se ela mudou.
- **Sweeper** (`sweep_usage`, 30 s): reserva local não publicada há 60 s ⇒ publica (visão:
  libera); não reivindicada em `local_claim_timeout_seconds` (120) ⇒ `released` e o item volta (sem
  contar tentativa); `running` sem heartbeat há `local_stale_seconds` (90) ⇒ `lost` (conta
  tentativa) ou `succeeded` se o job/página já concluiu. A mensagem reentregue encontra a linha
  fora de `reserved` e dá ack sem rodar.
- **Despachante parado** (`dispatcher_seen_at` velho): com `local_direct`, o submit publica direto
  no local **com** linha de uso (`placed_by=fallback`, conta no em-voo) e o **watchdog** da API (a
  cada 15 s) assume o lease por uma rodada, roda o sweeper local e coloca no máximo
  `capacidade − em_voo` itens em passos locais. Com `hold`, só alerta. Redis fora derruba o broker:
  o submit falha como hoje.
- **Remover a rota** (`DELETE`) a marca `draining`: itens novos vão pelo caminho de hoje, o
  backlog volta em lotes de 100 e a linha some quando o backlog esvazia.

## Motores remotos (Modal)

Um motor Modal é **uma conta** (workspace). O app `ingestify-whisper` é deployado na conta pela
CLI; o `worker-remote` (profile `engines`, imagem enxuta `docker/Dockerfile.remote`) é o único
processo com a chave privada. Nada disso é usado sem uma rota com passo remoto.

### Deploy

`modal-deploy` roda `python -m modal deploy -m workers.engines.modal_apps.whisper_app` num
subprocesso com env do zero, chama a função `meta()` (CPU, sem GPU) para conferir protocolo e
fingerprint e só então grava `deployments.transcription = {fingerprint, protocol, binding,
verified_at, hashed}`. O fingerprint cobre o código enviado à imagem (`modal_apps/files.py`), o
lock com hashes, a revisão do modelo, o protocolo e o decorator (GPU, cpu, memória, timeout,
`scaledown_window`, `max_containers`). **Mudar qualquer um — inclusive atualizar o Ingestify com
código novo nesses arquivos — deixa o motor `needs_redeploy`**: ele não recebe itens até o
próximo deploy (o resto da rota segue).

### Ativação

`activate` exige: credenciais, teste ok mais novo que as credenciais, `limit_usd`, deploy
verificado com o fingerprint atual e `E=1`; senão 409 com a lista do que falta. `pause` só impede
novas colocações; o que está em voo termina.

### Uma tentativa remota

1. **Colocação**: reserva o pior caso `(D ÷ s_p20 + 15 + cold_s_p80) × rate × 1,2` enquanto a chave
   `(motor, feature, gpu, E)` tem menos de 50 tentativas liquidadas; a partir de 50,
   `D × q95(actual_usd ÷ D) × 1,2`. `rate = GPU + cpu × P_cpu + memória × P_mem`
   (`pricing.py`, preços a conferir). Mídia acima de `max_input_bytes` (512 MB) ou
   `max_media_seconds` (4 h) fica nos passos locais.
2. **Claim** (`worker-remote`): `reserved→spawning` sob o lock do motor, refazendo a fórmula com a
   própria reserva e o gasto reportado; motor pausado, doente, `needs_redeploy` ou sem orçamento ⇒
   reserva devolvida e o item volta à cabeça do backlog.
3. **Execução**: a mídia (volume temporário ou MinIO) vai na chamada, no máximo
   `REMOTE_MAX_CONCURRENT_UPLOADS` por vez; `provider_call_id` e
   `deadline_at = spawned_at + reservado ÷ rate` gravados **antes** de esperar; passado o prazo,
   cancela (flag cooperativa no `modal.Dict` + `FunctionCall.cancel()`); legendas ao vivo drenadas
   enquanto espera.
4. **Saída e settle**: resposta validada contra `modal_apps/protocol.py`, `finish_transcription`
   como no local, depois `actual = max(segundos reportados, medidos) × rate`.

Falhas (Apêndice J da spec): `AUTH` ⇒ `unhealthy` até corrigir; `QUOTA_EXHAUSTED` ⇒ `exhausted`
até o próximo período; `NOT_DEPLOYED` ⇒ `unhealthy` 10 min; nenhum desses conta tentativa e o item
volta excluindo o motor por 15 min. `TIMEOUT` e `INTERNAL` contam; `INPUT_REJECTED` falha o job na
hora. O sweeper republica tentativas silenciosas, pede cancelamento de chamadas passadas do prazo
e, após 5 republicações, liquida `lost` cobrando a reserva inteira; nunca liquida uma chamada que
ainda pode terminar.

## Orçamento e alertas

- **Fórmula** (sob o lock do motor, na colocação e de novo no claim):
  `max(ledger, reportado) + reservado + estimativa ≤ limit_usd − min_remaining_usd`. O limite vale
  para a **conta inteira**; gasto de outros sistemas entra pelo relatório do provedor.
- **Período**: começa no dia `period_anchor_day` (1–28) no fuso `period_tz` (padrão UTC, dia 1):
  `engines.py budget modal_1 --limit-usd 30 --tz America/Sao_Paulo --anchor-day 5`.
- **Reconciliação** (`reconcile_spend`, 10 min, `worker-remote`): `modal billing report --json`,
  guarda o maior valor já visto; relatório ilegível, ou US$ 0 por mais de 3 h com ledger acima de
  US$ 0,50, deixa o motor `degraded` (fail closed). `unattributed = reportado − ledger`.
- **Esgotamento** (`budget_watch.py`): gasto ≥ `soft_pct` (80 %) ⇒ alerta `budget_soft`; sobra ≤ 0
  ou menor que o custo mediano de um item ⇒ `exhausted` até o próximo período e alerta
  `budget_exhausted`; cada alerta uma vez por período. Subir o limite limpa `exhausted`.
- **Alertas** (`alerts.py`): sempre no log (`[ENGINES] ALERT <evento>`) e, com
  `ENGINE_ALERT_WEBHOOK_URL`, um `POST` JSON `{source, event, engine, message, details, at}` sem
  segredos nem dados de usuário. Eventos: `budget_soft`, `budget_exhausted`, `quota_exhausted`,
  `billing_degraded`, `dispatcher_down`, `cost_divergence`, `engine_probe_failed`.
- **Probes** (`probe_engines`, 10 min): motores ativos usados em 24 h; `test_connection()` sem
  container nem GPU.
- Configure **também** o limite de gasto no próprio Modal: o do Ingestify enxerga o gasto alheio
  só com o atraso do relatório (~5 min).

## Velocidade aprendida e benchmark

`speed.py` calcula, por `(motor, feature, gpu, E)`, sobre as últimas 200 tentativas liquidadas:
`s_p20`, `cold_s_p80` e, a partir de 50 linhas, `q95(actual_usd ÷ D)`. Com menos de 5 velocidades,
vale o último benchmark; sem ele, `default_speed ÷ E`. Cache Redis de 1 h (`refresh_speed`).

`engines.py benchmark` mede velocidade, US$/hora de áudio, VRAM e cold start por `(gpu, E)` e
recomenda a menor US$/h que cabe na VRAM com velocidade ≥ `min_speed`:

- **Remoto** (custa dinheiro, no `worker-remote`): plano pessimista impresso por combinação,
  confirmação (ou `--yes`), reserva de `--max-usd` no ledger (linhas `kind=benchmark`), cada
  combinação como **app efêmero** (`modal run`, nunca o deploy de produção) cortada na sua parte do
  teto. `--plan` só imprime.
- **Local** (grátis, disputa a placa): fora do container avulso só imprime o
  `docker compose … run --rm --no-deps worker-audio python -m workers.engines.benchmark … --here`;
  lá dentro passa pela guarda de VRAM. `--pause-local` pausa o motor local durante a medição.
- `--apply` grava a recomendação (remoto ⇒ `needs_redeploy` até o deploy).

```bash
docker compose exec api python scripts/engines.py speed [--engine modal_1]
```

## Custos

- **Sem cobrança Modal** sem motor remoto em rota. Rotas só locais, backlog, despachante e visão
  roteada não criam uso Modal; o provider `openai-api`, se escolhido, tem cobrança própria fora
  deste orçamento.
- Teste, probes e relatório de gasto: grátis, sem container.
- Deploy: build da imagem (CPU; o primeiro baixa ~1,6 GB de pesos; depois só as camadas de código
  e env mudam) e alguns segundos de um container de 0,25 CPU para `meta()`: ~US$ 0,01–0,02.
- Cada item remoto: tempo do container (GPU + CPU + memória) desde o início do input, mais o cold
  start (~20–40 s em L4) quando frio e a cauda ociosa (`scaledown_window=60` s, ≈ US$ 0,016 em L4)
  depois do último item. Medido na `modal_1` (L4, clipe de 4 min): US$ 0,013 frio, US$ 0,003 quente.
- Legendas ao vivo: operações de `modal.Queue` (um `put` a cada ~2 s no container, um `get_many`
  a cada 3 s no worker); não acrescentam tempo de GPU.
- Teto do lado do Ingestify por conta: `(limit − min_remaining)` + cancelamento em voo + cauda
  ociosa ≈ limite + US$ 0,05 com 2 containers em L4.
- Economia (Apêndice G da spec): com 4 contas de US$ 30, ~760–2.450 h de áudio por mês conforme
  GPU e velocidade: o Modal é válvula de rajada, não substituto da GPU local.

## API admin

Listagem/detalhe de engines e descritores exigem JWT; com acesso habilitado, aplicam escopos
dos bindings de engines. Diagnósticos globais e alterações legadas exigem bootstrap; credenciais podem ser
delegadas ao papel `connection_manager`. Mudanças exigem sessão JWT (API key ⇒ 403),
gravam `admin_audit` e nunca
ecoam valores de credenciais.

| Método e caminho | O que faz |
|---|---|
| `GET /admin/engine-adapters` | adapters, GPUs e limites (`max_E`) |
| `GET /admin/engines` · `GET /admin/engines/{id}` | motores, bindings, em voo/capacidade, configurado × vivos, `deploy_state`, orçamento |
| `GET /admin/gpus` · `PUT /admin/engines/{id}/gpus` | GPUs locais declaradas × detectadas, VRAM orçada e usada |
| `PUT` · `DELETE /admin/engines/{id}/features/{feature}` | binding (guarda de VRAM; revalida rotas remotas) |
| `PUT /admin/engines/{id}/credentials` · `DELETE …` | credenciais seladas; exigem `current_password` |
| `POST /admin/engines/{id}/test` · `POST /admin/engines/test-all` | teste no `worker-remote` (sem GPU) |
| `PUT /admin/engines/{id}/budget` | `limit_usd`, `min_remaining_usd`, `soft_pct`, `period_tz`, `period_anchor_day` |
| `POST /admin/engines/{id}/activate` · `/pause` · `/reset-health` · `/reconcile` | ciclo de vida e relatório de gasto agora |
| `GET /admin/engines/{id}/benchmarks?feature=` | benchmarks e velocidade aprendida |
| `GET /admin/routing` · `PUT` · `DELETE /admin/routing/{feature}` | rotas e backlog por feature |
| `GET /admin/engines/status` | lease, em voo/capacidade por motor e feature, vivos × configurados, backlog |

A UI fica em `/admin/engines`, `/admin/gpus`, `/admin/routing` e `/admin/status`.
O item Compute e suas abas respeitam as permissões do usuário. Os comandos Docker
continuam disponíveis; operações gerenciadas usam planos do controlador e autorização atual.
APIs de biblioteca, IAM e vinculação estão em [perfis de execução](execution-profiles.md).

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Itens ficam `in_queue` e nada é colocado | `worker-dispatch` parado (o watchdog só coloca em passos locais) ou a raia local `unhealthy` | `docker compose --profile engines up -d worker-dispatch`; `GET /admin/engines/status` (lease, `dispatcher_seen_at`, vivos) |
| Local `unhealthy`, nada vai ao local | nenhum worker da feature com heartbeat há 180 s (serviço parado, fila errada) | suba o serviço da feature (`worker-audio`, `worker`, `worker-vision`); confira `engines:local:{feature}:*` no Redis |
| "configurado X, vivos Y" com Y < X | réplicas declaradas a mais | rode o `scale_hint` mostrado ou reduza `workers`; itens não reivindicados voltam ao backlog em 120 s |
| Motor remoto `needs_redeploy` depois de atualizar o código | o fingerprint cobre o código do app (ex.: protocolo 3 da fatia 7) | `modal-deploy --engine <slug>` (ou `--all`) |
| `PUT /admin/routing` responde 409 "worker-remote" | sem heartbeat do `worker-remote` | `docker compose --profile engines up -d worker-remote` |
| 422 "local engines only" | passo remoto numa rota de `document_conversion`/`vision` | só passos locais nessas features por enquanto |
| Motor `exhausted` | orçamento do período no fim, ou `QUOTA_EXHAUSTED` do provedor | espere o próximo período ou suba `limit_usd` (`budget`) |
| Motor `degraded` | relatório de gasto ilegível ou zerado por 3 h com ledger > US$ 0,50 | `reconcile --engine <slug>`; confira o token e o CLI `modal` no `worker-remote` |
| Motor `unhealthy` por `AUTH` | token revogado/errado | regrave as credenciais, `test`, `reset-health` |
| `/images/*` responde 503 `VISION_ENGINE_UNAVAILABLE` | rota de visão sem passo local e nada pode atender | ponha `local` na rota de visão |
| Página fica `PENDING` com a rota ativa | a página está no backlog (capacidade de `document_conversion` cheia) ou em backoff | `GET /admin/routing` (backlog), capacidade do `worker` |
| Legendas ao vivo não aparecem num job remoto | motor ainda no protocolo 2 (deploy antigo) ou fila do Modal indisponível | redeploy; a transcrição termina normalmente de qualquer jeito |
| Job antigo de Drive/Dropbox falha por token | desde a correção S-01 o token do provedor vai no header `X-Source-Token`, nunca em `Authorization` | reenviar com `X-Source-Token` ([sources.md](sources.md)) |

## A rodar com as contas reais

O código das fatias 4b, 4c, 7 e 8 foi testado só contra um `modal` falso. Com o dono, nesta ordem
(nada disso ativa motor nem cria rota):

```bash
R="docker compose --profile engines run --rm worker-remote python scripts/engines.py"
# 0. Fatia 7 mudou o protocolo do app (2 -> 3) e o código enviado à imagem: toda conta deployada
#    está needs_redeploy. Rebuild só das camadas de código/env (dependências e pesos em cache).
$R modal-deploy --engine modal_1 --dry-run
$R modal-deploy --engine modal_1          # ~US$ 0,01 (build de CPU + meta())
$R test --engine modal_1 --spend

# 1. Benchmark da modal_1 (pode continuar pausada). Amostra: o clipe de 4 min dos gates em ./tmp/bench
mkdir -p tmp/bench && cp <clipe-4min>.mp3 tmp/bench/a.mp3
$R benchmark --engine modal_1 --sample /tmp/ingestify/bench/a.mp3:240 --gpus T4,L4,A10G --concurrency 1 --max-usd 0.30 --plan
#    estimativa pessimista: T4 0,0233 + L4 0,0299 + A10G 0,0395 = US$ 0,093; teto duro US$ 0,30
#    esperado de verdade (gate 4a: frio em L4 = US$ 0,013 por clipe): ~US$ 0,04-0,06 + build de CPU
$R benchmark --engine modal_1 --sample /tmp/ingestify/bench/a.mp3:240 --gpus T4,L4,A10G --concurrency 1 --max-usd 0.30 --yes
$R reconcile --engine modal_1             # confere o gasto contra o relatório (atraso ~5 min)

# 2. Gate da fatia 7 (legendas ao vivo), quando o dono quiser uma rota: uma transcrição roteada de
#    um clipe de 3-5 min na modal_1; o job page deve mostrar o texto chegando a cada ~3 s e
#    GET /jobs/{id}/transcript/partial crescer. Custo: o de um item (~US$ 0,01-0,02 em L4).

# 3. Contas modal_2..4: binding e orçamento (na API), depois teste e deploy um por um
for n in 2 3 4; do
  docker compose exec api python scripts/engines.py set-capacity modal_$n transcription --workers 1 --gpu-type L4
  docker compose exec api python scripts/engines.py budget modal_$n --limit-usd 30
done
$R test --all                             # grátis, sem container
$R modal-deploy --all --dry-run
$R modal-deploy --all                     # build de imagem (CPU, ~1,6 GB de pesos) + meta(): ~US$ 0,01-0,02 por conta
$R test --all && $R reconcile

# 4. Local (opcional, grátis): imprime o comando do container avulso; rode-o com a placa ociosa
docker compose exec api python scripts/engines.py benchmark --engine local --sample /tmp/ingestify/bench/a.mp3:240 --concurrency 1,2 --pause-local
```

## Requisitos, funcionalidades e aplicações na documentação web

O índice público em [/docs/compute](https://dev.ingestify.ai/pt/docs/compute) reúne:

- [Recursos de engines](https://dev.ingestify.ai/pt/docs/engines): ENG-01 a ENG-08, conexões, adapters, capacidade/VRAM, rotas, orçamento, desempenho e casos de uso.
- [Operações](https://dev.ingestify.ai/pt/docs/engine-operations): OPS-01 a OPS-07, dependências, estados, ações por adapter, prévia, idempotência, drain, logs/SSE, cancelamento e recovery.
- [Perfis](https://dev.ingestify.ai/pt/docs/execution-profiles): PRF-01 a PRF-06, campos, revisões, catálogo e vínculo.
- [Acesso](https://dev.ingestify.ai/pt/docs/engine-access): ACL-01 a ACL-08, papéis, ABAC, grants, delegação, consumidores, revogação e principal CLI.

Versões em inglês usam os mesmos paths sem `/pt`. Rastreabilidade em RF012.
