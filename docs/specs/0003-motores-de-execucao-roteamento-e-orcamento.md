# 0003 — Motores de execução: roteamento por feature com orçamento (local + Modal)

| | |
|---|---|
| **Status** | Em revisão |
| **Autor** | Geda Valentim (com agentes de backend, MLOps, frontend, decisor) |
| **Criada em** | 2026-10-04 |
| **Atualizada em** | 2026-10-04 (rodada 1 de revisão: adversarial + segurança/OSS; ver "Histórico de revisão") |
| **Relacionadas** | 0002 |
| **Substituída por** | — |

---

## 1. Problema

Hoje cada feature pesada tem **um único lugar** onde pode rodar, fixado por env var e fila Celery:

| Feature | Entrada | Fila / serviço | Quem decide o "motor" |
|---|---|---|---|
| Transcrição | `POST /transcribe` → `process_conversion` (`options.is_audio`) | `ingestify-audio` / `worker-audio` (N réplicas, uma RTX 5060 Ti 16 GB) | `AUDIO_TRANSCRIBER_PROVIDER` |
| Conversão de documentos | `/upload`, `/convert` → SPLIT → `convert_page_task` → MERGE | `ingestify` / `worker` | Docling local |
| Visão | `/images/*` (síncrono) | `ingestify-vision` / `worker-vision` | `VISION_PROVIDER` |

Na instalação do dono (exemplo), numa semana: **7.318 transcrições, 4.038 h de áudio**, mediana
15,7× tempo real por job. Duas réplicas na mesma placa (~30× agregado) ficam ~80 % ocupadas **em
média**, e os jobs chegam em rajadas: a fila cresce por horas, sem válvula de escape.

O dono tem **4 contas Modal com limite de US$ 30/mês** (hoje usadas pelo projeto "cortes") e
pediu: motores por feature (`local`, `modal_1`…`modal_4`) com **limite de gasto**; custo checado
**no início e no fim de cada job**; adapters com ciclo de vida (*warmup → exec → cooldown*);
máquina **genérica** (Docling, visão); **credenciais no banco**. O Ingestify é **open source**:
nada de conta no código, e zero contas de nuvem continua sendo o caminho padrão e completo.

Lições do cortes a não repetir: tokens em `os.environ`; teto desligado por campo de cobrança
ausente lido como 0; failover só na próxima chamada; orçamento checado só antes do lote; fan-out
com `.map()` mais caro que um container em sequência (US$ 0,041 contra 0,026).

## 2. Objetivo

Cada feature pesada passa a ter uma **rota configurável**. Na v1 isso significa: o caminho
local continua **intocado**; no submit, um job **elegível a remoto** cuja espera local estimada
passa de um limiar **transborda** para um backlog durável, de onde um despachante o coloca numa
conta remota com vaga e orçamento. Se o remoto não puder atendê-lo por tempo demais, o job
**volta para a fila local**, que é sempre o fallback gratuito quando está na rota. Uma
instalação sem rota se comporta **exatamente** como hoje.

**Garantia de gasto, dita com honestidade.** O Ingestify **para de admitir** trabalho num motor
quando `max(gasto_ledger, gasto_reportado) + reservado + estimativa > limit − min_remaining`.
A conta final ainda pode passar desse ponto por um excesso **limitado**: cancelamento em voo,
cauda ociosa dos containers e probes, ≈ **US$ 0,10 por conta** com `max_concurrency=2` em L4
(§4.7). Isso vale sob a **precondição P**: a conta é dedicada a esta instalação, **ou** tem um
limite interno dividido entre os sistemas que a usam, **e** em ambos os casos o limite de gasto
do próprio Modal está configurado. Sem P, a única garantia dura é o limite do provedor.

### Fora de escopo (v1)

- Legendas ao vivo para jobs remotos (fatia 7). Na v1 um job remoto mostra progresso estimado.
- Docling e visão remotos (fatia 8). §4.15 é um **esboço**; o modelo de dados já os comporta.
- Estratégias `round_robin` e `cheapest`; override de motor por job; `prewarm`; `auto_deploy`.
- UI de edição (formulário por descritor, rotas editáveis). A UI v1 é **somente leitura**;
  configuração via API admin e CLI.
- Orçamento por feature dentro de uma conta; fator de correção `k` do ledger; justiça entre
  usuários no backlog.
- Provedores além de `local` e `modal`. O contrato do adapter fica **provisório** até um segundo
  provedor real.
- `min_containers > 0` ou qualquer GPU ociosa paga.
- Aplicar `max_audio_duration_seconds` no caminho local (mudaria o zero-config; ver §4.3).
- Importar as 4 contas do dono: feito durante a implementação, com a CLI da fatia 2.

## 3. Critérios de aceitação

**Paridade zero-config (critério duro)**
- [ ] Sem rota para `transcription`, `POST /transcribe` enfileira `process_conversion` em
      `settings.transcription_queue` com os kwargs de hoje; nenhuma linha em `job_dispatches` ou
      `engine_usage`; `modal` ausente de `sys.modules` em todo processo.
- [ ] A suíte de `backend/tests/` passa sem alteração depois das fatias 0 a 2.
- [ ] Com rota, um job **não elegível a remoto** (usuário não autorizado, `allow_remote=false`,
      despachante sem heartbeat, erro ao ler a rota) é enfileirado exatamente como hoje.

**Decisão no submit e hand-back**
- [ ] Com `spill_wait_seconds=1200`, um job elegível fica local quando
      `profundidade × p50_local ÷ slots_configurados ≤ 1200`, e vai ao backlog quando passa.
      Reiniciar todas as réplicas de `worker-audio` não muda a decisão.
- [ ] O backlog volta à fila local: sem remoto elegível por `handback_after_seconds`; fila local
      com menos jobs que slots; rota excluída; despachante parado (watchdog no `worker` padrão).

**Dinheiro**
- [ ] Reserva, claim e settle de uma conta acontecem sob o lock da linha em `engines`;
      concorrência e gasto vêm de `engine_usage` (teste com reservas simultâneas).
- [ ] Três checagens: fórmula na reserva, fórmula de novo no claim, settle com custo medido.
- [ ] Um `modal` falso que nunca retorna é cancelado em `deadline_at`, e
      `actual ≤ reserved + latência_de_cancelamento × rate`.
- [ ] `actual = max(uso reportado pelo container, tempo de parede medido) × rate`.
- [ ] Uma chamada que terminou com `worker-remote` morto tem a saída **persistida** antes do
      settle; o sweeper nunca liquida chamada terminada.
- [ ] Relatório sem o campo esperado ⇒ `degraded` (nunca 0); `provider_reported` não diminui no
      período.
- [ ] Ativar motor remoto exige `limit_usd`, fuso, âncora e `provider_cap_confirmed`; violar ⇒ 422.

**Falhas**
- [ ] 4 contas respondendo `AUTH`: o job volta à fila local e conclui (erros de motor não contam
      para `max_attempts`).
- [ ] `INPUT_REJECTED` falha na hora; um job maior que o `max_media_seconds` de todo remoto
      nunca bloqueia a cabeça (hand-back, ou `no_engine` sem `local_fallback`).

**Segurança**
- [ ] Remoto só para admins por padrão; com `all`, o teto por usuário é checado na reserva.
- [ ] A API só tem a chave **pública**; sem a privada em `worker-remote`, nada remoto ativa; sem
      a pública, `PUT …/credentials` ⇒ 409.
- [ ] Sentinela ausente de logs (filtro stdlib), mensagens Celery, result backend, Redis,
      colunas `engine_*`/`admin_audit` e corpos 4xx/5xx mesmo com `ENVIRONMENT=development`.
- [ ] Nenhum código muta `os.environ`; env de subprocesso montado de allowlist (teste de chaves).
- [ ] Mutações admin recusam `X-API-Key`, exigem JWT, gravam `admin_audit`; credenciais exigem
      `current_password`.
- [ ] `GET /jobs/{id}` continua só do dono; não-admins veem só `engine.kind` e
      `queue_reason ∈ {in_queue, starting}`.

## 4. Solução proposta

### 4.1 Modelo de domínio

| Conceito | O que é | Exemplo |
|---|---|---|
| **Feature** | Enum fechado no código. | `transcription`, `document_conversion`, `vision` |
| **Tipo de adapter** | Classe que sabe rodar features num backend; declara capacidades, schema de config e de credencial, e seu **modelo de custo**. | `local`, `modal` |
| **Motor** | Linha em `engines`: adapter + config + credencial selada + teto de concorrência + orçamento + saúde. | `local` (semeado), `modal_1` |
| **Rota** | Por feature: motores remotos em ordem, estratégia, limiar de spill, política de quem pode ir para remoto. | §4.5 |
| **Sujeito** | O que é roteado: `(subject_type, subject_id)`. | `job`/uuid, `page`/`page_job_id`, `vision_request`/uuid |
| **Uso (ledger)** | Uma linha por **tentativa** de um sujeito num motor, mais linhas `idle_tail` e `probe`. É a fonte única de concorrência e de gasto. | job X, tentativa 2, `modal_2` |
| **Período** | Mês do orçamento no fuso/âncora do motor. Não é tabela: é a coluna `period_start` do uso. | `modal_2` / 2026-10-01 |

### 4.2 Visão geral do fluxo (transcrição)

