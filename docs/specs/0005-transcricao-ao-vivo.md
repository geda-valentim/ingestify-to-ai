# 0005 — Transcrição ao vivo com legendas em streaming

| | |
|---|---|
| **Status** | Em revisão |
| **Autor** | Codex, a partir do pedido de Geda Valentim |
| **Criada em** | 2026-10-05 |
| **Atualizada em** | 2026-10-05 |
| **Relacionadas** | [0002 — Dispositivo e Whisper](0002-dispositivo-unico-e-migracao-do-whisper.md), [0003 — Motores de execução](0003-motores-de-execucao-roteamento-e-orcamento.md), [0004 — Projetos e pastas](0004-projects-and-folders.md) |
| **Substituída por** | — |

Os endpoints, serviços e configurações desta spec são **propostos**. O fluxo atual
continua sendo upload de arquivo e consulta de transcrição parcial; live ainda não
foi implementada nem medida nesta GPU.

## 1. Problema

`POST /transcribe` recebe um arquivo inteiro antes de despachar sua transcrição. O
faster-whisper produz segmentos durante o processamento, mas isso não permite
transcrever um microfone ou uma transmissão cujo áudio ainda está chegando.

Há também esperas na entrega do texto: o worker local agrupa segmentos com intervalo
de 2 s (`workers/tasks.py`); a UI consulta `/transcript/partial` a cada 3 s e revela os
trechos com animação (`components/job/live-transcript.tsx`). No caminho Modal, há
outro intervalo de consulta de 3 s. Esses valores não são um limite máximo de atraso:
o envio local depende da chegada de outro segmento, e ainda existem fila e inferência.

O pedido é produzir **legendas durante a chegada do áudio**, com atraso medido e sem
precisar esperar a gravação terminar. Trocar o transporte para RPC, mantendo upload
integral, fila e decodificação atual, não resolve esse problema.

## 2. Objetivo

Receber áudio contínuo em uma sessão autenticada, devolver texto provisório e segmentos
confirmados com timestamps, e guardar a transcrição final como um job do projeto do usuário.

### Fora de escopo

- Alterar o contrato de `POST /transcribe` ou a deduplicação de arquivos.
- SSE para melhorar os jobs de arquivo atuais: pode ter uma spec própria.
- Capturar RTMP/HLS/YouTube, transportar vídeo ou criar chamadas WebRTC.
- Tradução, diarização, timestamps por palavra e edição colaborativa.
- Retomar uma sessão de áudio após perda de conexão, migração entre GPUs ou replay
  automático do áudio em outro backend.
- Roteamento Modal, reserva de orçamento e cobrança por minuto de live na fase inicial.
  A live usa capacidade local própria; não entra escondida no ledger da feature `transcription`.
- Guardar o áudio original. Por padrão, só a transcrição final será persistida.

## 3. Critérios de aceitação

- [ ] JWT e API key criam sessão pelas mesmas regras de autenticação e projeto/pasta
      da spec 0004, incluindo precedência do JWT quando ambos os headers existem.
- [ ] Falta de projeto válido é rejeitada antes de criar job ou consumir capacidade;
      IDs alheios respondem `404`. Uma API key vinculada dispensa projeto explícito.
- [ ] Sessão aceita áudio progressivamente e emite texto **antes** de receber o fim
      do áudio. Um teste que envia o arquivo inteiro imediatamente não comprova isso.
- [ ] Há texto provisório substituível e segmentos confirmados imutáveis. Contexto
      repetido entre janelas não duplica palavras confirmadas.
- [ ] Timestamps referem-se ao áudio original, incluindo silêncios, e permanecem
      ordenados quando há VAD, sobreposição ou resampling interno.
- [ ] `finish` processa a cauda, persiste os formatos finais e só então emite
      `session.completed`. Nenhuma palavra confirmada desaparece do resultado.
- [ ] Os formatos de uma live concluída continuam consultáveis pelo endpoint existente
      após expirar status/resultado no Redis, usando o job e a sessão no MySQL.
- [ ] Cancelamento, desconexão, exclusão do job e perda do worker encerram a sessão
      e liberam sua capacidade. Um resultado atrasado não ressuscita o job.
- [ ] Sem modelo pronto, GPU disponível ou vaga, a criação falha com `503` e
      `Retry-After`, sem colocar a live na fila de arquivos.
- [ ] Áudio fora de ordem, sequência repetida, formato inválido e backlog excessivo
      produzem erro explícito; o servidor não descarta áudio silenciosamente.
- [ ] Uma sessão não lê nem altera o áudio, contexto, eventos ou resultado de outra.
- [ ] Reiniciar API/worker marca sessões abandonadas como `failed`, com motivo;
      elas não ficam indefinidamente `processing` nem viram `completed` com texto truncado.
- [ ] A liberação em produção exige benchmark em PT-BR no hardware alvo e os critérios
      de latência, memória e qualidade da seção 7. Os números publicados pelos modelos
      não contam como medição local.

