# Motores de execução: rotas, backlog e despachante

> Verificado contra o código em 2026-10-05 (spec 0003, fatias 2, 3a e 3b). Fonte da verdade:
> [backend/shared/engines/](../../backend/shared/engines/) (`routing.py`, `dispatch.py`,
> `ledger.py`, `budget.py`, `capacity.py`),
> [backend/workers/engines/](../../backend/workers/engines/) (`dispatcher.py`, `lease.py`,
> `sweeper.py`, `watchdog.py`, `tasks.py`, `local.py`),
> [backend/api/routing_admin_routes.py](../../backend/api/routing_admin_routes.py),
> [backend/api/engine_admin_routes.py](../../backend/api/engine_admin_routes.py),
> [scripts/engines.py](../../scripts/engines.py).
> Desenho completo e motivos: [specs/0003](../specs/0003-motores-de-execucao-roteamento-e-orcamento.md).

## Sem rota, nada muda

Uma instalação **sem linha em `feature_routes`** se comporta exatamente como antes: `/transcribe`
enfileira `process_conversion` em `ingestify-audio`; áudio em `/upload`/`/convert` transcreve no
`worker`; nenhuma linha em `job_dispatches` ou `engine_usage`; o `worker-dispatch` não é
necessário; `process_conversion` sem `usage_id` mantém o `self.retry`. Ler a rota (cache de 5 s)
com qualquer erro conta como "sem rota".

## O que uma rota faz

Uma rota é, por feature, uma lista **ordenada** de passos. Cada passo tem um motor ou um grupo
de motores (estratégia `priority` ou `fill_first`) e condições opcionais:

| Campo do passo | Efeito |
|---|---|
| `engine_ids` | motores do passo (ids ou slugs; gravados como ids) |
| `group_strategy` | `priority`: na ordem; `fill_first`: o motor "corrente" (o da linha `kind=job` mais recente) primeiro; cheio, o próximo só abre depois de `scale_out_after_seconds` (padrão 300) |
| `when.min_wait_seconds` / `when.min_backlog` | o passo só vale se o item esperou N s **ou** o backlog tem N itens |
| `spend_cap` | `{usd, window: day\|period}`: liquidado + reservado + estimativa ≤ usd (só remoto) |

E, por rota: `max_attempts` (3), `on_no_engine` (`hold`/`fail` + `fail_after_seconds`),
`remote_allowed_for` (`admins`/`all`), `dispatcher_fallback` (`local_direct`/`hold`),
`dispatcher_down_seconds` (120).

**Nesta versão só o motor `local` pode estar numa rota**: motores remotos (Modal) chegam na
fatia 4a e uma rota com eles responde `409`. Uma rota só com `local` já é útil: o backlog é
durável no MySQL, a capacidade configurada é respeitada e as falhas voltam com backoff.

## O caminho de um item com rota

1. **Entrada** (`dispatch.submit`): `/transcribe`; `/upload` e `/convert` com arquivo de áudio
   (mesma lista de extensões de sempre, com as opções padrão de `/transcribe`); e áudio que só se
   revela no worker (URL, Drive, Dropbox): `process_conversion` move o arquivo para
   `{TEMP}/audio/{job_id}/`, volta o job a `PENDING` e entrega à rota.
2. **Backlog**: linha em `job_dispatches` (`probing`), sonda de duração em `worker-dispatch`
   (lê no máximo `PROBE_MAX_BYTES`), depois `waiting`.
3. **Colocação** (`dispatch_tick`, líder único): para cada candidato (cabeça de 20 + cabeça de 20
   elegíveis a remoto), percorre os passos; num motor elegível, sob o lock da linha do motor,
   `em_voo < workers × executions_per_worker` ⇒ grava `engine_usage(reserved)` e faz
   `waiting → assigned` (CAS com `version`), e só depois do commit publica
   `process_conversion(..., usage_id)` na fila da feature (`ingestify-audio`).
