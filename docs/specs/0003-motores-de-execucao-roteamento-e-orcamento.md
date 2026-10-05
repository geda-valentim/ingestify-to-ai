# 0003 — Motores de execução: roteamento por feature com orçamento (local + Modal)

| | |
|---|---|
| **Status** | Em revisão |
| **Autor** | Geda Valentim (com agentes de backend, MLOps, frontend, decisor) |
| **Criada em** | 2026-10-04 |
| **Atualizada em** | 2026-10-04 (rodada 4: revisão adversarial de fila e concorrência; ver "Histórico de revisão") |
| **Relacionadas** | 0002 |
| **Substituída por** | — |

---

## 1. Problema

Hoje cada feature pesada tem **um único lugar** onde pode rodar, fixado por env var e fila Celery:

| Feature | Entrada | Fila / serviço | Quem decide o "motor" |
|---|---|---|---|
| Transcrição | `POST /transcribe` → `process_conversion` (`options.is_audio`) | `ingestify-audio` / `worker-audio` (N réplicas, uma RTX 5060 Ti 16 GB) | `AUDIO_TRANSCRIBER_PROVIDER` |
| Transcrição (entrada lateral) | `/upload`, `/convert` com extensão de áudio → `process_conversion` (`tasks.py`, lista `audio_extensions`) | `ingestify` / `worker` | idem |
| Conversão de documentos | `/upload`, `/convert` → SPLIT → `convert_page_task` → MERGE | `ingestify` / `worker` | Docling local |
| Visão | `/images/*` (síncrono) | `ingestify-vision` / `worker-vision` | `VISION_PROVIDER` |

Na instalação do dono (exemplo), numa semana: **7.318 transcrições, 4.038 h de áudio**, mediana
15,7× tempo real por job. Duas réplicas na mesma placa (~30× agregado) ficam ~80 % ocupadas **em
média**, e os jobs chegam em rajadas: a fila cresce por horas, sem válvula de escape. Passar de 2
para 4 réplicas na mesma placa **não aumentou a vazão**, só deixou cada job mais lento.

O dono tem **4 contas Modal com limite de US$ 30/mês** e pediu: motores por feature (`local`,
`modal_1`…`modal_4`) com **limite de gasto**; custo checado **no início e no fim de cada item**;
adapters com ciclo de vida (*warmup → exec → cooldown*); máquina **genérica** (Docling, visão);
**credenciais no banco**; o usuário **decide a ordem** dos motores e **escolhe a GPU** e a
concorrência. O Ingestify é **open source**: nada de conta no código, e zero contas de nuvem
continua sendo o caminho padrão e completo.

Lições do cortes a não repetir: tokens em `os.environ`; teto desligado por campo de cobrança
ausente lido como 0; failover só na próxima chamada; orçamento checado só antes do lote.

## 2. Objetivo

Cada feature pesada passa a ter uma **rota**: uma lista **ordenada pelo usuário** de passos (motor
ou grupo de motores equivalentes), cada um com condições opcionais. Com rota, todo item da feature
(inclusive áudio que chega por `/upload` e `/convert`) entra num **backlog durável** (FIFO,
MySQL). Um despachante examina a cabeça, percorre a rota na ordem e **coloca** cada item no
primeiro motor cuja regra permite agora: há vaga na capacidade configurada, as condições do passo
valem e, se for remoto, o orçamento comporta. "Local primeiro, nuvem sob pressão" e "crédito da
nuvem primeiro" são só duas ordens da mesma rota. Uma instalação sem rota se comporta
**exatamente** como hoje, sem despachante.

O usuário escolhe, por motor e feature, **qual GPU**, **quantos workers** e **quantas execuções
simultâneas por worker**; a capacidade é o produto, e uma configuração que não cabe na VRAM é
recusada (§4.6).

**Garantia de gasto, dita com honestidade.** O Ingestify **para de admitir** trabalho num motor
quando `max(gasto_ledger, gasto_reportado) + reservado + estimativa > limit − min_remaining`. O
limite vale para a **conta inteira** (o motor): não há como dividir uma conta entre sistemas. Como
`gasto_reportado` vem do provedor, o gasto de outros sistemas na mesma conta entra na conta, com
o atraso do relatório (5–15 min). A conta final pode passar desse ponto por um excesso
**limitado** do lado do Ingestify (cancelamento em voo, cauda ociosa, probes: ≈ US$ 0,05 por conta
com 2 containers em L4, §4.8), mais o que outro sistema gastar durante o atraso do relatório. Por
isso a documentação **recomenda** configurar também o limite de gasto no próprio provedor; não é
pré-requisito.

### Fora de escopo (v1)

- Legendas ao vivo para jobs remotos (fatia 7). Na v1 um job remoto mostra progresso estimado.
- Docling e visão remotos (fatia 8). §4.14 é um **esboço**; o modelo de dados já os comporta.
- Como na rodada 1: `round_robin`/`cheapest`, override por job, `prewarm`, `auto_deploy`,
  orçamento por feature numa conta, fator `k`, justiça entre usuários, provedores além de `local`
  e `modal`, `min_containers > 0`, `max_audio_duration_seconds` no local.
- O Ingestify **escalar réplicas Docker** sozinho (exigiria o socket do Docker); ele só mostra
  "configurado X, vivos Y" e a variável a mudar.
- Mais de uma execução por processo local em features de GPU (§4.6.3). Mais de uma execução por
  container remoto fica atrás dos gates T4/T8 (fatia 4d).
- UI de edição. A UI v1 é **somente leitura**; configuração via API admin e CLI (§4.6.8).

## 3. Critérios de aceitação

**Paridade zero-config (critério duro)**
- [ ] Sem rota para `transcription`, `POST /transcribe` enfileira `process_conversion` em
      `settings.transcription_queue` com os kwargs de hoje, e `/upload`/`/convert` com áudio
      transcrevem no `worker` como hoje; nenhuma linha em `job_dispatches` ou `engine_usage`;
      `modal` ausente de `sys.modules` em todo processo.
- [ ] A suíte de `backend/tests/` passa sem alteração depois das fatias 0 a 2.
- [ ] `process_conversion` sem `usage_id` se comporta exatamente como hoje, inclusive `self.retry`.

**Entrada e colocação pela fila**
- [ ] Com rota, áudio enviado a `/upload` ou `/convert` (arquivo, URL, Drive, Dropbox) segue a
      mesma rota, guarda de VRAM e orçamento de `/transcribe`; nenhuma transcrição roda no `worker`.
- [ ] Rota `[local] → [modal_1..4 fill_first, min_wait_seconds=600]`, capacidade local 2: com 10
      itens, 2 vão ao local e os outros esperam; um item que espera 600 s vai ao Modal se couber.
      Inverter a ordem faz o mesmo lote usar o Modal primeiro; só configuração muda.
- [ ] Jobs em voo por `(motor, feature)` nunca passam de `workers × executions_per_worker` nas
      colocações do despachante e do watchdog (ticks e claims concorrentes). Linhas do fallback do
      submit podem passar, mas **contam**: nada novo vai ao local até drenar.
- [ ] Reiniciar todas as réplicas de `worker-audio` em menos de `local_unhealthy_after_seconds`
      (padrão 180) não muda a capacidade; sem worker vivo por esse tempo, o local fica `unhealthy`.
- [ ] `workers=3` com 2 réplicas vivas, ou fila Celery esvaziada à mão: a colocação não reivindicada
      em `local_claim_timeout_seconds` (120) volta ao backlog e pode ir ao Modal; a mensagem
      atrasada dá ack sem rodar.
- [ ] Despachante parado com `local_direct`: o submit publica no local com linha de uso; o
      watchdog coloca no máximo `capacidade − em_voo(local)` por rodada e alerta; com `hold`, só
      alerta. Redis fora: como hoje (o submit falha).
- [ ] Um líder cuja época foi superada não grava colocação (tick lento + watchdog); toda transição
      de `job_dispatches` e `engine_usage` é condicional; nenhum item roda duas vezes por colocação.
- [ ] 50 itens de não-admins (só local, cheio) seguidos de 1 de admin: o do admin vai ao Modal no
      mesmo tick. Um item grande sem orçamento não impede os pequenos; uma linha bloqueante
      bloqueia só os motores em que caberia.
- [ ] `fill_first`: recusa por orçamento ou tamanho ⇒ próxima conta no mesmo tick; corrente cheio ⇒
      espera `scale_out_after_seconds` por `full_since` persistido; benchmark ou probe não muda a
      conta corrente.
- [ ] Rota com passo remoto e `remote_allowed_for=admins` sem passo local ⇒ 422.

**Capacidade e concorrência**
- [ ] Soma de VRAM numa GPU física (todas as features e motores que a usam) acima do total ⇒ 422
      com a conta detalhada; idem para Modal por `gpu_type`.
- [ ] Mudar `gpu_type`, `workers`, `executions_per_worker` ou `cpu` de um motor Modal o deixa
      `needs_redeploy` (não colocável) até o deploy por CLI gravar o fingerprint esperado.
- [ ] `executions_per_worker > 1` remoto ⇒ 422 enquanto T4/T8 com `max_inputs ≥ 2` não passarem.
      (Fatia 4d) Com `E=2`, no caminho de sucesso, partes fatiadas + `idle_tail` = tempo vivo do
      container × taxa (Apêndice L).
- [ ] Benchmark remoto: estimativa pessimista (× E), confirmação, reserva do total, prazo por
      combinação; gasto real ≤ `--max-usd` + latência de cancelamento × taxa. O local recusa, com
      a conta, se não couber na VRAM ao lado do residente.

**Dinheiro**
- [ ] Reserva, claim e settle de uma conta acontecem sob o lock da linha em `engines`;
      concorrência e gasto vêm de `engine_usage` (reservas simultâneas).
- [ ] Três checagens: fórmula na colocação, fórmula de novo no claim, settle com custo medido.
- [ ] `spend_cap` e teto por usuário contam reservas: com `spend_cap={usd: 1.50, window: day}` e 8
      vagas, `liquidado + reservado` no dia nunca passa de 1,50.
- [ ] Um `modal` falso que nunca retorna é cancelado em `deadline_at`, e
      `actual ≤ reserved + latência_de_cancelamento × rate`.
- [ ] Chamada que terminou com `worker-remote` morto tem a saída **persistida** antes do settle; o
      sweeper nunca liquida chamada terminada.
- [ ] Relatório sem o campo esperado ⇒ `degraded` (nunca 0); `provider_reported` não diminui.
- [ ] Ativar motor remoto exige `limit_usd`; fuso e âncora têm padrão `UTC`/dia 1.

**Falhas e recuperação**
- [ ] 4 contas respondendo `AUTH`: o item termina no local (erros de motor não contam tentativa).
- [ ] `INPUT_REJECTED` falha na hora; item que nenhum passo aceitaria falha na sonda.
- [ ] Item local cujo processo morre (filho morto, `task_time_limit`, container derrubado): em até
      `local_stale_seconds + 60 s` volta ao backlog, ou é liquidado `succeeded` se o job já está
      `COMPLETED`; a mensagem reentregue dá ack sem rodar; nenhum worker grava reserva.
- [ ] Com `usage_id`, `process_conversion` nunca chama `self.retry`: a exceção liquida `failed` e o
      backlog decide (backoff, `max_attempts`).

**Segurança** (inalterados desde a rodada 1)
- [ ] Remoto só para admins por padrão; com `all`, teto por usuário checado na reserva.
- [ ] A API só tem a chave **pública**; sem a privada em `worker-remote`, nada remoto ativa.
- [ ] Sentinela ausente de logs, mensagens Celery, result backend, Redis, colunas `engine_*`/
      `admin_audit` e corpos de erro; nenhum código muta `os.environ`.
- [ ] Mutações admin exigem JWT e gravam `admin_audit`; credenciais exigem `current_password`;
      `GET /jobs/{id}` continua só do dono.

## 4. Solução proposta

### 4.1 Modelo de domínio

| Conceito | O que é | Exemplo |
|---|---|---|
| **Feature** | Enum fechado no código, com pegada de VRAM por execução. | `transcription`, `document_conversion`, `vision` |
| **Tipo de adapter** | Classe que roda features num backend; declara capacidades, `gpu_options`, schemas de config e credencial, e seu **modelo de custo**. | `local`, `modal` |
| **Motor** | Linha em `engines`: adapter + config + credencial selada + orçamento + saúde. | `local` (semeado), `modal_1` |
| **Binding** | Config de um motor para uma feature: `gpu_type` (ou GPU física), `workers`, `executions_per_worker`. **Capacidade** = produto. | `modal_1`/transcrição: L4, 2 × 1 |
| **GPU física** | Uma placa local (UUID do `nvidia-smi`), compartilhada por bindings de várias features. | `gpu0`, RTX 5060 Ti 16 GB |
| **Rota** | Por feature: passos ordenados, cada um com motores, estratégia de grupo e condições; política de quem pode ir para remoto. | §4.5 |
| **Sujeito** | O que é roteado: `(subject_type, subject_id)`. | `job`/uuid, `page`/`page_job_id` |
| **Uso (ledger)** | Uma linha por **tentativa** de um sujeito num motor (local ou remoto), mais `idle_tail`, `probe` e `benchmark`. Fonte única de em-voo e de gasto. | job X, tentativa 2, `modal_2` |
| **Período** | Mês do orçamento no fuso/âncora do motor (padrão UTC, dia 1). É a coluna `period_start` do uso. | `modal_2` / 2026-10-01 |
| **Época** | Contador em `dispatcher_lease` (MySQL) incrementado a cada troca de líder; toda colocação confere a sua (*fencing*). | época 42 |

### 4.2 Visão geral do fluxo (transcrição)

```
POST /transcribe, ou /upload|/convert com áudio ─▶ API: salva o arquivo; grava o Job
  dispatch.submit(feature, sujeito, usuário):
    sem rota (ou erro ao ler a rota) → apply_async como hoje                            ← FIM
    despachante parado > dispatcher_down_seconds e fallback=local_direct
      → INSERT job_dispatches(bypassed) + engine_usage(local, reserved, placed_by=fallback);
        apply_async(..., usage_id)                                                        ← FIM
    INSERT job_dispatches(state=probing); probe_media → ingestify-dispatch
worker-dispatch:
  probe_media: duração D; nenhum passo aceitaria → failed(no_engine); senão waiting; chute
  dispatch_tick (líder, época 42), candidatos da cabeça por classe de elegibilidade:
    passo 1 [local]: em_voo(local, transcription)=2 < capacidade 2? ✗
    passo 2 [modal_1..4 fill_first, min_wait_seconds=600]: esperou 640 s ✓ → corrente modal_2
      BEGIN; lease.epoch = 42 (LOCK IN SHARE MODE) ✓; SELECT engines WHERE id=modal_2 FOR UPDATE
        em_voo 1 < 2×1 ✓; deploy ok ✓; spend_cap e teto do usuário (com reservas) ✓
        max(ledger 21.40, reportado 21.55) + reservado 0.07 + est. 0.069 ≤ 30.00 − 0.50 ✓
        INSERT engine_usage(status=reserved)                                      ← CHECAGEM 1
        UPDATE job_dispatches SET state=assigned WHERE id=? AND state=waiting AND version=v
        (0 linhas ⇒ ROLLBACK, inclusive da reserva)
      COMMIT → publica execute_remote(usage_id) em ingestify-remote
    (passo local: o mesmo, com reserva de US$ 0, publicando process_conversion(..., usage_id))
worker-remote: claim reserved→spawning (condicional; perdeu ⇒ ack sem rodar)      ← CHECAGEM 2
  spawn; laço get(15 s)/heartbeat/deadline_at; valida; finish_transcription
  SETTLE: custo medido; output_persisted_at; settled                              ← CHECAGEM 3
worker-audio (item local): claim reserved→running (perdeu ⇒ ack sem rodar); heartbeat 15 s;
  roda como hoje; settle US$ 0
```

### 4.3 Entrada no backlog e sonda de mídia

`shared/engines/dispatch.submit` usa só MySQL e Redis e **nunca** importa `modal`.