## 4. Solução proposta

### 4.0 Código existente a reutilizar

Revisão do código em 2026-10-05: a entrega acrescenta entrada contínua e controle
de sessão. Os contratos de identidade, localização e resultado continuam compartilhados.

| Área | Código existente (caminhos a partir da raiz) | Uso na live |
|---|---|---|
| JWT / API key | `backend/shared/auth.py:get_current_active_user` | Mesma dependência REST e precedência de credenciais; ticket WS é novo. |
| Projeto / pasta | `backend/api/projects_api.py:LocationFields`, `prepare_upload_location`, `resolve_upload_location` | Converter JSON para `LocationFields`; reutilizar validação, key vinculada, fallback configurado e criação de localização. |
| Propriedade | `backend/api/deps.py:get_owned_job`, `resolve_owned_job` | Além da autorização, exigir `job is not None and job.id == job_id`; live não aceita autorização por cache nem pelo job pai. |
| Tags | `backend/api/tag_routes.py:parse_tags_or_422`, `backend/shared/tags.py:set_job_tags` | Reutilizar normalização e associação existentes, que já aceitam listas. |
| Confirmados | `backend/shared/redis_client.py:RedisClient.append_partial_transcript`, `get_partial_transcript`, `delete_partial_transcript` | Mesmo schema `{start,end,text}` e TTL; adicionar guarda de geração e tratar falha de escrita. Provisórios ficam no WS. |
| Formatos / persistência | `backend/workers/audio/base_transcriber.py:format_markdown`, `format_text`, `format_vtt`, `format_srt`; `backend/workers/engines/pipeline.py`; `backend/shared/transcripts.py` | Reutilizar formatação e extração da pipeline; adaptar metadata sem arquivo e conclusão estrita descrita em 4.6. |
| Consulta / exclusão | `backend/api/routes.py:get_job_result`, `_transcript_response`, `delete_job` | Mesmos endpoints; acrescentar resolução de artefatos live, fallback após TTL e revogação antes do cleanup. |
| Modelo / dispositivo | `backend/workers/engines/whisper_core.py:load_model`; `backend/shared/device.py:resolve_whisper_device`, `resolve_whisper_compute_type` | Reutilizar no adapter faster-whisper compatível, exigindo CUDA; decoder online é novo. |
| Capacidade / transações | `backend/shared/engines/capacity.py:LocalGpu`, `Binding`, `VramUse`; `backend/shared/engines/ledger.py:run_txn` | Reutilizar aritmética e helper transacional; transições de sessão têm semântica própria. |
| Seleção na UI | `frontend/components/projects/upload-location-fields.tsx:UploadLocationFields`, comboboxes e `projectsApi` | Reutilizar seleção de projeto/pasta. |
| Legendas / resultado na UI | `frontend/components/job/live-transcript.tsx:LiveTranscriptView`; `frontend/components/job/result-views.tsx:TranscriptView`; `jobsApi.getResult/getTranscriptFile` | Adaptar apresentação para parcial substituível e render imediato; manter resultado/downloads. Hook WS e captura são novos. |
| Benchmark GPU | `backend/workers/engines/heartbeat.py:detect_gpu`; `backend/workers/engines/benchmark.py:gpu_memory`, `local_vram_guard` | Reutilizar medição e adaptar guarda para footprint live medido; replay 1× e métricas de legenda/WER são novos. |

`shared/engines/dispatch.py:place_now` já faz admissão imediata, mas cria
`vision_request` e pode devolver `today` para uma fila cheia. `ledger.mark_lost`,
`settle_succeeded` e o sweeper de arquivos admitem retry ou resultado tardio. Esses
comportamentos não atendem live: reaproveitar padrões/helpers, sem chamar esses fluxos
nem copiar todo o subsistema. A live recusa falta de vaga e termina uma conexão perdida.
O heartbeat existente em `shared/engines/liveness.py` mede presença de worker,
**não capacidade nem modelo aquecido**; readiness, ticket e lease da conexão são extensões.

### 4.1 Fluxo e transporte

```text
Cliente ── POST autenticado /transcribe/live/sessions ──► API
        ◄── job_id + URL WebSocket + ticket de uso único ──

Cliente ⇄ WebSocket público ⇄ API ⇄ WebSocket interno ⇄ worker-live / GPU
            áudio PCM →             modelo residente      → eventos de legenda

finish → decodificar cauda → formatos finais → Redis / MinIO / Elasticsearch
       → atualizar job no MySQL → session.completed → liberar capacidade
```

WebSocket permite enviar áudio e receber legendas pela mesma conexão no navegador.
A API faz autenticação e controle da sessão; a inferência fica em um processo separado,
sem bloquear o event loop da API. O transporte interno começa também com WebSocket,
para usar um protocolo só. gRPC bidirecional poderá substituí-lo se uma medição justificar
a dependência; não é um requisito para obter baixa latência.