```
POST /transcribe ─▶ API: salva o arquivo (volume temp + MinIO, como hoje); grava o Job
  dispatch.submit(feature, sujeito, usuário):
    rota existe? usuário/job elegível a remoto? despachante vivo? algum motor remoto ativo?
      └─ não → process_conversion.apply_async(queue=ingestify-audio)       ← hoje, FIM
    W_local = LLEN(ingestify-audio) × p50_local ÷ slots_configurados
      └─ W_local ≤ spill_wait_seconds → apply_async como hoje               ← FIM
    INSERT job_dispatches(state=probing) (transação própria, depois do arquivo no lugar)
    probe_media.apply_async(queue=ingestify-dispatch)
worker-dispatch:
  probe_media: duração com leitura limitada em bytes → media_seconds; inelegível p/ todo remoto?
               → hand-back (ou falha no_engine sem local); senão state=waiting; chute
  dispatch_tick (líder único): cabeça elegível → candidato (priority|fill_first)
     BEGIN; SELECT engines WHERE id=modal_2 FOR UPDATE
        vivos(modal_2) < max_concurrency ✓; teto do usuário ✓
        max(ledger 21.40, reportado 21.55) + reservado 0.07 + est. 0.069 ≤ 30.00 − 0.50 ✓
        INSERT engine_usage(status=reserved, heartbeat_at=now)          ← CHECAGEM 1
        UPDATE job_dispatches SET state=assigned
     COMMIT → publica execute_remote(usage_id) em ingestify-remote
worker-remote (threads, sem GPU, sem modelo, com a chave privada):
  claim condicional (reserved→spawning, holder, attempt_key); refaz a fórmula  ← CHECAGEM 2
  spawn(req, attempt_key) → grava provider_call_id (running), deadline_at
  laço: get(timeout=15s); renova heartbeat_at; passou de deadline_at? cancel()
  resultado → valida contra protocol.py → finish_transcription (idempotente)
  SETTLE: actual=max(reportado, medido)×rate; output_persisted_at; settled ← CHECAGEM 3
  chute no dispatch_tick; ack
```

### 4.3 Decisão no submit e sonda de mídia

`shared/engines/dispatch.submit` decide **uma vez**, no submit, entre "local como hoje" e
"backlog remoto". Roda na API só com MySQL e Redis e **nunca** importa `modal`.

**Elegibilidade a remoto** (todas precisam valer; senão, caminho de hoje):

1. há rota para a feature com algum motor remoto `active` (cache de 5 s; **qualquer erro** de
   leitura cai no caminho de hoje);
2. o dono do job passa `remote_allowed_for` (`admins`, padrão, ou `all`) e não mandou
   `allow_remote=false` (aceito de qualquer usuário, porque só restringe);
3. o heartbeat do despachante tem menos de 60 s (sem Redis, nada transborda).

**Espera local estimada**: `W_local = LLEN(fila local) × p50_local ÷ slots_configurados`.
`p50_local` é a mediana de `completed_at − started_at` dos últimos 200 jobs locais concluídos
(MySQL, cache de 10 min, fallback `default_job_seconds`); `slots_configurados` vem de
`engines[local].config.slots[feature]` (obrigatório para habilitar spill; para o dono,
`AUDIO_WORKER_REPLICAS`). **Heartbeats não entram**: um restart de `worker-audio` não provoca
transbordo em massa. Só jobs elegíveis calculam `W_local`.

Se `W_local ≤ spill_wait_seconds`, o job é enfileirado **exatamente** como hoje e nunca toca o
despachante. Senão, a linha `job_dispatches` é inserida **depois** de o arquivo estar no lugar,
em transação própria; se o `Job` não foi gravado, cai no caminho de hoje.

**Sonda** (`probe_media`, em `worker-dispatch`, nunca na API): lê através de um wrapper que
recusa bytes além de `PROBE_MAX_BYTES` (8 MB), com timeout de 10 s, e extrai a duração `D` do
container (sem ela, tamanho ÷ bitrate). Se `D` excede o `max_media_seconds` de **todo** motor
remoto da rota (derivado do `timeout` do app e de `max_audio_duration_seconds`), ou se a
estimativa não cabe no limite **inteiro** de nenhum motor, o job volta à
fila local na hora, ou falha `no_engine` sem `local_fallback`: um job que nenhum motor aceitaria
nunca chega à cabeça do backlog. Senão, para vídeo, o mesmo worker extrai o áudio (remux, sem
re-encode, com time limit) e a linha vira `waiting`. O processo com a chave privada nunca demuxa
mídia não confiável.

`max_audio_duration_seconds` (declarado e nunca aplicado) passa a valer como **limite de
admissão remota**. No caminho local continua como hoje: aplicá-lo lá rejeitaria jobs que hoje
funcionam (issue própria). Uma duração **subdeclarada** não é detectada pela sonda; a defesa é o
teto por tentativa (§4.6).

### 4.4 Backlog, despachante, raia remota e hand-back

- **Backlog**: `job_dispatches`, só com jobs que transbordaram. FIFO por `(priority,
  enqueued_at)`; `priority=0` para jobs devolvidos por falha de motor.
- **Despachante**: `dispatch_tick` em `ingestify-dispatch`, servido por `worker-dispatch`
  (prefork, `-c 2`: um tick por vez via lock, sondas em paralelo). Gatilhos: chute após sonda,
  settle e requeue (deduplicado por `SET engines:kick NX PX 500`), e beat a cada 5 s com
  `expires`. Líder único via `SET engines:dispatch:lock <token> NX EX 15`, liberado por
  compare-and-delete. Escreve `engines:dispatcher:heartbeat` (TTL 30 s). É o **único escritor**
  de reservas, o que serializa o teto por usuário entre motores.
- **Lookahead**: olha as 20 primeiras linhas `waiting`. Uma cabeça que espera **orçamento** não
  bloqueia uma menor que cabe; uma linha pulada 10 vezes vira bloqueante (não morre de fome).
- **Raia remota**: `ingestify-remote`, consumida por `worker-remote` (`--pool=threads
  --concurrency=${REMOTE_WORKER_CONCURRENCY:-16}`), mais `ingestify-remote-ctl` para teste,
  saúde e reconciliação. Configurar rotas com `Σ max_concurrency > REMOTE_WORKER_CONCURRENCY − 2`
  responde 409, então mensagens de execução não esperam na raia e sempre sobram threads para
  controle. `stop_grace_period: 60s`; o que morrer em `get()` é retomado pelo sweeper (§4.6).
- **Hand-back à fila local** (só com `local_fallback=true`), com `UPDATE … WHERE state='waiting'`
  condicional e publicação depois do commit (`local_published_at`; o watchdog republica linhas
  `local` sem publicação há 60 s):
  1. a linha está `unplaceable_since` há mais de `handback_after_seconds` (padrão 600): remoto
     indisponível, esgotado ou ocupado;
  2. a fila local tem menos jobs que `slots_configurados` (a GPU local vai ficar ociosa);
  3. a sonda achou o job grande demais para todo remoto;
  4. a rota foi excluída ou perdeu os motores remotos (na mesma requisição);
  5. `engines_watchdog` (beat roteado para a fila `ingestify`, servida pelo `worker` padrão que
     sempre roda) vê o heartbeat do despachante parado há mais de `handback_after_seconds`.
- **Payload**: `job_dispatches.payload` segue um schema **por feature com allowlist** (não os
  kwargs crus); um teste rejeita chaves `*token*`, `*secret*`, `auth_token`.

### 4.5 Rota e estratégias

```
transcription: remote=[modal_1, modal_2, modal_3, modal_4]  strategy=fill_first
               local_fallback=true  spill_wait_seconds=1200  handback_after_seconds=600
               remote_allowed_for=admins  max_attempts=3
```

Isso é a **configuração de exemplo do dono**, não um padrão do repositório. Uma rota com motor
remoto exige `spill_wait_seconds` explícito (não há default: um número que dependa da GPU de
alguém não deve virar padrão de todo mundo). Para o dono, 20 min ≈ 10 h de áudio drenadas pela
placa local. Gastar crédito com o que a placa termina em minutos desperdiça a única capacidade
de rajada que existe (§4.16; Q2 pergunta se ele prefere o inverso, `spill_wait_seconds=0`).

| Estratégia | Comportamento |
|---|---|
| `priority` | Ordem da lista; o próximo é usado quando o anterior está sem vaga ou inelegível. |
| `fill_first` | *Sticky*: a conta "corrente" é a elegível com o uso mais recente no período (derivado de `engine_usage`, não do Redis), ou a primeira da lista. Recebe tudo até esgotar ou ficar indisponível; a próxima só abre se a corrente estiver lotada há mais de `scale_out_after_seconds` (padrão 300). Amortiza cold start e cauda ociosa. |

Um motor é **elegível** para um job quando está `active`, saúde ∉ {`unhealthy`, `exhausted`,
`degraded`}, não está em `exclude_engines` do job, `D ≤ max_media_seconds`, tem vaga e a reserva
cabe (§4.6). Sem candidato: a linha fica `waiting` com `unplaceable_since` e o hand-back resolve;
sem `local_fallback`, vale `on_no_engine` (`hold` ou `fail` com `budget_exhausted`/`no_engine`).

### 4.6 Dinheiro: uma tentativa do início ao fim

O MySQL é a fonte da verdade. **Um lock por motor**: toda transação de dinheiro começa com
`SELECT … FROM engines WHERE id=? FOR UPDATE`, e não existe outro lock de dinheiro. Settle e
nova reserva são transações separadas. Toda transação de dinheiro repete em erro 1213/1205.
Valores usam `Decimal(str(x))`, reservas arredondam para cima, `DECIMAL(12,6)` no banco.

**Derivações do ledger** (índice `(engine_id, period_start, status)`; poucos milhares de
linhas por mês):

```
vivos(e)    = COUNT(*)  WHERE engine_id=e AND status IN (reserved, spawning, running)
ledger(e,p) = SUM(actual_usd)   WHERE engine_id=e AND period_start=p AND status IN (settled, orphaned)
reservado   = SUM(reserved_usd) WHERE engine_id=e AND period_start=p AND status IN (reserved, spawning, running)
admite      ⇔ vivos < max_concurrency
              ∧ max(ledger, engines.provider_reported_usd do período) + reservado + estimativa
                  ≤ limit_usd − min_remaining_usd
              ∧ (remote_allowed_for=all ⇒ gasto_do_usuário_no_período + estimativa ≤ user_period_limit_usd)
```

Linhas vivas com heartbeat velho **continuam contando** (conservador) até o sweeper resolvê-las.
Não há leases no Redis nem tabela de contadores: perder o Redis não muda nada de dinheiro.

**Estados de `engine_usage`** (dinheiro e saída são passos separados):

| `status` | Dinheiro | Saída | Quem avança |
|---|---|---|---|
| `reserved` | reservado | — | executor (claim condicional) |
| `spawning` | reservado; `attempt_key` gravado; `spawn` pode ter acontecido | — | executor |
| `running` | reservado; `provider_call_id` e `deadline_at` gravados | — | executor |
| `settled` | liquidado (`actual_usd`) | `output_persisted_at` preenchido, **ou** `outcome ∈ {failed, cancelled}` | terminal |
| `released` | reserva devolvida, nada cobrado | — | terminal |
| `orphaned` | liquidado pela **reserva inteira** (conservador) | nenhuma; sujeito devolvido ao backlog | terminal |