- **Entradas**: `/transcribe`; `/upload` e `/convert` quando o arquivo tem extensão de áudio (a
  lista `audio_extensions` de `tasks.py` vai para `shared/`, sem mudar). Fontes baixadas no worker
  (URL, Drive, Dropbox) só revelam a extensão depois do download: `process_conversion` **sem**
  `usage_id`, ao cair no ramo de áudio com rota de transcrição, move o arquivo para o volume
  temporário compartilhado, chama `dispatch.submit` e retorna sem transcrever (o job volta a
  `PENDING`). Sem rota, o ramo de áudio roda como hoje. Opções de transcrição: os padrões de
  `/transcribe`; esses endpoints não aceitam `allow_remote`, então vale a política da rota.
- **Sem rota** para a feature (cache de 5 s; **qualquer erro** de leitura conta como "sem rota"):
  caminho de hoje.
- **Despachante parado** (`dispatcher_lease.dispatcher_seen_at` mais velho que
  `dispatcher_down_seconds`, padrão 120), `dispatcher_fallback=local_direct` (padrão) e a rota tem
  passo local: numa transação, `job_dispatches(state=bypassed)` e uma linha de uso local
  (`reserved`, US$ 0, `placed_by=fallback`); depois do commit, publica a task de hoje com
  `usage_id`. Não checa capacidade (como hoje), mas a linha **conta** no em-voo. Com `hold`, ou
  sem passo local, o item espera no backlog. Redis fora derruba o broker do Celery: falha como hoje.
- **Senão**: a linha `job_dispatches` é inserida **depois** de o arquivo estar no lugar, em
  transação própria (sem `Job` gravado, caminho de hoje), e `probe_media` é publicada.

Elegibilidade a remoto é por item, avaliada na colocação: o dono passa `remote_allowed_for`
(`admins`, padrão, ou `all`) e não mandou `allow_remote=false`. Sem esse direito, ou sem sonda
(`media_seconds` nulo, ex.: devolvido de um fallback; o sweeper republica a sonda), só passos
locais.

**Sonda** (`probe_media`, em `worker-dispatch`, nunca na API): lê através de um wrapper que recusa
bytes além de `PROBE_MAX_BYTES` (8 MB), com timeout de 10 s, e extrai a duração `D` (sem ela,
tamanho ÷ bitrate). Se nenhum passo da rota aceitaria o item (`D` acima do `max_media_seconds` de
todo motor remoto e sem passo local, ou estimativa maior que o limite **inteiro** de todo remoto),
ele falha com `no_engine` na hora. Para vídeo, o mesmo worker extrai o áudio (remux, sem
re-encode, com time limit). O processo com a chave privada nunca demuxa mídia não confiável.

`max_audio_duration_seconds` vale como **limite de admissão remota** (no local, nada muda). Uma
duração **subdeclarada** não é detectada pela sonda; a defesa é o teto por tentativa (§4.7).

### 4.4 Despachante e colocação

- **Backlog**: `job_dispatches`, todos os itens de features com rota. FIFO por `(priority,
  enqueued_at)`, respeitando `not_before`; `priority=0` para itens devolvidos.
- **Despachante**: `dispatch_tick` em `worker-dispatch` (`-c 2`), por chute deduplicado (sonda,
  settle, requeue) e beat de 5 s. Todo o seu estado está no MySQL: reiniciá-lo é barato.
- **Liderança com época** (Apêndice E): linha única `dispatcher_lease(epoch, holder, renewed_at,
  dispatcher_seen_at)`. Assumir é um `UPDATE` condicional que incrementa `epoch` quando o lease está
  livre ou expirado (15 s); o líder renova a cada tick. Toda transação de colocação lê o lease com
  `LOCK IN SHARE MODE` e aborta se a época não é a sua; assumir exige lock exclusivo, então um
  líder antigo (tick lento, pausa de GC) não grava nada depois de substituído.
- **Transições condicionais**: toda mudança de `job_dispatches.state` e de `engine_usage.status`
  é `UPDATE … WHERE id=? AND <estado esperado> [AND version=?]`; 0 linhas ⇒ rollback, inclusive
  da reserva. Só o líder (despachante ou watchdog) e o fallback do submit (que só **insere**
  sujeitos novos) criam reservas; workers e executores só fazem claim e settle.
- **Algoritmo** do tick. Candidatos: as 20 primeiras linhas `waiting` da feature **e** as 20
  primeiras com `remote_allowed` (duas consultas indexadas), unidas em ordem FIFO; assim itens só
  locais com o local cheio não escondem itens que poderiam ir à nuvem.

  ```
  para cada candidato, em ordem:
    para cada passo da rota, na ordem:
      condições do passo valem para este item? (§4.5)            senão → próximo passo
      para cada motor do passo, na ordem da estratégia do grupo:
        elegível? (active; saúde ∉ {unhealthy, exhausted, degraded}; binding sem needs_redeploy;
                   não excluído; D ≤ max_media_seconds; remoto ⇒ item com direito a remoto;
                   motor não reservado por uma candidata anterior bloqueante)
        sob o lock do motor: em_voo_job(motor, feature) < capacidade
                             ∧ (remoto ⇒ orçamento ∧ spend_cap ∧ teto do usuário, com reservas)
        ✓ → reserva, CAS waiting→assigned, publica depois do COMMIT; próximo candidato
    nada coube → unplaceable_since (se nulo); regra de pulos; on_no_engine decide
  ```

- **Capacidade local** = `workers × executions_per_worker` **configurados** menos linhas locais
  `kind=job` em `reserved|running` (inclui as do fallback). Heartbeats **nunca** entram nessa
  conta: só decidem saúde (§4.6.7). Um item colocado no local espera na fila Celery no máximo
  `local_claim_timeout_seconds` (120): não reivindicado, o sweeper faz `reserved→released` e o
  sujeito volta a `waiting` (cabeça, sem contar tentativa, sem excluir o local); a mensagem
  atrasada dá ack. Réplicas ausentes, em crash-loop ou uma fila esvaziada nunca prendem itens.
  "Configurado X, vivos Y" com Y < X por 5 min vira alerta.
- **Pulos sem fome e sem congelar**: uma candidata pulada porque um item posterior foi colocado
  num motor M incrementa `skip_count` **só se** ela caberia em M quando o em-voo de M liquidasse
  (`D ≤ max_media_seconds`, `estimativa ≤ limit − min_remaining − max(ledger, reportado)`,
  `spend_cap` idem). Com 10 pulos ela **reserva** M (`blocked_engine_id`): nenhum item posterior é
  colocado em M até ela sair; os outros motores seguem. Uma candidata que não caberia em M nem com
  M vazio nunca o bloqueia.
- **Sem lugar**: com `on_no_engine=hold` (padrão) o item espera; com `fail`, falha com
  `budget_exhausted`/`no_engine` após `fail_after_seconds` em `unplaceable_since`.
- **Raia remota**: `ingestify-remote` em `worker-remote` (`--pool=threads`,
  `REMOTE_WORKER_CONCURRENCY`, padrão 16) e `ingestify-remote-ctl`; `Σ capacidade remota >
  REMOTE_WORKER_CONCURRENCY − 2` ⇒ 409, checado ao gravar a rota **e** ao mudar um binding.
  Publicação sempre depois do commit; payload com schema **por feature com allowlist**.

**O despachante como ponto único de falha.** Com rota, o trabalho **local** também passa por ele.
Três defesas:

1. **Submit**: `dispatcher_seen_at` velho ⇒ `local_direct` com linha de uso (§4.3). Cobre beat e
   `worker-dispatch` mortos. Não cobre Redis fora: o broker do Celery é o Redis.
2. **Watchdog** `engines_watchdog`: laço de 15 s **no processo da API** (não no `worker`, cujas
   vagas os jobs de página podem ocupar). Com `dispatcher_seen_at` velho: alerta (log e webhook)
   e, com `local_direct`, assume o lease (nova época) por uma rodada e coloca no máximo
   `capacidade − em_voo(local)` linhas que podem usar um passo local (o código do tick, restrito a
   passos locais). O resto fica no backlog, ao alcance dos passos remotos quando o despachante
   voltar.
3. **Remover a rota** marca-a `draining`; o backlog volta ao caminho de hoje em lotes (Apêndice E).

### 4.5 Rota: passos, condições e estratégias

Uma rota é uma lista ordenada de **passos**; a ordem é a prioridade. Um passo tem um motor ou um
**grupo** de motores equivalentes (ex.: `modal_1..4`) com estratégia de grupo:

| Estratégia de grupo | Comportamento |
|---|---|
| `priority` | Ordem do grupo; o próximo é usado quando o anterior está sem vaga ou inelegível. |
| `fill_first` | *Sticky*: o "corrente" é o elegível com a linha `kind=job` mais recente no período (probes, benchmarks e caudas não contam), ou o primeiro. Cada item tenta o corrente primeiro. Recusa por **orçamento, tamanho ou `spend_cap`** ⇒ o item tenta o próximo na hora. Recusa por **capacidade cheia** ⇒ o próximo só abre quando o corrente está cheio há mais de `scale_out_after_seconds` (padrão 300), medido por `full_since` em `engine_feature_state`. Um motor inelegível (ex.: `needs_redeploy`) é pulado e volta a ser o corrente quando voltar. Amortiza cold start e cauda ociosa. |

**Condições** (opcionais por passo; todas as presentes precisam valer). O conjunto é pequeno de
propósito:

| Condição | Vale quando | Uso típico |
|---|---|---|
| `when.min_wait_seconds` / `when.min_backlog` | o item esperou ≥ N s **ou** o backlog `waiting` da feature tem ≥ N itens (as duas, quando presentes, combinam com **ou**) | nuvem só sob pressão |
| `spend_cap: {usd, window: day\|period}` | gasto **liquidado + reservado** deste motor nesta feature na janela + estimativa ≤ `usd` | espalhar o crédito pelo mês |

Sempre valem, sem configurar: vaga na capacidade, elegibilidade do motor, orçamento do motor e,
para remoto, o direito do item a remoto e o teto por usuário (que também conta reservas).

Exemplos (configuração do usuário, não padrões do repositório):

```
# local primeiro, nuvem sob pressão
transcription: 1. [local]
               2. [modal_1, modal_2, modal_3, modal_4] fill_first  when.min_wait_seconds=600
               remote_allowed_for=admins  max_attempts=3  on_no_engine=hold

# crédito da nuvem primeiro (ex.: crédito que expira), local como reserva
transcription: 1. [modal_1, modal_2, modal_3, modal_4] fill_first  spend_cap={usd: 1.50, window: day}
               2. [local]
```

No segundo exemplo, com `dispatcher_fallback=local_direct` (padrão), uma queda do despachante
manda itens novos ao local, contra a ordem: é a escolha de latência. Quem prefere a ordem usa
`hold`.

Validação: passo remoto com `remote_allowed_for=admins` exige um passo local ⇒ 422; motores
precisam suportar a feature e ter binding. Avisos: `capacidade × hold(D_p50)` acima do
`spend_cap`, do teto por usuário ou do que resta do orçamento (a admissão vai limitar a
concorrência, §4.6.6); primeiro passo remoto com `local_direct`.

### 4.6 Capacidade e concorrência

#### 4.6.1 Opções de GPU

O descritor do adapter expõe `gpu_options`:

- **Modal**: lista fixa no código com `gpu_type`, VRAM e preço por segundo (Apêndice G), com
  `prices_as_of` e marca "verificar", sobrescrevível; e `account_max_gpus` (limite do plano,
  padrão 10, "verificar").
- **Local**: as GPUs relatadas no heartbeat (NVML) unidas às **declaradas** no motor `local`
  (`config.gpus`); a validação usa o declarado, e divergência vira aviso.

#### 4.6.2 Binding por motor × feature

| Campo | Modal | Local |
|---|---|---|
| `gpu_type` / `gpu_ref` | GPU do decorator `@app.cls(gpu=…)` | GPU física declarada |
| `workers` | `max_containers` | réplicas do serviço (ex.: `AUDIO_WORKER_REPLICAS`); **declarado**, porque o Ingestify não escala Docker; a API mostra `scale_hint` com a variável ou o `--scale` a mudar |
| `executions_per_worker` | `@modal.concurrent(max_inputs=N)`; **1 na v1** (§4.6.3) | `--concurrency` do Celery por réplica (§4.6.3) |
| `cpu` | `cpu` do decorator, padrão `1 + E`; entra em `rate` e no fingerprint | — |
| **capacidade** | `max_containers × N` | `réplicas × concurrency` |

O despachante nunca coloca mais jobs em voo num `(motor, feature)` que a capacidade. Para o
Modal, `Σ workers` dos bindings de uma conta ≤ `account_max_gpus` (422).

#### 4.6.3 Execuções simultâneas por worker

- **Modal**: na v1, `executions_per_worker` remoto é **limitado a 1** (`max_E=1` no descritor;
  422) até os gates **T4** e **T8** passarem com `max_inputs ≥ 2`: cancelar um input para a
  cobrança e não derruba os vizinhos; os pesos são compartilhados e `transcribe` é seguro em
  threads (inclusive o extrator de features, que muta estado). Depois dos gates (fatia 4d):
  `WhisperModel(..., num_workers=E)`, VRAM contada como pegada inteira por execução até medir,
  `memory = 4 + E × (0,5 + 0,45 × max_h)` GiB (`max_h` = `max_media_seconds` em horas), e o laço
  de `whisper_core` checa entre segmentos uma flag de cancelamento por input, parando em ≤ 1
  segmento. Settle fatiado, cauda e correlação de falhas: Apêndice L.
- **Local**: `--concurrency=N` com prefork cria N processos, cada um com seu modelo e seu contexto
  CUDA: em VRAM e vazão é o mesmo que N réplicas, só que com falhas acopladas. Por isso, **na v1,
  bindings locais de GPU aceitam só `executions_per_worker=1`** (422 com "aumente as réplicas"),
  como o compose de hoje (`worker-audio` e `worker-vision` em `--concurrency=1`). Bindings locais
  em CPU (Docling sem GPU) aceitam N.

Mais execuções na mesma GPU **não** garantem mais vazão (a medição do dono, de 2 para 4 réplicas,
mostra isso). Quem decide é o benchmark.

#### 4.6.4 Guarda de VRAM

Cada feature declara `vram_per_execution_gb` **por processo, já com o contexto CUDA** (Apêndice G;
Whisper turbo float16 = 3,0 GB, medido 2,2–3 GB neste projeto com o contexto); cada GPU tem
`vram_reserve_gb` (padrão 1,0). Com benchmark, a pegada vira `base_gb + E × per_exec_gb` ajustada
na grade de `E`, × 1,1; um override por binding é aceito, auditado e mostrado com aviso.

```
local, por GPU física g:  Σ_{bindings em g} workers × E × pegada_f + reserva_g ≤ vram_g
modal, por binding:       pegada_f(E) + reserva ≤ vram(gpu_type)
```

A soma local cobre **todas** as features que usam a placa, inclusive as que não têm rota (o
`worker` do Docling e o `worker-vision` são declarados como bindings do `local` para isso).
Exemplo, RTX 5060 Ti 16 GB: Whisper 3 réplicas `3 × 3,0 = 9,0` + visão `1,8` + Docling `1,5` +
reserva `1,0` = **13,3 ✓**; com 4 réplicas, **16,3 ✗ (422)**, e a resposta lista cada parcela.
Sem rota de transcrição, áudio vindo de `/upload` ainda roda no `worker` (comportamento de hoje)
e não está nessa conta; com rota, não roda.

Com mais de uma GPU no host, o compose (`count: all`) põe toda réplica na GPU 0: o `scale_hint`
inclui `CUDA_VISIBLE_DEVICES=<uuid>`, e um heartbeat com UUID diferente do `gpu_ref` gera alerta.

#### 4.6.5 Mudanças que precisam de ação fora da API

- **Modal**: `gpu`, `cpu`, `max_containers`, `max_inputs`, `timeout`, `memory` e
  `scaledown_window` vivem no decorator e entram no fingerprint do deploy. Mudar qualquer um põe o
  binding em `needs_redeploy`: ele **não recebe** itens novos até `modal_deploy --engine <slug>`
  rodar, o fingerprint conferir **e** o em-voo da versão antiga zerar (ou `Σ workers novos +
  containers antigos ≤ account_max_gpus`). As linhas em voo guardam `gpu_type`, `E` e
  `fingerprint` da reserva e terminam na versão antiga; o resto da rota segue. (Se o SDK aplicar
  parte disso sem redeploy é o gate T9; a v1 não depende disso.)
- **Local**: mudar `workers` grava o desejado; a API e a UI mostram **"configurado X, vivos Y"**
  e o `scale_hint` (ex.: `AUDIO_WORKER_REPLICAS=3 docker compose up -d`). A capacidade usa X.