### 4.2 API e admissão

| Método | Rota proposta | Autenticação | Uso |
|---|---|---|---|
| POST | `/transcribe/live/sessions` | JWT ou API key | Validar localização, reservar vaga e criar sessão/job. |
| GET | `/transcribe/live/sessions/{job_id}` | JWT ou API key, dono do job no MySQL | Consultar estado, duração recebida e motivo de término. |
| DELETE | `/transcribe/live/sessions/{job_id}` | JWT ou API key, dono do job no MySQL | Cancelar de forma idempotente; preservar registro do job cancelado. |
| WS | `/transcribe/live/sessions/{job_id}/stream` | Ticket enviado no primeiro frame JSON | Enviar áudio e receber eventos. |

Exemplo de criação, sem exigir mudanças nos headers dos clientes existentes:

```jsonc
// POST /transcribe/live/sessions — application/json
{
  "project": "Reuniões",
  "folder": "Equipe",
  "name": "Reunião ao vivo",
  "tags": ["live"],
  "language": "pt",
  "audio": {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1}
}

// 201 Created; a vaga aguarda conexão por até 60 s
{
  "job_id": "uuid",
  "status": "pending",
  "ws_url": "wss://api.exemplo/transcribe/live/sessions/uuid/stream",
  "ticket": "<opaco, aleatório, uso único>",
  "ticket_expires_in": 60,
  "audio": {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1},
  "chunk_ms": 200,
  "max_duration_seconds": 1800
}
```

Também são aceitos `project_id` / `folder_id` em vez dos nomes, com as exclusões e
normalização existentes; `tags` é uma lista. O backend/modelo é escolhido pelo servidor,
não pelo cliente. PT-BR é o idioma de aceitação da fase 1; outros idiomas e autodetecção
precisam de validação adicional.

Antes de reservar capacidade, a API valida o request, autenticação e plano de localização
com os helpers existentes. Depois reserva atomicamente uma vaga de worker pronto,
resolve/cria a localização e grava job/sessão. Falha de gravação libera a reserva.
Falha depois do commit deixa o job em estado terminal e libera a reserva. Uma criação
cuja resposta se perde expira em 60 s; repetir o POST pode criar outra sessão, por isso
o cliente não faz retry automático dessa criação.

Erros de criação: `401` credencial inválida; `404` localização alheia/inexistente;
`422` localização, idioma, tags ou formato inválido; `503 LIVE_DISABLED`,
`LIVE_NOT_READY` ou `LIVE_CAPACITY_FULL`, com `Retry-After`.

### 4.3 Autenticação WebSocket

O ticket tem 32 bytes aleatórios, validade de 60 s, hash guardado no Redis e vínculo
com job, usuário, worker e geração da reserva. Não é JWT nem API key e não entra na URL.
Resposta de criação usa `Cache-Control: no-store`.
O navegador usa sua autenticação normal no POST e envia o ticket no primeiro frame:

```json
{"type":"authenticate","protocol":1,"ticket":"<ticket>"}
```

A conexão pode ser aceita para ler esse frame, mas tem prazo de 5 s e limite de 8 KiB
até autenticar; não encaminha áudio nem inicia inferência antes disso. Consumo do ticket
é atômico e de uso único. A API reconfirma job/dono/estado no MySQL antes de encaminhar.
Ticket repetido, vencido ou de outro job fecha com `4401`; job removido ou encerrado,
com `4404`. A vaga só admite uma conexão. A sessão começa após `session.ready`.

Em produção usa WSS, origem do navegador em allowlist e limite de conexões de handshake.
Clientes nativos sem `Origin` usam o mesmo ticket. Tokens, frames de áudio e texto não
entram nos logs. O serviço interno não publica porta no host e exige credencial própria
da API, além da reserva válida; essa credencial não é entregue ao navegador.

### 4.4 Áudio, eventos e controle de fluxo

O protocolo 1 recebe PCM mono, signed 16-bit little-endian, 16 kHz. O cliente faz a
conversão da captura; MP3/WebM não são enviados diretamente ao socket. Um bloco normal
de 200 ms contém 3.200 amostras / 6.400 bytes de áudio. O último bloco pode ser menor.
O adapter pode resamplear para a taxa interna do modelo, preservando a linha do tempo.

Cada frame binário tem cabeçalho de 12 bytes, little-endian: `seq: uint32`, começando
em 0, e `offset_samples: uint64`, começando em 0; o restante são as amostras PCM.
O servidor verifica sequência consecutiva, offset cumulativo e tamanho par do PCM.
Aceita blocos de até 500 ms (16.000 bytes de PCM), limita frames por segundo e conta
duração pelas amostras recebidas. Incompatibilidade fecha com `4400`.
O limite inicial é 20 frames de áudio/s por sessão, com burst de até 10; o cliente
normal envia 5/s. Frames de controle têm limites próprios, sem consumir esse orçamento.