Regra dura: **`settled` com `outcome=succeeded` só existe com `output_persisted_at`**.

**1. Reserva (despachante).** A estimativa é do modelo de custo do adapter (§4.10):

```
rate     = P_gpu + cpu·P_cpu + mem_GiB·P_mem         (tabela com prices_as_of, overridável)
exec_hi  = D / s_p20 + 15
hold     = (exec_hi + P_cold·cold_s_p80) × rate × (1 + margin)
```

`s_p20` e `cold_s_p80` vêm das últimas 200 linhas liquidadas do mesmo `(motor, gpu, modelo)`
(cache `engine:{id}:speed`); com n < 20, `default_speed` da config (benchmark). Exemplo: aula de
33 min em L4, fria, hold ≈ US$ 0,07. A reserva grava `heartbeat_at=now()`.

**2. Claim (executor).** `UPDATE … SET status='spawning', holder=?, attempt_key=uuid,
heartbeat_at=now() WHERE id=? AND status='reserved'`. Sob o lock do motor, refaz a fórmula com
a própria reserva já incluída e o `provider_reported` mais recente; motor pausado/esgotado ou
fórmula violada → `released`, linha do backlog volta a `waiting` (`UPDATE … WHERE
state='assigned' AND usage_id=?`). O claim também revalida os invariantes de orçamento (§4.7).

**3. Execução com teto.** `spawn(req)` leva `attempt_key`; o app registra
`attempt_key → call_id` num `modal.Dict` na entrada e recusa duplicata (confirmar API, gate da
fatia 4a). Em seguida grava `provider_call_id`, `spawned_at`, `status='running'` e
`deadline_at = spawned_at + reserved_usd ÷ rate`. O laço faz `get(timeout=15 s)`, renova
`heartbeat_at` em transação curta (nunca segura sessão durante `get`), e ao passar de
`deadline_at` chama `cancel()`. **A reserva é o teto da tentativa**: o excesso possível é
`(fatia de 15 s + latência de cancelamento) × rate`, ≈ US$ 0,008 em L4. O `timeout` da função
Modal é fixado no deploy pelo maior job admissível (§4.11), como segunda barreira.

**4. Saída e settle (executor).** O resultado é validado contra `protocol.py` (pydantic,
`max_segments` e `max_text_bytes` proporcionais a `D`); `finish_transcription` grava Redis,
MinIO, ES e MySQL de forma idempotente; depois, numa transação: `actual_usd = max(segundos
reportados pelo container, segundos de parede medidos de spawn ao resultado) × rate`,
`output_persisted_at=now()`, `status='settled'`, `outcome='succeeded'`. Divergência
`|medido/reportado − 1| > 0,3` gera alerta. Se a sobra do período ficar menor que o custo
mediano de um job (com n < 20, a estimativa do `default_speed`), o motor fica `exhausted` até o
início do próximo período. Elevar o limite no meio do mês reavalia e limpa `exhausted`.

**Reentrega e sweeper.** O executor trata a reentrega de `execute_remote(usage_id)` pelo
estado da linha (Apêndice E): um detentor vivo (heartbeat < 60 s) faz o outro sair; um detentor
morto é substituído por `UPDATE … WHERE heartbeat_at=<lido>`, que retoma por `attempt_key` ou
`provider_call_id`; estados terminais dão ack. O sweeper (`sweep_usage`, 60 s) **nunca liquida**
uma chamada terminada e **nunca estende** prazos: ele republica o executor para que a saída seja
buscada e persistida, cancela o que passou de `deadline_at` e, após 5 republicações sem
progresso, marca `orphaned` cobrando a **reserva inteira** (o teto que a tentativa podia gastar).

**Cauda ociosa e probes.** O sweeper grava `kind=idle_tail`, custo `scaledown_window × rate`,
quando um motor fica `scaledown_window + 30 s` sem linhas vivas e sem cauda desde o último
settle (só do banco, sem Redis). Com dois containers a cauda de um deles pode não ser vista
(≤ US$ 0,016 cada); a reconciliação cobre pelo `max()`. Probes de saúde com container gravam
`kind=probe`.

### 4.7 Orçamento, período, reconciliação e a precondição P

**Invariante de orçamento**, checado em toda escrita e no claim: motor remoto `active` ⇒
`limit_usd IS NOT NULL ∧ min_remaining_usd ≥ 0 ∧ period_tz ∧ period_anchor_day ∧
provider_cap_confirmed`. Não existe orçamento "soft" nem "desabilitado" para motor remoto.

**Período**: começa no dia `period_anchor_day` no fuso `period_tz`, ambos **obrigatórios** ao
criar o orçamento ("use o ciclo de cobrança do provedor"). A reserva grava `period_start`, e a
linha é liquidada contra **o seu** período. Alertas `soft_pct` (padrão 80) e de esgotamento
disparam uma vez por período (`alerted_*_period`): log WARNING/ERROR e, opcionalmente,
`ENGINE_ALERT_WEBHOOK_URL` (só env; sem segredos nem dados de usuário no payload).

**Reconciliação** (`reconcile_spend`, 10 min, em `ingestify-remote-ctl`): lê o relatório de
cobrança do provedor via CLI em subprocesso com **env de allowlist** (§4.12), para o intervalo
`[period_start, period_end)` em UTC quando o CLI aceitar intervalo; senão, não reconcilia a
menos de 1 dia de uma virada. Parsing estrito; campo ausente → `degraded` (**fail closed**).
`provider_reported_usd = GREATEST(anterior, novo)` dentro do período. Zero com ledger >
`max(0,50, 5 × resolução do relatório)` por mais de 3 h → `degraded`. `unattributed = reportado −
ledger` aparece na visão admin, com aviso quando > 0.

**Precondição P (contas compartilhadas).** `max(ledger, reportado)` protege contra o gasto que o
Ingestify **vê**. Ele não protege contra outro sistema escrevendo na mesma conta com 5–15 min de
atraso: dois controladores com US$ 9,50 de folga cada podem gastar US$ 39 numa conta de US$ 30.
Por isso, ativar um motor remoto exige:

1. conta **dedicada** a esta instalação, **ou** limite interno dividido (`limit_usd = conta ×
   fração`, e o outro sistema configurado com o complemento); e
2. o **limite de gasto do workspace Modal** configurado no provedor (o admin confirma com
   `provider_cap_confirmed`; a API não consegue verificar). Se ele disparar, o adapter
   classifica como `QUOTA_EXHAUSTED`.

Recomenda-se um token próprio do Ingestify por conta (`modal token new`), nunca o token de outro
app.

**Excesso limitado** (contas sob P, tabela de preço correta), por conta:
`(limit − min_remaining) + max_concurrency × excesso_de_cancelamento + max_concurrency × cauda +
probes`. Em L4 com `max_concurrency=2`: 29,50 + 2×0,008 + 2×0,016 + ~0 ≈ **US$ 29,55**. Uma
tabela de preço desatualizada desloca isso proporcionalmente até a reconciliação seguinte; por
isso o alerta `reportado/ledger > 1,2` e o aviso de `prices_as_of` velho.

### 4.8 Falhas e re-enfileiramento

Não existe failover dentro da task. Em falha, o executor liquida o que foi cobrado, marca o
motor e **devolve o sujeito à cabeça do backlog** (`priority=0`) com o motor em
`exclude_engines`, e chuta o despachante. A latência até a próxima conta é ≤ 1–5 s, o que
mantém a correção do cortes (o **mesmo** job troca de conta na hora) com um único escritor
de reservas.

| Erro (`classify_error`) | Estado do motor | Conta em `max_attempts`? | Este job |
|---|---|---|---|
| `AUTH` | `unhealthy` até corrigir credenciais | não | requeue na cabeça, excluindo o motor |
| `QUOTA_EXHAUSTED` | `exhausted` até o período seguinte; reconcilia na hora | não | idem; cobra o medido |
| `CAPACITY` / `RATE_LIMITED` | capacidade efetiva −1 por 5 min | não | idem |
| `COLD_START_FAILED` / `NOT_DEPLOYED` | `unhealthy` 10 min (exponencial até 2 h) | não | idem |
| `TRANSIENT` (rede antes do `spawn`) | — | não | até 3× no mesmo motor, com backoff |
| `TIMEOUT` (passou de `deadline_at`) | `consecutive_failures++` | **sim** | requeue com reserva ×1,5 |
| `INTERNAL` | 3 em 5 min → `unhealthy` 10 min | **sim** | requeue excluindo o motor |
| `INPUT_REJECTED` | — | — | falha na hora |

Contadores separados: `job_failures` (só os que contam) e `placements` (toda tentativa, que é
o `attempt` do ledger). Com `job_failures ≥ max_attempts`, ou com todo remoto excluído, o job
volta à fila local se `local_fallback`; senão falha com `engine_error`. Exclusões expiram em
15 min para rotas sem `local`.

### 4.9 Estado do job no caminho roteado

| Momento | `jobs.status` | `started_at` | Redis `job:{id}:status` |
|---|---|---|---|
| Transbordo, sonda, espera, colocação | `PENDING` | `NULL` | `queued` |
| Claim | `PROCESSING` | agora | `processing` |
| Requeue | `PENDING` | `NULL` | `queued` |
| Hand-back | `PENDING` (o worker local segue como hoje) | `NULL` | `queued` |
| Settle com saída | `COMPLETED` (via `finish_*`) | — | `completed` |

Jobs no backlog ficam `PENDING` com `started_at NULL`, então `detect_stuck_jobs` (que só olha
`PROCESSING` com `started_at` > 30 min) não os marca. Para jobs remotos em execução,
`get_stuck_jobs` passa a **excluir** jobs com linha viva em `engine_usage` e `heartbeat_at`
recente; jobs sem linha de uso (todo o zero-config) não mudam. No caminho roteado,
`finish_transcription` só conclui a partir de `PROCESSING` e registra em log qualquer tentativa
FAILED→COMPLETED.

### 4.10 Contrato do adapter (provisório)

