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
| `PUT /admin/routing/{feature}` | Cria ou troca a rota (`version` opcional ⇒ 409 em conflito). 422: motor sem capacidade para a feature, motor repetido, passo remoto com `admins` sem passo local; 409: motor remoto (fatia 4a). `remote_allowed_for=all` exige `current_password`, `user_period_limit_usd` e `remote_data_notice` |
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