#### 4.6.6 Velocidade e custo sob concorrência

**Velocidade.** Os quantis aprendidos (`s_p20`, `cold_s_p80`) são chaveados por `(motor, feature,
gpu_type, executions_per_worker)`, sobre as últimas 200 linhas liquidadas da chave. Chave nova:
resultado do benchmark, senão `default_speed ÷ E` (supõe que concorrência não ganha nada).

**Reserva.** Enquanto a chave tem menos de **50** linhas `kind=job` liquidadas com sucesso, vale o
pior caso: `hold = (D / s_p20 + 15 + P_cold · cold_s_p80) × rate × (1 + margin)`. A partir de 50,
`hold = D × q95(actual_usd ÷ D da chave) × (1 + margin)`, que já inclui cold start e, com `E > 1`,
o compartilhamento real. Com `E = 1`, `deadline_at = spawned_at + reserved_usd ÷ rate` e a reserva
é o teto da tentativa. Com `E > 1`, `deadline_at` usa o tempo de parede pessimista e o teto de
dinheiro da tentativa é `deadline × rate`; a diferença entra no excesso limitado (§4.8).

**Troca explícita.** O pior caso deixa a admissão conservadora: perto do fim do período, ou com
`spend_cap` apertado, menos itens rodam ao mesmo tempo do que a capacidade permitiria; o settle
devolve a diferença. A validação da rota avisa quando isso vai acontecer (§4.5).

**Settle.** Com `E = 1`: `actual = max(segundos reportados, segundos medidos) × rate`. Com `E > 1`
(fatia 4d): fatiado por item segundo o número de itens simultâneos no container, mais linhas
`idle_tail` por container (Apêndice L).

**Benchmark** (CLI, Apêndice H): mede velocidade, US$/hora de áudio e VRAM por `(gpu, E)` e
recomenda. No remoto, estimativa pessimista, confirmação, reserva, prazo por combinação e app
efêmero; no local, container avulso que passa pela guarda de VRAM.

#### 4.6.7 Saúde local e o que a API mostra

Cada worker local de GPU publica a cada 10 s um heartbeat no Redis (device, UUID, VRAM usada).
Sem nenhum worker vivo por `local_unhealthy_after_seconds` (padrão 180, acima de um restart com
carga de modelo), o binding fica `unhealthy` e não recebe
itens; os já colocados e não reivindicados voltam ao backlog pelo claim timeout (§4.4). Réplica
que caiu para CPU (`mark_gpu_unavailable`) gera aviso; a saúde e a capacidade do binding não
mudam (senão uma réplica tiraria o local da rota).

A API admin expõe binding, `em_voo/capacidade`, "configurado vs vivos", `deploy_state` e, por GPU
física, VRAM declarada, orçada e usada.

#### 4.6.8 Por que a UI v1 continua somente leitura

Capacidade se muda por `PUT /admin/engines/{id}/features/{feature}` ou `engines set-capacity`;
a mudança só fecha com deploy (Modal) ou compose (local), então a UI mostra o estado e o comando.
Ver Q5.

#### 4.6.9 Riscos de controle

Tabela de riscos (GPU compartilhada, OOM, vizinho barulhento, redeploy, réplicas declaradas ≠
reais, limite de GPUs da conta, gasto alheio, líder antigo) e tratamentos no Apêndice K.

### 4.7 Dinheiro: uma tentativa do início ao fim

O MySQL é a fonte da verdade. **Um lock por motor**: toda transação de dinheiro e de capacidade
começa com `SELECT … FROM engines WHERE id=? FOR UPDATE`; transações de colocação leem antes o
lease em modo compartilhado (ordem: lease → motor). Settle e nova reserva são transações
separadas; toda transação repete em erro 1213/1205. Valores usam `Decimal(str(x))`, reservas
arredondam para cima, `DECIMAL(12,6)` no banco.

**Derivações do ledger**:

```
em_voo_job(e,f) = COUNT(*)  WHERE engine_id=e AND feature=f AND kind=job AND status IN (reserved, spawning, running)
ledger(e,p)     = SUM(actual_usd)   WHERE engine_id=e AND period_start=p AND status=settled
reservado(e,p)  = SUM(reserved_usd) WHERE engine_id=e AND period_start=p AND status IN (reserved, spawning, running)
admite ⇔ em_voo_job < workers × executions_per_worker
         ∧ max(ledger, provider_reported_usd do período) + reservado + estimativa ≤ limit_usd − min_remaining_usd
         ∧ spend_cap do passo: liquidado + reservado na janela + estimativa ≤ usd   (se houver)
         ∧ (remote_allowed_for=all ⇒ liquidado + reservado do usuário no período + estimativa ≤ user_period_limit_usd)
```

Para o `local`, só a primeira linha vale (custo zero). Probes e benchmarks contam no dinheiro,
não nas vagas de produção. Linhas vivas com heartbeat velho **continuam contando** até o sweeper
resolvê-las. Perder o Redis não muda nada de dinheiro nem de capacidade.

**Estados de `engine_usage`** (dinheiro e saída são passos separados; não existe estado terminal
que deixe o sujeito sem dono):

| `status` | Dinheiro | Saída | Quem avança |
|---|---|---|---|
| `reserved` | reservado | — | executor ou worker local (claim condicional); sweeper (claim timeout) |
| `spawning` | reservado; `attempt_key` gravado; `spawn` pode ter acontecido | — | executor remoto |
| `running` | reservado; `provider_call_id` e `deadline_at` gravados (remoto) | — | executor / worker local |
| `settled` | liquidado (`actual_usd`) | `output_persisted_at` (`succeeded`), ou `outcome ∈ {failed, cancelled, lost}` | terminal |
| `released` | reserva devolvida, nada cobrado | — | terminal |

`outcome=lost`: o executor sumiu e não há saída. Remoto cobra a reserva inteira (conservador);
local cobra 0. **Na mesma transação** o sujeito volta a `waiting`, salvo se o job já está
`COMPLETED`, caso em que o settle é `succeeded`. Regra dura: **`settled` com `outcome=succeeded`
só existe com `output_persisted_at`** (ou job `COMPLETED`).

**1. Reserva (líder, na colocação).** `rate = P_gpu + cpu·P_cpu + mem_GiB·P_mem` (tabela com
`prices_as_of`, overridável); `hold` como em §4.6.6. Exemplo: aula de 33 min em L4, `E=1`, fria,
hold ≈ US$ 0,07. A reserva grava `heartbeat_at=now()`, `gpu_type`, `executions_per_worker`,
`placed_by` e `dispatch_epoch`.

**2. Claim (no início).** Todo executor, `execute_remote` e `process_conversion` com `usage_id`,
só roda depois de vencer `UPDATE … SET status=<spawning|running>, holder=<host:pid>,
heartbeat_at=now() WHERE id=? AND status='reserved'`. Perdeu (qualquer outro estado) ⇒ ack e sai
**sem rodar**; workers nunca criam nem reabrem reservas. Remoto: o claim leva a `spawning` e, sob
o lock do motor, refaz a fórmula com a própria reserva e o `provider_reported` mais recente; motor
pausado/esgotado, `needs_redeploy` ou fórmula violada → `released` e o sujeito volta a `waiting`.
Local: o claim leva a `running`; se `jobs.status=COMPLETED` (tentativa anterior dada como perdida
que terminou), liquida `succeeded` e sai. Nos dois, `job_dispatches` faz `assigned→running` (CAS).

**3. Execução com teto.** `spawn(req)` leva `attempt_key` (deduplicado num `modal.Dict`, gate T1);
grava `provider_call_id`, `running` e `deadline_at` (§4.6.6). O laço faz `get(timeout=15 s)`,
renova `heartbeat_at` em transação curta e, passado `deadline_at`, chama `cancel()`. Com `E=1`,
**a reserva é o teto da tentativa** (excesso ≈ US$ 0,008 em L4); o `timeout` da função Modal é a
segunda barreira. No local, uma thread renova `heartbeat_at` a cada 15 s.

**4. Saída e settle (no fim).** Saída validada contra `protocol.py`; `finish_transcription`
(idempotente; no caminho roteado só conclui a partir de `PROCESSING`) grava Redis, MinIO, ES e
MySQL; depois, numa transação condicional (`WHERE status IN (spawning, running) AND
holder=<eu>`), `actual_usd`, `output_persisted_at`, `settled`. Se o sweeper já deu a linha como
perdida, o settle não muda nada e a saída persistida vale; a nova tentativa vê `COMPLETED` no claim
e liquida sem rodar. Divergência `|medido/reportado − 1| > 0,3` (`E=1`) gera alerta. Sobra do
período menor que o custo mediano de um item ⇒ `exhausted` até o próximo período (subir o limite
limpa). No local, `actual_usd=0` e os segundos medidos alimentam a ETA.

**Reentrega e sweeper** (Apêndice E): itens se recuperam **sempre pelo backlog**, nunca pela
reentrega do broker. O sweeper nunca liquida chamada remota terminada nem estende prazos. Local
`running` sem heartbeat há `local_stale_seconds` (padrão 90) vira `lost` (ou `succeeded`, se o job
concluiu) e o sujeito volta; local `reserved` não reivindicada no claim timeout vira `released` e
o sujeito volta. A mensagem reentregue (filho morto, ou container derrubado após o
`visibility_timeout`) encontra a linha fora de `reserved` e dá ack; o limite suave de tempo
liquida `failed`/`TIMEOUT` antes do `task_time_limit`.

### 4.8 Orçamento, período e reconciliação

**Invariante**, checado em toda escrita e no claim: motor remoto `active` ⇒ `limit_usd IS NOT
NULL ∧ min_remaining_usd ≥ 0`. Não existe orçamento "soft" nem "desabilitado" para motor remoto.

**Período**: começa no dia `period_anchor_day` (1–28, padrão 1) no fuso `period_tz` (IANA,
padrão `UTC`). A reserva grava `period_start` e é liquidada contra **o seu** período; mudar
fuso/âncora vale a partir do período seguinte. Alertas `soft_pct` (padrão 80) e de esgotamento
disparam uma vez por período: log e, opcionalmente, `ENGINE_ALERT_WEBHOOK_URL` (só env, sem
segredos nem dados de usuário).

**Reconciliação** (`reconcile_spend`, 10 min, em `ingestify-remote-ctl`): relatório de cobrança via
CLI em subprocesso com env de allowlist, para `[period_start, period_end)` em UTC quando o CLI
aceitar intervalo (senão, não reconcilia a menos de 1 dia de uma virada). Parsing estrito; campo
ausente → `degraded` (**fail closed**). `provider_reported_usd = GREATEST(anterior, novo)`. Zero
com ledger > `max(0,50, 5 × resolução)` por mais de 3 h → `degraded`. `unattributed = reportado −
ledger` (inclui gasto de outros sistemas, que já entra pelo `max()`).

**Excesso limitado** (lado do Ingestify), por conta: `(limit − min_remaining) + capacidade ×
excesso_de_cancelamento + workers × cauda + probes`, e, com `E > 1`, `+ capacidade × max(0,
deadline × rate − hold)`. Em L4 com 2 containers e `E=1`: 29,50 + 2×0,008 + 2×0,016 + ~0 ≈
**US$ 29,55**, mais o que outro sistema gastar durante o atraso do relatório. Benchmarks reservam
antes e ficam dentro do limite. A doc recomenda (não exige) o limite de gasto no provedor (se ele
disparar: `QUOTA_EXHAUSTED`) e um token próprio do Ingestify por conta.

### 4.9 Falhas, re-enfileiramento e estado do job

Não existe failover dentro da task. Em falha, o executor liquida o que foi cobrado, marca o motor
e **devolve o item à cabeça do backlog** (`priority=0`) com o motor em `exclude_engines`, e chuta o
despachante, que percorre a rota de novo (≤ 1–5 s até o próximo motor, inclusive o local). Erros
de motor (`AUTH`, `QUOTA_EXHAUSTED`, `CAPACITY`, `NOT_DEPLOYED`…) **não** contam para
`max_attempts`; `TIMEOUT` e `INTERNAL` (inclui OOM remoto) contam; `INPUT_REJECTED` falha na hora
(tabela no Apêndice J). Com `job_failures ≥ max_attempts`, o item falha com `engine_error`; com
todo remoto excluído, só passos locais continuam elegíveis.

**Local com `usage_id`**: `process_conversion` **não** chama `self.retry`. A exceção liquida a
linha `failed` (`INTERNAL`, conta) e o ramo de exceção não grava `FAILED` no job; o backlog
devolve o sujeito com `not_before = now + 60 · 2^(n−1)` s (o backoff de hoje), sem excluir o
local, até `max_attempts` (padrão 3), e só o settle terminal grava `FAILED`. Uma tentativa local
`lost` também conta: um item que derruba o worker não gira para sempre. Sem `usage_id`, o
`self.retry` de hoje.

Itens no backlog ficam `PENDING` com `started_at NULL`; o estado do job e o ajuste de
`get_stuck_jobs` estão no Apêndice J.

### 4.10 Contrato do adapter (provisório)

Em `backend/workers/engines/base.py`; tipos puros em `backend/shared/engines/types.py`;
assinaturas no Apêndice F. O descritor declara capacidades por feature (inclui `max_E`),
`gpu_options`, schema do binding e `CostModel`. A instância recebe snapshot do motor e credenciais
(só no objeto) e expõe `ensure_ready` (só verifica), `execute` (com `deadline_at`, heartbeat e
`record_call_id`), `resume`, `lookup_attempt`, `cancel`, `cooldown`, `provider_spend`, `health`,
`test_connection`, `classify_error`, `expected_fingerprint(binding)` e `benchmark(...)`.

I/O pydantic com `schema_version`; `Usage` inclui `container_id`, intervalo de execução e
`shared_seconds`. O `container_id` é conhecido também **em falha**: ao começar um input, o
container grava `attempt_key → container_id` no `modal.Dict` da conta (protocolo v2).

**`LocalAdapter`** embrulha o código de hoje: `execute` é a task existente, publicada com `usage_id`.

### 4.11 Adapter Modal e o app Whisper

Código no repositório, deployável em qualquer conta; imagem, dependências e árvore de arquivos no
Apêndice F. **App** `ingestify-whisper`: `@app.cls(gpu=<gpu_type>, cpu=<1+E>, memory=<§4.6.3>,
timeout=ceil(max_media_seconds ÷ min_speed(E)) + 300, scaledown_window=60,
max_containers=<workers>, min_containers=0, retries=0)` e `@modal.concurrent(max_inputs=<E>)`
(`E=1` na v1). O container mantém a linha do tempo dos seus inputs (`shared_seconds`) e checa a
flag de cancelamento entre segmentos.

**Deploy só por CLI** (`python -m workers.engines.modal_deploy --engine <slug>`, em
`worker-remote`, subprocesso com env de allowlist). O fingerprint cobre imagem, código, protocolo
**e o binding**; `ensure_ready` só **verifica**: fingerprint diferente ⇒ `needs_redeploy`;
protocolo diferente ⇒ `unhealthy`. É checagem de consistência, não autenticação. Inalterados da
rodada 1: saúde sem container quando possível; `client=` explícito; bytes na chamada com
`REMOTE_MAX_CONCURRENT_UPLOADS`; **nunca** `min_containers ≥ 1`.

### 4.12 Credenciais, segredos e administração

Sem mudança de decisão desde a rodada 1; detalhes no Apêndice M. Em resumo: credenciais
**seladas** (`SealedBox`; a API só sela, só `worker-remote` abre), somente escrita, redação em todo
log e erro, subprocessos com env montado do zero. Remoto só para admins por padrão
(`remote_allowed_for`; com `all`, teto por usuário e aviso de dados); mutações admin exigem JWT,
auditoria e, para credenciais, `current_password`; `GET /jobs/{id}` continua só do dono.

### 4.13 Mudanças por camada

Lista completa por camada no Apêndice I. Em resumo: **7 tabelas novas** e nenhuma coluna nova em
tabela existente; dois serviços opcionais (`worker-dispatch`, `worker-remote`) no profile
`engines`; o watchdog é um laço na API; `process_conversion` ganha `usage_id` opcional e o desvio
de áudio para o backlog quando há rota; UI admin somente leitura; fatia 0a corrige o
`visibility_timeout` (hoje, uma transcrição local de mais de 1 h é reentregue enquanto roda).