Fica em `backend/workers/engines/base.py`; tipos puros em `backend/shared/engines/types.py`;
assinaturas no Apêndice F. O adapter recebe snapshot do motor e credenciais (que vivem só no
objeto), e expõe `ensure_ready` (só verifica), `execute` (com `deadline_at`, heartbeat e
`record_call_id`), `resume`, `lookup_attempt`, `cancel`, `cooldown`, `provider_spend`, `health`,
`test_connection` e `classify_error`, mais um `CostModel` próprio.

`TranscriptionInput/Output` são pydantic com `schema_version`, em `shared/engines/features.py`.
O modelo de custo é do adapter: Modal cobra segundos × (GPU + CPU + memória); um provedor por
minuto de áudio implementaria outro `CostModel`.

Regras de contrato (testes, em `tests/engines/contract.py`, parametrizáveis): `ensure_ready`
não gasta GPU; `execute` devolve `Usage` mesmo em falha cobrada; o custo nunca depende de
`cooldown`; nada de credencial em `os.environ`; todo objeto do SDK é criado com `client=`
explícito. Um provedor com pod persistente só seria aceito com um beat que pare pods ociosos.

**`LocalAdapter`** embrulha o código de hoje e só é usado pela tarefa local já existente; na
v1 o despachante não coloca jobs nele (o local é a fila de hoje).

### 4.11 Adapter Modal e o app Whisper

**Código no repositório, deployável em qualquer conta**, em `backend/workers/engines/` (as
imagens só copiam `api/`, `shared/` e `workers/`; árvore no Apêndice F). `whisper_core.py` é a
fonte única do laço de decodificação (VAD, beam 5, timestamps por palavra, extrator com memória
limitada), usado também pelo transcritor local (fatia 1b), cuja revisão HF passa a ser fixada.

**Imagem**: `debian_slim` Python 3.12, `faster-whisper`, `ctranslate2>=4.5,<5`, **`av<19`**,
cuBLAS/cuDNN 9 cu12. Lock com `uv pip compile --generate-hashes`, instalado com
`--require-hashes`; base e `image_builder_version` fixados; pesos embutidos numa revisão HF
fixada. Tudo entra no fingerprint.

**App** `ingestify-whisper`: `@app.cls(gpu=<config>, cpu=2, memory=6144, timeout=<derivado>,
scaledown_window=60, max_containers=<cap>, min_containers=0, retries=0)`, com
`timeout = ceil(max_media_seconds ÷ min_speed) + 300` (3 h de áudio a 6× ⇒ 2.100 s).
`retries=0` porque quem decide retentativa é o dono do ledger; uma reexecução por preempção do
Modal aparece na reconciliação.

**Deploy só por CLI**: `python -m workers.engines.modal_deploy --engine <slug>`, no container de
`worker-remote`, em subprocesso com env de allowlist. Grava `deployed_fingerprint` no motor e num
`modal.Dict` da conta. `ensure_ready` só **verifica**: fingerprint diferente ⇒ `degraded` com
"rode `modal_deploy`"; protocolo diferente ⇒ `unhealthy`. O fingerprint é checagem de
**consistência**, não autenticação.

**Saúde barata**: sem container quando possível (hidratar a função com o cliente confere auth e
deploy; o fingerprint vem do `Dict`). Se precisar de `meta()`: `scaledown_window=2`, só para
motores usados nas últimas 24 h ou no teste, gravando `kind=probe` (§4.16 mostra por quê).

**Credenciais por cliente**: `modal.Client.from_credentials(...)` e todo objeto do SDK com
`client=` explícito. Teste: `worker-remote` com `MODAL_TOKEN_ID=sentinela` no env e sem
`~/.modal.toml` funciona, e qualquer fallback para o env falha alto.

**Mídia e recursos**: bytes vão na chamada (o MinIO está atrás de NAT), lidos do arquivo que a
sonda preparou; `REMOTE_MAX_CONCURRENT_UPLOADS` (padrão 4); pool do SQLAlchemy =
`REMOTE_WORKER_CONCURRENCY + 4`. **Nunca** `min_containers ≥ 1`; `cooldown` só solta o cliente.

### 4.12 Credenciais e segredos

- **Selagem assimétrica** (`SealedBox`, PyNaCl): API e CLI de importação têm só
  `ENGINE_SECRETS_PUBLIC_KEY` e **selam**; só `worker-remote` (e CLIs no container dele) tem
  `ENGINE_SECRETS_PRIVATE_KEYS` (lista para rotação; também `*_FILE`). Um RCE na API não decifra
  tokens. O selado inclui `engine_id` e `key_id`, verificados ao abrir (troca de linhas falha).
- **Não existe chave padrão.** Sem pública: `PUT …/credentials` ⇒ 409. Sem privada: o teste
  falha com `NO_KEY` e o motor não ativa. Formato validado no boot, desligando só motores. As
  chaves vão só em `api` e `worker-remote`, não no `worker` base que `worker-audio` estende. Doc:
  guardar a privada longe dos backups do banco; runbook de perda.
- **Somente escrita**: respostas trazem `{is_set, hint, updated_at, updated_by}`; `hint` só em
  campos `hint_mode=last4`, proibido em `kind=secret` (teste do registro).
- **Redação** no logging que o projeto usa (stdlib, não structlog): `logging.Filter` no root
  logger da API, workers e CLIs, removendo padrões de token, chaves
  (`token_secret|api_key|secret|authorization`) e os valores decifrados no processo; `redact()` em
  toda string de erro persistida. Rotas admin devolvem `ErrorCode` e mensagem saneada em
  qualquer `ENVIRONMENT`.
- **Subprocessos**: env **montado do zero** (`PATH`, `LANG`, `HOME=<tmpdir>`, `PYTHONPATH`,
  `MODAL_TOKEN_ID/SECRET`, `MODAL_ENVIRONMENT`), `cwd=tmpdir`, tokens nunca em argv.
- **CLI de importação** (`python -m workers.engines.cli import`): `getpass`, JSON ou `.env` pela
  stdin (`dotenv_values`, sem tocar `os.environ`; `--prefix MODAL_ACCOUNT_` cobre o formato do
  dono) ou perfis do `~/.modal.toml`. Dry-run por padrão (`--apply`), motores **pausados**, só
  IDs mascarados, idempotente por slug, sem mexer em rotas. `--activate` enfileira o teste em
  `ingestify-remote-ctl`.

### 4.13 Quem pode gastar e quem administra

- **`remote_allowed_for`**: `admins` (padrão) ou `all`. Com `all`, `user_period_limit_usd` é
  obrigatório e checado na reserva (API keys contam como seu usuário), e a rota exige um
  `remote_data_notice` exibido no upload e na doc da API (a mídia sai para a nuvem; `purge_source`
  não cobre cópias retidas pelo provedor).
- **`is_effective_admin(user)`** sai de `require_admin` para `shared/` e é a única regra de
  `/auth/me`, rotas admin e política de rota. Rebaixar via `ADMIN_USER_IDS` exige restart.
- **Mutações** de motor, credencial, orçamento e rota usam `require_admin_session`: JWT
  obrigatório (`X-API-Key` ⇒ 403), `admin_audit` (ator, método, IP, alvo, antes/depois sem
  segredos) e log WARNING. Credenciais e ampliar `remote_allowed_for` exigem `current_password`.
  Leituras seguem `require_admin`. Sem `PATCH` (o CORS não o permite): `PUT` com `version`.
- **`GET /jobs/{id}` continua só do dono** e ganha `engine.kind` e `queue_reason ∈ {in_queue,
  starting}`. Orçamento, slug, custo e trilha ficam em `GET /admin/jobs/{id}/engine`, que devolve
  **metadados**, nunca conteúdo.
- **Primeiro admin**: `scripts/make_admin.py`, corrigido na fatia 0b (`--email`/`--id`
  explícito, recusa ambiguidade, mostra id+username+email e pede confirmação). A tela 403 diz
  "peça ao administrador"; o comando fica no README.
- CSP (`script-src 'self'`) em `/admin/*`. Se a auth for para cookie `HttpOnly`, mutações
  `/admin` passam a exigir token CSRF.

### 4.14 Mudanças por camada

**API**: `engine_admin_routes.py` (Apêndice B); `/transcribe` passa por `dispatch.submit` e
aceita `allow_remote`; `/auth/me` e login ganham `is_admin`. Nenhum `av.open` na API.

**Workers** (`backend/workers/engines/`): `base.py`, `registry.py` (imports lazy),
`adapters/{local,modal}.py`, `dispatcher.py`, `pipeline.py`, `cli.py` e `tasks.py`
(`probe_media`, `dispatch_tick`, `execute_remote`, `sweep_usage`, `reconcile_spend`,
`engine_health`, `engines_watchdog`). `pipeline.finish_transcription` é o pós-processamento
extraído de `process_conversion`, idempotente, mantendo a semântica de falha de hoje no caminho
local. Beats novos com `options.expires` e `task_routes` explícitas. Correção do `force_provider`
global da factory de áudio (fatia 4a).

**Shared** (`backend/shared/engines/`, sem dependências pesadas): `features.py`, `types.py`,
`specs.py`, `pricing.py`, `sealing.py`, `redact.py`, `routing.py`, `budget.py`, `dispatch.py`.

**Celery (fatia 0a)**: `broker_transport_options={"visibility_timeout": 14400}`, acima do maior
`time_limit` (10.800 s do `worker-audio`), e beat `broker_unacked_check` que alerta mensagens em
`unacked` além disso. Hoje, com o padrão de 3.600 s, uma transcrição local de mais de 1 h é
reentregue **enquanto ainda roda**. Custo: após crash de worker, a reentrega demora até 4 h.

**Dados** (Apêndice A): **5 tabelas novas**: `engines` (com orçamento, credencial selada,
deploy e relatório do provedor), `feature_routes` (motores em JSON validado), `engine_usage`,
`job_dispatches`, `admin_audit` (append-only). **Nenhuma coluna nova em tabela existente**, logo
nada em `_ADDED_COLUMNS`: models (o `create_all` cobre instalações novas) + uma revisão Alembic,
com teste de CI comparando os esquemas. `init_db()` semeia só `local`. Sujeitos sem FK para
`jobs`; `cleanup_old_jobs` não apaga custo.