4. **Execução local**: o worker faz o *claim* `reserved → running` antes de qualquer trabalho
   (perdeu ⇒ ack e sai sem rodar), renova `heartbeat_at` a cada 15 s, e liquida: sucesso ⇒
   `settled/succeeded` com `output_persisted_at`; exceção ⇒ `settled/failed` e o item volta à
   cabeça do backlog com `not_before = 60 · 2^(n−1)` s até `max_attempts`; estouro do limite suave
   de tempo ⇒ falha definitiva (como hoje para transcrição).

Estados do job: no backlog fica `PENDING` com `started_at` nulo (o detector de jobs travados não o
vê); `PROCESSING` quando o worker começa; `FAILED` só no settle terminal. `GET /jobs/{id}` (só o
dono) ganha `engine: {kind: local|cloud}` e `queue_reason: in_queue|starting`.

## Liderança, recuperação e quedas

- **Lease com época** (`dispatcher_lease`): um líder por vez; assumir incrementa a época, e toda
  colocação relê a época em modo compartilhado e aborta se ela mudou.
- **Capacidade** = configurado − linhas em voo do ledger (incluindo as do fallback). Heartbeats
  dos workers só decidem saúde: sem worker vivo por `local_unhealthy_after_seconds` (180) a raia
  local fica `unhealthy`.
- **Sweeper** (`sweep_usage`, 30 s): reserva local não publicada há 60 s ⇒ publica; não
  reivindicada em `local_claim_timeout_seconds` (120) ⇒ `released` e o item volta (sem contar
  tentativa); `running` sem heartbeat há `local_stale_seconds` (90) ⇒ `lost` (conta tentativa) ou
  `succeeded` se o job já concluiu. A mensagem reentregue encontra a linha fora de `reserved` e dá
  ack sem rodar.
- **Despachante parado** (`dispatcher_seen_at` velho): com `local_direct`, o submit publica direto
  no local **com** linha de uso (`placed_by=fallback`, conta no em-voo) e o **watchdog** da API (a
  cada 15 s) assume o lease por uma rodada, roda o sweeper local e coloca no máximo
  `capacidade − em_voo` itens em passos locais. Com `hold`, só alerta no log. Redis fora derruba o
  broker: o submit falha como hoje.
- **Remover a rota** (`DELETE`) a marca `draining`: itens novos vão pelo caminho de hoje, o
  backlog volta em lotes de 100 e a linha some quando o backlog esvazia.

## Administração

| Método e caminho | O que faz |
|---|---|
| `GET /admin/routing` | Rotas por feature (a implícita "sem rota" inclusive) e backlog: esperando, espera mais antiga, fallback em voo, desvios em 24 h |
| `PUT /admin/routing/{feature}` | Cria ou troca a rota (`version` opcional ⇒ 409 em conflito). 422: motor sem capacidade para a feature, motor repetido, passo remoto com `admins` sem passo local; 409: motor remoto não pronto (pausado, com saúde ruim, sem orçamento, `needs_redeploy`), `worker-remote` sem heartbeat, ou capacidade remota acima de `REMOTE_WORKER_CONCURRENCY − 2`. `remote_allowed_for=all` exige `current_password`, `user_period_limit_usd` e `remote_data_notice` |
| `DELETE /admin/routing/{feature}` | `202`, rota `draining` |
| `GET /admin/engines/status` | Lease (época, detentor, `dispatcher_seen_at`), em voo/capacidade por motor e feature, vivos × configurados, backlog por estado |

Leituras exigem admin; mudanças exigem sessão JWT (API key ⇒ 403) e gravam `admin_audit`
(`target_type=route`).

CLI (no container da API):

```bash
docker compose exec api python scripts/engines.py routes show
docker compose exec api python scripts/engines.py routes set transcription --step local
docker compose exec api python scripts/engines.py routes delete transcription
```

## Operação