### 4.14 Generalidade: Docling e visão (esboço, fatia 8)

Uma feature nova precisa de: um valor no enum com input/output tipados e pegada de VRAM; uma
função `finish_*`; capacidades nos adapters; um `CostModel` por unidade. Ledger, backlog,
capacidade, orçamento e UI não mudam, porque a chave é `(subject_type, subject_id)`.

- **`document_conversion`**: a unidade roteada é a **página** (`subject_type=page`).
  `split_pdf_task` e o retry por página passam por `dispatch.submit`; `finish_page` assume o que
  hoje está em `_run_page_conversion`. Estimativa = páginas × `sec_per_page_p90` × preço.
  **Pré-requisito**: corrigir S-01 (JWT do usuário em `task_kwargs["auth_token"]`).
- **`vision`** (síncrono): sem backlog; reserva inline sob o mesmo lock; remoto só quente; nada
  cabe e local na rota → `ingestify-vision` como hoje; senão 503 com `Retry-After`.

### 4.15 Economia

Com as 4 contas (US$ 120) cabem ~760–2.450 h de áudio por mês conforme GPU e velocidade, contra
~17.500 h/mês no ritmo da semana medida: **o Modal é válvula de rajada, não substituto da GPU
local**. Custos por GPU e tabela no Apêndice G.

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| **Transbordo decidido no submit** (rodada 1) | **Decisão do owner**: a fila obedece à ordem configurada, com controles por item. A decisão no submit envelhece na rajada e precisava de cinco regras de hand-back. |
| Workers remotos consumindo `ingestify-audio` | Sem controle de colocação; orçamento checado depois de tomar a mensagem. |
| Task roteadora segurando a mensagem sem ack | O `visibility_timeout` reentrega e duplica. |
| Capacidade local por heartbeat (ou pelo máximo de vivos em 10 min) | Restart ⇒ capacidade 0 ⇒ tudo para a nuvem; contraria a decisão do owner de capacidade configurada. O claim timeout já devolve o que réplicas ausentes não pegam. |
| Recuperar item local pela reentrega do broker | Mensagem já confirmada se perde; container derrubado espera 4 h; o worker teria de gravar reservas. A recuperação é pelo backlog. |
| Lock de líder só no Redis | Sem *fencing*: um tick lento grava depois de perder a liderança. Lease com época no MySQL. |
| Watchdog no `worker` padrão | Suas vagas podem estar todas em jobs de página; beats com `expires` caem justo sob carga. |
| Recusar áudio em `/upload` e `/convert` com 415 | Quebra clientes de hoje; rotear mantém compatibilidade. |
| O Ingestify escalar réplicas Docker | Exigiria o socket do Docker (root no host). Mostra o desejado e o comando. |
| `executions_per_worker > 1` por processo local na v1 | Prefork = N modelos e N contextos CUDA (igual a réplicas); threads com modelo compartilhado não verificadas. |
| Rateio igual entre itens do container | Distorce custo e aprendizado; o fatiamento por `k(t)` é exato. |
| Contas compartilhadas com limite dividido (rodada 1) | **Decisão do owner**: o limite é da conta inteira; `max(ledger, reportado)` enxerga o gasto alheio. |
| Leases no Redis + tabela de contadores de período | Duas verdades. Contar o ledger sob o lock do motor basta nesta escala. |
| Failover dentro da task | Segundo escritor de reservas; requeue na cabeça tem a mesma latência prática. |
| Mantidas da rodada 1 | Chamada remota dentro de `worker-audio`; `round_robin`/`cheapest`/`prewarm`; `auto_deploy`; Fernet com chave na API; sonda na API; admins lendo qualquer job; pesos em `modal.Volume`; Docling por documento; fator `k`. |

## 6. Impactos

- **Compatibilidade**: sem rota, nada muda. Com rota, todo item da feature passa pelo backlog,
  inclusive áudio de `/upload` e `/convert`; o local é a task de hoje, com `usage_id` e sem
  `self.retry`. APIs só ganham campos; `make_admin.py` exige `--email`/`--id`;
  `visibility_timeout` de 4 h em todas as filas.
- **Performance e disponibilidade**: com rota, cada item paga um INSERT, uma sonda e um tick
  (1–5 s) antes do local (despachante no caminho, mitigado por fallback e watchdog). Remotos pagam
  upload (10–25 s) e, frios, cold start de ~18–30 s.
- **Segurança**: sem mudança desde a rodada 1; S-04 (Redis sem auth) não piora, porque dinheiro,
  capacidade e liderança não vivem no Redis.
- **Operação**: dois serviços opcionais, env vars opcionais, logs `engine.*` por transição.
- **Custo**: zero por padrão; com remotos, ≤ limite + ~US$ 0,05 por conta do lado do Ingestify
  (§4.8); benchmarks reservam dentro do limite.

## 7. Plano de testes

- **Unitários (sem rede)**: passos, condições e estratégias (`fill_first` com recusa por
  orçamento/tamanho, `full_since`, corrente só por `kind=job`); regra de pulos; candidatos por
  classe; guarda de VRAM (GPU compartilhada, `base + E × per_exec`, `max_E=1` remoto); fingerprint
  com binding e `cpu`; `hold` pior caso × q95 (limiar 50); `CostModel` (Decimal); reserve/claim/
  settle concorrentes, virada de período, tetos com reservas; parser de cobrança;
  `classify_error`; selagem; `redact()`; allowlist do payload; contrato do adapter contra um
  **`modal` falso**.
- **Paridade**: suíte intacta nas fatias 0–2; teste de import; `process_conversion` sem `usage_id`
  (com `self.retry`); áudio em `/upload`/`/convert` sem rota; `whisper_core` contra o transcritor
  anterior (clipe ≥ 3 min, CPU int8 e GPU float16).
- **Integração (MySQL + Redis de teste)**: cada critério de §3 de colocação, recuperação e
  dinheiro com executor falso, inclusive: áudio por `/upload`/`/convert` (arquivo e URL); claim
  timeout; fallback e watchdog limitados; época superada; rota `draining`; os três cenários de
  crash local; exceção local sem `self.retry`; cada estado do Apêndice E; `detect_stuck_jobs`
  ignora backlog e linhas vivas; sentinela em todas as superfícies.
- **`pytest -m modal_live`** (fora do CI): deploy, fingerprint, transcrição com `E=1`, cancel no
  prazo, `container_id` em falha, T1–T5, T8, T9, benchmark com `--max-usd 0.30`; na 4d, `E=2`.

## 8. Plano de implementação

Cada item cabe num PR, na ordem. Fora das mudanças deliberadas de 0a/0b, zero-config intocado.

- [x] **0a — `visibility_timeout`** e alerta de `unacked` (feita em 2026-10-04: 14.400 s em todos
      os serviços, checagem `check_broker_unacked` no beat e `GET/POST /admin/broker/unacked`).
- [x] **0b — Admin** (`make_admin.py`, `is_effective_admin`, `is_admin`) (feita em 2026-10-04:
      `make_admin.py --email|--id` com confirmação e recusa de username-sósia; regra única em
      `shared/admin.py`; `is_admin` em `/auth/me` e `/auth/register`).
- [x] **1a — Extrair `finish_transcription`** (feita em 2026-10-04: `workers/engines/pipeline.py`;
      formatadores como funções de módulo; saída idêntica byte a byte ao código anterior).
- [x] **1b — `whisper_core.py`** no local, com paridade (feita em 2026-10-04: laço e carga do modelo
      em `workers/engines/whisper_core.py`, importável sem `shared`; flag de cancelamento entre
      segmentos; clipe de 4 min idêntico byte a byte ao transcritor anterior em GPU float16 e CPU
      int8, inclusive as chamadas de progresso. GPU float16 e CPU int8 diferem entre si (85 × 114
      segmentos), então a paridade local × Modal compara mesma precisão).
- [x] **2 — Dados + selagem + redação + CLI de importação** (dry-run). Remotos **não ativáveis**.
      (Feita em 2026-10-04: 7 tabelas em `shared/models.py` + revisão Alembic `b3e1c0d9a7f2`, testadas
      em SQLite e MySQL 8; selagem X25519 + HKDF + ChaCha20-Poly1305 com `cryptography`, já
      dependência, no lugar de PyNaCl, presa ao `engine_id` e ao `key_id`; redação pela record
      factory do `logging`; `scripts/engines.py keygen | import-env | import-modal-toml`.)
- [ ] **3a — Capacidade**: pegadas, bindings, guarda de VRAM, GPUs declaradas, heartbeats NVML,
      "configurado vs vivos", `GET /admin/gpus`, `set-capacity`. Sem rota ainda.
- [ ] **3b — Backlog e colocação com executor falso**: `dispatch.submit` (inclui `/upload`,
      `/convert` e o desvio em `process_conversion`), sonda, lease com época, transições
      condicionais, candidatos por classe, regra de pulos, passos e condições, local com
      `usage_id` (claim, heartbeat, sem `self.retry`), claim timeout, fallback com linha de uso,
      watchdog na API, rota `draining`, sweeper, estados de job. Rota só com `local` já é útil.
- [ ] **4a — Uma conta Modal, `E=1`**: app Whisper, imagem com hashes, deploy por CLI com
      fingerprint, `ModalAdapter`, `container_id` no protocolo, `worker-remote`, rotas admin de
      mutação, correção do `force_provider`. Gates T1–T5, T8. **Primeiro PR que ativa remoto.**
- [ ] **4b — Benchmark** remoto (estimativa pessimista, reserva, prazo por combinação, app
      efêmero) e local (container avulso, guarda de VRAM); `--apply`; quantis por chave.
- [ ] **4c — Várias contas**: `fill_first` com `full_since`, `reconcile_spend`, `exhausted`,
      alertas, probes baratos.
- [ ] **4d — `E > 1` remoto**, depois de T4/T8 com `max_inputs ≥ 2`: settle fatiado, `idle_tail`
      por container, correlação por `container_id`, `solo`, flag de cancelamento, `memory`.
- [ ] **5 — UI admin somente leitura** + CSP de `/admin`. **6 — Doc** `docs/engines/`.
- [ ] **7 — Legendas ao vivo remotas.** **8 — Docling por página e visão** (pré-requisito: S-01).

## 9. Questões em aberto

**Decisões do dono (2026-10-04), fechadas:** Q1 contas compartilhadas descartadas, o limite é
da conta inteira (§2, §4.8); Q2 o usuário decide a ordem e a fila obedece (§4.4, §4.5); Q3 fuso e
âncora por motor, padrão `UTC`/dia 1 (§4.8); Q4 o usuário escolhe GPU, workers e execuções por
worker, com guarda de VRAM, redeploy e benchmark (§4.6); padrão Modal `L4`, `workers=1`, `E=1`.

**Nova:**

- [ ] **Q5.** A UI v1 fica somente leitura para capacidade (GPU, workers, `E`), com edição pela
      API/CLI (§4.6.8)? A alternativa é um formulário mínimo que grava o binding e mostra o comando
      de deploy/compose a rodar. Não bloqueia nenhuma fatia antes da 5.

**Verificações técnicas (gates, não decisões):** T1 superfície do SDK fixado
(`Client.from_credentials`; `client=` em `Cls`/`FunctionCall`/`Dict`; retenção de resultados;
limite de entrada; put-if-absent em `Dict`; `@modal.concurrent`). T2 limite de gasto de workspace
no plano e o erro que produz. T3 precedência `~/.modal.toml` × env × `client=`. **T4** latência de
`cancel()`, se para a cobrança e, com `max_inputs ≥ 2` e método síncrono, se derruba os vizinhos.
T5 formato dos tokens, preços atuais e lista de GPUs. T6 (fatia 8) overhead do Docling por página.
T7 uplink em rajada (40 × 50 MB). **T8** `num_workers` do faster-whisper/CTranslate2 numa GPU:
pesos compartilhados ou replicados, segurança de threads (inclusive o extrator de features
modificado), VRAM e vazão por `E`. **T9** se `with_options`/`update_autoscaler` aplicam GPU,
`max_containers` ou `max_inputs` sem redeploy. **T10** NVML disponível nos containers locais com o
overlay de GPU. T1, T3, T4 (`E=1`), T5, T7 e T8 (`E=1`) são gates da 4a; T4 e T8 com
`max_inputs ≥ 2` são gates da 4d; T10 é gate da 3a. T2 deixou de ser gate.

---

## Apêndice A — DDL resumida

Dinheiro `DECIMAL(12,6)`; taxas `DECIMAL(14,10)`; ids `CHAR(36)`. MySQL externo de versão
desconhecida: nada depende de `SKIP LOCKED`. Ordem de lock: `dispatcher_lease` (compartilhado, só
em colocação) → linha de `engines`.

| Tabela | Colunas | Chaves / índices |
|---|---|---|
| `engines` | `id`, `slug` (`^[a-z0-9][a-z0-9_-]*$`), `display_name`, `adapter_type`, `config JSON` (não secreto, validado por pydantic: `features: {feature: {gpu_type \| gpu_ref, workers, executions_per_worker, cpu?, vram_override_gb?, scale_hint?}}`, `gpus` (local: `[{ref, uuid, name, vram_gb, vram_reserve_gb}]`), `account_max_gpus` (modal), `default_speed`, `max_media_seconds`, `min_speed`, `scaledown_window`, `prices`, `prices_as_of`, `local_unhealthy_after_seconds` (180), `local_stale_seconds` (90), `local_claim_timeout_seconds` (120)), `deployments JSON` (`{feature: {fingerprint, protocol, verified_at}}`), `status ENUM(active,paused,disabled)`, `health ENUM(unknown,healthy,degraded,unhealthy,exhausted)`, `health_reason TEXT` (redigido), `health_until NULL`, `consecutive_failures INT`, **orçamento**: `limit_usd NULL`, `min_remaining_usd DEFAULT 0.50`, `soft_pct TINYINT DEFAULT 80`, `period_tz VARCHAR(64) NOT NULL DEFAULT 'UTC'`, `period_anchor_day TINYINT NOT NULL DEFAULT 1` (1–28), `alerted_soft_period DATE NULL`, `alerted_hard_period DATE NULL`, **provedor**: `provider_reported_usd NULL`, `provider_reported_period DATE NULL`, `provider_reported_at NULL`, **credencial**: `credentials_sealed BLOB NULL`, `credentials_key_id VARCHAR(16) NULL`, `credentials_masked JSON`, `credentials_updated_at`, `credentials_updated_by`, `is_system BOOL`, `version INT`, `created_by`, `created_at`, `updated_at` | `UNIQUE(slug)` |
| `feature_routes` | `feature` PK, `state ENUM(active,draining) DEFAULT 'active'`, `steps JSON` (`[{position, engine_ids[], group_strategy ENUM(priority,fill_first), scale_out_after_seconds?, when?: {min_wait_seconds?, min_backlog?}, spend_cap?: {usd, window: day\|period}}]`, validado), `on_no_engine ENUM(hold,fail) DEFAULT 'hold'`, `fail_after_seconds INT NULL`, `max_attempts INT DEFAULT 3`, `remote_allowed_for ENUM(admins,all) DEFAULT 'admins'`, `user_period_limit_usd NULL`, `remote_data_notice TEXT NULL`, `dispatcher_fallback ENUM(local_direct,hold) DEFAULT 'local_direct'`, `dispatcher_down_seconds INT DEFAULT 120`, `version INT`, `updated_by`, `updated_at` | — |
| `engine_usage` | `id BIGINT AI`, `kind ENUM(job,idle_tail,probe,benchmark)`, `engine_id` FK RESTRICT, `feature`, `subject_type ENUM(job,page,vision_request) NULL`, `subject_id VARCHAR(64) NULL`, `attempt INT NULL`, `job_id CHAR(36) NULL` (sem FK), `user_id CHAR(36) NULL`, `period_start DATE`, `status ENUM(reserved,spawning,running,settled,released)`, `outcome ENUM(succeeded,failed,cancelled,lost) NULL`, `counts_toward_attempts BOOL`, `placed_by ENUM(dispatcher,watchdog,fallback,cli) NULL`, `dispatch_epoch BIGINT NULL`, `gpu_type VARCHAR(32) NULL`, `executions_per_worker TINYINT NULL`, `container_id VARCHAR(128) NULL`, `segment_start DATETIME(6) NULL` (só `idle_tail`), `exec_started_at DATETIME(6) NULL`, `exec_ended_at DATETIME(6) NULL`, `shared_seconds DECIMAL(12,3) NULL`, `cold_start_seconds DECIMAL(9,3) NULL`, `estimated_usd`, `reserved_usd`, `actual_usd NULL`, `cost_basis ENUM(measured,reported,shared,reserved)`, `reported_seconds NULL`, `measured_seconds NULL`, `rate_usd_per_s`, `price_snapshot JSON`, `units JSON` (inclui resultado de benchmark), `fingerprint VARCHAR(64)`, `attempt_key CHAR(36) NULL`, `provider_call_id VARCHAR(128) NULL`, `holder VARCHAR(128) NULL`, `heartbeat_at DATETIME(6)`, `published_at NULL`, `spawned_at NULL`, `deadline_at NULL`, `output_persisted_at NULL`, `republish_count INT DEFAULT 0`, `error_code NULL`, `error_detail TEXT NULL` (redigido), `created_at`, `finished_at NULL` | `UNIQUE(subject_type, subject_id, attempt)`; `UNIQUE(container_id, kind, segment_start)`; `INDEX(engine_id, period_start, status)`, `INDEX(engine_id, feature, kind, status)`, `INDEX(engine_id, feature, gpu_type, executions_per_worker, status, finished_at)`, `INDEX(container_id)`, `INDEX(status, heartbeat_at)`, `INDEX(user_id, period_start)`, `INDEX(job_id)` |
| `job_dispatches` | `id BIGINT AI`, `feature`, `subject_type`, `subject_id VARCHAR(64)`, `job_id CHAR(36) NULL`, `user_id CHAR(36)`, `remote_allowed BOOL`, `state ENUM(probing,waiting,assigned,running,done,failed,bypassed)`, `version INT DEFAULT 0`, `priority TINYINT DEFAULT 5`, `not_before DATETIME(6) NULL`, `placements INT DEFAULT 0`, `job_failures INT DEFAULT 0`, `skip_count INT DEFAULT 0`, `blocked_engine_id NULL`, `solo BOOL DEFAULT 0`, `exclude_engines JSON` (`[{engine_id, until}]`), `payload JSON` (schema por feature, allowlist), `media_seconds DECIMAL(12,3) NULL`, `media_bytes BIGINT`, `usage_id NULL`, `engine_id NULL`, `placed_step TINYINT NULL`, `place_reason VARCHAR(64) NULL`, `enqueued_at`, `unplaceable_since NULL`, `assigned_at NULL`, `error_code NULL`, `updated_at` | `UNIQUE(subject_type, subject_id)`, `INDEX(feature, state, priority, enqueued_at)`, `INDEX(feature, state, remote_allowed, priority, enqueued_at)` |
| `dispatcher_lease` | `id TINYINT` PK (=1), `epoch BIGINT`, `holder VARCHAR(128) NULL`, `holder_kind ENUM(dispatcher,watchdog) NULL`, `renewed_at DATETIME(6)`, `dispatcher_seen_at DATETIME(6) NULL` | — |
| `engine_feature_state` | `engine_id`, `feature`, `full_since DATETIME(6) NULL`, `capacity_penalty INT DEFAULT 0`, `penalty_until NULL`, `alive_below_configured_since NULL`, `updated_at` | PK `(engine_id, feature)` |
| `admin_audit` | `id BIGINT AI`, `actor_user_id NULL`, `auth_method ENUM(jwt,cli)`, `ip VARCHAR(45) NULL`, `action`, `target_type`, `target_id`, `before JSON`, `after JSON` (nunca valores secretos), `created_at` | `INDEX(target_type, target_id, created_at)` |