**Frontend** (somente leitura): `is_admin` no store; link "Compute" só para admin; guard em
`app/admin/layout.tsx` (403 "peça ao administrador"); `/admin/engines` (status, vivos/cap,
`EngineBudgetBar` com `role="meter"`, estimado × reportado, avisos de `unattributed` e preço
velho); `/admin/routing` (`describeRoute()`, backlog); `/admin/usage` ($/h de áudio);
`/jobs/[id]` mostra "Local / Nuvem". Sem dependência nova; tipos no Apêndice C.

**Compose / Ops**: `worker-dispatch` (`-Q ingestify-dispatch -c 2`, com `av`, sem chave
privada) e `worker-remote` (`-Q ingestify-remote,ingestify-remote-ctl --pool=threads`,
`requirements-remote.txt` com modal, av, celery, SQLAlchemy, minio, ES, PyNaCl; volume temp;
`stop_grace_period: 60s`), no **profile `engines`**. Rota com remoto sem heartbeat desses
serviços ⇒ 409. Env vars novas, todas opcionais: `ENGINE_SECRETS_PUBLIC_KEY`,
`ENGINE_SECRETS_PRIVATE_KEYS[_FILE]`, `REMOTE_WORKER_CONCURRENCY`,
`REMOTE_MAX_CONCURRENT_UPLOADS`, `PROBE_MAX_BYTES`, `ENGINE_ALERT_WEBHOOK_URL`. Docs:
`docs/engines/MODAL.md` (deploy, custos, precondição P, dados enviados e retenção, atualização
do cliente `modal`) e `docs/engines/ADAPTERS.md`.

### 4.15 Generalidade: Docling e visão (esboço, fatia 8)

Uma feature nova precisa de: um valor no enum com input/output tipados; uma função `finish_*`;
capacidades nos adapters; um `CostModel` por unidade. Ledger, backlog, orçamento e UI não mudam,
porque a chave é `(subject_type, subject_id)`.

- **`document_conversion`**: a unidade roteada é a **página** (`subject_type=page`,
  `subject_id=page_job_id`). `split_pdf_task` (que hoje chama `convert_page_task.delay`) e o
  retry por página passam por `dispatch.submit`; `process_page` é só um shim de compatibilidade.
  `finish_page` assume o que hoje está em `_run_page_conversion`: atualizar a linha `pages`,
  recontar o pai, progresso, e disparar `merge_pages_task` quando todas terminam. Estimativa =
  páginas × `sec_per_page_p90` × preço; `batching` vem depois da medição (T6).
  **Pré-requisito**: corrigir S-01 (JWT do usuário em `task_kwargs["auth_token"]` de `/convert`).
- **`vision`** (síncrono, `subject_type=vision_request`): sem backlog; reserva inline na
  requisição sob o mesmo lock do motor; motor remoto elegível só quente (`max_cold_start_seconds`);
  nada cabe e local na rota → `ingestify-vision` como hoje; senão 503 com `Retry-After`.

### 4.16 Economia

Preços **a confirmar**: GPU T4 ≈ US$ 0,59/h, L4 ≈ 0,80/h, A10G ≈ 1,10/h, mais ≈ 0,144/h de
`cpu=2` e 6 GiB. Container: **T4 ≈ 0,73/h, L4 ≈ 0,94/h, A10G ≈ 1,24/h**. Custo por hora de áudio
= custo do container ÷ velocidade (× tempo real).

O número anterior, **US$ 0,065/h de áudio, supõe L4 a ~14,5×** sustentado (meio da faixa
estimada de 12–18×); T4 precisaria de ~11,3× e A10G de ~19×. "As três a ±20 %" era hipótese.
Áudio por mês nas 4 contas (US$ 120), sem cold start e cauda:

| Velocidade sustentada | T4 | L4 | A10G |
|---|---|---|---|
| 6× | ~980 h | ~760 h | ~580 h |
| 10× | ~1.630 h | ~1.270 h | ~960 h |
| 15× | ~2.450 h | ~1.910 h | ~1.450 h |

Com ~4.038 h numa semana (~17.500 h/mês nesse ritmo), mesmo o melhor caso cobre ~60 % de **uma
semana**. **O Modal é válvula de rajada, não substituto da GPU local**: daí *local first +
spill* e `fill_first`.

**Fora do job**: cauda ociosa ≈ US$ 0,016 por container em L4 (60 s); cold start ~18–30 s. Um
health check com container custa ≈ **US$ 0,00012** (1 s de CPU + ~60 s de `scaledown_window`),
não US$ 0,00001: a cada 5 min, ≈ US$ 1 por conta por mês (~3,5 % do orçamento). Por isso não há
probes periódicos com container (§4.11). `BatchedInferencePipeline` (2–4× mais barato, talvez)
fica para depois de um A/B de WER.

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| **Despachante para todos os jobs** (opção D, versão anterior) | Ponto único de falha para o trabalho **local**; capacidade local por heartbeat (restart ⇒ W infinito ⇒ transbordo em massa); paridade virava teste, não propriedade. Agora só o que transborda passa pelo despachante. |
| (A) Escolher o motor de **todo** job no submit, uma fila por motor | A decisão envelhece numa rajada. Adotamos só a decisão local × backlog no submit; a colocação remota é tardia e o hand-back desfaz decisões velhas. |
| (B) Workers remotos consumindo `ingestify-audio` | Sem controle de spill; orçamento checado depois de tomar a mensagem. |
| (C) Task roteadora segurando a mensagem sem ack | O `visibility_timeout` reentrega e duplica. |
| Chamada remota dentro de `worker-audio` | Segura VRAM e modelo ociosos durante a chamada. |
| Leases no Redis + tabela de contadores de período | Duas verdades, sem heartbeat durável, reconstrução frágil. Contar o ledger sob o lock do motor basta nesta escala. |
| Failover dentro da task | Segundo escritor de reservas e risco de deadlock; requeue na cabeça tem a mesma latência prática. |
| `round_robin`/`cheapest`, override por job, `prewarm` na v1 | Sem caso de uso com um provedor; `round_robin` entre contas Modal multiplica cold starts. |
| `auto_deploy` pelo `worker-remote` | Ping-pong em upgrade, deploy na thread de um job, risco de cadeia de suprimentos. |
| Fernet simétrico com a chave na API | Quem cifra decifra; a API é exposta. |
| Sonda de duração na API | Demuxers FFmpeg no processo com `JWT_SECRET_KEY`. |
| Admins lendo qualquer job em `GET /jobs/{id}` | Expansão silenciosa de privilégio sobre conteúdo. |
| Pesos em `modal.Volume`; `remote_gen()` para legendas | Sem ganho de cold start; reentrega geraria segunda chamada de GPU. |
| Docling remoto por documento inteiro | Página reusa hierarquia e retry; overhead tratado por `batching` após medição. |
| Margem maior (US$ 28 + 1,00) como padrão | Com teto por tentativa e P, o excesso calculado é ~US$ 0,05; contas compartilhadas se resolvem dividindo o limite. |
| Fator `k` / linhas de ajuste no ledger | Adiado; `max(ledger, reportado)` e o alerta de razão cobrem a v1. |
| Primeiro usuário admin / `BOOTSTRAP_ADMIN_EMAIL` | Corrida em instância pública; escalada sem verificação de e-mail. |

## 6. Impactos

- **Compatibilidade**: sem rota, nada muda. `GET /jobs/{id}` e `UserResponse` só ganham campos;
  o status do job não ganha valor. `make_admin.py` passa a exigir `--email`/`--id`. O
  `visibility_timeout` de 4 h vale para todas as filas.
- **Performance**: o submit com rota faz um `LLEN`, uma leitura de rota em cache e, se
  transbordar, um INSERT. Jobs remotos pagam sonda, upload (10–25 s, não cobrado) e, frios,
  cold start de ~18–30 s.
- **Segurança**: remoto só para admins por padrão; API sem capacidade de decifrar; mutações só
  com JWT e auditadas; mídia não confiável nunca demuxada na API nem no processo com a chave
  privada. A mídia sai para o provedor quando transborda (decisão do admin, avisada com `all`).
  S-04 (Redis sem auth) não piora: dinheiro e capacidade não vivem no Redis.
- **Operação**: dois serviços opcionais, env vars opcionais, beats com `expires`, logs
  `engine.reserve|refuse|claim|spawn|cancel|settle|requeue|handback|exhausted|orphaned`.
- **Custo**: zero por padrão; com a rota do dono, ≤ ~US$ 29,55 por conta por mês sob P (§4.7).

## 7. Plano de testes

- **Unitários (sem rede)**: `priority`/`fill_first` e `W_local`; `CostModel` (Decimal,
  arredondamento); reserve/claim/settle concorrentes, virada de período, teto por usuário,
  invariantes de orçamento; parser de cobrança estrito e monotônico; `classify_error` com os
  textos do cortes; selagem (rotação, troca de linha falha); filtro de log e `redact()`;
  allowlist do payload; `describeRoute()`; contrato do adapter contra um **`modal` falso**
  (spawn, get, cancel, from_id, Dict, erros, chamada que nunca retorna).
- **Paridade**: suíte intacta nas fatias 0–2; teste de import; `whisper_core` contra o
  transcritor anterior com clipe ≥ 3 min com silêncios, em CPU int8 **e** GPU float16.
- **Integração (MySQL + Redis de teste)**: submit → transbordo → sonda → despachante → executor
  falso; restart de `worker-audio` sem transbordo; as cinco causas de hand-back; cada estado do
  Apêndice E; sweeper (saída antes do settle, cancel no prazo, `orphaned`); 4×`AUTH` ⇒ local;
  `detect_stuck_jobs` ignora backlog e remotos vivos; sentinela em todas as superfícies;
  `Σcaps` > threads ⇒ 409.
- **`pytest -m modal_live`** (fora do CI): deploy por CLI, fingerprint, transcrição real, cancel
  no prazo, settle × relatório, T1–T5, `bench.py`.

## 8. Plano de implementação

Cada item cabe num PR, na ordem. Fora das mudanças deliberadas de 0a/0b, zero-config intocado.

- [ ] **0a — `visibility_timeout`.** `broker_transport_options` acima do maior `time_limit` e
      alerta de `unacked`. Resolve a antiga Q9.
- [ ] **0b — Admin.** `make_admin.py` com `--email`/`--id`, recusa ambígua, confirmação;
      `is_effective_admin` em `shared/`; `is_admin` em `UserResponse`.