- Serviço opcional `worker-dispatch` no profile `engines`:
  `docker compose --profile engines up -d worker-dispatch`. Ele consome `ingestify-dispatch`
  (`-c 2`) e roda o próprio beat (`-B`, `ENGINES_DISPATCH_BEAT=true`): tick a cada 5 s, sweeper a
  cada 30 s. O beat compartilhado não publica nada nessa fila.
- Variáveis (todas opcionais): `PROBE_MAX_BYTES`, `PROBE_TIMEOUT_SECONDS`,
  `ENGINES_WATCHDOG_ENABLED`, `DISPATCH_QUEUE`, `DISPATCH_WORKER_MEM_LIMIT`.
- Coluna nova `engine_feature_state.workers_seen_at` (Alembic `5d2e8f1a6c47`; instalações por
  `create_all` a recebem no startup).

## Motores remotos (Modal, fatia 4a)

Um motor Modal é **uma conta** (workspace). O app `ingestify-whisper` é deployado na conta
pela CLI; o `worker-remote` (serviço opcional, profile `engines`, imagem enxuta
`docker/Dockerfile.remote`) é o único processo com a chave privada que abre as credenciais. Nada
disso é usado sem uma rota com passo remoto.

### Do zero até rotear

```bash
# 1. Par de chaves (uma vez). Pública no .env (API); privada SÓ em ./secrets/engine_secrets_private
docker compose exec api python scripts/engines.py keygen

# 2. Contas: importadas pausadas, credenciais seladas (ou PUT /admin/engines/{id}/credentials)
docker compose exec -T api python scripts/engines.py import-env --limit-usd 30 --apply < contas.env

# 3. Binding: GPU e containers (E=1 na v1)
docker compose exec api python scripts/engines.py set-capacity modal_1 transcription --workers 1 --gpu-type L4

# 4. worker-remote de pé (lê ./secrets/engine_secrets_private)
docker compose --profile engines up -d --build worker-remote

# 5. Lock com hashes da imagem Modal (só fala com o PyPI) e deploy (fala com o Modal)
docker compose --profile engines run --rm worker-remote python scripts/engines.py modal-lock
docker compose --profile engines run --rm worker-remote python scripts/engines.py modal-deploy --engine modal_1 --dry-run
docker compose --profile engines run --rm worker-remote python scripts/engines.py modal-deploy --engine modal_1

# 6. Teste (sem GPU), orçamento e ativação
docker compose --profile engines run --rm worker-remote python scripts/engines.py test --engine modal_1 --spend
docker compose exec api python scripts/engines.py budget modal_1 --limit-usd 30
docker compose exec api python scripts/engines.py activate modal_1

# 7. Rota: local primeiro, Modal sob pressão
docker compose exec api python scripts/engines.py routes set transcription \
    --step local --step "modal_1 min_wait=600"
```

`modal-deploy` monta o env do subprocesso do zero (token como variável, nunca em argv; `HOME`
temporário), roda `python -m modal deploy -m workers.engines.modal_apps.whisper_app`, chama a
função `meta()` (CPU, sem GPU) para conferir protocolo e fingerprint e só então grava
`deployments.transcription = {fingerprint, protocol, binding, verified_at, hashed}`. O fingerprint
cobre o código enviado à imagem, o lock, a revisão do modelo e o decorator (GPU, cpu, memória,
timeout, `scaledown_window`, `max_containers`). Mudar qualquer um (inclusive atualizar o código)
deixa o motor `needs_redeploy`: ele não recebe itens até o próximo deploy.

### Ativação

`POST /admin/engines/{id}/activate` (ou `engines.py activate`) exige: credenciais, teste ok mais
novo que as credenciais, `limit_usd`, deploy verificado com o fingerprint atual e `E=1`; senão 409
com a lista do que falta. `pause` só impede novas colocações; o que está em voo termina.

