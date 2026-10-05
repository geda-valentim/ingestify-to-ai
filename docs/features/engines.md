# Motores de execução: rotas, backlog e despachante

> Verificado contra o código em 2026-10-05 (spec 0003, fatias 2 a 4c). Fonte da verdade:
> [backend/shared/engines/](../../backend/shared/engines/) (`routing.py`, `dispatch.py`,
> `ledger.py`, `budget.py`, `budget_watch.py`, `alerts.py`, `speed.py`, `pricing.py`, `capacity.py`),
> [backend/workers/engines/](../../backend/workers/engines/) (`dispatcher.py`, `lease.py`,
> `sweeper.py`, `watchdog.py`, `tasks.py`, `local.py`, `remote.py`, `remote_tasks.py`,
> `benchmark.py`, `modal_deploy.py`),
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
| `group_strategy` | `priority`: na ordem; `fill_first`: o motor "corrente" (o elegível com a linha `kind=job` mais recente **do período**; sem nenhuma, o primeiro) primeiro. Recusa por orçamento, tamanho ou `spend_cap` ⇒ o próximo na hora; corrente **cheio** ⇒ o próximo só abre depois de `scale_out_after_seconds` (padrão 300), medido por `engine_feature_state.full_since` (zerado quando o motor volta a ter vaga). Probes, benchmarks e caudas nunca mudam o corrente |
| `when.min_wait_seconds` / `when.min_backlog` | o passo só vale se o item esperou N s **ou** o backlog tem N itens |
| `spend_cap` | `{usd, window: day\|period}`: liquidado + reservado + estimativa ≤ usd (só remoto) |

E, por rota: `max_attempts` (3), `on_no_engine` (`hold`/`fail` + `fail_after_seconds`),
`remote_allowed_for` (`admins`/`all`), `dispatcher_fallback` (`local_direct`/`hold`),
`dispatcher_down_seconds` (120).

Motores remotos (Modal, fatia 4a) entram numa rota quando estão ativos, saudáveis, com orçamento,
deployados e com um `worker-remote` vivo (senão `409`). Uma rota só com `local` já é útil: o
backlog é durável no MySQL, a capacidade configurada é respeitada e as falhas voltam com backoff.

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
  `capacidade − em_voo` itens em passos locais. Com `hold`, só alerta (log e webhook). Redis fora derruba o
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

1. **Colocação** (despachante): reserva, com `rate = GPU + cpu × P_cpu + memória × P_mem`
   (`shared/engines/pricing.py`; preços de `gpus.py`, a conferir no gate T5), enquanto a chave
   `(motor, feature, gpu, E)` tem menos de 50 tentativas liquidadas com sucesso, o **pior caso**
   `(D ÷ s_p20 + 15 + cold_s_p80) × rate × 1,2` (velocidade e cold start da chave; sem 5 linhas,
   do último benchmark dela; sem benchmark, `default_speed ÷ E` e 30 s); a partir de 50,
   `D × q95(actual_usd ÷ D) × 1,2` (ver "Velocidade aprendida"). Mídia acima de
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
workspace desabilitado) `exhausted` até o início do próximo período (no fuso do motor) com um
alerta por período, `NOT_DEPLOYED` `unhealthy` por 10 min;
nenhum desses conta tentativa e o item volta excluindo o motor por 15 min. `TIMEOUT` e `INTERNAL`
contam; `INPUT_REJECTED` falha o job na hora. O sweeper republica tentativas silenciosas, pede
cancelamento de chamadas passadas do prazo e, após 5 republicações, liquida `lost` cobrando a
reserva inteira; nunca liquida uma chamada que ainda pode terminar.

A cada 10 min o `worker-remote` lê `modal billing report --json` de cada motor ativo e guarda o
maior valor já visto (`provider_reported_usd`), que entra no `max(ledger, reportado)` do orçamento;
relatório ilegível deixa o motor `degraded` (não recebe itens) até a próxima leitura, e também um
relatório de **US$ 0 por mais de 3 h** com o ledger acima de US$ 0,50 no período (fail closed). A
saída mostra `unattributed = reportado − ledger` (gasto de fora do Ingestify, ou atraso).

### Custos

- Teste (`test`) e relatório de gasto: grátis, sem container.
- Deploy: build da imagem (CPU; o primeiro baixa ~1,6 GB de pesos) e alguns segundos de um
  container de 0,25 CPU para `meta()`.
- Cada item: o tempo do container (GPU + CPU + memória) desde o início do input, mais o cold start
  (~20–40 s em L4) quando o container estava frio e a cauda ociosa (`scaledown_window=60` s,
  ≈ US$ 0,016 em L4) depois do último item. Nunca `min_containers > 0`.
