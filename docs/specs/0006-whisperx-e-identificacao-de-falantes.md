# 0006 — WhisperX e identificação de falantes

| | |
|---|---|
| **Status** | Aprovada para implementação pelo usuário; implementação e qualificação em andamento |
| **Revisão técnica** | Subagent `review_whisperx_spec`, 2026-10-05: revisão inicial e nova revisão online concluídas; achados corrigidos e rechecados, sem bloqueios na proposta |
| **Autor** | Codex, a pedido de Geda Valentim |
| **Criada em** | 2026-10-05 |
| **Atualizada em** | 2026-10-05 |
| **Relacionadas** | 0002 (dispositivo), 0003 (Compute/Modal), 0005 (live) |
| **Substituída por** | — |

## 1. Problema

O Ingestify transcreve áudio/vídeo, mas não informa quem falou cada trecho.
Hoje o provider padrão é `faster-whisper`; local, Modal e live têm caminhos de
execução diferentes. Trocar apenas a factory deixa Modal e live no motor antigo.
Além disso, serializadores existentes descartam campos novos de falante.

WhisperX usa faster-whisper/CTranslate2 para reconhecimento, alinhamento de
palavras e pyannote para diarização. A migração troca a pipeline de aplicação;
faster-whisper continua como dependência interna. `SPEAKER_00` representa uma
voz dentro de um job, não o nome de uma pessoa nem identidade entre gravações.

### Evidência disponível