Os eventos JSON têm `event_seq` crescente na conexão. Exemplo ilustrativo:

```jsonc
{"type":"session.ready","event_seq":1,"job_id":"uuid","backend":"whisper","model":"turbo"}
{"type":"transcript.partial","event_seq":2,"utterance_id":1,"revision":1,"text":"Vamos iniciar"}
{"type":"transcript.partial","event_seq":3,"utterance_id":1,"revision":2,"text":"Vamos iniciar a reunião."}
{"type":"transcript.final","event_seq":4,"segment_id":0,"utterance_id":1,"start":0.6,"end":2.1,"text":"Vamos iniciar a reunião."}
{"type":"session.completed","event_seq":5,"job_id":"uuid","result_url":"/jobs/uuid/result"}
```

Uma parcial substitui a revisão anterior do mesmo `utterance_id`; não é concatenada.
Um final confirma o segmento e remove a parcial correspondente. Finais usam IDs únicos,
timestamps na fonte e não são reescritos. O adapter mantém contexto limitado e confirma
apenas texto seguro; recortes independentes sem sobreposição/contexto não são aceitos.
Se um backend fornece somente texto confirmado, pode omitir eventos parciais.

O cliente envia `{"type":"finish","last_seq":1199}` ao terminar o áudio, e continua
lendo até o terminal. O servidor verifica que recebeu essa sequência, processa a cauda
e persiste o resultado. `{"type":"cancel"}` equivale ao DELETE da sessão. Fechar o
socket sem `finish` é interrupção, não sucesso. O limite total é 30 min; o servidor
avisa antes e solicita término; áudio além do limite é rejeitado explicitamente.

Buffers são limitados a 2 s de áudio recebido ainda não processado; o loop de recepção
continua separado da inferência. Não há fila Celery por bloco. Saída também tem fila
limitada. Consumidor lento ou backlog acima do limite encerra com evento `session.error`
(`LIVE_BACKPRESSURE`) e código `4429`, em vez de acumular atraso ou perder áudio.
Aplicar esse limite ao canal interno é obrigatório: controle de fluxo em um hop não
autoriza buffers ilimitados no outro. Ping não substitui áudio; 20 s sem novos frames
de áudio encerra por inatividade, enquanto frames de silêncio preservam a sessão.

### 4.5 Worker, capacidade e decoder

Novo serviço opt-in `worker-live`, um processo com modelo pré-carregado e aquecido antes
de ficar pronto. Default inicial: uma sessão simultânea; decoder/buffer/VAD separados
por sessão. O loop de inferência usa executor dedicado, sem bloquear recepção/envio.
Não há fallback silencioso para CPU. Sem CUDA ou sem memória suficiente, o serviço
fica indisponível e informa o motivo.

O piloto começa com faster-whisper `turbo` via uma política online de confirmação,
preferencialmente adapter do WhisperLiveKit, fixando versões/commits antes de adicionar
dependências. Comparar LocalAgreement/SimulStreaming e Voxtral Mini Realtime 4B com o
mesmo cliente e áudio; a promoção de backend depende do benchmark, não de reputação.
O adapter normaliza eventos e timestamps para o schema de resultado existente e não
expõe um servidor do pacote com autenticação diferente da API. Para faster-whisper
compatível, reutiliza `whisper_core.load_model` e a resolução de dispositivo/compute
type existentes, aquece uma vez e mantém estado de decoder separado por sessão.
Resolução para CPU torna live indisponível; não usar `transcribe_with_gpu_fallback`.
`whisper_core.transcribe` recebe arquivo completo: seu generator não substitui o
decoder online. Loader próprio para Voxtral/SimulStreaming só entra se o backend
escolhido exigir outra interface; não reescrever factory, resolver ou loader por padrão.

A RTX 5060 Ti de 16 GB já é compartilhada com outros workers. Criar outro serviço não
cria uma GPU adicional nem garante prioridade. O piloto roda em janela controlada ou
GPU de teste; ativação em produção só ocorre após definir capacidade reservada e medir
a concorrência real com workloads de arquivo/visão. Pausar workers de produção não é
efeito implícito de iniciar a live ou de executar o cliente de benchmark.
Antes de produção, incluir o footprint residente live medido na soma de usos da GPU,
reutilizando `LocalGpu`, `Binding` e `VramUse`/a aritmética de `capacity.py`; considerar
também os modelos residentes de arquivos/visão e a reserva de VRAM. `LIVE_MAX_SESSIONS`
não substitui essa conta. O perfil operacional deve tornar o consumo live explícito
no mesmo inventário usado pelo admin. O registro atual de features pressupõe lane
Celery: integração nesse cadastro exige adaptação, não fingir que live já é suportada.

### 4.6 Estado, MySQL, Redis e persistência