- [ ] **1a — Refactor sem mudança de comportamento.** Extrair `finish_transcription` e
      formatadores. Suíte verde sem teste alterado.
- [ ] **1b — `whisper_core.py`** usado pelo local, revisão do modelo local fixada, teste de
      paridade de §7.
- [ ] **2 — Dados + selagem + redação + CLI.** As 5 tabelas (models + Alembic), semente `local`,
      `sealing.py`, `redact.py` (filtro stdlib instalado em todos os processos), CLI de
      importação em dry-run. Motores remotos **não ativáveis**. Depois: importar as contas do
      dono, sem rota.
- [ ] **3 — Spill no submit + backlog + despachante + hand-back com executor falso.**
      `dispatch.submit`, `probe_media`, `worker-dispatch`, watchdog, `job_dispatches`,
      reserve/claim/settle e sweeper contra um adapter falso, `remote_allowed_for`, teto por
      usuário, estados de job e ajuste de `get_stuck_jobs`. Ainda não ativável.
- [ ] **4a — Uma conta Modal de verdade.** App Whisper, imagem com hashes, CLI de deploy,
      `ModalAdapter` (spawn/resume/cancel/lookup/classify), `worker-remote`, rotas admin de
      mutação (JWT, auditoria, `current_password`), correção do `force_provider`. Gate:
      verificações T1–T5 em `modal_live`. **Primeiro PR que permite ativar um motor remoto**,
      exigindo os invariantes de orçamento e P.
- [ ] **Benchmark** (antes de fixar a GPU padrão): `bench.py` em T4, L4 e A10G; velocidade,
      cold start, custo por hora de áudio, A/B de WER; grava `default_speed`.
- [ ] **4b — Várias contas + `fill_first` + reconciliação.** `reconcile_spend` estrito e
      monotônico, `exhausted` por período, alertas, `idle_tail`, probes baratos.
- [ ] **5 — UI admin somente leitura** + CSP de `/admin`.
- [ ] **6 — Doc** `docs/engines/MODAL.md` e `ADAPTERS.md` (pode acompanhar 4a).
- [ ] **7 — Legendas ao vivo remotas** (`spawn` + partição de `modal.Queue` por `attempt_key`).
- [ ] **8 — Docling por página e visão síncrona** (pré-requisito: S-01). Depois: UI de edição.

## 9. Questões em aberto

**Decisões do dono:**

- [ ] **Q1.** As 4 contas são compartilhadas com o cortes? A precondição P exige resposta antes
      da fatia 4a: contas dedicadas (recomendado) ou limite dividido (ex.: 15 + 15) com o limite
      do workspace configurado no Modal.
- [ ] **Q2.** *Local first + spill* (exemplo) ou **crédito Modal primeiro**
      (`spill_wait_seconds=0`)? Se os US$ 30 são crédito que expira, usá-lo cedo libera a GPU
      local sem custo marginal. Só muda configuração.
- [ ] **Q3.** Fuso e dia de âncora do período: o ciclo de cobrança/crédito do Modal coincide com
      o mês civil, e em qual fuso? (Campos obrigatórios, sem padrão no código.)
- [ ] **Q4.** GPU padrão do app Whisper: provisório `L4`; decide o benchmark.

**Verificações técnicas (gates, não decisões):** T1 superfície do SDK fixado
(`Client.from_credentials`; `client=` em `Cls`/`FunctionCall`/`Dict`; retenção de resultados;
limite de entrada; cobrança em Python; put-if-absent em `Dict`). T2 limite de gasto de
workspace no plano e o erro que produz. T3 precedência `~/.modal.toml` × env × `client=`. T4
latência de `cancel()` e se para a cobrança. T5 formato dos tokens e preços atuais. T6 (fatia 8)
overhead do Docling por página. T7 uplink em rajada (40 × 50 MB). T1–T5 e T7 são gates da 4a.

---

## Apêndice A — DDL resumida

Dinheiro `DECIMAL(12,6)`; taxas `DECIMAL(14,10)`; ids `CHAR(36)`. MySQL externo de versão
desconhecida: nada depende de `SKIP LOCKED`. Ordem de lock: só a linha de `engines`.

| Tabela | Colunas | Chaves / índices |
|---|---|---|
| `engines` | `id`, `slug` (`^[a-z0-9][a-z0-9_-]*$`), `display_name`, `adapter_type`, `config JSON` (não secreto: `gpu`, `slots`, `default_speed`, `max_media_seconds`, `min_speed`, `scaledown_window`, `prices`, `prices_as_of`), `max_concurrency INT`, `status ENUM(active,paused,disabled)`, `health ENUM(unknown,healthy,degraded,unhealthy,exhausted)`, `health_reason TEXT` (redigido), `health_until DATETIME NULL`, `consecutive_failures INT`, **orçamento**: `limit_usd NULL`, `min_remaining_usd DEFAULT 0.50`, `soft_pct TINYINT DEFAULT 80`, `period_tz VARCHAR(64) NULL`, `period_anchor_day TINYINT NULL`, `provider_cap_confirmed BOOL DEFAULT 0`, `alerted_soft_period DATE NULL`, `alerted_hard_period DATE NULL`, **provedor**: `provider_reported_usd NULL`, `provider_reported_period DATE NULL`, `provider_reported_at NULL`, **credencial**: `credentials_sealed BLOB NULL`, `credentials_key_id VARCHAR(16) NULL`, `credentials_masked JSON`, `credentials_updated_at`, `credentials_updated_by`, **deploy**: `deployed_fingerprint VARCHAR(64) NULL`, `deployed_protocol INT NULL`, `deploy_verified_at NULL`, `is_system BOOL`, `version INT`, `created_by`, `created_at`, `updated_at` | `UNIQUE(slug)` |
| `feature_routes` | `feature` PK, `engines JSON` (`[{engine_id, position, max_concurrency?}]`, validado), `strategy ENUM(priority,fill_first)`, `local_fallback BOOL DEFAULT 1`, `spill_wait_seconds INT NOT NULL`, `handback_after_seconds INT DEFAULT 600`, `scale_out_after_seconds INT DEFAULT 300`, `on_no_engine ENUM(hold,fail) DEFAULT 'hold'`, `max_attempts INT DEFAULT 3`, `remote_allowed_for ENUM(admins,all) DEFAULT 'admins'`, `user_period_limit_usd NULL`, `remote_data_notice TEXT NULL`, `version INT`, `updated_by`, `updated_at` | — |
| `engine_usage` | `id BIGINT AI`, `kind ENUM(job,idle_tail,probe)`, `engine_id` FK RESTRICT, `feature`, `subject_type ENUM(job,page,vision_request) NULL`, `subject_id VARCHAR(64) NULL`, `attempt INT NULL` (= `placements`; NULL fora de `kind=job`), `job_id CHAR(36) NULL` (sem FK), `user_id CHAR(36) NULL`, `period_start DATE`, `status ENUM(reserved,spawning,running,settled,released,orphaned)`, `outcome ENUM(succeeded,failed,cancelled) NULL`, `counts_toward_attempts BOOL`, `estimated_usd`, `reserved_usd`, `actual_usd NULL`, `cost_basis ENUM(measured,reported,reserved)`, `reported_seconds NULL`, `measured_seconds NULL`, `rate_usd_per_s`, `price_snapshot JSON`, `units JSON`, `fingerprint VARCHAR(64)`, `attempt_key CHAR(36) NULL`, `provider_call_id VARCHAR(128) NULL`, `holder VARCHAR(128) NULL`, `heartbeat_at DATETIME(6)`, `spawned_at NULL`, `deadline_at NULL`, `output_persisted_at NULL`, `republish_count INT DEFAULT 0`, `error_code NULL`, `error_detail TEXT NULL` (redigido), `created_at`, `finished_at NULL` | `UNIQUE(subject_type, subject_id, attempt)`; `INDEX(engine_id, period_start, status)`, `INDEX(status, heartbeat_at)`, `INDEX(user_id, period_start)`, `INDEX(job_id)` |
| `job_dispatches` | `id BIGINT AI`, `feature`, `subject_type`, `subject_id VARCHAR(64)`, `job_id CHAR(36) NULL`, `user_id CHAR(36)`, `state ENUM(probing,waiting,assigned,running,local,done,failed)`, `priority TINYINT DEFAULT 5`, `placements INT DEFAULT 0`, `job_failures INT DEFAULT 0`, `skip_count INT DEFAULT 0`, `exclude_engines JSON` (`[{engine_id, until}]`), `payload JSON` (schema por feature, allowlist), `media_seconds DECIMAL(12,3) NULL`, `media_bytes BIGINT`, `usage_id NULL`, `engine_id NULL`, `enqueued_at`, `unplaceable_since NULL`, `assigned_at NULL`, `local_published_at NULL`, `error_code NULL`, `updated_at` | `UNIQUE(subject_type, subject_id)`, `INDEX(feature, state, priority, enqueued_at)` |
| `admin_audit` | `id BIGINT AI`, `actor_user_id NULL`, `auth_method ENUM(jwt,cli)`, `ip VARCHAR(45) NULL`, `action`, `target_type`, `target_id`, `before JSON`, `after JSON` (nunca valores secretos), `created_at` | `INDEX(target_type, target_id, created_at)` |

`job_dispatches.state=running` é escrito no claim (junto com `spawning` do uso) e volta a
`waiting` em requeue; `done`/`failed` no settle terminal; `local` no hand-back.

## Apêndice B — Endpoints admin

Leituras: `require_admin`. Mutações: `require_admin_session` (JWT só, auditado). Sem `PATCH`.