| Método e caminho | O que faz |
|---|---|
| `PUT /admin/engines/{id}/credentials` | `{fields: {token_id, token_secret}, current_password}`; 403 sem a senha, 409 sem `ENGINE_SECRETS_PUBLIC_KEY`; exige novo teste |
| `DELETE /admin/engines/{id}/credentials` | `{current_password}`; motor ativo é pausado |
| `POST /admin/engines/{id}/test` | enfileira em `ingestify-remote-ctl` e espera ≤ 30 s; 409 sem `worker-remote` |
| `PUT /admin/engines/{id}/budget` | `limit_usd`, `min_remaining_usd`, `soft_pct`, `period_tz`, `period_anchor_day`; motor remoto ativo não fica sem limite |
| `POST /admin/engines/{id}/activate` · `/pause` · `/reset-health` | ciclo de vida |

Todas exigem sessão JWT e gravam `admin_audit` (nunca o valor das credenciais).

### Uma tentativa remota

1. **Colocação** (despachante): reserva o pior caso
   `(D ÷ default_speed + 15 + cold_start) × rate × 1,2`, com `rate = GPU + cpu × P_cpu + memória × P_mem`
   (`shared/engines/pricing.py`; preços de `gpus.py`, a conferir no gate T5). Mídia acima de
   `max_input_bytes` (512 MB) ou de `max_media_seconds` (4 h) fica nos passos locais.
2. **Claim** (`worker-remote`): `reserved→spawning` sob o lock do motor, refazendo a fórmula com a
   própria reserva e o gasto reportado; motor pausado, doente, `needs_redeploy` ou sem orçamento ⇒
   reserva devolvida e o item volta à cabeça do backlog.
3. **Execução**: lê a mídia do volume temporário (ou do MinIO) e a envia na chamada (o Modal não
   alcança o MinIO), no máximo `REMOTE_MAX_CONCURRENT_UPLOADS` por vez; grava `provider_call_id` e
   `deadline_at = spawned_at + reservado ÷ rate` **antes** de esperar; espera em fatias de 15 s com
   heartbeat; passado o prazo, cancela (flag cooperativa no `modal.Dict` + `FunctionCall.cancel()`).
4. **Saída e settle**: resposta validada contra `modal_apps/protocol.py`, depois
   `finish_transcription` como no local, depois `actual = max(segundos reportados, medidos) × rate`.

Falhas (Apêndice J): `AUTH` deixa o motor `unhealthy`, `QUOTA_EXHAUSTED` (limite de gasto,
workspace desabilitado) `exhausted` até o próximo período, `NOT_DEPLOYED` `unhealthy` por 10 min;
nenhum desses conta tentativa e o item volta excluindo o motor por 15 min. `TIMEOUT` e `INTERNAL`
contam; `INPUT_REJECTED` falha o job na hora. O sweeper republica tentativas silenciosas, pede
cancelamento de chamadas passadas do prazo e, após 5 republicações, liquida `lost` cobrando a
reserva inteira; nunca liquida uma chamada que ainda pode terminar.

A cada 10 min o `worker-remote` lê `modal billing report --json` de cada motor ativo e guarda o
maior valor já visto (`provider_reported_usd`), que entra no `max(ledger, reportado)` do orçamento;
relatório ilegível deixa o motor `degraded` (não recebe itens) até a próxima leitura.

### Custos

- Teste (`test`) e relatório de gasto: grátis, sem container.
- Deploy: build da imagem (CPU; o primeiro baixa ~1,6 GB de pesos) e alguns segundos de um
  container de 0,25 CPU para `meta()`.
- Cada item: o tempo do container (GPU + CPU + memória) desde o início do input, mais o cold start
  (~20–40 s em L4) quando o container estava frio e a cauda ociosa (`scaledown_window=60` s,
  ≈ US$ 0,016 em L4) depois do último item. Nunca `min_containers > 0`.
- Recomenda-se configurar também o limite de gasto no próprio Modal; o do Ingestify é por conta
  inteira e enxerga o gasto de outros sistemas com o atraso do relatório (~5 min).