O job continua `MAIN`, `source_type=audio`, com usuário/projeto/pasta/tags nas estruturas
existentes. Não há checksum para deduplicar uma captura. `filename` é descritivo,
com extensão `.pcm`, `mime_type=application/octet-stream`, encoding na metadata e os
caminhos do áudio no MinIO ficam nulos.

Uma nova tabela `live_sessions`, PK/FK `job_id → jobs.id ON DELETE CASCADE`, guarda:
`state` (varchar), `backend`, `model`, `language`, `sample_rate`, `worker_id`,
`generation` (bigint), `audio_samples` (bigint), `created_at`, `connected_at`,
`last_audio_at`, `ended_at` e `error_code` (nullable). Não guarda tickets nem áudio.
O dono é sempre determinado por join com `jobs.user_id`, não pelo cache. A migration
cria só essa tabela e índices de `(state, last_audio_at)`; downgrade exige sessões
encerradas e remove só a tabela. Os jobs/resultados permanecem.
A tabela guarda atributos da conexão que `Job` não possui; não duplica usuário,
projeto, pasta, tags nem o status final do job. `JobDispatch` modela backlog/retry e
não substitui o estado de uma conexão que não pode ser reexecutada.
Em banco que já contém `jobs`, `init_db/create_all` deve excluir essa nova tabela da
criação automática: o DDL é aplicado pelo procedimento de migração aprovado. Banco
novo de desenvolvimento pode criá-la no bootstrap. Com a flag desligada, ausência
da tabela não quebra o fluxo de arquivos; com a flag ligada, bloqueia admissão de
live (`503 LIVE_NOT_READY`). Testar ambos os casos antes do rollout.

```text
created → streaming → finalizing → completed
    └─────────┴───────────┴──────→ failed / cancelled
```

`created` mapeia para job `PENDING`; `streaming/finalizing`, `PROCESSING`; terminais,
para os estados existentes. Durante live não se inventa percentual de conclusão:
mostrar duração recebida e atraso estimado. A duração e atividade são gravadas em lote
no MySQL a cada 5 s; nenhuma transação fica aberta durante a sessão.

| Chave Redis proposta/existente | Conteúdo e ciclo de vida |
|---|---|
| `live:worker:{id}` | Heartbeat/prontidão/capacidade; tick 2 s, TTL 10 s. |
| `live:lease:{job_id}` | Worker/geração/estado da reserva; TTL 45 s, renovação a cada 5 s; reserva inicial de conexão até 60 s. |
| `live:ticket:{hash}` | Vínculo do ticket; TTL 60 s e consumo atômico. |
| `job:{id}:transcript:partial` | Reaproveitar a lista de **segmentos confirmados**, para o endpoint parcial existente; TTL 24 h, até resultado final/cancelamento. |
| `job:{id}:status` / `job:{id}:result` | Usar os TTLs e formato do fluxo de transcrição existente. |

A reserva inicial e a lease ativa têm fases distintas; conectar consome a reserva e
instala a lease de 45 s. Reserva de vaga, renovação e liberação são atômicas e verificam
worker/geração. Um sweeper consulta `live_sessions` e leases: reserva vencida cancela;
lease perdida ou worker morto falha a sessão em até 60 s. API reiniciada sem conexão
válida também interrompe a sessão; não recria stream automaticamente.
Reservas órfãs também expiram e liberam capacidade quando a API cai antes de gravar
`live_sessions`: a admissão e a coleta não dependem só dessa tabela nem de um contador
que sobreviva à lease. Testar crash entre reserva, commit e emissão do ticket.

Somente uma geração pode escrever segmentos ou finalizar. Antes do commit final,
revalidar job existente, sessão `finalizing` e geração ativa; terminais não voltam atrás.
Os hooks de DELETE do job e cancelamento revogam a lease e sinalizam o decoder. Se o
processo estiver dentro de uma chamada de inferência, cancela na próxima saída do
decoder; o fencing impede publicação tardia nesse intervalo.

Conclusão normal reutiliza os cinco formatos de transcrição: Markdown no
Redis/Elasticsearch e JSON, TXT, VTT e SRT no Redis/MinIO, como no contrato atual.
Não acrescentar um armazenamento/download de Markdown paralelo. Extrair/adaptar
`finish_transcription` para receber metadata da entrada sem exigir `file_path.stat()`;
reutilizar os formatters e operações de armazenamento. O helper atual tolera falhas
de MinIO/commit e mesmo assim publica `completed`: live exige uma opção de finalização
estrita que confira cada escrita e o commit, preservando a política atual de arquivos.
Na live, falha de indexação do Markdown também impede sucesso; retry limitado durante
finalização e, se esgotado, `failed` com motivo, sem perder os artefatos já persistidos.
A adaptação não exige arquivo de origem para fazer cleanup. Metadata inclui
`input_mode=live`, idioma, modelo, dispositivo, duração por amostras e versão do protocolo.
`session.completed` só sai após armazenamento durável dos formatos e commit do job.
`transcript_object_name` hoje usa nomes por job, sem geração: estendê-lo com geração
opcional para os artefatos live em `transcripts/{job_id}/live/{generation}/`, conservando
os nomes atuais de arquivos. A sessão concluída no MySQL seleciona a geração publicada;
adaptar o leitor existente, sem promover uma escrita atrasada para o resultado público.
Se cancelamento/exclusão/perda de geração vencer enquanto os objetos são escritos,
o commit final é recusado e a finalização remove os objetos que acabou de escrever;
esse cleanup é idempotente e limitado aos artefatos daquela geração. A corrida com
DELETE precisa de teste, inclusive quando DELETE já fez seu cleanup antes da escrita.
Resultado parcial após interrupção não é apresentado como transcrição completa: job
`failed`, motivo visível, segmentos confirmados consultáveis pelo endpoint parcial por
seu TTL. Cancelamento descarta os parciais. DELETE elimina resultados como hoje.