| Método e rota | Corpo → resposta |
|---|---|
| `GET /admin/engine-adapters` | → `AdapterDescriptor[]` |
| `GET /admin/engines` · `GET /admin/engines/{id}` | → lista / detalhe (status derivado, vivos/cap, orçamento do período, credenciais mascaradas) |
| `GET /admin/engines/status` | → em voo por motor (do ledger), backlog por feature, heartbeat do despachante e do `worker-remote` |
| `GET /admin/engines/{id}/ledger?cursor` | → linhas do ledger |
| `GET /admin/routing` | → `FeatureRoute[]` (inclui a implícita "só local", backlog e espera mais antiga) |
| `GET /admin/usage?period&engine_id&feature` | → por motor, feature e dia; estimado × reportado; `unattributed` |
| `GET /admin/jobs/{id}/engine` | → slug, custo, segundos, cold start, trilha de tentativas (sem conteúdo) |
| `GET /admin/audit?limit=50` | → `admin_audit` |
| `POST /admin/engines` | `EngineCreate` → 201, criado **pausado** |
| `PUT /admin/engines/{id}` | `EngineUpdate` com `version` (409 em conflito; 422 por invariante) |
| `PUT` / `DELETE /admin/engines/{id}/credentials` | `{fields, current_password}`; 409 sem chave pública |
| `POST /admin/engines/{id}/test` | enfileira em `ingestify-remote-ctl`, espera ≤ 30 s → `HealthReport` |
| `POST /admin/engines/{id}/activate` · `/pause` · `/reset-health` | `activate` exige teste ok + invariantes; `pause` drena |
| `PUT /admin/engines/{id}/budget` | limite, `min_remaining`, `soft_pct`, `period_tz`, `period_anchor_day`, `provider_cap_confirmed` |
| `POST /admin/engines/{id}/reconcile` | puxa o gasto do provedor agora |
| `PUT /admin/routing/{feature}` | `FeatureRoute`; valida motores, `Σcaps`, heartbeats (409); ampliar `remote_allowed_for` exige `current_password` |
| `DELETE /admin/routing/{feature}` | volta ao zero-config e devolve o backlog à fila local |

A CLI (`python -m workers.engines.cli`) espelha as mutações (`engines`, `budget`, `routes`,
`import`, `rotate-keys`), audita com `auth_method=cli`, e `modal_deploy` faz o deploy.

## Apêndice C — Contrato TypeScript (`frontend/types/compute.ts`, espelhado em Pydantic)

```ts
export type Feature = "transcription" | "document_conversion" | "vision";
export type EngineStatus = "healthy" | "idle" | "busy" | "exhausted" | "paused" | "error" | "degraded" | "unknown";
export type EngineKind = "local" | "cloud";

export interface UserResponse { id: string; email: string; username: string;
  is_active: boolean; created_at: string; is_admin: boolean; }   // dica de UI; a API decide

export interface CredentialState { is_set: boolean; hint?: string | null;
  updated_at?: string | null; updated_by?: string | null; }
export interface BudgetState { period_start: string; period_end: string; timezone: string;
  limit_usd: number; min_remaining_usd: number; soft_pct: number;
  spent_estimated_usd: number; spent_reported_usd: number | null; reported_at: string | null;
  reserved_usd: number; unattributed_usd: number | null; used_pct: number;
  state: "ok" | "warning" | "exhausted"; resets_at: string; prices_as_of: string | null; }
export interface EngineSummary { id: string; slug: string; display_name: string;
  adapter_type: string; kind: EngineKind; features: Feature[];
  status: EngineStatus; status_detail?: string | null; paused: boolean;
  budget: BudgetState | null; in_flight: { live: number; cap: number };
  month: { jobs: number; gpu_seconds: number; failures: number }; last_used_at: string | null; }
export interface EngineDetail extends EngineSummary { config: Record<string, unknown>;
  credentials: Record<string, CredentialState>; version: number;
  deployed_fingerprint: string | null; expected_fingerprint: string | null; }

export type RoutingStrategy = "priority" | "fill_first";
export interface FeatureRoute { feature: Feature; implicit: boolean; strategy: RoutingStrategy;
  engines: { engine_id: string; position: number; max_concurrency?: number | null }[];
  local_fallback: boolean; spill_wait_seconds: number; handback_after_seconds: number;
  scale_out_after_seconds: number; on_no_engine: "hold" | "fail"; max_attempts: number;
  remote_allowed_for: "admins" | "all"; user_period_limit_usd: number | null;
  backlog?: { waiting: number; oldest_wait_seconds: number | null };
  version: number; updated_at: string | null; updated_by: string | null; }

// JobStatusResponse += (dono)
//   engine?: { kind: EngineKind } | null;
//   queue_reason?: "in_queue" | "starting" | null;
// AdminJobEngine (GET /admin/jobs/{id}/engine):
//   { slug: string; cost_usd: number | null; gpu_seconds: number | null;
//     cold_start_seconds: number | null; queue_reason: string | null;
//     trail: { engine: string; outcome: string; error_code?: string | null }[] }
```

## Apêndice D — Chaves Redis

Todas com TTL. Nenhum valor de dinheiro ou de capacidade vive no Redis; perdê-lo só desliga o
transbordo até o despachante voltar a escrever o heartbeat.

| Chave | Tipo / TTL | Escreve | Lê |
|---|---|---|---|
| `engines:dispatch:lock` | string NX com token, 15 s | despachante | despachante |
| `engines:dispatcher:heartbeat` | string, 30 s | despachante | `submit`, watchdog, admin |
| `engines:remote:heartbeat` | string, 30 s | `worker-remote` | validação de rota, admin |
| `engines:kick` | string NX, 500 ms | `submit`/executor | — (deduplicação) |
| `engines:local:{feature}:p50` | string, 10 min | `submit` | `submit` |
| `engine:{id}:speed` | hash, 1 h | beat | `CostModel.estimate` |
| `job:{id}:transcript:partial` | existente | fase 2: `worker-remote` | `GET /jobs/{id}/transcript/partial` |

## Apêndice E — Reentrega e sweeper (`engine_usage`)

**Reentrega do `execute_remote(usage_id)`**:

| Estado da linha | O executor |
|---|---|
| `reserved` | faz o claim |
| `spawning`/`running` com `heartbeat_at` < 60 s | outro detentor vivo: ack e sai |
| `spawning` com heartbeat velho | toma a linha (`UPDATE … WHERE heartbeat_at=<lido>`); procura `attempt_key` no provedor: achou → `running` e retoma; não achou → `spawn` de novo sob a mesma reserva |
| `running` com heartbeat velho | toma a linha; `resume(provider_call_id)`; se já passou de `deadline_at`, `cancel()` antes |
| `running` cuja chamada terminou mas o resultado expirou no provedor | se `jobs.status=COMPLETED` (finish já rodou) → settle com o medido; senão → `orphaned` |
| `settled`, `released`, `orphaned` | ack e sai (o sujeito pertence ao backlog ou está pronto) |

**Sweeper** (`sweep_usage`, 60 s, em `ingestify-dispatch`). Ele **nunca liquida** uma chamada
terminada e **nunca estende** prazos:

| Condição (colunas do Apêndice A) | Ação |
|---|---|
| `reserved` e `heartbeat_at` > 5 min | republica `execute_remote`; com `republish_count ≥ 3` → `released` e o sujeito volta a `waiting` |
| `spawning`/`running` e `heartbeat_at` > 120 s | republica `execute_remote` (o executor retoma, persiste e só então liquida); `republish_count++` |
| `running` e `now > deadline_at + 60 s` | `cancel(provider_call_id)` e republica |
| `republish_count ≥ 5` sem progresso | `orphaned`: cobra a reserva inteira, sujeito volta ao backlog, alerta |

A cobrança de um `orphaned` pela reserva inteira (e não pela estimativa) é intencional: a
reserva é o teto que a tentativa podia gastar.

## Apêndice F — Assinaturas do adapter e árvore de arquivos

```python
class EngineAdapter(ABC):
    type_name: ClassVar[str]                                   # "local" | "modal"
    capabilities: ClassVar[dict[Feature, Capability]]          # sync_ok, cold_start_s, max_input_bytes
    cost_model: ClassVar[type[CostModel]]                      # estimate(unit) / settle(usage) -> Decimal

    def __init__(self, engine: EngineSnapshot, credentials: Mapping[str, str] | None): ...
    def ensure_ready(self, feature) -> ReadyState: ...         # só VERIFICA; idempotente; nunca gasta GPU
    def execute(self, feature, unit: WorkUnit, ctx: ExecutionContext) -> ExecResult: ...
    #   ctx: subject, usage_id, attempt_key, deadline_at, on_progress, heartbeat(), record_call_id(str)
    #   ExecResult(output: <FeatureOutput tipado, schema_version>, usage: Usage)
    #   Usage(billable_seconds, measured_seconds, units: dict, provider_cost_usd: Decimal|None, raw: dict)
    #   levanta EngineError(code, usage_parcial)
    def resume(self, provider_call_id: str, ctx) -> ExecResult | None: ...
    def lookup_attempt(self, attempt_key: str) -> str | None: ...   # call_id, se o spawn ocorreu
    def cancel(self, provider_call_id: str) -> None: ...
    def cooldown(self) -> None: ...                            # o custo NUNCA depende dele
    def provider_spend(self, period) -> Decimal | None: ...
    def health(self) -> HealthReport: ...                      # sem container quando possível
    def test_connection(self) -> HealthReport: ...
    def classify_error(self, exc) -> ErrorCode: ...
```

```
whisper_core.py                    # laço de decodificação compartilhado com o local
modal_apps/protocol.py             # PROTOCOL_VERSION, request/response pydantic com limites
modal_apps/image.py                # receita da imagem
modal_apps/whisper_app.py          # alvo de deploy; nunca importado pela API nem pelos workers
modal_apps/fingerprint.py
modal_apps/requirements-whisper-modal.lock   # pins exatos COM hashes
adapters/modal.py                  # ModalAdapter (import lazy de modal)
cli.py / modal_deploy.py           # CLI de motores e de deploy
```

---

## Histórico de revisão

**Rodada 1 (2026-10-04).** Duas revisões: adversarial (A: 3 blockers, 12 major, 15 minor) e
segurança/OSS (S: 2 blockers, 12 major, 11 minor). O líder da sessão decidiu simplificar a v1;
as decisões estão aplicadas acima. Legenda: **aceito**, **aceito c/ mudança**, **rejeitado**.

### Revisão adversarial