Teste isolado em 2026-10-05: WhisperX 3.8.6, pyannote.audio 4.0.7, PyTorch e
torchaudio 2.8.0 CPU, transformers 4.57.3; turbo/int8, beam 1, batch 1, quota
2 CPUs. O WAV público de 30 s do [tutorial pyannote](https://github.com/pyannote/pyannote-audio/tree/b749285c5cdd4636b2edc7f766f1352c8dde9369/tutorials/assets)
tem duas pessoas anotadas e 1,89 s de sobreposição. Transcrição: 80 palavras em
7,414 s; alinhamento: 80 palavras com timestamps em 3,952 s; pico RSS 2.595 MiB.
Tempos de inferência excluem carregamento/download de modelos. Uma execução
curta em inglês/CPU não valida GPU, PT-BR, arquivos longos ou streaming.

**A diarização não executou:** `DiarizationPipeline` recebeu HTTP 401
`GatedRepoError` ao carregar `pyannote/speaker-diarization-community-1`.
Não há resultado de contagem de falantes, DER ou qualidade do WhisperX ainda.
Artefatos locais: `/tmp/ingestify-whisperx-validation/{summary.json,run_probe.py,requirements.lock}`;
WAV SHA256 `c319b4abca767b124e41432d364fd7df006cb26bb79d09326c487d606a134e6e`.
O [teste anterior](../benchmarks/speaker-detection-2026-10-05.md) com Resemblyzer
não mede a qualidade do pyannote/WhisperX.

## 2. Objetivo

Tornar WhisperX o provider padrão de transcrição de arquivos local e Modal,
com identificação automática de falantes nos resultados e downloads, preservando
os contratos e a operação existentes. Cobrir a live em uma segunda fatia explícita,
sem tratar WhisperX de arquivo como substituto direto do decoder online.

**Decisão do usuário (2026-10-05): identificar falantes durante a captura.**
A live exibe texto sem esperar a identificação; rótulos chegam por eventos próprios,
com indicação provisória e correções limitadas. A migração de todos os usos só
termina após validar essa segunda fatia. Identificação online é um componente
adicional: WhisperX continua sendo a pipeline de arquivos e fornece a base ASR;
não há evidência de que sua diarização de arquivo atenda streaming sozinha.

### Fora de escopo

- Reconhecer nomes reais, cadastrar biometria ou associar pessoas entre jobs.
- Identificar pessoas apenas por tom grave/agudo; separar fontes de áudio sobrepostas.
- Substituir providers explicitamente escolhidos `openai-api`/`openai-whisper`.
- Reprocessar automaticamente acervo antigo ou alterar resultados já concluídos.
- Recriar filas, motor Compute, autenticação, projetos, armazenamento ou transportes.

## 3. Critérios de aceitação

- [ ] Arquivo novo no provider padrão percorre WhisperX → alinhamento → diarização;
      local e Modal entregam o mesmo schema e a mesma semântica de opções.
- [ ] Quantidade de falantes é inferida quando não há limites informados; teste com
      duas pessoas não força `num_speakers=2` para alegar detecção automática.
- [ ] JSON, UI e os cinco formatos de saída exibem IDs coerentes dentro do job;
      ausências/ambiguidades não ganham um falante inventado.
- [ ] Resultados antigos sem campos novos continuam legíveis e disponíveis após TTL.
- [ ] Reenviar áudio pedindo diarização não reutiliza job antigo sem diarização.
- [ ] Progresso parcial, cancelamento, timeout, retry e fallback CPU preservam a
      semântica existente; falha de diarização solicitada não vira sucesso silencioso.
- [ ] Campos de falante sobrevivem ao protocolo Modal e à persistência JSON/MinIO.
- [ ] GPU/RAM, qualidade PT-BR e coexistência com live passam pelos gates da seção 7
      antes de mudar o padrão. O teste CPU atual não satisfaz esses gates.
- [ ] Na live, falantes aparecem durante a captura; texto/timestamps confirmados
      permanecem imutáveis. Correções de rótulo são versionadas e limitadas a uma
      janela recente; conclusão exige persistir o estado final da geração atual.
- [ ] Identificação online tem métricas de atraso, cobertura e erro próprias;
      esperar `finish` para emitir todos os falantes reprova o teste de streaming.

## 4. Solução proposta

### 4.1 Inventário do código existente e reaproveitamento

Levantamento em 2026-10-05 sobre `main` (`073291b`) e alterações locais presentes.
Caminhos são relativos à raiz. Estes são pontos de implementação, não código novo
já entregue por esta spec.

| Caminho / símbolo | Uso atual | Mudança necessária |
|---|---|---|
| `backend/api/routes.py:transcribe_audio` | `POST /transcribe`, upload, deduplicação e fila | Aceitar opções de diarização; persistir perfil efetivo antes do enqueue. |
| `backend/api/routes.py:upload_and_convert`, `convert_document`, `_enqueue_maybe_routed`, `backend/api/projects_api.py:find_duplicate_job` | Entradas multipart, descoberta de mídia, defaults substituídos no roteamento e dedupe por dono/projeto/checksum | Campos Form e normalizador comum; propagar snapshot também no caminho `today`; compartilhar classificação áudio/vídeo com o worker. |
| `backend/workers/tasks.py:_transcribe_audio`, `_divert_audio_to_backlog`, `_run_routed_transcription`, `process_conversion` | Arquivos locais e redirecionamento após detectar mídia | Propagar opções e progresso de fases; reutilizar tasks e guardas. |
| `backend/workers/audio/factory.py`, `base_transcriber.py`, `device.py` | Provider singleton/override, formatos e fallback GPU→CPU | Adicionar `WhisperXTranscriber` implementando `AudioTranscriber`; preservar isolamento por override. |
| `backend/workers/audio/faster_whisper_transcriber.py`, `backend/workers/engines/whisper_core.py` | Core compartilhado local/Modal; também carrega modelo da live | Manter caminho legado para rollback; extrair somente helpers realmente compartilháveis. |
| `backend/workers/audio/feature_extractor.py` | Espectrograma de memória limitada | Verificar compatibilidade real com o ASR do WhisperX; não presumir que o patch se aplica ao wrapper. |
| `backend/shared/engines/dispatch.py:TRANSCRIPTION_OPTIONS`, `DEFAULT_TRANSCRIPTION_OPTIONS` | Allowlist de backlog e defaults | Incluir perfil/opções normalizadas, sem tokens; preservar decisão entre tentativas. |
| `backend/workers/engines/modal_apps/{runner,whisper_app,protocol,files,image}.py` | Modelo residente remoto; protocolo 3 valida/reconstrói output; lista explícita de fontes | Core WhisperX comum sem importar settings/DB; protocolo versionado, campos novos, fontes e pesos no fingerprint. |
| `backend/workers/engines/{remote,adapters/modal,modal_deploy}.py` | Execução remota, parciais, validação, deploy | Negociação de capacidades/versão e erro explícito em engine antigo; manter orçamento/cancelamento. |
| `backend/workers/engines/pipeline.py:build_transcription_outputs`, `finish_transcription` | Serialização JSON seleciona só quatro campos; grava formatos e metadados | Preservar diarização e provenance; usar a pipeline existente para todas as saídas. |
| `backend/shared/transcripts.py`, `backend/api/routes.py:get_job_result`, `_transcript_response` | Object keys, formatos, leitura após TTL, owner checks | Mesmas rotas/buckets; leitura retrocompatível de schema 1 e 2. |
| `backend/shared/redis_client.py`, `tasks.py:_transcription_progress`, `modal_apps/runner.py` | Parciais de arquivos e progresso | Parciais sem speaker definitivo; estado de fase separado do contador temporal. |
| `backend/workers/live/{server,decoder}.py` | Modelo residente, LocalAgreement-2, contexto ~8 s, descarta PCM antigo | Adapter ASR e diarizador incremental sobre o mesmo relógio PCM; buffers limitados e estado por sessão em 4.7. |
| `backend/api/live_routes.py`, `backend/shared/live/{protocol,store,persistence,lifecycle,capacity}.py` | API recompõe resultado e fixa provider `faster-whisper`; leases/generation/persistência | Eventos de speaker versionados, capability online, provider real, limites e finalização ampliados. |
| `frontend/types/api.ts`, `components/job/{result-views,live-transcript}.tsx`, `lib/api.ts`, `hooks/use-live-capture.ts`, `app/live/page.tsx` | Resultados, downloads e captura | Speaker badges/legenda, estados de fase e leitura de resultados antigos; unificar as duas declarações `TranscriptSegment`. |
| `backend/shared/config.py`, `shared/device.py`, `shared/engines/features.py`, `frontend/types/compute.ts` | Default provider, seleção de dispositivo, footprint 3 GB e label Whisper | Novo default após gates; medir capacidade por pipeline e atualizar labels sem mudar feature `transcription`. |
| `backend/workers/engines/benchmark.py`, `scripts/benchmark_live_transcribe.py` | Benchmark carrega diretamente `whisper_core`; replay live | Benchmark medir a pipeline efetivamente selecionada, inclusive alinhamento/diarização. |
| `backend/requirements*.txt`, `docker/Dockerfile.worker`, `docker-compose{,.gpu,.live}.yml`, `modal_apps/requirements-whisper-modal.{in,lock}` | Imagem local Python 3.13 e pins específicos de live/Modal | Dependências separadas para áudio, lock por alvo CPU/CUDA e validação do build real. |
| `backend/tests/test_{audio_factory,whisper_core,whisper_device,device_whisper_guard,remote_live_captions,live_transcription}.py`, testes Modal/formatos | Contratos/regressões existentes | Estender fixtures e casos, mantendo as garantias atuais. |
| `.env.example`, `docs/GPU.md`, `docs/features/{engines,live-transcription}.md`, `frontend/app/docs/page.tsx`, `frontend/docs/doc2md_openapi.json` | Documentação/operação/contrato público | Atualizar junto de cada fatia entregue, sem declarar recurso atual nesta spec. |

### 4.2 Pipeline comum e migração de provider

```text
API + perfil efetivo → filas/Compute existentes → worker local ou Modal
  → WhisperX ASR → alinhamento → pyannote → associação/normalização
  → finish_transcription → formatos + MinIO/Redis/Elasticsearch + status SQL
```

Adicionar um core `backend/workers/engines/whisperx_core.py`, independente de
settings/DB/Celery, consumido pelo adapter `WhisperXTranscriber` e pelo runner
Modal. Reutilizar `AudioTranscriber`, formatos, resolução de dispositivo, guardas,
progresso e conclusão. Evitar copiar `tasks.py`, `pipeline.py` ou o protocolo live.
Os métodos auxiliares de metadados/formatos do transcriber atual devem ser extraídos
para helpers existentes/compartilhados quando necessário, sem herança que carregue
o modelo legado acidentalmente.

`AUDIO_TRANSCRIBER_PROVIDER=whisperx` torna-se padrão somente no cutover.
`WHISPER_MODEL` continua escolhendo os pesos ASR (inicialmente turbo); manter
`WHISPER_DEVICE` e `WHISPER_COMPUTE_TYPE`. Tipos de precisão CTranslate2 não são
aplicados cegamente aos modelos PyTorch. Registrar dispositivo e versão de cada
etapa. Fallback CPU mantém WhisperX e diarização, libera recursos CUDA e reinicia
a tentativa com parciais limpas; erro HF/idioma não é classificado como erro GPU.

Processar arquivos em lotes limitados, batch inicial 1. Cancelamento/deadline devem
ser checados entre lotes/etapas e antes da persistência. Para chamadas de biblioteca
não interrompíveis, utilizar o isolamento/timeout do worker e cancelamento remoto
existentes. A duração total tem que caber no deadline de transcrição, incluindo
alinhamento e diarização. Não usar a quantidade de segmentos como progresso linear.
Fases propostas no status: `transcribing`, `aligning`, `diarizing`, `saving`;
`transcribed_seconds` continua medindo apenas cobertura do áudio pelo ASR.

**Adapter de progresso é requisito verificável:** WhisperX 3.8.6 devolve a lista
de segmentos ao terminar; `progress_callback` recebe apenas percentual por
quantidade de segmentos. Não é o callback Ingestify `(segundos, total, segmento)`.
Criar adapter estreito sobre o iterador de lotes da versão fixada, com testes
contra a biblioteca real, emitindo texto e offsets originais à medida que cada
lote termina. Reusar o flush Redis/local/Modal existente; não copiar toda a
pipeline upstream nem emitir parciais falsas a partir de percentuais. Esse adapter
e sua interrupção entre lotes são gate anterior à migração local/Modal.

As opções `beam_size` e `temperature` existentes precisam de tradução explícita
para `load_model(asr_options=...)`, incluindo `temperature` → `temperatures`.
Elas não são argumentos de `WhisperX.transcribe`. Wrapper/tokenizer/options devem
ser isolados por execução em torno dos pesos residentes, sem mutação concorrente
nem vazamento entre jobs. Testar jobs sucessivos e overrides com opções diferentes.

### 4.3 Entrada, defaults, erros e perfil durável

`POST /transcribe`, `/upload` e `/convert` ganham campos multipart reais,
validados por um normalizador comum. `ConversionOptions` e `ConvertRequest` são
importados, mas não participam das assinaturas atuais: alterá-los isoladamente
não expõe parâmetros. `/convert` hoje enfileira `options={}` e
`_enqueue_maybe_routed` substitui opções pelos defaults; ambos devem encaminhar
o snapshot normalizado também quando o dispatcher devolve `today`. Compartilhar
classificação de áudio/vídeo entre API e worker: o helper atual de roteamento
considera apenas extensões de áudio e pode deixar MP4 no caminho de documentos.
Para documentos, rejeitar opções de diarização
explicitamente ativadas com 422 quando o tipo for conhecido; descoberta tardia
incompatível falha o job com erro claro.

| Campo | Regra |
|---|---|
| `diarize` | Booleano opcional; omitido usa default do servidor para novos jobs WhisperX (true após cutover). |
| `min_speakers`, `max_speakers` | Inteiros opcionais 1–20; min ≤ max; só aceitos com diarização efetiva. Omitidos permitem inferência automática. |
| `include_word_timestamps` | Preserva default false de exposição; alinhamento interno ocorre mesmo assim para atribuir falantes. |
| `transcriber_provider` | Override interno já consumido por tasks/factory; não é campo público das rotas atuais e não será exposto por esta spec. Preservar seu isolamento em chamadas internas. |

Providers legados configurados e overrides internos com `diarize` omitido
conservam transcrição sem diarização. Pedido explícito de diarização em provider
sem suporte é 422 antes de enqueue quando conhecido, ou erro de capacidade
explícito na descoberta tardia. Contagem livre que retornar mais de 20 falantes
falha com `SPEAKER_LIMIT_EXCEEDED`, tanto local quanto Modal; não truncar catálogo
nem forçar max=20 silenciosamente para fazer o teste passar.
Configuração padrão indisponível retorna 503 `DIARIZATION_NOT_READY` no caminho
que puder validar antes do enqueue. Falha posterior de download/acesso/modelo,
idioma sem alinhador ou inferência termina o job com código específico:
`DIARIZATION_MODEL_UNAVAILABLE`, `ALIGNMENT_UNSUPPORTED_LANGUAGE`,
`DIARIZATION_FAILED`. Não marcar `completed` sem cumprir `diarize=true`.
ASR sem diarização permanece disponível por `diarize=false`; idioma sem alinhador
nesse modo usa timestamps nativos e registra `alignment.status=unavailable`.

**Deduplicação é parte da migração.** Hoje checksum no mesmo dono/projeto pode
reutilizar resultado antigo, ignorando a pipeline/opções. Acrescentar em `Job`
`transcription_profile` (JSON nullable) e `transcription_profile_hash` (String(64)
nullable, índice não único), via migration explícita. Perfil inclui schema,
provider, revisões dos modelos, idioma, beam/temperatura, diarização/limites,
exposição de palavras e VAD (método, revisão e parâmetros). O canário inicial usa
Silero, como o probe; não deixar o default pyannote do WhisperX mudar isso sem
requalificação e alteração do perfil. A API persiste o perfil normalizado e seu
hash antes de enfileirar; workers/retries usam esse snapshot, não defaults que mudaram depois.
Falha no commit impede enqueue e remove staging; corrigir nos caminhos de áudio
o comportamento atual que captura erro SQL e continua. Para URL/Drive/Dropbox
de tipo desconhecido, gravar perfil candidato já no enqueue inicial, antes do
download: se o worker descobrir mídia depois, ativa esse snapshot, sem consultar
o default do momento. Perfil candidato não participa do dedupe de documentos.
A definição de modelos é pequena configuração compartilhada e versionada;
a API não importa bibliotecas de inferência para resolver perfil.

Deduplicar mídia somente com dono + projeto + checksum + hash de perfil iguais;
perfil nulo legado não satisfaz WhisperX. Formato de download, nome, tags e pasta
não entram no hash. Manter a política existente de mesclar tags/default de formato
para jobs equivalentes. Áudio descoberto após download recebe o mesmo perfil e
checagem antes da inferência; quando não for possível reutilizar com segurança,
processar um novo job. Documentos conservam dedupe atual. Migration nullable sem
backfill inferido; downgrade remove só as colunas/índice, não resultados.

### 4.4 Resultado normalizado, palavras e sobreposição

Manter `text`, `language`, `duration`, `segments`, contagens e metadata atuais.
JSON novo adiciona `schema_version: 2`, `speakers`, `diarization`, `alignment` e
campos opcionais de falante. Exemplo ilustrativo:

```json
{
  "schema_version": 2,
  "language": "pt", "duration": 30.0, "text": "Bom dia.",
  "speakers": [{"id": "SPEAKER_00", "label": "Falante 1"}],
  "diarization": {
    "status": "completed", "model": "pyannote/speaker-diarization-community-1",
    "speaker_count": 1,
    "turns": [{"start": 0.2, "end": 1.4, "speaker_id": "SPEAKER_00"}]
  },
  "alignment": {"status": "completed", "model": "modelo-do-idioma"},
  "segments": [{
    "start": 0.2, "end": 1.4, "text": "Bom dia.", "speaker_id": "SPEAKER_00",
    "words": [{"word": "Bom", "start": 0.2, "end": 0.5,
               "speaker_id": "SPEAKER_00", "alignment_score": 0.94}]
  }]
}
```

Exemplo abreviado: `words` aparece somente quando solicitado. Normalizar a saída
WhisperX `word`/`score`/`speaker` para o contrato Ingestify. `alignment_score` não é
`probability` do ASR; este último torna-se opcional e não recebe score fabricado.
WhisperX também não fornece `language_probability` nesse retorno: manter null/
ausente, sem o zero artificial hoje inserido pelo parser Modal. Adaptar tipos,
validação e metadata para essa ausência tanto local quanto remota.
Palavras sem alinhamento podem ter `start/end=null` e `speaker_id=null`; tipos e
validadores devem aceitar isso explicitamente. Não descartar palavras/números do
texto por falta de alinhamento. Timestamps finitos e dentro da duração; campos
nullable não se convertem implicitamente em zero. Nunca devolver NaN em JSON.

Em arquivos, IDs são renumerados pela primeira ocorrência. Na live, IDs são
alocados na primeira detecção online e nunca renumerados/reutilizados até o fim,
inclusive nos downloads, para preservar cores/rótulos vistos durante a captura.
Turnos podem sobrepor; preservar a diarização regular na lista `turns`.
Atribuição às palavras usa interseção temporal; sem interseção ou empate, null;
não usar atribuição ao vizinho mais próximo para preencher ausência de evidência.
Na fala simultânea, um único rótulo por palavra não prova separação das duas vozes.
Para arquivos, dividir segmentos em mudanças de speaker usando os tempos alinhados;
sem evidência para divisão, manter segmento com `speaker_id=null` e seus turnos.
Silêncio válido produz `speakers=[]`, count 0; diarização desativada retorna
`diarization.status=disabled`, count null (não confundir com zero pessoas).

Persistir provenance com versões/revisões ASR, alinhador, diarizador e parâmetros
na metadata; armazenar também os campos novos no JSON, hoje filtrado em
`build_transcription_outputs`. Manter buckets/object keys e owner checks SQL.

**Barreira durável para resultados novos:** hoje `store_transcript_outputs` engole
falhas de upload e `finish_transcription` pode completar e executar `purge_source`
mesmo assim. Estender essas funções com modo estrito para perfil WhisperX/schema 2,
sem duplicar a pipeline. Os quatro objetos TXT/SRT/VTT/JSON e o Markdown/metadados
no Elasticsearch precisam de confirmação antes de publicar sucesso SQL/cache e
apagar a origem. Falha de gravação impede `completed`/purge e conserva fonte para
retry; tentativas não podem misturar outputs de execuções diferentes. Estender a
guarda de tentativa/cancelamento existente à publicação e limpeza, usando escrita
idempotente ou staging por tentativa com referência ativa publicada sob lock SQL.
Não aplicar `finish_live` de forma indiscriminada a arquivos, pois usa LiveSession/
generation; extrair apenas helpers comuns de escrita/verificação. Testes injetam
falha em cada upload, falha ES e cancelamento antes da publicação. Exclusão limpa
objetos de staging de tentativas, além dos nomes finais existentes.

### 4.5 Modal, capacidade e dependências

Evoluir protocolo remoto 3→4 com limites para IDs, turnos (até MAX_SEGMENTS),
catálogo (até 20), palavras e resposta total. Validar referências a IDs existentes,
intervalos, nulidade e status; ampliar `_OPTIONS`, `_word`, `_segment`,
`parse_response` e mensagens de progresso sem remover limites existentes.
Meta/fingerprint devem anunciar versão e capacidade de diarização. Job com perfil
novo não pode cair em deployment antigo que elimina campos: impedir placement;
preferir engine compatível ou deixar na fila com motivo explícito, conforme Compute.

Incluir core/fontes novas em `SOURCE_FILES`, locks com hashes e revisões de todos
os modelos no fingerprint/deploy. Reusar classe/app/ledger e contabilidade atuais;
progresso de arquivo no Modal não é uma sessão de microfone. Deadline, cancelamento
e preço incluem todas as etapas. Ao mudar fingerprint/pipeline, invalidar benchmarks
de velocidade/custo/VRAM anteriores, sem reaproveitar o footprint fixo de 3 GB.

O ambiente validado do teste é Python 3.11 CPU; a imagem de workers usa Python 3.13.
Criar conjunto de dependências de áudio compatível com o alvo e validá-lo em build
limpo CPU e CUDA. Não fixar torch 2.8 na imagem compartilhada de Docling/Florence-2
sem verificar compatibilidade. Preferir imagem/requirements específicos de áudio
usando os pontos de configuração existentes; documentar a versão Python efetiva.
`pip check`, import, pesos e uma inferência real fazem parte do gate de cada alvo.

Pré-carregar ASR, alinhadores PT/EN e diarizador; outros idiomas só entram na lista
de suporte quando seus alinhadores forem provisionados e validados. Revisões são
fixadas. HF token é segredo de provisionamento em arquivo/secret store, sem entrar
em task, Redis, fingerprint, logs ou imagem. Pesos acessíveis apenas a operadores/
workers; respeitar licença e termos do modelo. Não aceitar condições em nome do
usuário. Jobs executam com pesos locais; não depender de download durante inferência.

### 4.6 UI e formatos

Estender `TranscriptView`, tipos e formatação existentes. Exibir “Falante 1”,
“Falante 2” com cores consistentes e indicação “Falante não identificado” para null;
cor não é a única identificação. Resultado antigo continua sem badges.
Parciais de arquivos exibem texto e fase de processamento; não prometer speaker
estável antes de terminar o agrupamento global.

JSON mantém texto limpo e IDs estruturados. Markdown/TXT/SRT e texto dos cues VTT
recebem prefixo `Falante N:` quando o segmento tem atribuição; o texto da fala
continua escapado pelas regras existentes. Segmento ambíguo não recebe prefixo
enganoso. Todos os downloads derivam do mesmo resultado normalizado. API e UI
mostram quantidade de falantes e estado da diarização; não mostrar embeddings.

### 4.7 Live: identificação de falantes durante a captura

#### Pipeline incremental e prova de viabilidade

Preservar LocalAgreement-2, relógio PCM, eventos finais de texto, backpressure,
ticket e leases. `OnlineWhisper` depende de `model.transcribe` com palavras;
`whisperx.load_model` não é um substituto direto. O adapter ASR continua exigido.
Diarização consome a mesma sequência PCM em paralelo lógico, sem chamar uma
pipeline de arquivo inteira a cada bloco. Nenhuma inferência roda no event loop.

Primeira candidata ao experimento: [Diart](https://github.com/juanmc2005/diart),
que oferece agrupamento incremental com modelos de segmentação/embedding.
Usar seus blocos de inferência; reutilizar o WebSocket público Ingestify, sem
instalar outro servidor público nem usar captura de microfone no servidor.
Ponto inicial a medir: janela de 5 s, avanço de 500 ms, agregação com atraso de
1 s; esses valores são parâmetros experimentais, não latência já comprovada.
Fixar revisão/pesos, separar estado por sessão e não recalcular todo o histórico.

A compatibilidade não está resolvida: Diart 0.9.2 declara NumPy <2, enquanto
WhisperX 3.8.6 exige NumPy ≥2.1. Seu [manifest](https://github.com/juanmc2005/diart/blob/main/setup.cfg)
e a recomendação upstream para reproduzir benchmarks com versões antigas de
pyannote impedem presumir instalação conjunta. Primeiro experimento em ambiente
isolado. Se qualificado, usar processo/container privado com lock próprio, limite
de CPU/RAM/GPU e canal interno autenticado; lifecycle vinculado ao worker-live.
Readiness/capacidade são por capability: ASR aquecido permite protocolo 1;
protocolo 2 com diarização exige os dois processos aquecidos e versões compatíveis.
Ausência/falha do diarizador remove apenas `online_diarization` da admissão e
encerra as sessões v2 afetadas, sem derrubar v1. Startup/health não devem bloquear
o ASR à espera do processo online. Recuperação exige novo warmup/check antes de
readmitir v2. Não modificar os workers atuais para satisfazer dependências do experimento.

Acesso ao Community-1 não garante acesso aos modelos online: provisionar também
os pesos de segmentação/embedding escolhidos, com termos/token próprios quando
exigidos. Preservar pins/licenças no manifest. Não usar números upstream como
resultado do hardware local. Se o experimento reprovar os gates, a fatia live
continua pendente; identificação só após `finish` não satisfaz o requisito.

#### Estado e orçamento da sessão

```text
PCM + seq/offset → validação/relógio existente → ASR online → transcript.*
                                           → diarizador → diarization.update
Cliente combina texto imutável + turnos de falantes versionados
finish → drenar as duas caudas → fechar anotações → finish_live → completed
```

Usar filas separadas e limitadas para ASR/diarização; uma inferência não bloqueia
os eventos já produzidos pela outra. Mesmo relógio de amostras, inclusive silêncio,
sem remover VAD e perder offsets. Limitar backlog de cada consumidor a 2 s e
buffer de áudio do diarizador a 10 s; saturação gera `LIVE_DIARIZATION_BACKPRESSURE`
e encerra a sessão, sem descartar áudio ou continuar prometendo identificação.
Um árbitro de GPU/capacidade compartilhado contabiliza as duas pipelines; “paralelo”
não autoriza exceder VRAM. Estado incremental contém centros de voz/turnos, nunca
identidades de outras sessões. Embeddings ficam apenas em RAM e são limpos ao sair.

Não exigir spool do áudio completo para entregar speaker durante a captura.
Guardar apenas buffers limitados e turnos textuais necessários ao resultado
(até 200.000 turnos, catálogo até 20, duração máxima existente). Limites atingidos
retornam erro explícito. O adapter deve detectar falta de capacidade do clustering,
sem fundir silenciosamente uma nova voz para caber em 20 slots; testar esse caso.
Além do overflow, o clustering original do Diart pode atribuir um centro próximo
a uma fala curta sem evidência suficiente para atualizar/criar um centro. O adapter
precisa observar decisão/distância e evidência antes desse fallback e produzir
unknown nesses casos; um wrapper que recebe apenas a Annotation final não basta.
Usar extensão estreita e versionada do bloco de clustering, sem copiar a pipeline
inteira; teste real obrigatório com fala curta, voz nova e limite de slots.
Se a biblioteca não expuser informação suficiente, a qualificação reprova essa
integração até existir mecanismo verificável; não simular confiança por distância.
Os parâmetros min/max de arquivos não são automaticamente suportados online:
no protocolo live 2 inicial, `diarize=true` usa contagem incremental livre até a
capacidade declarada; rejeitar `min_speakers`/`max_speakers` na criação com 422.

#### Protocolo de rótulos e compatibilidade

Criação recebe `protocol: 2` e `diarize: true`; omissão conserva protocolo 1 sem
diarização durante a transição. Pedido explícito incompatível recebe 422;
worker sem capability `online_diarization` pronto recebe 503 antes da reserva.
Negociar a versão também na autenticação WS, no ticket/lease e na resposta
`session.ready`; não aceitar v2 sobre reserva v1. API mantém owner checks SQL.

Texto `transcript.partial`/`transcript.final` mantém sua semântica; não esperar
speaker para confirmar palavras. Um novo evento contém a substituição completa
dos turnos de um intervalo revisável, e não texto reescrito:

```json
{
  "type": "diarization.update", "event_seq": 42, "generation": 1,
  "revision": 3, "horizon_samples": 80000,
  "replace_from_samples": 32000, "replace_to_samples": 80000,
  "stable_until_samples": 32000,
  "speakers": [{"id": "SPEAKER_00", "label": "Falante 1"}],
  "turns": [{"start_samples": 33600, "end_samples": 73600,
             "speaker_id": "SPEAKER_00"}]
}
```

`revision` começa em 1 e cresce consecutivamente por geração; `event_seq` segue
o contador global atual. Tempos do protocolo de diarização são índices inteiros de
amostras PCM de 16 kHz, sem bool/float/NaN. Intervalos são semiabertos `[start,end)`.
Converter para segundos apenas na apresentação e no resultado schema 2, dividindo
por 16.000. Máximo 64 turnos por update e mensagem até 64 KiB.
Catálogo completo até 20 IDs, append-only; cada referência precisa existir.
Cada evento substitui todas as anotações no intervalo, inclusive com `turns=[]`
para removê-las. API e UI fazem recorte exato dos turnos nas bordas, preservando
as partes externas. A API valida antes de guardar/encaminhar. Replays idênticos
são idempotentes, revisão antiga não sobrescreve nova; lacuna ou mesmo revision
com outro conteúdo falha o protocolo. Reutilizar enquadramento/limites internos.

Definir `H=horizon_samples`: última fronteira de áudio real já observada e
processada pelo diarizador (exclusiva), monotônica e ≤ contador PCM recebido pela
API. A janela revisável é calculada sobre H, não sobre áudio mais recente que
tenha chegado à API enquanto o evento trafegava. Para cada update:

- `0 ≤ replace_from_samples ≤ replace_to_samples ≤ H`;
- `replace_from_samples ≥ max(watermark_anterior, H - 80.000)`;
- cada turno está completamente contido no intervalo substituído;
- `max(watermark_anterior, H - 80.000, 0) ≤ stable_until_samples ≤ H`;
- nenhuma anotação anterior ao watermark já publicado pode mudar.

O watermark avança apenas após incorporar todos os dados correspondentes; silêncio
ou ausência de evidência congela ausência de speaker. Permitir evento sem turnos
e intervalo vazio `[H,H)` que só avance horizonte/watermark/catálogo. A janela de
5 s é relativa ao horizonte processado; após a primeira janela, backlog e trânsito
podem torná-la mais antiga que os últimos 5 s vistos pela API. Medir e limitar
esses atrasos separadamente, sem rejeitar um evento válido por chegada tardia.

Usar dois contadores: `A` = PCM incorporado ao ring buffer de contexto e `H` =
fronteira de saída/decisão após inferência. `0 ≤ H ≤ A ≤ recebido`. Antes de haver
5 s de contexto, A avança mas H pode permanecer zero: isso não é backlog.
Backlog de trabalho = `(recebido - A) / 16.000` mais `0,5 s × número de passos
elegíveis pendentes` (inclui passo em execução). Um passo fica elegível ao completar
a primeira janela e depois a cada avanço de 500 ms. Contexto retido não é trabalho
pendente. Limite total 2 s, sem fila ilimitada de passos; atraso de uma inferência
individual também tem watchdog de 2 s. Readiness já garante modelos aquecidos.
No startup, o primeiro output/watermark precisa chegar até 6 s de áudio recebido,
inclusive silêncio; o limite de contexto é 10 s em todas as fases. EOF antes de
5 s agenda uma única janela com padding e deadline de drenagem, sem criar backlog
falso. Testes específicos cobrem primeira janela, silêncio longo e EOF curto.
A API
não rejeita update válido comparando-o a um relógio que avançou durante o trânsito.
No EOF, H é a duração real em amostras e watermark termina em H após drenar;
padding não aumenta nenhum deles. Ao congelar, dado ainda sem speaker permanece
desconhecido, sem atribuição ao vizinho.

Uma pessoa que volta a falar
usa o mesmo ID se o agrupamento a reconhecer; não prometer acerto sem benchmark.
Não renomear nem fundir globalmente IDs já congelados: erros antigos entram na
métrica de qualidade. Correção manual/global posterior fica fora desta fatia.

UI mostra rótulo provisório após receber turnos, mesmo se o texto ainda estiver
chegando; o watermark determina quando fica definitivo. `LiveTranscriptView` e
`use-live-capture` mantêm anotações separadas do array de texto confirmado.
Enquanto não há evidência, “Identificando falante”. Em fala simultânea, mostrar
os dois rótulos no intervalo; segmento com múltiplos falantes recebe
`speaker_id=null` no resultado e preserva os turnos, sem duplicar a frase. Texto
confirmado não é dividido/retimado depois para acomodar troca de pessoa.

#### Drenagem, falhas e persistência

No `finish`, impedir novos frames, drenar ASR e diarizador incluindo a cauda menor
que a janela; eventual padding não conta como áudio recebido e não aparece nos
turnos. Manter estado `finalizing`, lease, heartbeat e vaga até persistência.
Não executar Community-1 sobre a gravação inteira nessa fatia live: resultado
final deriva das anotações online congeladas, com provenance `diart` e revisões
reais, enquanto arquivos continuam usando WhisperX/Community-1.

API acumula o estado validado de turnos e monta resultado schema 2. Worker envia
fim de diarização com revisão final, duração, contagem e digest do estado canônico;
API confere antes de chamar `finish_live`. Nenhum speaker update após completed.

Canonicalização única para o digest SHA256: recortar em amostras inteiras, ordenar
por speaker e unir intervalos sobrepostos/contíguos do mesmo ID; depois ordenar
turnos por `(start_samples,end_samples,speaker_id)`. Catálogo por número do ID.
Serializar UTF-8 JSON compacto, sem espaços e sem escapes ASCII desnecessários,
com ordem de campos fixa: `generation`, `revision`, `horizon_samples`,
`stable_until_samples`, `speakers`, `turns`; catálogo usa `id,label`, turno usa
`start_samples,end_samples,speaker_id`. Não incluir `event_seq`/intervalo de update.
Calcular digest completo uma vez no EOF, não reprocessar histórico inteiro a cada
bloco. Reducer de referência e fixtures compartilhadas provam igualdade de estado
canônico entre worker, API e TypeScript, incluindo turnos que cruzam bordas e
sobreposição entre pessoas. Estado final schema 2 deve ser conversão exata desse
estado, mantendo IDs da captura.

Catalogar engine online dentro de `diarization` e corrigir hardcodes de provider
na API/worker. A lista persistida precisa coincidir com o estado final exibido.

Prazo de drenagem alvo: ≤10 s após EOF com modelos aquecidos; deadline operacional
30 s, encerrando com `LIVE_DIARIZATION_TIMEOUT` se excedido. UI mostra finalização.
Falha do diarizador, perda de canal, cancelamento, disconnect ou perda de lease
encerra ambas as pipelines e mantém política terminal da live existente; não
publicar sucesso só de texto quando `diarize=true`. Liberação de GPU/capacidade
aguarda término efetivo da inferência ou encerramento do processo isolado, sem
reusar recursos de sessão que ainda executa. Sem fallback CPU durante live.

## 5. Alternativas consideradas

| Alternativa | Decisão |
|---|---|
| Adicionar pyannote diretamente ao core atual | Menor troca de ASR, mas pedido é padronizar WhisperX; preservar esta opção se a qualificação reprovar o wrapper. |
| WhisperX como segundo backend sem migração | Útil no canário/rollback; não satisfaz o objetivo de torná-lo padrão. |
| Substituir só a factory | Rejeitada: ignora Modal, live, benchmarks e filtros de serialização. |
| Resemblyzer + clustering próprio | Teste anterior falhou na contagem; exigiria desenvolver e calibrar pipeline própria. |
| WhisperX de arquivo em cada frame live | Rejeitada: interface/agrupamento global não garantem latência nem identidade online estável. |
| Diart para speakers durante a live | Primeira candidata ao experimento isolado; integração e qualidade online ainda precisam ser qualificadas. |
| Identificação somente após encerrar | Não atende à decisão do usuário de 2026-10-05. |

## 6. Impactos e rollout

Campos aditivos e leitura retrocompatível; texto rotulado nos downloads é mudança
visível documentada. Provider legado explícito continua suportado. Novas colunas
nullable exigem migration anterior ao enqueue novo; resultados antigos não mudam.
Autorização/projeto/tags/ownership permanecem nos helpers atuais. Nenhum registro
biométrico durável é necessário para IDs locais ao job; embeddings online ficam
em RAM durante a sessão e são descartados ao encerrá-la.

Criar configurações `WHISPERX_DIARIZATION_DEFAULT` (false no canário; true no
cutover), `WHISPERX_DIARIZATION_MODEL` (revisão pinada no manifest),
`WHISPERX_BATCH_SIZE` (1 inicial) e caminho de secret HF só no provisionamento.
Não duplicar `DEVICE`, `WHISPER_MODEL`, feature Compute ou endpoints de resultado.
Footprints dependem de ASR/alinhador/diarizador e concorrência; carregar etapas
sequencialmente quando necessário e medir a soma com os outros modelos residentes.

Rollout: migration/adapters/leitores → pesos/deploys compatíveis → canário opt-in
local/Modal → gates → default WhisperX → fatia live. O experimento online pode
acontecer antes do cutover de arquivos, isoladamente, usando o replay PCM existente. Rollback seleciona provider e
imagens anteriores para novos jobs, drena ou termina tentativas novas e preserva
leitores schema 2/artefatos já salvos. Não rotear perfil WhisperX pendente para
legado silenciosamente. Reverter o default não exige remover as colunas.

## 7. Plano de testes e gates de liberação

**Contratos automatizados:** factory/override, opções através das três entradas,
perfil durável/deduplicação/retry, formatos antigos e novos, palavras sem tempo,
probability versus alignment_score, sobreposição, referência inválida de speaker,
limites de payload, paridade local/Modal, fingerprint/capacidades, cancelamento em
cada etapa e antes de persistir, erro HF sem fallback indevido, CPU após erro CUDA,
leitura MinIO após expirar Redis, exclusão/purge_source com novos resultados,
falha parcial MinIO/ES sem sucesso ou purge prematuro, opções distintas sem
vazamento entre execuções e callback de lotes com áudio real.

**Qualificação real antes do default:** obter acesso ao modelo e executar primeiro
a fixture de 30 s com contagem livre; detectar as duas pessoas e medir DER com
collar 0 e sobreposição incluída. Não usar RTTM para escolher limites de inferência.
Depois corpus versionado com no mínimo 10 gravações PT-BR e 60 min totais, 1/2/3+
falantes, vozes parecidas, variação natural de entonação, ruído e fala simultânea;
referência humana de texto e RTTM, distinta de dados usados para ajustar parâmetros.

Gates propostos, que são requisitos e não medições já alcançadas: contagem exata
em ≥90% dos arquivos; DER agregado ≤20% com collar 0 e overlap incluído; publicar
DER por cenário e componentes miss/false alarm/confusion. WER não pode piorar mais
de 2 pontos percentuais contra o backend atual no mesmo corpus/configuração ASR.
Medir três execuções aquecidas por fixture/alvo e separar cold start/download.
GPU: RTF total ≤0,8, sem OOM em arquivo de 2 h dentro dos limites de upload e com
concorrência declarada; pelo menos 20% de margem VRAM após contabilizar workloads
residentes. Publicar p50/p95 por etapa, RAM, VRAM, custo Modal e cobertura de palavras
com speaker (sem confundir cobertura com acerto). CPU é fallback funcional com
orçamento explícito de memória, sem promessa de mesma latência GPU.

**Live — experimento e gates:** começar com replay 1× da fixture anotada de 30 s,
com contagem livre, depois o corpus PT-BR e navegador real, incluindo áudio curto,
silêncio inicial, silêncio longo, turnos rápidos e reentrada da mesma pessoa.
Salvar timestamps de envio do áudio e dos eventos para provar que a atribuição
aconteceu antes do `finish`, sem acesso a áudio futuro no algoritmo. Não usar
processamento offline acelerado para alegar latência de streaming.

Manter primeira legenda ≤1,5 s, atraso confirmado p95 ≤3 s, backlog ASR <2 s e
texto/tempos confirmados invariantes. Para speakers, primeiro rótulo em até 6 s
após início de fala contínua (considerando a janela inicial), atraso p95 ≤3 s
para turnos após aquecimento, backlog de diarização <2 s e RTF conjunto ASR +
diarização ≤0,8 no alvo e concorrência declarados. São gates propostos, ainda não
medidos. Drenagem p95 ≤10 s e todas as sessões dentro do deadline de 30 s.

Medir DER online com collar 0, overlap incluído e mapeamento global de IDs contra
RTTM apenas para pontuação, nunca para inferência. Usar grade fixa de células de
100 ms: pontuar cada célula com o estado de turnos que a UI tinha exatamente
3 s após o envio da última amostra real dessa célula. Congelar esse snapshot para
a avaliação, sem aplicar correções futuras retroativamente. Definir warmup como
os primeiros 5 s de áudio de cada sessão, independentemente do RTTM/conteúdo;
reportá-lo separadamente, inclusive silêncio inicial, sem aumentar warmup depois
de ver o resultado. Células ainda desconhecidas contam como erro. Medir p95 de
atribuição também por célula, desde envio da última amostra até primeiro rótulo
mostrado; ausência é deadline perdido e precisa entrar na cobertura. Publicar DER
final do estado congelado, contagem exata por sessão, atraso de primeira atribuição
(inclusive valores ausentes), cobertura e trocas indevidas de ID por pessoa.
Exigir DER final ≤20%, DER online ≤25% e contagem final exata em ≥90% das sessões;
publicar cobertura nos deadlines e proporção de trechos corrigidos dentro da
janela. Separar resultados de warmup e fala simultânea. Não excluir desconhecidos
nem reatribuir IDs usando o RTTM na inferência para melhorar métricas.

Repetir sessões de 30 s, 5 min e 30 min, com concorrência de arquivos e margem
VRAM ≥20%. Testar geração antiga, revisão duplicada/divergente, lacuna, mudanças
atrás do watermark, avanço em silêncio, atraso de transporte, recorte nas bordas,
canonicalização Python/TypeScript, overflow de catálogo/turnos, filas cheias,
cauda curta/padding, morte do processo online, lease perdido, cancelamento durante
inferência/drenagem e falha de persistência. Resultado JSON/turnos deve ser igual
ao estado final da UI; todos os formatos derivam dele. Sem aprovação desses gates,
a live atual continua disponível no protocolo 1 e a migração global fica pendente.

## 8. Plano de implementação

- [ ] Qualificar pesos/acesso HF e fixture anotada; fixar revisões e locks CPU/CUDA.
- [ ] Perfil durável/migration, opções/dedupe e leitores schema 2; testes de compatibilidade.
- [ ] Provar adapter de lotes/progresso/cancelamento contra WhisperX real; core e
      adapter local, isolamento das opções, memória limitada, fallback e formatos.
- [ ] Barreira de persistência para schema 2 e limpeza de tentativas; falhas injetadas.
- [ ] Modal protocolo 4, source list, fingerprint, capacidades, deploy e benchmark completo.
- [ ] UI de falantes, downloads, documentação e snapshot OpenAPI.
- [ ] Corpus PT-BR, canário local/Modal e alteração do default após gates.
- [ ] Experimento isolado Diart: locks/pesos, replay 1×, qualidade/atraso e identidade online.
- [ ] Adapter ASR + diarização incremental, lifecycle/capacidade, protocolo 2,
      rótulos provisórios na UI e drenagem/persistência do estado congelado.
- [ ] Qualificação live/concorrência, rollout e teste de rollback; encerrar uso legado por padrão.

## 9. Questões em aberto

- [ ] Acesso Hugging Face ao Community-1 — bloqueia o benchmark de diarização,
      não a redação/revisão desta spec. Termos aceitos e token ainda não disponíveis.
- [x] Preferência do usuário: speakers durante a live ou no resultado final?
      **Decisão (2026-10-05): durante a captura**, com rótulos provisórios e
      correções limitadas, preservando texto confirmado. §4.7 substitui a premissa
      anterior de identificação somente após encerrar.
- [ ] Qualificar Diart e seus modelos online em ambiente isolado; resolver conflito
      de dependências e medir gates. Se reprovado, revisar escolha do algoritmo
      mantendo o requisito online, sem mudar para identificação só no final.
- [ ] Compatibilidade Python 3.13/CUDA/torch no hardware alvo — resolver na qualificação;
      teste em Python 3.11 CPU não valida a imagem existente.
- [ ] Resultados reais dos gates de qualidade e consumo — reprovação mantém canário,
      não permite baixar thresholds depois de olhar a amostra sem nova revisão.

Referências: [WhisperX](https://github.com/m-bain/whisperX),
[Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1),
[Diart](https://github.com/juanmc2005/diart),
[spec 0005](0005-transcricao-ao-vivo.md). A implementação está em andamento na branch `feat/whisperx-speaker-identification`. O default e a liberação global continuam condicionados aos gates acima; ver [guia do canário](../features/whisperx.md).