- Recomenda-se configurar também o limite de gasto no próprio Modal; o do Ingestify é por conta
  inteira e enxerga o gasto de outros sistemas com o atraso do relatório (~5 min).

## Velocidade aprendida (fatia 4b)

`shared/engines/speed.py` calcula, por chave `(motor, feature, gpu, E)`, sobre as últimas 200
tentativas `kind=job` liquidadas com sucesso: `s_p20` (velocidade por item, × tempo real, ponta
lenta), `cold_s_p80` e, **a partir de 50 linhas**, `q95(actual_usd ÷ D)`. A duração vem de
`units.media_seconds` (remoto) ou de `job_dispatches.media_seconds` (local). Com menos de 5
velocidades, vale o último benchmark da chave; sem ele, `default_speed ÷ E`. O cache é
`engine:{id}:{feature}:{gpu}:{E}:speed` no Redis (1 h), escrito pelo beat do `worker-dispatch`
(`refresh_speed`, 10 min) e em cada falta; a fonte é sempre o ledger (sem Redis, recalcula).

```bash
docker compose exec api python scripts/engines.py speed [--engine modal_1]
```

## Benchmark (fatia 4b)

`engines.py benchmark` (Apêndice H) mede velocidade por item e agregada, US$/hora de áudio, VRAM e
cold start por `(gpu, E)` e recomenda **a menor US$/h que cabe na VRAM com velocidade por item ≥
`min_speed`** (no local, tudo custa 0: a maior velocidade agregada).

**Remoto** (custa dinheiro; roda no `worker-remote`, único com a chave privada):

1. Plano pessimista por combinação: `(cold_p80 + scaledown + Σ amostras × E ÷ default_speed) × rate`,
   com cada parcela impressa e o total; recusa acima de `--max-usd` (padrão 1,00), `E > 1` sem
   `--experimental` (até T4/T8 na 4d) e `workers de produção + 1 > account_max_gpus`.
2. Confirmação interativa (ou `--yes`). `--plan` só imprime.
3. Reserva: o `--max-usd` repartido entre as combinações na proporção das estimativas, uma linha
   `kind=benchmark` (`placed_by=cli`) por combinação, sob o lock do motor e a mesma fórmula de
   orçamento de qualquer reserva (sem folga ⇒ recusa). Conta no dinheiro, nunca nas vagas, e não
   muda a conta corrente do `fill_first`. O motor pode estar pausado.
4. Cada combinação é um **app efêmero**: `python -m modal run -m
   workers.engines.modal_apps.bench_entry::bench` num subprocesso com env do zero (token como
   variável, `HOME` temporário) e o deploy spec daquela GPU/`E` — nunca o app de produção, nunca um
   deploy. O prazo (`parte ÷ rate`) conta a partir do momento em que o app sobe; passou, Ctrl-C
   (o Modal para o app efêmero). Antes de cada combinação, `gasto + estimativa > --max-usd` ⇒ para
   e relata o parcial.
5. Settle: segundos em que o app esteve de pé × `rate` (o subprocesso inteiro, se foi cortado). Um
   CLI que morre deixa linhas sem heartbeat: o sweeper as liquida `lost` em 15 min cobrando a reserva.

**Local** (custo zero, mas disputa a placa): nunca dentro de um worker vivo. Fora do container
avulso o comando só imprime o `docker compose ... run --rm --no-deps worker-audio python -m
workers.engines.benchmark ... --here` a rodar; lá dentro, antes de cada `E`, a guarda de VRAM
`usada agora (nvidia-smi) + E × pegada + reserva ≤ VRAM` recusa com a conta. `E` processos, cada
um com seu modelo (como réplicas). `--pause-local` pausa o motor local e espera o em-voo roteado;
sem ele o resultado sai `contended`.

`--apply` grava a recomendação: remoto, o binding (`gpu_type`, `E`), que passa a `needs_redeploy`
até `modal-deploy`; local, as réplicas e a pegada medida por processo (`(base + per_exec) × 1,1`,
ajuste `base_gb + E × per_exec_gb` na grade de `E`) como `vram_override_gb`, mais o `scale_hint`.
Resultados: linhas `benchmark` do ledger (`units.result`) e `GET /admin/engines/{id}/benchmarks`.

## Várias contas (fatia 4c)