| # | Achado | Resolução |
|---|---|---|
| A1 (blocker) | Sweeper liquida chamada terminada sem salvar a saída | **Aceito.** Dinheiro e saída separados; sweeper só republica; `settled/succeeded` exige `output_persisted_at` (§4.6). `stop_grace_period` e `visibility_timeout` (fatia 0a). |
| A2 (blocker) | Nada limita o gasto de uma tentativa | **Aceito.** `deadline_at = spawned_at + reserved/rate`, cancel no prazo, sweeper nunca estende, `timeout` do app derivado do maior job admissível (§4.6, §4.11). |
| A3 (blocker) | Dois controladores na mesma conta estouram | **Aceito.** Precondição P (dedicada ou dividida + limite do Modal), §2 reescrito com excesso limitado (§4.7, Q1). |
| A4 | Failovers contam em `max_attempts` | **Aceito.** Só erros do job contam; 4×`AUTH` ⇒ local (§4.8). |
| A5 | Despachante é SPOF; backlog órfão | **Aceito.** Local nunca passa pelo despachante; watchdog no `worker` padrão; excluir rota drena o backlog (§4.4). |
| A6 | Capacidade local por heartbeat ⇒ W infinito em restart | **Aceito.** Slots configurados; heartbeat não entra (§4.3). O ajuste por réplica em CPU fica fora (a fórmula usa p50 medido, que reflete CPU com atraso). |
| A7 | Leases sem heartbeat durável; raia única bloqueia controle | **Aceito c/ mudança.** Sem leases: contagem do ledger sob o lock do motor, `heartbeat_at` na reserva; `ingestify-remote-ctl`; `Σcaps ≤ threads − 2` (§4.4, §4.6). |
| A8 | Spawn não gravado roda duas vezes; `released` sem regra | **Aceito.** Estado `spawning` + `attempt_key` com `modal.Dict` (gate T1); tabela de reentrega cobre todos os estados (§4.6). Sem put-if-absent, o fallback é re-spawn com risco documentado. |
| A9 | Período desalinhado do ciclo; reconciliação sobrescreve | **Aceito.** Âncora e fuso obrigatórios; intervalo explícito ou pausa perto da virada; `GREATEST`; regra de zero mais tolerante (§4.7). |
| A10 | Estado do job indefinido × `detect_stuck_jobs` | **Aceito.** Tabela de estados; backlog em `PENDING`; `get_stuck_jobs` exclui remotos vivos (§4.9). |
| A11 | Modelo não serve para páginas e visão | **Aceito.** Chave de sujeito, sem FK; nome da task corrigido (`convert_page_task`); responsabilidades de `finish_page`; §4.15 marcado como esboço. |
| A12 | Health checks custam 10× | **Aceito.** Saúde sem container, `scaledown_window=2`, só motores usados em 24 h, `kind=probe`; conta em §4.16. |
| A13 | Maquinário desproporcional | **Aceito** (decisão do líder): spill no submit, 5 tabelas, 2 estratégias, requeue em vez de failover na task, deploy por CLI, UI só leitura, sem `prewarm`. Cauda ociosa: mantida como linha `idle_tail` derivada do banco (somar na liquidação superestimaria em sequência). |
| A14 | Auto-deploy frágil e entre contas | **Aceito.** Só CLI; teste com token sentinela no env; critério de grep reescrito como "nunca muta `os.environ`". |
| A15 | Cabeça impossível trava a feature | **Aceito.** Rejeição/hand-back na sonda; lookahead de 20 com limite de pulos (§4.3, §4.4). |
| A16 | Qualificadores da economia | **Aceito.** Velocidade exigida por GPU e tabela por velocidade (§4.16). |
| A17 | Cauda ociosa subconta e depende do Redis | **Aceito c/ mudança.** Derivada do banco; subcontagem com 2 containers aceita e limitada, coberta pelo `max()`. |
| A18 | "Mesma transação do Job" põe job sem arquivo | **Aceito.** INSERT depois do arquivo, transação própria, fallback ao caminho de hoje. |
| A19 | Ordem de locks | **Aceito.** Um lock (linha do motor); settle e reserva separados; retry em 1213/1205. |
| A20 | Arredondamento | **Aceito.** `Decimal(str())`, reserva para cima, taxa `DECIMAL(14,10)`. |
| A21 | Higiene de beat/chute | **Aceito.** `expires`, `task_routes`, lock com token, chute deduplicado. |
| A22 | Superfície do SDK | **Aceito.** Gates T1–T4 da fatia 4a. |
| A23 | Pool do banco < threads | **Aceito.** Pool = concorrência + 4; sem sessão durante `get`. |
| A24 | Imagem do `worker-remote` | **Aceito.** `requirements-remote.txt` e volume temp (§4.14). |
| A25 | `whisper_core` muda o local depois da janela de paridade | **Aceito.** Fatia 1b própria, clipe ≥ 3 min, CPU e GPU; semântica de falha preservada; `callback_url` de áudio não é "corrigido". |
| A26 | Leitura da rota deve falhar com segurança | **Aceito.** Erro ⇒ caminho de hoje; cache de 5 s. |
| A27 | Bordas de esgotamento | **Aceito.** Subir limite limpa `exhausted`; fallback com n < 20; sobra encalhada aceita. |
| A28 | Memória de uploads | **Aceito.** `REMOTE_MAX_CONCURRENT_UPLOADS`, streaming se houver. |
| A29 | Contradições e critérios faltantes | **Aceito.** §2/§3 reescritos; claim refaz a fórmula; `job_dispatches.running` definido; critérios novos; dependências das fatias reordenadas. |
| A30 | O ledger protege contra o quê depende do tipo de conta | **Aceito.** Precondição P + Q1–Q3 antes da fatia 4a. |

### Revisão de segurança / OSS

| # | Achado | Resolução |
|---|---|---|
| S1 (blocker) | Duração adversarial ⇒ DoS de cabeça e estimativa manipulada | **Aceito c/ mudança.** Sonda limitada em bytes no worker; impossível ⇒ hand-back/falha; teto por tentativa cobre subdeclaração; `max_audio_duration_seconds` aplicado como limite de admissão remota, não no local (paridade). Re-reserva por duração decodificada: rejeitada, o teto por tentativa já limita o gasto. |
| S2 (blocker) | Qualquer usuário gasta o dinheiro do operador | **Aceito.** `remote_allowed_for=admins` padrão; teto por usuário na reserva; estimativa só para elegíveis. `ALLOW_REGISTRATION` e justiça entre usuários: **rejeitados para esta spec** (o padrão `admins` remove o vetor; registro aberto é S-02, tratado à parte). |
| S3 | Mídia sai sem aviso | **Aceito c/ mudança.** Aviso obrigatório com `all`; `allow_remote=false` por job; retenção do provedor na doc. Coluna `allow_remote` por usuário: adiada. |
| S4 | Chave simétrica na API + demux na API | **Aceito.** SealedBox; sonda em `worker-dispatch`, que não tem chave privada. |
| S5 | Admin aceita API key, sem step-up | **Aceito.** JWT só, `admin_audit`, `current_password` para credenciais e ampliação de política; CSP no `/admin`. |
| S6 | `make_admin.py` promove o usuário errado | **Aceito.** Fatia 0b. Proibir `@` em username: fica para issue própria (muda registro). |
| S7 | Uso autodeclarado e saída confiados | **Aceito.** `max(reportado, medido)`; validação por `protocol.py`; fingerprint é consistência, não autenticação. |
| S8 | Redação mira structlog, que não é usado | **Aceito.** Filtro stdlib + `redact()` + erros saneados em qualquer `ENVIRONMENT`. |
| S9 | Env de subprocesso | **Aceito.** Allowlist, `HOME` temporário, nada em argv. |
| S10 | `auto_deploy` é risco de cadeia de suprimentos | **Aceito.** Só CLI; hashes; base e builder fixados; política de atualização do `modal` na doc. |
| S11 | Orçamento "ilimitado/soft/desabilitado" representável | **Aceito.** Invariante na escrita e no claim; `hard`/`enabled` removidos; `prices_as_of`. |
| S12 | CLI de importação | **Aceito.** Stdin/getpass/`~/.modal.toml`, `dotenv_values`, dry-run, `--activate` via `worker-remote`, token dedicado. |
| S13 | Contrato do adapter não é API estável | **Aceito c/ mudança.** `CostModel` do adapter, `Usage` genérico, I/O tipado com `schema_version`, kit de contrato, marcado provisório. Entry points para adapters fora da árvore: adiado até o segundo provedor. |
| S14 | v1 grande demais | **Aceito.** Fatias reordenadas (§8). A sugestão de "um motor sem roteamento, por override" foi trocada por executor falso na fatia 3 + `spill_wait_seconds=0` na 4a. Reconciliação manual: rejeitada, o parsing estrito com `degraded` já falha fechado. |
| S15 | Lacunas de auditoria | **Aceito.** `admin_audit` append-only + log. |
| S16 | Gestão de chave | **Aceito.** `_FILE`, backups separados, runbook, `engine_id` no selado, chave só em `api`/`worker-remote`. |
| S17 | Hints mascarados | **Aceito.** Regra mecânica e teste. |
| S18 | Estado do orçamento exposto a usuários | **Aceito.** Só `in_queue`/`starting` para não-admins. |
| S19 | "Dono/admin" em `GET /jobs/{id}` | **Aceito.** Só dono; rota admin de metadados; `is_effective_admin` em `shared/`. |
| S20 | CORS sem `PATCH` | **Aceito c/ mudança.** Sem `PATCH`; `PUT` com `version`. |
| S21 | Payload cru + S-01 | **Aceito.** Allowlist por feature; S-01 pré-requisito da fatia 8. |
| S22 | Detalhes do dono em padrões e docs | **Aceito c/ mudança.** `spill_wait_seconds` sem default; config do dono rotulada como exemplo; fuso/âncora sem padrão. Os números de carga ficam como motivação (decisão do dono, repositório dele). |
| S23 | Três caminhos de migração | **Aceito.** Nenhuma coluna nova em tabela existente; models + uma revisão Alembic + teste de CI. Resolve a antiga Q10 nesta spec. |
| S24 | Licença e proveniência | **Aceito c/ mudança.** Revisão do modelo local fixada (1b); licenças na doc. Arquivo `LICENSE` ausente: fora do escopo, vira issue. |
| S25 | Itens menores | **Aceito.** Webhook só por env; nota de CSRF; S-04 não piora; restart para rebaixar admin documentado. |

**Questões fechadas nesta rodada:** Q5 (virou gates T1–T5), Q6 (T7), Q7 (T6), Q8 (resolvida
por `remote_allowed_for=admins` + aviso), Q9 (fatia 0a), Q10 (sem colunas novas; Alembic +
models), Q11 (fora de escopo), Q12 (`auto_deploy` removido).