`get_job_result` hoje exige status Redis antes de consultar os objetos duráveis.
Para live, adaptar o mesmo endpoint para reconstruir autorização/estado/metadata
do job e da sessão concluída no MySQL quando o cache expirar, e ler os formatos da
geração publicada. Não criar endpoint de resultado paralelo nem alterar o fallback
de autorização para permitir jobs sem linha própria. Cobrir expiração de status e
resultado; sessão excluída ou não concluída não habilita leitura desses artefatos.

### 4.7 Frontend e operação

Adicionar entrada **Transcrever ao vivo** com seleção de projeto/pasta, idioma e botão
de captura. A captura começa depois de `session.ready`; modelo/aquecimento/vaga têm
estado visível. Mostrar parcial imediatamente, substituir revisões e fixar confirmados,
sem animação que adie texto já recebido. Botão **Finalizar** envia `finish` e espera o
resultado; **Cancelar** encerra; queda de conexão mostra interrupção e oferece nova sessão.
O navegador usa AudioWorklet/resampler e frames binários. Testar também mudanças de aba,
negação de microfone e captura interrompida; acesso a microfone requer contexto seguro.

Reutilizar `UploadLocationFields` e os comboboxes atuais. Adaptar `LiveTranscriptView`
para receber segmentos confirmados/provisórios e render imediato no modo live, sem
usar `useLiveTranscript`/`useReveal` para a captura. Ao concluir, reutilizar
`TranscriptView`, a página do job e seus downloads existentes.

Configurações propostas: `LIVE_TRANSCRIPTION_ENABLED=false`, `LIVE_BACKEND=whisper`,
`LIVE_MAX_SESSIONS=1`, `LIVE_MAX_DURATION_SECONDS=1800`,
`LIVE_MAX_AUDIO_BACKLOG_SECONDS=2`, URL privada do worker e credencial interna obrigatória
quando habilitado. Modelo/dispositivo/capacidade são do servidor e entram no relatório.
Readiness verifica pesos, warmup e decoder; alteração de modelo exige reinício controlado.
O baseline usa `WHISPER_MODEL=turbo` e a resolução `WHISPER_DEVICE`/`DEVICE` existentes
no ambiente do worker-live. Não criar `LIVE_MODEL` como segundo knob de Whisper.
Modelo/pesos de outro backend são fixados no perfil escolhido pelo benchmark.

## 5. Alternativas consideradas

| Alternativa | Decisão |
|---|---|
| Polling REST atual | Continua para arquivos; não oferece entrada contínua nem entrega imediata. |
| SSE | Adequado para receber texto de um job de arquivo; áudio precisa de outro canal. Fora desta entrega. |
| gRPC no navegador | gRPC-Web oficial não tem streaming bidirecional; exigiria outra solução/proxy. |
| gRPC interno desde o início | Viável, mas adiciona geração de contratos e dependências sem ganho local medido. |
| WebRTC | Útil se houver chamada de mídia; captura/transporte de vídeo não fazem parte deste pedido. |
| Um job Celery por bloco | Fila, contexto fragmentado, reordenação e overhead incompatíveis com a sessão. |
| Whisper em recortes independentes | Pode cortar palavras e repetir texto; exigir política de contexto/confirmação. |
| Serviço de ASR pago | Pode servir no futuro; piloto usa processamento local e não envia o áudio a terceiros. |

## 6. Impactos

- **Compatibilidade:** endpoints de arquivos e formatos finais preservados. Novas rotas
  e tabela são opt-in; não mudar a spec 0004 implementada nem sua migração.
- **Performance:** uma sessão mantém contexto limitado/modelo residente e consome GPU
  mesmo sem gerar um arquivo. Memória, backlog e concorrência são limites de admissão.
- **Segurança:** propriedade vem do MySQL; tickets de uso único, autorização interna,
  buffers limitados e cancelamento de exclusões impedem reutilização/acesso alheio.