- **Rota**: `--step "modal_1,modal_2,modal_3,modal_4 fill_first"` (ver a tabela de passos).
- **Orçamento por período** (`budget_watch.py`, após cada settle remoto, reconciliação e
  benchmark, sob o lock do motor): gasto `max(ledger, reportado) ≥ soft_pct %` do limite ⇒ alerta
  `budget_soft`; sobra (`limite − min_remaining − gasto`) ≤ 0 ou menor que o custo mediano de um
  item ⇒ `exhausted` até o início do próximo período e alerta `budget_exhausted`. Cada alerta uma
  vez por período (`alerted_soft_period` / `alerted_hard_period`). Subir o limite limpa
  `exhausted`; a virada do período também.
- **Alertas** (`alerts.py`): sempre no log (`[ENGINES] ALERT <evento>`) e, com
  `ENGINE_ALERT_WEBHOOK_URL`, um `POST` JSON genérico
  `{source, event, engine, message, details, at}` sem segredos nem dados de usuário. Eventos:
  `budget_soft`, `budget_exhausted`, `quota_exhausted`, `billing_degraded`, `dispatcher_down`,
  `cost_divergence`, `engine_probe_failed`. Webhook fora do ar nunca quebra quem alertou.
- **Probes baratos** (`probe_engines`, beat do `worker-remote`, 10 min): só motores ativos usados
  em 24 h; `test_connection()` (token, workspace, app deployado e o fingerprint que o motor gravou),
  **sem container nem GPU**, por isso sem linha `kind=probe`. Falha ⇒ `unhealthy` 10 min (`AUTH`:
  até novo teste) e alerta; erro transitório não muda nada; deploy trocado por fora ⇒
  `DEPLOY_CHANGED`.
- **Todas as contas, uma de cada vez** (uma falha não para as outras):

```bash
docker compose --profile engines run --rm worker-remote python scripts/engines.py test --all
docker compose --profile engines run --rm worker-remote python scripts/engines.py modal-deploy --all --dry-run
docker compose --profile engines run --rm worker-remote python scripts/engines.py modal-deploy --all
docker compose --profile engines run --rm worker-remote python scripts/engines.py reconcile
```

| Método e caminho | O que faz |
|---|---|
| `POST /admin/engines/test-all` | testa cada motor remoto com credenciais, em sequência, no `worker-remote` (sem GPU) |
| `POST /admin/engines/{id}/reconcile` | lê o relatório de gasto daquele motor agora |
| `GET /admin/engines/{id}/benchmarks?feature=` | linhas de benchmark (`gpu × E`, resultado, custo) e a velocidade aprendida por chave |

Deploy continua só por CLI.

## A rodar com as contas reais (pendente em 2026-10-05)

O código de 4b/4c foi testado só contra um `modal` falso. Com o dono, nesta ordem (nada disso
ativa motor nem cria rota):

```bash
# 1. Benchmark da modal_1 (pode continuar pausada). Amostra: o clipe de 4 min dos gates em ./tmp/bench
mkdir -p tmp/bench && cp <clipe-4min>.mp3 tmp/bench/a.mp3
R="docker compose --profile engines run --rm worker-remote python scripts/engines.py"
$R benchmark --engine modal_1 --sample /tmp/ingestify/bench/a.mp3:240 --gpus T4,L4,A10G --concurrency 1 --max-usd 0.30 --plan
#    estimativa pessimista: T4 0,0233 + L4 0,0299 + A10G 0,0395 = US$ 0,093; teto duro US$ 0,30
#    esperado de verdade (gate 4a: frio em L4 = US$ 0,013 por clipe): ~US$ 0,04-0,06 + build de CPU
$R benchmark --engine modal_1 --sample /tmp/ingestify/bench/a.mp3:240 --gpus T4,L4,A10G --concurrency 1 --max-usd 0.30 --yes
$R reconcile --engine modal_1                       # confere o gasto contra o relatório (atraso ~5 min)
#    --apply só se a recomendação trocar a GPU; depois: $R modal-deploy --engine modal_1

# 2. Contas modal_2..4: binding e orçamento (na API), depois teste e deploy um por um
for n in 2 3 4; do
  docker compose exec api python scripts/engines.py set-capacity modal_$n transcription --workers 1 --gpu-type L4
  docker compose exec api python scripts/engines.py budget modal_$n --limit-usd 30
done
$R test --all                                       # grátis, sem container
$R modal-deploy --all --dry-run
$R modal-deploy --all                               # build de imagem (CPU, ~1,6 GB de pesos) + meta(): ~US$ 0,01-0,02 por conta
$R test --all && $R reconcile

# 3. Local (opcional, grátis): imprime o comando do container avulso; rode-o com a placa ociosa
docker compose exec api python scripts/engines.py benchmark --engine local --sample /tmp/ingestify/bench/a.mp3:240 --concurrency 1,2 --pause-local
```