`job_dispatches.state`: transições no Apêndice E. `published_at` passou para `engine_usage`
(cada tentativa é publicada uma vez).

## Apêndice B — Endpoints admin

Leituras: `require_admin`. Mutações: `require_admin_session` (JWT só, auditado). Sem `PATCH`.

| Método e rota | Corpo → resposta |
|---|---|
| `GET /admin/engine-adapters` | → `AdapterDescriptor[]` (com `gpu_options`, schema do binding, pegadas de VRAM e `max_E` por feature) |
| `GET /admin/engines` · `GET /admin/engines/{id}` | → lista / detalhe (status, orçamento, credenciais mascaradas, e por feature: binding, capacidade, em voo, configurado × vivos, `deploy_state`, `scale_hint`) |
| `GET /admin/engines/status` | → em voo/capacidade por `(motor, feature)`, backlog por feature, lease (época, detentor, `dispatcher_seen_at`), heartbeat do `worker-remote`, linhas do fallback em voo |
| `GET /admin/gpus` | → GPUs físicas: declarada × detectada, VRAM total/orçada/usada, bindings que a usam |
| `GET /admin/engines/{id}/ledger?cursor` | → linhas do ledger |
| `GET /admin/engines/{id}/benchmarks?feature` | → resultados `gpu × E` e recomendação |
| `GET /admin/routing` | → `FeatureRoute[]` (inclui a implícita "só local", backlog, espera mais antiga, `state`) |
| `GET /admin/usage?period&engine_id&feature` | → por motor, feature e dia; estimado × reportado; `unattributed` |
| `GET /admin/jobs/{id}/engine` | → slug, passo e motivo da colocação, custo, segundos, cold start, trilha de tentativas (sem conteúdo) |
| `GET /admin/audit?limit=50` | → `admin_audit` |
| `POST /admin/engines` | `EngineCreate` → 201, criado **pausado** |
| `PUT /admin/engines/{id}` | `EngineUpdate` com `version` (409 em conflito; 422 por invariante) |
| `PUT /admin/engines/{id}/features/{feature}` | `{gpu_type \| gpu_ref, workers, executions_per_worker, cpu?, vram_override_gb?, version}` → 422 com a conta de VRAM quando não cabe ou `E > max_E`; revalida as rotas que usam o motor (`Σ` capacidade remota ⇒ 409); Modal ⇒ `needs_redeploy` |
| `PUT /admin/engines/{id}/gpus` | GPUs físicas declaradas do `local` (revalida todos os bindings) |
| `PUT` / `DELETE /admin/engines/{id}/credentials` | `{fields, current_password}`; 409 sem chave pública |
| `POST /admin/engines/{id}/test` | enfileira em `ingestify-remote-ctl`, espera ≤ 30 s → `HealthReport` |
| `POST /admin/engines/{id}/activate` · `/pause` · `/reset-health` | `activate` exige teste ok + invariante; `pause` drena |
| `PUT /admin/engines/{id}/budget` | `limit_usd`, `min_remaining_usd`, `soft_pct`, `period_tz`, `period_anchor_day` |
| `POST /admin/engines/{id}/reconcile` | puxa o gasto do provedor agora |
| `PUT /admin/routing/{feature}` | `FeatureRoute`; valida passos, bindings, `Σ` capacidade remota, heartbeats (409), passo local quando `admins` (422); avisos de §4.5 |
| `DELETE /admin/routing/{feature}` | marca a rota `draining` (202); o backlog volta ao caminho de hoje em lotes (§4.4) |

A CLI (`python -m workers.engines.cli`) espelha as mutações (`engines`, `set-capacity`, `gpus`,
`budget`, `routes`, `import`, `rotate-keys`), audita com `auth_method=cli`; `benchmark` só existe
na CLI (custa dinheiro e é longo); `modal_deploy` faz o deploy.

## Apêndice C — Contrato TypeScript (`frontend/types/compute.ts`, espelhado em Pydantic)

```ts
export type Feature = "transcription" | "document_conversion" | "vision";
export type EngineStatus = "healthy" | "idle" | "busy" | "exhausted" | "paused" | "error" | "degraded" | "unknown";
export type EngineKind = "local" | "cloud";
export type DeployState = "ok" | "needs_redeploy" | "not_applicable";

export interface UserResponse { id: string; email: string; username: string;
  is_active: boolean; created_at: string; is_admin: boolean; }   // dica de UI; a API decide

export interface GpuOption { gpu_type: string; vram_gb: number;
  usd_per_second: number | null; prices_as_of: string | null; verify: boolean;
  detected?: { uuid: string; host: string } | null; }             // local: detectada por heartbeat
export interface AdapterDescriptor { type_name: string; features: Feature[];
  gpu_options: GpuOption[]; vram_per_execution_gb: Partial<Record<Feature, number>>;
  max_executions_per_worker: Partial<Record<Feature, number>>; }

export interface CredentialState { is_set: boolean; hint?: string | null;
  updated_at?: string | null; updated_by?: string | null; }
export interface BudgetState { period_start: string; period_end: string; timezone: string;
  anchor_day: number; limit_usd: number; min_remaining_usd: number; soft_pct: number;
  spent_estimated_usd: number; spent_reported_usd: number | null; reported_at: string | null;
  reserved_usd: number; unattributed_usd: number | null; used_pct: number;
  state: "ok" | "warning" | "exhausted"; resets_at: string; prices_as_of: string | null; }
export interface FeatureCapacity { feature: Feature; gpu: string;      // gpu_type ou gpu_ref
  workers: { configured: number; alive: number | null };               // alive: só local
  executions_per_worker: number; capacity: number; in_flight: number;
  deploy_state: DeployState; scale_hint: string | null; vram_per_worker_gb: number; }
export interface EngineSummary { id: string; slug: string; display_name: string;
  adapter_type: string; kind: EngineKind; status: EngineStatus; status_detail?: string | null;
  paused: boolean; budget: BudgetState | null; features: FeatureCapacity[];
  month: { jobs: number; gpu_seconds: number; failures: number }; last_used_at: string | null; }
export interface EngineDetail extends EngineSummary { config: Record<string, unknown>;
  credentials: Record<string, CredentialState>; version: number;
  deployed_fingerprint: Partial<Record<Feature, string>>;
  expected_fingerprint: Partial<Record<Feature, string>>; }

export interface PhysicalGpu { ref: string; uuid: string | null; host: string | null;
  name: string; vram_gb: number; reserve_gb: number; budgeted_gb: number; used_gb: number | null;
  bindings: { engine_slug: string; feature: Feature; workers: number;
    executions_per_worker: number; gb: number }[];
  detected_mismatch: boolean; }

export interface BenchmarkResult { engine_slug: string; feature: Feature; gpu: string;
  executions_per_worker: number; speed_per_item: number; speed_aggregate: number;
  usd_per_audio_hour: number | null; vram_peak_gb: number; cold_start_seconds: number | null;
  cost_usd: number; contended: boolean; recommended: boolean; ran_at: string; }

export type GroupStrategy = "priority" | "fill_first";
export interface RouteStep { position: number; engine_ids: string[]; group_strategy: GroupStrategy;
  scale_out_after_seconds?: number | null;
  when?: { min_wait_seconds?: number | null; min_backlog?: number | null } | null;
  spend_cap?: { usd: number; window: "day" | "period" } | null; }
export interface FeatureRoute { feature: Feature; implicit: boolean; state: "active" | "draining";
  steps: RouteStep[];
  on_no_engine: "hold" | "fail"; fail_after_seconds: number | null; max_attempts: number;
  remote_allowed_for: "admins" | "all"; user_period_limit_usd: number | null;
  dispatcher_fallback: "local_direct" | "hold"; dispatcher_down_seconds: number;
  backlog?: { waiting: number; oldest_wait_seconds: number | null; bypassed_24h: number;
    fallback_in_flight: number };
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

Todas com TTL. Nenhum valor de dinheiro, capacidade ou liderança vive no Redis (o lease e o
heartbeat do despachante estão em `dispatcher_lease`, no MySQL). Perder o Redis derruba o broker
do Celery, como hoje; não muda nenhuma decisão de colocação.

| Chave | Tipo / TTL | Escreve | Lê |
|---|---|---|---|
| `engines:remote:heartbeat` | string, 30 s | `worker-remote` | validação de rota, admin |
| `engines:local:{feature}:{hostname}` | hash (device, GPU UUID, VRAM total/usada), 30 s | workers locais de GPU | saúde, `GET /admin/gpus` |
| `engines:kick` | string NX, 500 ms | `submit`/executor/worker local | — (deduplicação) |
| `engine:{id}:{feature}:{gpu}:{E}:speed` | hash, 1 h | beat | `CostModel.estimate` (cache; a fonte é o ledger) |
| `job:{id}:transcript:partial` | existente | fase 2: `worker-remote` | `GET /jobs/{id}/transcript/partial` |

## Apêndice E — Liderança, transições, reentrega e sweeper

**Lease do líder** (`dispatcher_lease`, linha única):

```
assumir:  UPDATE dispatcher_lease SET epoch=epoch+1, holder=?, holder_kind=?, renewed_at=now()
          WHERE id=1 AND (holder IS NULL OR renewed_at < now() − 15 s)          -- 1 linha ⇒ líder
renovar:  UPDATE … SET renewed_at=now() [, dispatcher_seen_at=now() se holder_kind=dispatcher]
          WHERE id=1 AND epoch=<minha> AND holder=<eu>                          -- 0 linhas ⇒ parar
colocar:  BEGIN; SELECT epoch FROM dispatcher_lease WHERE id=1 LOCK IN SHARE MODE  (≠ minha ⇒ ROLLBACK)
          SELECT … FROM engines WHERE id=? FOR UPDATE; …; COMMIT