- **Operação:** serviço novo, heartbeat, leases, sweeper e métricas de latência/RTF;
  nenhuma migração ou troca de código em produção é executada por esta spec.
- **Custo/retenção:** sem API paga e sem persistir áudio; formatos finais seguem os
  buckets e políticas existentes. Fixtures locais ficam fora do Git.

## 7. Plano de testes e benchmark

### 7.1 Áudio local disponível

Em 2026-10-05 foi localizado e validado com ffprobe um clipe usado nos testes anteriores,
com referência faster-whisper indicando idioma `pt`. Uma cópia está preservada em:

```text
tmp/bench/live-transcribe/clip-pt-240s.mp3
tmp/bench/live-transcribe/clip-pt-240s.pcm
tmp/bench/live-transcribe/clip-pt-240s.reference-machine.json
tmp/bench/live-transcribe/manifest.json
```

PCM: **240,0 s, 16 kHz, mono, s16le, 3.840.000 amostras / 7.680.000 bytes**.
A referência contém 85 segmentos e foi gerada por máquina; serve para comparação de
regressão, **não é ground truth para WER**. O manifest registra hashes/bytes. Esses
arquivos são locais, ignorados pelo Git e podem não existir em outro checkout; o runner
deve exigir fixture válida e falhar com instrução clara quando faltar. Não baixar amostra
nem executar inferência paga ou alterar workers de produção automaticamente.

### 7.2 Replay que realmente simula captura

Criar `scripts/benchmark_live_transcribe.py` com `--audio`, `--api-url`, `--project`
e credencial pelo ambiente; nunca no argumento impresso/log. O script é uma entrega
futura desta spec. Ele lê/decode o áudio no cliente, inicia uma sessão e envia PCM em
blocos de 200 ms, enquanto outra coroutine recebe todos os eventos.
Reaproveitar a medição de GPU e a aritmética de guarda do benchmark atual, passando
o footprint live medido em vez de assumir os 3 GB do default `transcription`.
O comando batch existente não valida streaming; não chamar seus caminhos
`--apply`/`--pause-local` nem o runner que reserva uso remoto para executar este replay.

Usar deadlines cumulativos de relógio monotônico: o bloco só pode ser enviado quando
**sua última amostra** estaria disponível (`t0 + (offset + n_samples)/sample_rate`).
Não usar sleep fixo somado ao tempo de processamento nem mandar todo o áudio em burst.
Se o cliente atrasar, registrar o atraso; nunca mascará-lo com rajadas de catch-up.
O receptor continua lendo durante envio, silêncio, `finish` e armazenamento final.

Além do clipe completo, testar recortes de 10/30/60 s, silêncio inicial/final, última
palavra sem pausa, contexto atravessando blocos, interrupção e backpressure. O clipe
completo demora pelo menos 4 min por replay a 1×; benchmark batch rápido não substitui isso.

### 7.3 Métricas e portão de seleção

Medir separadamente: criação/readiness, primeira legenda desde o início da fala,
atraso das parciais, atraso de segmentos confirmados, finalização após EOF, RTF
(tempo de inferência / duração de áudio), pico de VRAM/RAM, backlog e texto perdido/duplicado.
Usar relógio monotônico local por etapa. No cliente, comparar envio/render com a linha
do tempo do replay; não subtrair timestamps monotônicos de máquinas distintas.
Datas UTC servem para correlação, não para medir diferenças sem sincronização.

O relatório distingue atraso estimado com timestamps do próprio modelo de atraso
verificado com timestamps de referência. Para o portão de qualidade/latência, revisar
transcrição e alinhar manualmente uma amostra de pelo menos 20 trechos; congelar o
arquivo de referência com hash. Registrar WER contra esse texto revisado e alterações
do conteúdo confirmado; comparar apenas o mesmo corpus/normalização.

**Metas iniciais, ainda não comprovadas:** em uma sessão aquecida, primeira parcial
até 1,5 s após início da fala, atraso confirmado p95 ≤ 3 s, RTF ≤ 0,8, backlog abaixo
de 2 s, sem palavras confirmadas duplicadas/perdidas e pelo menos 20% de margem de VRAM
no perfil de GPU reservado. Backend sem parciais é comparado por primeira legenda
confirmada e atraso confirmado. WER não pode piorar mais de 2 pontos percentuais em
relação ao baseline Whisper offline no mesmo corpus revisado. Reportar resultados
ruins; não relaxar limites automaticamente para fazer um backend passar.

Comparar Whisper turbo com política online e Voxtral Mini Realtime na RTX 5060 Ti de
16 GB. Começar o candidato Voxtral com atraso configurado de 480 ms; isso é lookahead
do modelo, não promessa de latência fim a fim. Nos números publicados do fornecedor,
português tem WER 5,03% a 480 ms e 10,01% a 160 ms em FLEURS; esse corpus não substitui
o áudio local. Antes da liberação, executar pelo menos 3 replays completos aquecidos
por candidato e 1 início frio, registrando versões/configuração/hashes. Depois repetir
o candidato escolhido com a concorrência de produção planejada; falta de margem/SLO
mantém a feature desabilitada naquele perfil.

### 7.4 Automação

- **Unitários:** framing/offset/seq, tamanho e duração; revisões/finais; confirmação
  sem duplicação; tail flush; timestamps preservados; estado terminal/fencing.
- **Integração com decoder fake:** tickets e propriedade, key vinculada/JWT, capacidade
  atômica, corrida finish/cancel/delete, sweeper após restart, buffers limitados,
  persistência dos cinco formatos, erro de armazenamento/commit antes do terminal,
  geração inválida sem publicação, reserva órfã antes do commit/ticket e leitura após
  expiração do cache. Reutilizar os
  casos relevantes de `test_finish_transcription.py`, `test_transcript_formats.py`
  e `test_transcript_result_endpoint.py`, acrescentando cenários live.
- **Integração GPU opt-in:** replay real 1×, dois clients tentando a última vaga,
  privacidade de contexto, quedas e relatório de desempenho/qualidade. Serviço e
  banco/Redis de teste isolados; não usar o banco nem o worker live de produção.
- **Frontend:** protocolo real com decoder fake, parcial substituída sem repetição,
  finalização/cancelamento, erro de microfone, socket interrompido e resultado final.
- **Exploratório:** revisar texto/timestamps do corpus e captura de microfone em
  navegadores alvo; os replays e cálculo das métricas continuam automatizados.

## 8. Plano de implementação

- [ ] Adapter online e harness de replay com áudio local, isolados dos serviços atuais;
      registrar baseline, candidato Voxtral e referência revisada.
- [ ] Fixar backend/versões e perfil de GPU com base no portão da seção 7.
- [ ] Aplicar o mapa de reuso da seção 4.0; extrair somente helpers necessários,
      com regressão dos contratos de arquivo preservados.
- [ ] Migration enxuta `live_sessions`, reservas/tickets/fencing/sweeper e `worker-live`,
      sem replicar o dispatcher/ledger inteiro nem seus retries de arquivo.
- [ ] API/WS usando auth/localização/tags existentes, cancelamento e adaptação da
      pipeline estrita, leitura após TTL e revogação no DELETE existente.
- [ ] Captura/hook WS e adaptação da view de legendas, reutilizando projeto/pasta,
      resultado final e downloads; não criar outra tela de resultado.
- [ ] Docs de uso, observabilidade, teste de concorrência, runbook e rollout opt-in.

Rollout: criar a tabela pelo procedimento de migração aprovado, manter a flag desligada,
subir/aquecer o worker e verificar readiness; ativar só depois do benchmark e teste de
cancelamento/restart. Rollback: bloquear novas sessões, drenar/cancelar as ativas e
desligar o serviço; manter tabela e resultados para auditoria. Não reiniciar um worker
com sessão ativa como forma normal de mudar o modelo.

## 9. Questões em aberto e decisões

- [x] É saída progressiva de arquivo ou entrada ao vivo? → **Decisão (2026-10-05):**
  esta spec cobre entrada contínua; o fluxo de arquivo existente permanece separado.
- [x] RPC é obrigatório? → **Decisão (2026-10-05):** WebSocket público e interno no
  primeiro protocolo; gRPC interno só com benefício medido.
- [x] Há áudio local? → **Verificado (2026-10-05):** clipe PT de 240 s e PCM preservados.
- [ ] Backend final, versões e perfil de GPU? → Resolver pelo portão de benchmark;
  Whisper turbo é baseline do piloto, Voxtral Realtime é candidato.
- [ ] Disponibilidade/capacidade de GPU para uso contínuo ao lado dos workers atuais?
  → Bloqueia liberação em produção, não a implementação e o benchmark isolado.
- [ ] Representação do footprint live no inventário/admin da GPU compartilhada?
  → Definir antes de produção; reutilizar aritmética de capacidade, sem registrar
  uma feature com lane Celery fictícia nem ocultar memória residente.
- [ ] Referência humana para WER/timestamps? → Revisar o corpus antes da seleção;
  a referência atual é gerada por máquina.

## Referências

- [SSE: canal de eventos do servidor ao cliente (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events).
- [WebSocket: comunicação bidirecional no navegador (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API).
- [gRPC: tipos de streaming](https://grpc.io/docs/what-is-grpc/core-concepts/) e
  [limites de streaming do gRPC-Web oficial](https://github.com/grpc/grpc-web#streaming-support).
- [WhisperLiveKit: API de áudio ao vivo e parciais](https://github.com/QuentinFuxa/WhisperLiveKit/blob/main/docs/API.md)
  e [backends/políticas online](https://github.com/QuentinFuxa/WhisperLiveKit).
- [Voxtral Mini Realtime: delay configurável e benchmark por idioma](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602).