soltar:   UPDATE … SET holder=NULL WHERE id=1 AND epoch=<minha>                 -- watchdog, ao fim da rodada
```

O submit e o watchdog leem `dispatcher_seen_at` (cache de 5 s no submit). Réplicas da API
disputam o lease; só uma age por rodada.

**Transições de `job_dispatches`** (todas `UPDATE … WHERE id=? AND state=<de> AND version=?`,
`version=version+1`):

| De → para | Quem | Na mesma transação |
|---|---|---|
| — → `probing` | submit | — |
| — → `bypassed` | submit (fallback) | INSERT de uso local `reserved`, `placed_by=fallback` |
| `probing` → `waiting` / `failed` | sonda | — |
| `waiting` → `assigned` | líder (época conferida) | INSERT de uso `reserved` |
| `assigned`/`bypassed` → `running` | claim do executor / worker | uso `reserved → spawning/running` |
| `assigned`/`running`/`bypassed` → `waiting` | claim recusado, claim timeout, falha com nova tentativa, `lost` | uso → `released` ou `settled`; `priority=0`; `not_before` se houver backoff; `media_seconds` nulo ⇒ republica a sonda |
| `running` → `done` / `failed` | settle terminal | uso `settled` |
| `waiting`/`probing` → (fim) | rota `draining`: lote de 100 por rodada publicado no caminho de hoje | — |

Com a rota em `draining`, reservas remotas não reivindicadas viram `released` e o sujeito vai ao
caminho de hoje; requeues sem rota também. Com o backlog vazio, a linha de `feature_routes` é
apagada.

**Reentrega do `execute_remote(usage_id)`**:

| Estado da linha | O executor |
|---|---|
| `reserved` | faz o claim condicional (`reserved→spawning`) |
| `spawning`/`running` com `heartbeat_at` < 60 s | outro detentor vivo: ack e sai |
| `spawning` com heartbeat velho | toma a linha (`UPDATE … WHERE heartbeat_at=<lido>`); procura `attempt_key` no provedor: achou → `running` e retoma; não achou → `spawn` de novo sob a mesma reserva |
| `running` com heartbeat velho | toma a linha; `resume(provider_call_id)`; se já passou de `deadline_at`, `cancel()` antes |
| `running` cuja chamada terminou mas o resultado expirou no provedor | `jobs.status=COMPLETED` → settle com o medido; senão → `settled/lost` (custo medido) e o sujeito volta a `waiting` |
| `settled`, `released` | ack e sai |

**Reentrega de `process_conversion(usage_id)` no local**: claim condicional `reserved→running`;
perdeu (qualquer outro estado) ⇒ ack e sai sem rodar. Venceu com `jobs.status=COMPLETED` ⇒
`settled/succeeded` e sai. O worker nunca cria, reabre ou estende uma reserva.

**Sweeper** (`sweep_usage`, 30 s, em `ingestify-dispatch`; cada ação é condicional). **Nunca
liquida** uma chamada remota terminada e **nunca estende** prazos:

| Condição | Ação |
|---|---|
| remoto `reserved` sem publicação há 60 s | publica `execute_remote` |
| remoto `reserved` e `heartbeat_at` > 5 min | republica; com `republish_count ≥ 3` → `released` e o sujeito volta a `waiting` |
| remoto `spawning`/`running` e `heartbeat_at` > 120 s | republica `execute_remote`; `republish_count++` |
| remoto `running` e `now > deadline_at + 60 s` | `cancel(provider_call_id)` e republica |
| remoto com `republish_count ≥ 5` sem progresso | `settled/lost` cobrando a reserva inteira; sujeito volta a `waiting` (não conta tentativa); alerta |
| local `reserved` sem publicação há 60 s | publica a task local |
| local `reserved` há `local_claim_timeout_seconds` (120) após `published_at` | `released`; sujeito volta a `waiting` (não conta tentativa, não exclui o local) |
| local `running` sem heartbeat há `local_stale_seconds` (90) | `jobs.status=COMPLETED` → `settled/succeeded`; senão `settled/lost` (US$ 0, conta tentativa) e o sujeito volta a `waiting`; mesma transação |
| `waiting` com `media_seconds` nulo e sem sonda há 60 s | republica `probe_media` |
| container sem item vivo há `scaledown_window + 30 s` (só `E > 1`) | grava ou recalcula as linhas `idle_tail` do container (Apêndice L) |

Cenários de crash local cobertos (testes de integração): **A** filho morto (`reject_on_worker_lost`
reentrega na hora; a nova cópia perde o claim e dá ack; o sweeper devolve o sujeito em ≤ 90 s +
30 s); **B** `task_time_limit` (o limite suave já liquidou `failed/TIMEOUT`; se não, como A);
**C** container derrubado (o sujeito volta em ≤ 120 s; a mensagem reaparece após o
`visibility_timeout` e dá ack).

## Apêndice F — Assinaturas do adapter, imagem e árvore de arquivos

```python
class EngineAdapter(ABC):
    type_name: ClassVar[str]                                   # "local" | "modal"
    capabilities: ClassVar[dict[Feature, Capability]]          # sync_ok, cold_start_s, max_input_bytes, max_E
    cost_model: ClassVar[type[CostModel]]                      # estimate(unit, binding) / settle(usage) -> Decimal

    @classmethod
    def gpu_options(cls, engine: EngineSnapshot | None) -> list[GpuOption]: ...   # local: detectadas
    @classmethod
    def validate_binding(cls, feature, binding, engine) -> list[VramTerm]: ...     # levanta 422 (inclui E > max_E)

    def __init__(self, engine: EngineSnapshot, credentials: Mapping[str, str] | None): ...
    def expected_fingerprint(self, feature) -> str: ...        # imagem + código + protocolo + binding (inclui cpu)
    def ensure_ready(self, feature) -> ReadyState: ...         # só VERIFICA; nunca gasta GPU
    def execute(self, feature, unit: WorkUnit, ctx: ExecutionContext) -> ExecResult: ...
    #   ctx: subject, usage_id, attempt_key, deadline_at, on_progress, heartbeat(), record_call_id(str)
    #   ExecResult(output: <FeatureOutput tipado, schema_version>, usage: Usage)
    #   Usage(billable_seconds, measured_seconds, container_id, exec_started_at, exec_ended_at,
    #         shared_seconds, cold_start_seconds, units: dict, provider_cost_usd: Decimal|None, raw: dict)
    #   levanta EngineError(code, usage_parcial)   # usage_parcial.container_id lido do Dict em falha
    def resume(self, provider_call_id: str, ctx) -> ExecResult | None: ...
    def lookup_attempt(self, attempt_key: str) -> str | None: ...
    def container_of(self, attempt_key: str) -> str | None: ...  # protocolo v2: attempt_key → container_id
    def cancel(self, provider_call_id: str, attempt_key: str) -> None: ...  # cancel() + flag cooperativa
    def cooldown(self) -> None: ...                            # o custo NUNCA depende dele
    def provider_spend(self, period) -> Decimal | None: ...
    def health(self) -> HealthReport: ...
    def test_connection(self) -> HealthReport: ...
    def classify_error(self, exc) -> ErrorCode: ...
    def benchmark(self, feature, samples, grid, max_usd) -> BenchmarkPlan: ...  # estimar; run() após confirmar
```

**Imagem**: `debian_slim` Python 3.12 com `faster-whisper`, `ctranslate2>=4.5,<5`, `av<19`,
cuBLAS/cuDNN 9 e `nvidia-ml-py`, lock com hashes, base fixada e pesos embutidos numa revisão HF
fixada. `whisper_core.py` é o laço de decodificação compartilhado com o local (fatia 1b) e checa a
flag de cancelamento entre segmentos. Deploy só por CLI, no container de `worker-remote`; o
fingerprint é gravado no motor e num `modal.Dict` da conta. Inalterados da rodada 1: saúde sem
container quando possível (senão `scaledown_window=2` e `kind=probe`);
`modal.Client.from_credentials(...)` com `client=` explícito; bytes na chamada (MinIO atrás de NAT).

```
whisper_core.py                    # laço de decodificação compartilhado com o local
capacity.py / benchmark.py         # bindings, guarda de VRAM; comando de benchmark
dispatcher.py / lease.py           # tick, candidatos por classe, regra de pulos; lease com época
modal_apps/protocol.py             # PROTOCOL_VERSION (v2: container_id em falha), request/response com limites
modal_apps/image.py                # receita da imagem
modal_apps/whisper_app.py          # alvo de deploy; também construído como app efêmero do benchmark
modal_apps/fingerprint.py          # inclui o binding
modal_apps/requirements-whisper-modal.lock   # pins exatos COM hashes
adapters/modal.py                  # ModalAdapter (import lazy de modal)
cli.py / modal_deploy.py           # CLI de motores e de deploy
```

## Apêndice G — GPUs, pegadas de VRAM e economia

**Opções Modal** (`gpu_options`; preços de GPU por segundo, **verificar** no gate T5 e manter
`prices_as_of`; CPU e memória somam ≈ US$ 0,144/h com `cpu=2` e 6 GiB):

| `gpu_type` | VRAM | US$/s (GPU) | ≈ US$/h (GPU) |
|---|---|---|---|
| `T4` | 16 GB | 0,000164 | 0,59 |
| `L4` | 24 GB | 0,000222 | 0,80 |
| `A10G` | 24 GB | 0,000306 | 1,10 |
| `L40S` | 48 GB | 0,000542 | 1,95 |
| `A100-40GB` | 40 GB | 0,000583 | 2,10 |
| `A100-80GB` | 80 GB | 0,000694 | 2,50 |
| `H100` | 80 GB | 0,001097 | 3,95 |

**Pegada de VRAM por processo, com o contexto CUDA** (padrões em `features.py`; substituídos por
`base_gb + E × per_exec_gb` medidos × 1,1):

| Feature | Modelo | Padrão | Fonte |
|---|---|---|---|
| `transcription` | Whisper `turbo` float16 (CTranslate2) | 3,0 GB | medido neste projeto 2,2–3 GB por réplica, com contexto (comentário do compose: "model plus its CUDA context is ~2-3 GB") |
| `document_conversion` | Docling layout + TableFormer | 1,5 GB | `docs/GPU.md`: 0,9 GB do modelo (15 páginas) + 0,3 GB de contexto, arredondado |
| `vision` | Florence-2-base-ft | 1,8 GB | `docs/GPU.md`: 1,0–1,5 GB do modelo + 0,3 GB de contexto |
| `vision` | Florence-2-large-ft | 3,8 GB | `docs/GPU.md`: 2,5–3,5 GB do modelo + 0,3 GB de contexto |
| (por GPU) | reserva | 1,0 GB | driver, fragmentação, display |

**Economia.** Custo por hora de áudio = custo do container ÷ velocidade agregada (× tempo real).
Container (GPU + `cpu=2` + 6 GiB, preços **a confirmar**): **T4 ≈ 0,73/h, L4 ≈ 0,94/h, A10G ≈
1,24/h**. O número US$ 0,065/h de áudio supõe L4 a ~14,5× sustentado. Fora do item: cauda ≈
US$ 0,016 por container em L4; cold start ~18–30 s.

**Áudio por mês nas 4 contas** (US$ 120, `E=1`, sem cold start e cauda):

| Velocidade sustentada | T4 | L4 | A10G |
|---|---|---|---|
| 6× | ~980 h | ~760 h | ~580 h |
| 10× | ~1.630 h | ~1.270 h | ~960 h |
| 15× | ~2.450 h | ~1.910 h | ~1.450 h |

L4 a US$ 0,065/h de áudio exige ~14,5×; T4 precisaria de ~11,3× e A10G de ~19×. Com `E > 1`, a
coluna certa é a velocidade **agregada** medida pelo benchmark. Contra ~17.500 h/mês no ritmo da
semana medida, o Modal é válvula de rajada.

## Apêndice H — Comando de benchmark

`python -m workers.engines.cli benchmark --engine modal_1 --feature transcription --sample a.mp3
--sample b.mp3 --gpus T4,L4,A10G --concurrency 1,2,4 [--max-usd 1.00] [--yes] [--apply]`

**Remoto** (custa dinheiro):

- Cada `(gpu, E)` roda como **app efêmero** (`with app.run()`) construído para aquele decorator,
  nunca o app de produção nem um deploy; cada combinação paga seu cold start. Enquanto `max_E=1`
  (antes da 4d), a grade aceita `E > 1` só com `--experimental`, que já mede T8.
- **Estimativa pessimista** por combinação, igual à de §4.6.6: `(cold_p80 + scaledown + amostra × E
  ÷ default_speed) × rate`, somada sobre a grade. Imprime cada parcela e o total, exige confirmação
  interativa ou `--yes`, recusa acima de `--max-usd` (padrão 1,00).
- **Teto duro pelo ledger**: reserva o total (`kind=benchmark`, `placed_by=cli`) sob a mesma
  fórmula do orçamento; cada combinação tem `deadline_at` = sua parte de `--max-usd` ÷ `rate` e é
  cancelada ao passar; antes de cada combinação, `gasto_real_acumulado + estimativa_da_próxima >
  --max-usd` ⇒ para e relata parcial. Recusa se `Σ workers de produção da conta + 1 >
  account_max_gpus`.
- Linhas `benchmark` contam no dinheiro, não nas vagas de produção.

**Local** (custo zero, mas disputa a placa): roda num **container avulso** (`docker compose run
--rm --no-deps worker-audio python -m workers.engines.cli benchmark …`), com memória própria,
nunca dentro de um worker vivo. Antes de começar, passa pela guarda de VRAM contra o que está
residente: `VRAM usada (heartbeats/NVML) + E × pegada + reserva ≤ vram_g`; não cabe ⇒ recusa com a
conta. `--pause-local` pausa o binding e espera os em voo; sem ele, o resultado sai `contended`.

**Saída**: tabela `gpu × E` com velocidade por item e agregada, US$/hora de áudio (`rate ÷
velocidade agregada`), pico de VRAM (NVML), cold start, custo; ajuste `base_gb + E × per_exec_gb`;
**recomendação**: a menor US$/h com VRAM ≤ total − reserva e velocidade por item ≥ `min_speed`.
`--apply` grava o binding recomendado (que então pede redeploy). Os resultados ficam nas linhas
`benchmark` do ledger (`units`) e alimentam os quantis da chave.

## Apêndice I — Mudanças por camada

**API**: `engine_admin_routes.py` (Apêndice B); `/transcribe` passa por `dispatch.submit` e aceita
`allow_remote`; `/upload` e `/convert` mandam arquivos com extensão de áudio para
`dispatch.submit('transcription')` quando há rota; laço `engines_watchdog` (15 s) no lifespan;
`/auth/me` e login ganham `is_admin`. Nenhum `av.open` na API.

**Workers** (`backend/workers/engines/`): `base.py`, `registry.py` (imports lazy),
`adapters/{local,modal}.py`, `dispatcher.py`, `lease.py`, `capacity.py`, `pipeline.py`,
`benchmark.py`, `cli.py` e `tasks.py` (`probe_media`, `dispatch_tick`, `execute_remote`,
`sweep_usage`, `reconcile_spend`, `engine_health`). `process_conversion` ganha o `usage_id`
opcional (claim condicional, heartbeat em thread, settle, nunca `self.retry` com `usage_id`) e, sem
`usage_id` e com rota de transcrição, o desvio do ramo de áudio para `dispatch.submit`; sem rota,
nada muda. `audio_extensions` vai para `shared/`. Workers locais de GPU publicam heartbeat com
NVML. Beats com `options.expires` e `task_routes` explícitas. Correção do `force_provider` global
da factory de áudio (fatia 4a).

**Shared** (`backend/shared/engines/`, sem dependências pesadas): `features.py` (com pegadas de
VRAM), `types.py`, `specs.py`, `pricing.py`, `gpus.py`, `sealing.py`, `redact.py`, `routing.py`,
`budget.py`, `dispatch.py`, `media.py` (`AUDIO_EXTENSIONS`).

**Celery (fatia 0a)**: `broker_transport_options={"visibility_timeout": 14400}`, acima do maior
`time_limit` (10.800 s), e beat `broker_unacked_check`. Hoje, com 3.600 s, uma transcrição local
de mais de 1 h é reentregue **enquanto ainda roda**.

**Dados** (Apêndice A): **7 tabelas novas** (`engines`, `feature_routes`, `engine_usage`,
`job_dispatches`, `dispatcher_lease`, `engine_feature_state`, `admin_audit`); bindings, GPUs
declaradas e deploys vivem no JSON validado de `engines`; benchmarks são linhas do ledger.
**Nenhuma coluna nova em tabela existente**: models + uma revisão Alembic, com teste de CI
comparando os esquemas. `init_db()` semeia só `local` e a linha do lease.

**Frontend** (somente leitura): `is_admin` no store; link "Compute" só para admin; guard em
`app/admin/layout.tsx`; `/admin/engines` (status, `em_voo/capacidade`, binding, "configurado vs
vivos", `needs_redeploy` com o comando, `EngineBudgetBar` com `role="meter"`, estimado ×
reportado, lease e fallback); `/admin/gpus`; `/admin/routing` (`describeRoute()`, backlog,
`draining`); `/admin/usage` ($/h de áudio, benchmarks); `/jobs/[id]` mostra "Local / Nuvem". Sem
dependência nova; tipos no Apêndice C.

**Compose / Ops**: `worker-dispatch` (`-Q ingestify-dispatch -c 2`, com `av`, sem chave privada)
e `worker-remote` (`-Q ingestify-remote,ingestify-remote-ctl --pool=threads`,
`requirements-remote.txt`; `stop_grace_period: 60s`), no **profile `engines`**. Rota com remoto
sem heartbeat desses serviços ⇒ 409. O overlay de GPU não muda (`WHISPER_DEVICE` do `worker`
fica como está: com rota, ele não transcreve). Env vars novas, todas opcionais:
`ENGINE_SECRETS_PUBLIC_KEY`, `ENGINE_SECRETS_PRIVATE_KEYS[_FILE]`, `REMOTE_WORKER_CONCURRENCY`,
`REMOTE_MAX_CONCURRENT_UPLOADS`, `PROBE_MAX_BYTES`, `ENGINE_ALERT_WEBHOOK_URL`. Docs:
`docs/engines/MODAL.md` (deploy, custos, GPUs, benchmark, limite no provedor recomendado, dados
enviados e retenção) e `docs/engines/ADAPTERS.md`.

## Apêndice J — Falhas e estado do job

| Erro (`classify_error`) | Estado do motor | Conta em `max_attempts`? | Este item |
|---|---|---|---|
| `AUTH` | `unhealthy` até corrigir credenciais | não | volta à cabeça, excluindo o motor |
| `QUOTA_EXHAUSTED` | `exhausted` até o período seguinte; reconcilia na hora | não | idem; cobra o medido |
| `CAPACITY` / `RATE_LIMITED` | `capacity_penalty` −1 por 5 min (`engine_feature_state`) | não | idem |
| `COLD_START_FAILED` / `NOT_DEPLOYED` | `unhealthy` 10 min (exponencial até 2 h) | não | idem |
| `TRANSIENT` (rede antes do `spawn`) | — | não | até 3× no mesmo motor, com backoff |
| `TIMEOUT` (passou de `deadline_at`) | `consecutive_failures++` | **sim** | volta com reserva ×1,5 |
| `INTERNAL` remoto (inclui OOM) | 3 em 5 min → `unhealthy` 10 min | **sim** | volta excluindo o motor |
| Falha de container com `E > 1` (≥ 2 inputs do mesmo `container_id` em 10 s) | **um** evento de motor | não, para nenhum | volta; o suspeito com `solo=true` (Apêndice L) |
| `INTERNAL` local (exceção em `process_conversion` com `usage_id`) | — | **sim** | volta com `not_before = 60 · 2^(n−1)` s, sem excluir o local |
| `lost` local (processo morreu) | — | **sim** | volta (Apêndice E) |
| `lost` remoto (`worker-remote` sumiu) | alerta | não | volta |
| `INPUT_REJECTED` | — | — | falha na hora |

Contadores separados: `job_failures` (só os que contam) e `placements` (o `attempt` do ledger).
Exclusões expiram em 15 min.

| Momento | `jobs.status` | `started_at` | Redis `job:{id}:status` |
|---|---|---|---|
| Backlog, sonda, espera, colocação | `PENDING` | `NULL` | `queued` |
| Claim (remoto) ou início do worker (local) | `PROCESSING` | agora | `processing` |
| Requeue (inclui o desvio de áudio de `/upload`/`/convert`) | `PENDING` | `NULL` | `queued` |
| Settle com saída | `COMPLETED` (via `finish_*`) | — | `completed` |
| Settle terminal sem saída (`max_attempts`, `no_engine`, `budget_exhausted`) | `FAILED` | — | `failed` |

Itens no backlog ficam `PENDING` com `started_at NULL`, então `detect_stuck_jobs` não os marca.
`get_stuck_jobs` passa a **excluir** jobs com linha viva em `engine_usage` e `heartbeat_at`
recente; jobs sem linha de uso (todo o zero-config) não mudam. No caminho roteado,
`finish_transcription` só conclui a partir de `PROCESSING` e registra em log qualquer tentativa
FAILED→COMPLETED; com `usage_id`, só o settle terminal grava `FAILED`.

## Apêndice K — Riscos de controle

| Risco | Como acontece | Tratamento |
|---|---|---|
| Sobre-assinatura de GPU local compartilhada | Réplicas de features diferentes somam VRAM na mesma placa; hosts multi-GPU põem tudo na GPU 0 | Soma por GPU física (422); VRAM usada no heartbeat comparada ao orçado; "vivos > configurados" e UUID ≠ `gpu_ref` viram alerta; `scale_hint` com `CUDA_VISIBLE_DEVICES` |
| OOM de VRAM ou de RAM | Pegada subestimada; picos (beam, áudio longo, OCR) | Reserva por GPU; padrão conservador, depois `base + E × per_exec` medido × 1,1; `memory` remoto por `max_media_seconds`; local segue o fallback CPU de hoje + alerta; remoto conta como `INTERNAL` (ou evento de container, Apêndice L) |
| Vizinho barulhento | Concorrência na mesma GPU desacelera itens e invalida estimativas | Quantis por `(motor, feature, gpu, E)`; reserva pior caso até 50 amostras; `deadline_at` limita o gasto; `TIMEOUT` > 5 % em 1 h gera alerta |
| Janela de redeploy | Mudança de decorator; containers velhos e novos somados | `needs_redeploy` não colocável até o em-voo antigo zerar ou caber em `account_max_gpus`; deploy só por CLI |
| Réplicas declaradas ≠ reais | Compose não alterado, crash-loop, fila esvaziada | Capacidade pelo configurado; claim timeout devolve ao backlog; alerta com Y < X por 5 min |
| Limite de GPUs da conta | `Σ max_containers` (+ benchmark) acima do plano | Validação por `account_max_gpus`; benchmark recusado; `CAPACITY` reduz a capacidade efetiva por 5 min |
| Gasto de outros sistemas na conta | Conta usada fora do Ingestify | `max(ledger, reportado)`; recomendação de limite no provedor |
| Líder antigo ou duplo | Tick lento, pausa de GC, watchdog assumindo | Lease com época no MySQL; colocação confere a época; transições condicionais |
| Entrada lateral | Áudio por `/upload`/`/convert` | Com rota, desvio para `dispatch.submit`; sem rota, comportamento de hoje (fora da guarda) |

## Apêndice L — Concorrência > 1 no remoto (fatia 4d, atrás de T4/T8)

**Settle fatiado.** O container conhece seus inputs (threads do mesmo processo) e devolve, por
item, `container_id`, `exec_started_at`, `exec_ended_at`, `cold_start_seconds` (só no primeiro
item) e `shared_seconds = ∫ dt / k(t)` sobre o intervalo do item, onde `k(t)` é o número de itens
rodando no container no instante `t`. O executor liquida:

```
exec_s   = exec_ended_at − exec_started_at
share_s  = clamp(shared_seconds, exec_s / E, exec_s)                 # o container não pode inventar
cold_s   = clamp(cold_start_seconds, 0, exec_started_at − spawned_at) # medido pelo executor
actual   = (share_s + cold_s) × rate
```

Item com falha ou cancelado sem dados de fatiamento: `share_s = clamp(exec_s_medido / E, …,
exec_s_medido)` pelo relógio do executor. Por container, `Σ share_s` deve ficar a ± 5 % da união dos
intervalos `[exec_started, exec_ended]`; fora disso, alerta (a divergência de `E=1` não se aplica).

**Cauda ociosa** (`idle_tail`), derivada do banco pelo sweeper sobre a **união** dos intervalos dos
itens de cada `container_id`: lacuna `g ≤ scaledown_window` é cobrada inteira; maior cobra
`scaledown_window`; após o último item, `scaledown_window`. Cada trecho é uma linha com
`UNIQUE(container_id, kind, segment_start)`; se um item posterior aparece no mesmo container, as
linhas do container são recalculadas e substituídas numa transação sob o lock do motor. A
reconciliação, pelo `max()`, cobre o que escapar.

**Exemplo** (L4, `rate` ≈ US$ 0,000261/s, `E=2`, `scaledown_window=60`). A roda de 0 a 300 s, B de
100 a 500 s. `k=1` em [0,100), `k=2` em [100,300), `k=1` em [300,500).
A: `100 + 200/2 = 200 s` → US$ 0,0522. B: `200/2 + 200 = 300 s` → US$ 0,0783. Soma 500 s =
tempo ocupado do container ✓. Cauda: `idle_tail` 60 s → US$ 0,0157. O critério de §3 vale só no
caminho de sucesso.

**Falhas correlacionadas.** ≥ 2 inputs do mesmo `container_id` (lido do `modal.Dict` mesmo quando
a chamada morre) falhando em 10 s contam como **um** evento de motor (para `degraded` e
`unhealthy`) e não contam em `max_attempts` para nenhum deles. O suspeito (maior `D`, ou o último a
começar antes da falha) volta com `solo=true` e só é colocado em binding com `E=1` ou no local.

**Dimensionamento.** `memory = 4 + E × (0,5 + 0,45 × max_h)` GiB, `cpu = 1 + E`; ambos no
fingerprint. **Cancelamento**: `cancel()` do provedor mais a flag por `attempt_key` checada entre
segmentos (≤ 1 segmento). **Adiado**: aprender a velocidade contra o `k` médio do item (`exec_s ÷
shared_seconds`) em vez do `E` configurado; até lá, o `deadline_at` usa o pior caso.

## Apêndice M — Credenciais, segredos e administração (inalterado desde a rodada 1)

- **Selagem assimétrica** (`SealedBox`): API e CLI de importação só **selam**
  (`ENGINE_SECRETS_PUBLIC_KEY`); só `worker-remote` abre (`ENGINE_SECRETS_PRIVATE_KEYS`, lista para
  rotação, `*_FILE`). O selado inclui `engine_id` e `key_id`. Não existe chave padrão: sem pública,
  `PUT …/credentials` ⇒ 409; sem privada, nada remoto ativa.
- **Somente escrita**: respostas trazem `{is_set, hint, updated_at, updated_by}`; `hint` só em
  `hint_mode=last4`, nunca em `kind=secret`.
- **Redação**: `logging.Filter` stdlib no root logger de todo processo, `redact()` em todo erro
  persistido, `ErrorCode` saneado nas rotas admin em qualquer `ENVIRONMENT`.
- **Subprocessos** com env **montado do zero** (`PATH`, `LANG`, `HOME=<tmpdir>`, `PYTHONPATH`,
  `MODAL_TOKEN_ID/SECRET`, `MODAL_ENVIRONMENT`), tokens nunca em argv.
- **CLI de importação**: `getpass`, stdin (`dotenv_values`, `--prefix MODAL_ACCOUNT_`) ou
  `~/.modal.toml`; dry-run por padrão, motores criados **pausados**, idempotente por slug.
- **`remote_allowed_for`**: `admins` (padrão) ou `all`. Com `all`, `user_period_limit_usd` é
  obrigatório e checado na reserva, com reservas (API keys contam como seu usuário), e a rota
  exige um `remote_data_notice` exibido no upload e na doc da API.
- **`is_effective_admin(user)`** sai de `require_admin` para `shared/` e é a única regra de
  `/auth/me`, rotas admin e política de rota.
- **Mutações** de motor, binding, credencial, orçamento e rota usam `require_admin_session`: JWT
  obrigatório (`X-API-Key` ⇒ 403), `admin_audit` e log WARNING. Credenciais e ampliar
  `remote_allowed_for` exigem `current_password`. Sem `PATCH`: `PUT` com `version`.
- **`GET /jobs/{id}` continua só do dono** e ganha `engine.kind` e `queue_reason ∈ {in_queue,
  starting}`. Custo e trilha ficam em `GET /admin/jobs/{id}/engine` (metadados, nunca conteúdo).
- **Primeiro admin**: `scripts/make_admin.py` corrigido na fatia 0b. CSP (`script-src 'self'`) em
  `/admin/*`.

---

## Histórico de revisão

**Rodada 1 (2026-10-04).** Duas revisões: adversarial (A: 3 blockers, 12 major, 15 minor) e
segurança/OSS (S: 2 blockers, 12 major, 11 minor). O líder da sessão decidiu simplificar a v1;
as decisões foram aplicadas. Legenda: **aceito**, **aceito c/ mudança**, **rejeitado**. As
resoluções marcadas com † foram revistas na rodada 3 (abaixo).

### Revisão adversarial

| # | Achado | Resolução |
|---|---|---|
| A1 (blocker) | Sweeper liquida chamada terminada sem salvar a saída | **Aceito.** Dinheiro e saída separados; sweeper só republica; `settled/succeeded` exige `output_persisted_at`. `stop_grace_period` e `visibility_timeout` (fatia 0a). |
| A2 (blocker) | Nada limita o gasto de uma tentativa | **Aceito.** `deadline_at = spawned_at + reserved/rate`, cancel no prazo, sweeper nunca estende, `timeout` do app derivado do maior job admissível. |
| A3 (blocker) | Dois controladores na mesma conta estouram | **Aceito.** Precondição P (dedicada ou dividida + limite do Modal), §2 reescrito com excesso limitado. † |
| A4 | Failovers contam em `max_attempts` | **Aceito.** Só erros do job contam; 4×`AUTH` ⇒ local. |
| A5 | Despachante é SPOF; backlog órfão | **Aceito.** Local nunca passa pelo despachante; watchdog no `worker` padrão; excluir rota drena o backlog. † |
| A6 | Capacidade local por heartbeat ⇒ W infinito em restart | **Aceito.** Slots configurados; heartbeat não entra. O ajuste por réplica em CPU fica fora. † |
| A7 | Leases sem heartbeat durável; raia única bloqueia controle | **Aceito c/ mudança.** Sem leases: contagem do ledger sob o lock do motor, `heartbeat_at` na reserva; `ingestify-remote-ctl`; `Σcaps ≤ threads − 2`. |
| A8 | Spawn não gravado roda duas vezes; `released` sem regra | **Aceito.** Estado `spawning` + `attempt_key` com `modal.Dict` (gate T1); tabela de reentrega cobre todos os estados. |
| A9 | Período desalinhado do ciclo; reconciliação sobrescreve | **Aceito.** Âncora e fuso obrigatórios; intervalo explícito ou pausa perto da virada; `GREATEST`. † |
| A10 | Estado do job indefinido × `detect_stuck_jobs` | **Aceito.** Tabela de estados; backlog em `PENDING`; `get_stuck_jobs` exclui remotos vivos. |
| A11 | Modelo não serve para páginas e visão | **Aceito.** Chave de sujeito, sem FK; `convert_page_task`; `finish_page`; esboço. |
| A12 | Health checks custam 10× | **Aceito.** Saúde sem container, `scaledown_window=2`, só motores usados em 24 h, `kind=probe`. |
| A13 | Maquinário desproporcional | **Aceito** (decisão do líder): spill no submit, 5 tabelas, 2 estratégias, requeue em vez de failover na task, deploy por CLI, UI só leitura, sem `prewarm`. † |
| A14 | Auto-deploy frágil e entre contas | **Aceito.** Só CLI; teste com token sentinela no env; "nunca muta `os.environ`". |
| A15 | Cabeça impossível trava a feature | **Aceito.** Rejeição na sonda; lookahead de 20 com limite de pulos. |
| A16 | Qualificadores da economia | **Aceito.** Velocidade exigida por GPU e tabela por velocidade. |
| A17 | Cauda ociosa subconta e depende do Redis | **Aceito c/ mudança.** Derivada do banco; coberta pelo `max()`. † |
| A18 | "Mesma transação do Job" põe job sem arquivo | **Aceito.** INSERT depois do arquivo, transação própria, fallback ao caminho de hoje. |
| A19 | Ordem de locks | **Aceito.** Um lock (linha do motor); retry em 1213/1205. |
| A20 | Arredondamento | **Aceito.** `Decimal(str())`, reserva para cima, taxa `DECIMAL(14,10)`. |
| A21 | Higiene de beat/chute | **Aceito.** `expires`, `task_routes`, lock com token, chute deduplicado. |
| A22 | Superfície do SDK | **Aceito.** Gates T1–T4 da fatia 4a. |
| A23 | Pool do banco < threads | **Aceito.** Pool = concorrência + 4; sem sessão durante `get`. |
| A24 | Imagem do `worker-remote` | **Aceito.** `requirements-remote.txt` e volume temp. |
| A25 | `whisper_core` muda o local depois da janela de paridade | **Aceito.** Fatia 1b própria, clipe ≥ 3 min, CPU e GPU. |
| A26 | Leitura da rota deve falhar com segurança | **Aceito.** Erro ⇒ caminho de hoje; cache de 5 s. |
| A27 | Bordas de esgotamento | **Aceito.** Subir limite limpa `exhausted`; fallback com n < 20. |
| A28 | Memória de uploads | **Aceito.** `REMOTE_MAX_CONCURRENT_UPLOADS`. |
| A29 | Contradições e critérios faltantes | **Aceito.** §2/§3 reescritos; claim refaz a fórmula; critérios novos. |
| A30 | O ledger protege contra o quê depende do tipo de conta | **Aceito.** Precondição P + Q1–Q3 antes da fatia 4a. † |

### Revisão de segurança / OSS

| # | Achado | Resolução |
|---|---|---|
| S1 (blocker) | Duração adversarial ⇒ DoS de cabeça e estimativa manipulada | **Aceito c/ mudança.** Sonda limitada em bytes no worker; impossível ⇒ falha na sonda; teto por tentativa cobre subdeclaração; `max_audio_duration_seconds` como limite de admissão remota. |
| S2 (blocker) | Qualquer usuário gasta o dinheiro do operador | **Aceito.** `remote_allowed_for=admins` padrão; teto por usuário na reserva. `ALLOW_REGISTRATION` e justiça entre usuários: **rejeitados para esta spec**. |
| S3 | Mídia sai sem aviso | **Aceito c/ mudança.** Aviso obrigatório com `all`; `allow_remote=false` por job; retenção na doc. |
| S4 | Chave simétrica na API + demux na API | **Aceito.** SealedBox; sonda em `worker-dispatch`, sem chave privada. |
| S5 | Admin aceita API key, sem step-up | **Aceito.** JWT só, `admin_audit`, `current_password`; CSP no `/admin`. |
| S6 | `make_admin.py` promove o usuário errado | **Aceito.** Fatia 0b. |
| S7 | Uso autodeclarado e saída confiados | **Aceito.** `max(reportado, medido)`; validação por `protocol.py`; fingerprint é consistência. (Rodada 3: com `E > 1`, `shared_seconds` limitado por clamp.) |
| S8 | Redação mira structlog, que não é usado | **Aceito.** Filtro stdlib + `redact()` + erros saneados. |
| S9 | Env de subprocesso | **Aceito.** Allowlist, `HOME` temporário, nada em argv. |
| S10 | `auto_deploy` é risco de cadeia de suprimentos | **Aceito.** Só CLI; hashes; base e builder fixados. |
| S11 | Orçamento "ilimitado/soft/desabilitado" representável | **Aceito.** Invariante na escrita e no claim; `prices_as_of`. |
| S12 | CLI de importação | **Aceito.** Stdin/getpass/`~/.modal.toml`, `dotenv_values`, dry-run, token dedicado. |
| S13 | Contrato do adapter não é API estável | **Aceito c/ mudança.** `CostModel` do adapter, I/O tipado, kit de contrato, provisório. |
| S14 | v1 grande demais | **Aceito.** Fatias reordenadas. Executor falso na fatia 3 + `spill_wait_seconds=0` na 4a. † |
| S15 | Lacunas de auditoria | **Aceito.** `admin_audit` append-only + log. |
| S16 | Gestão de chave | **Aceito.** `_FILE`, backups separados, runbook, `engine_id` no selado. |
| S17 | Hints mascarados | **Aceito.** Regra mecânica e teste. |
| S18 | Estado do orçamento exposto a usuários | **Aceito.** Só `in_queue`/`starting` para não-admins. |
| S19 | "Dono/admin" em `GET /jobs/{id}` | **Aceito.** Só dono; rota admin de metadados. |
| S20 | CORS sem `PATCH` | **Aceito c/ mudança.** `PUT` com `version`. |
| S21 | Payload cru + S-01 | **Aceito.** Allowlist por feature; S-01 pré-requisito da fatia 8. |
| S22 | Detalhes do dono em padrões e docs | **Aceito c/ mudança.** Config do dono rotulada como exemplo; fuso/âncora sem padrão. † |
| S23 | Três caminhos de migração | **Aceito.** Nenhuma coluna nova em tabela existente; models + Alembic + teste de CI. |
| S24 | Licença e proveniência | **Aceito c/ mudança.** Revisão do modelo local fixada; `LICENSE` vira issue. |
| S25 | Itens menores | **Aceito.** Webhook só por env; nota de CSRF; S-04 não piora. |

**Questões fechadas na rodada 1:** Q5 (virou gates T1–T5), Q6 (T7), Q7 (T6), Q8 (resolvida por
`remote_allowed_for=admins` + aviso), Q9 (fatia 0a), Q10 (sem colunas novas; Alembic + models),
Q11 (fora de escopo), Q12 (`auto_deploy` removido). A numeração Q5 foi reutilizada na rodada 3.

### Rodada 3 — decisões do owner (2026-10-04)

O owner respondeu Q1–Q4; o decisor reescreveu as seções afetadas (não só anexou).

| Decisão | O que mudou na spec | Resoluções anteriores revistas |
|---|---|---|
| **1. Contas compartilhadas: descartado.** O limite é da conta inteira; não há divisão entre sistemas. | Removidos a precondição P, `provider_cap_confirmed` (coluna, endpoint, critério, gate de ativação) e a nota sobre limite dividido. Mantido `max(ledger, reportado)`, que enxerga o gasto alheio; o limite no provedor virou recomendação da doc (§2, §4.8). `unattributed` explicado como gasto alheio. | A3, A30 |
| **2. O usuário decide a ordem; a fila obedece à regra; controles por item.** | Transbordo no submit substituído por **colocação pela fila**: com rota, todo item entra em `job_dispatches`; o despachante percorre passos ordenados com condições (`min_wait_seconds`/`min_backlog`, `spend_cap`) e estratégias de grupo (`priority`, `fill_first`) (§4.4, §4.5). Removidos `W_local`, `p50_local`, `spill_wait_seconds`, `local_fallback`, `handback_after_seconds` e as cinco regras de hand-back. O local virou um passo com `usage_id` e capacidade configurada (nunca heartbeat). Defesas do SPOF: fallback `local_direct` no submit e no watchdog, alerta, remoção de rota drena (§4.4). Alternativas: o transbordo no submit é a alternativa descartada, com o motivo do owner. Critérios, DDL (`steps`, `dispatcher_fallback`, `bypassed`, `published_at`), endpoints, tipos, testes e fatias 3a/3b reescritos. | A5, A6, A13, S14 |
| **3. Período**: fuso e âncora configuráveis por motor, padrão UTC e dia 1. | `period_tz`/`period_anchor_day` com padrão; critério de ativação ajustado (§4.8). | A9, S22 |
| **4. Escolha de GPU e concorrência.** | Nova §4.6 "Capacidade e concorrência": `gpu_options` (Modal e GPUs locais detectadas), binding `gpu × workers × executions_per_worker`, capacidade como teto do despachante, `@modal.concurrent` e limite de `E=1` local em GPU (com motivo), guarda de VRAM por GPU física compartilhada, `needs_redeploy` e "configurado X, vivos Y", quantis por `(motor, feature, gpu, E)`, reserva no pior caso, settle fatiado por `k(t)` com exemplo, `idle_tail` por container, comando `benchmark` com estimativa e confirmação, riscos de controle. Apêndice G novo; Apêndices A–F atualizados; gates T8–T10; fatias 3a e 4b. | A17, S7 |

Nova questão aberta: Q5 (edição de capacidade na UI v1). Para manter o corpo revisável
(≈ 7.600 palavras), sem mudar decisões: economia e preços foram para o Apêndice G, detalhes do
benchmark para o H, mudanças por camada para o I, tabela de erros e estados do job para o J;
credenciais, adapter Modal e alternativas da rodada 1 foram condensados. As seções 4.10–4.16
foram renumeradas.

### Rodada 4 — revisão adversarial de fila e concorrência (2026-10-04)

Uma revisão adversarial focada nas mudanças da rodada 3 (colocação pela fila, capacidade e
concorrência): 1 blocker, 13 major, 17 minor. Antes de decidir, os fatos de código foram
conferidos: `/upload` (`routes.py:224`) e `/convert` (`routes.py:906`) chamam
`process_conversion.delay` na fila padrão; `process_conversion` trata como transcrição qualquer
arquivo com extensão em `audio_extensions` (`tasks.py:219-223`); o ramo de exceção chama
`self.retry` (`tasks.py:559`, `max_retries=3`); `task_acks_late` e `task_reject_on_worker_lost`
estão ligados e o broker é o Redis (`celery_app.py`). O decisor reescreveu as seções afetadas.
Mudanças estruturais: estado `orphaned` removido (vira `settled/lost` com o sujeito sempre de volta
ao backlog); liderança e heartbeat do despachante saíram do Redis para `dispatcher_lease` (MySQL,
com época); 2 tabelas novas (`dispatcher_lease`, `engine_feature_state`); `E > 1` remoto foi para
a fatia 4d; §4.6.9 virou o Apêndice K, o settle fatiado o Apêndice L, credenciais e administração
o Apêndice M.

| # | Achado | Resolução |
|---|---|---|
| R1 (blocker) | Recuperar item local que caiu perde o item ou faz o worker gravar reserva | **Aceito.** Todo executor só roda depois de vencer o claim condicional que sai de `reserved`; perdeu ⇒ ack sem rodar. O sweeper dá a linha como `lost` (ou `succeeded`, se o job já concluiu) e devolve o sujeito ao backlog na mesma transação; `orphaned` saiu; workers nunca gravam reservas; `local_stale_seconds` 300 → 90 com heartbeat de 15 s; testes A/B/C (§4.7, Apêndice E). Revê A1/A8 da rodada 1. |
| R2 | Vagas configuradas acima das réplicas vivas prendem itens no Celery; `reserved` nunca consumida não tem regra | **Aceito.** `local_claim_timeout_seconds` (120): colocação local não reivindicada vira `released` e o sujeito volta ao backlog, onde outro passo pode pegá-lo; alerta com Y < X por 5 min. A parte opcional (capacidade efetiva pelo máximo de vivos) foi **rejeitada**: contraria a decisão do owner de capacidade configurada, e o claim timeout já resolve. |
| R3 | Itens `bypassed` invisíveis à capacidade; watchdog despeja o backlog inteiro no local | **Aceito.** O fallback do submit grava linha de uso local que conta no em-voo; o watchdog coloca no máximo `capacidade − em_voo(local)` por rodada e o resto fica ao alcance dos passos remotos. O item (c) (chave ausente lida como parado) some com o heartbeat no MySQL. |
| R4 | Despachante lento e watchdog/submit em *split brain* rodam o item duas vezes | **Aceito.** Toda transição de `job_dispatches` e `engine_usage` é condicional (com `version`); lease com época em `dispatcher_lease` (MySQL), conferida com `LOCK IN SHARE MODE` em toda colocação; o watchdog assume o lease (nova época) para agir. A checagem "ainda `bypassed`" vira o claim condicional da linha de uso. |
| R5 | Transcrição entra por `/upload` e `/convert` sem passar pela rota | **Aceito c/ mudança** (decisão do líder: rotear, não 415). Com rota, áudio em `/upload`/`/convert` vai para `dispatch.submit('transcription')`: na API para arquivos (mesma lista de extensões, movida para `shared/`) e em `process_conversion` sem `usage_id` para fontes baixadas no worker. Sem rota, comportamento de hoje. **Rejeitado** `WHISPER_DEVICE=cpu` no `worker`: mudaria o zero-config, e com rota o `worker` não transcreve. |
| R6 | `self.retry` de `process_conversion` conflita com o ledger | **Aceito.** Com `usage_id`, nunca `self.retry`: liquida `failed` (`INTERNAL`, conta) e o backlog devolve com `not_before` no backoff de hoje, até `max_attempts`; só o settle terminal grava `FAILED`. Sem `usage_id`, o retry de hoje (§4.9). |
| R7 | A regra de 10 pulos congela a feature até o fim do período | **Aceito.** Pulo só conta se a candidata caberia no motor quando o em-voo dele liquidasse; bloqueante reserva só esse motor (`blocked_engine_id`), nunca o tick; quem não caberia nem com o motor vazio nunca bloqueia. Revê A15. |
| R8 | Lookahead de 20 deixa admins e itens elegíveis a remoto atrás de itens só locais | **Aceito.** Candidatos = cabeça de 20 geral ∪ cabeça de 20 com `remote_allowed`, por índice `(feature, state, remote_allowed, priority, enqueued_at)`; teste 50 + 1. Revê A15. |
| R9 | `fill_first` indefinido sob recusa por orçamento; `full_since` sem lugar; corrente contaminado por probe/benchmark | **Aceito.** Recusa por orçamento, tamanho ou `spend_cap` ⇒ próxima conta na hora; só "cheio" espera `scale_out_after_seconds`; `full_since` em `engine_feature_state` (MySQL); corrente derivado só de `kind=job`; motor inelegível é pulado e volta a ser corrente. |
| R10 | Reserva pior caso × E estoura ou estrangula `spend_cap` e teto por usuário | **Aceito.** `spend_cap` e teto por usuário contam `liquidado + reservado`; validação avisa `capacidade × hold(D_p50)` acima do cap, do teto ou do restante; com ≥ 50 linhas liquidadas na chave, `hold` passa a `D × q95(actual ÷ D)`; troca documentada (§4.6.6). Com `E > 1`, o teto de dinheiro da tentativa é `deadline × rate`, somado ao excesso limitado (§4.8). |
| R11 | Com E > 1, o cancel no prazo pode não parar o gasto nem poupar os vizinhos | **Aceito.** `max_E=1` remoto até T4 e T8 passarem com `max_inputs ≥ 2` (T4 ampliado: latência e raio do cancel em método síncrono); flag de cancelamento por input checada entre segmentos. `E > 1` virou a fatia 4d. |
| R12 | Falha de container cobra tentativas de itens inocentes e degrada o binding de uma vez | **Aceito.** Correlação por `container_id` (o container grava `attempt_key → container_id` no `modal.Dict`; protocolo v2, para saber o container também em falha): ≥ 2 inputs em 10 s = um evento, nenhum conta tentativa; suspeito volta `solo`; `memory` por `max_media_seconds` (Apêndice L). |
| R13 | Benchmark: estimativa subconta por E, sem prazo, deploy por combinação | **Aceito.** Estimativa pessimista (`amostra × E ÷ default_speed`) + cold/cauda por combinação; reserva do total no ledger, `deadline_at` por combinação e parada quando o acumulado + a próxima passa de `--max-usd`; app efêmero por `(gpu, E)`; recusa se não cabe em `account_max_gpus` (Apêndice H). |
| R14 | Benchmark local pode derrubar a GPU e o container de produção | **Aceito.** Container avulso (`docker compose run --rm --no-deps`), nunca dentro do worker vivo; passa pela guarda de VRAM contra o residente e recusa com a conta se não couber. |
| R15 | "Cobre Redis fora" é falso: o broker é o Redis | **Aceito.** Frase corrigida: Redis fora = como hoje (o submit falha). |
| R16 | Critério de restart contradiz `unhealthy` em 60 s | **Aceito.** `local_unhealthy_after_seconds` padrão 180; critério fala de restart mais curto que isso. |
| R17 | Hosts multi-GPU: a guarda conta GPUs declaradas, não reais | **Aceito c/ mudança.** `scale_hint` com `CUDA_VISIBLE_DEVICES`; UUID ≠ `gpu_ref` gera **alerta** (não `degraded`, para uma réplica não tirar o local da rota). `gpu_ref` em lista: adiado. |
| R18 | Pegada linear aprendida em E > 1 subestima E = 1 | **Aceito.** Ajuste `base_gb + E × per_exec_gb` na grade do benchmark. |
| R19 | Contexto CUDA contado duas vezes | **Aceito.** Pegadas são por processo e já incluem o contexto; termo separado removido; exemplo refeito (13,3 ✓ com 3 réplicas; 16,3 ✗ com 4). |
| R20 | `cpu=2` fixo com E crescente | **Aceito.** `cpu` é campo do binding, padrão `1 + E`, no `rate` e no fingerprint. |
| R21 | Estado compartilhado do extrator de features entre threads | **Aceito.** Incluído no gate T8. |
| R22 | `cold_start_seconds` autodeclarado sem clamp | **Aceito.** Clamp em `[0, exec_started_at − spawned_at]` medido pelo executor; checagem `Σ share_s` ≈ união dos intervalos ± 5 % com alerta. |
| R23 | Linhas `idle_tail` nem idempotentes nem recalculáveis | **Aceito.** União dos intervalos por container; `UNIQUE(container_id, kind, segment_start)`; recalcula e substitui sob o lock quando aparece item posterior. |
| R24 | Itens que falham com E > 1 não têm dados de fatiamento | **Aceito.** Critério limitado ao caminho de sucesso; falhas usam `exec_s/E … exec_s` pelo relógio do executor. |
| R25 | `PUT …/features/{feature}` pula a checagem de `Σ` capacidade remota | **Aceito.** Mudança de binding revalida as rotas que usam o motor (409). |
| R26 | Sobreposição no redeploy | **Aceito.** Não colocável até o em-voo antigo zerar ou caber em `account_max_gpus`; linhas em voo guardam `gpu_type`, `E` e fingerprint da reserva. |
| R27 | Apagar a rota no meio de uma rajada deixa estados indefinidos | **Aceito.** Rota `draining`; lotes de 100 por rodada no caminho de hoje; reservas remotas não reivindicadas liberadas; requeues sem rota vão ao local; a linha é apagada com o backlog vazio (`DELETE` responde 202). |
| R28 | Watchdog vive num worker que pode estar saturado | **Aceito c/ mudança.** Laço de 15 s no processo da API (sempre de pé quando há entrada), coordenado pelo lease; não ganha fila própria. |
| R29 | Velocidade aprendida mistura níveis de concorrência | **Adiado** para depois da 4d: com `max_E=1` remoto, `k` é sempre 1. Registrado no Apêndice L. |
| R30 | `em_voo` conta probes/benchmarks; falta o passo da colocação | **Aceito.** Vagas contam só `kind=job`; `placed_step`/`place_reason` em `job_dispatches` e na visão admin. |
| R31 | `local_direct` contraria rotas crédito-primeiro | **Aceito.** Documentado em §4.5 junto do exemplo; validação avisa quando o primeiro passo é remoto com `local_direct`. |

Nenhuma questão nova para o owner. Corpo mantido em ~8.000 palavras movendo detalhe para os
Apêndices E, H, K, L e M.
