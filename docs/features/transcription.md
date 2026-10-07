# Transcrição de áudio e vídeo pela API

Contratos verificados no código em 2026-10-06:
[rotas](../../backend/api/routes.py), [formatos](../../backend/shared/transcripts.py)
e [modelos](../../backend/shared/schemas.py). Campos e modelos completos na
[referência dos endpoints](../api-reference.md).

## Criar a transcrição

`POST /transcribe` recebe **multipart/form-data**, com JWT ou `X-API-Key`.
Retorna 200 com `{job_id, status:"queued", created_at, message, project, folder}`.
O processamento é assíncrono; consulte `GET /jobs/{job_id}` até concluir.

| Campo | Padrão / regra |
| --- | --- |
| `file` | Obrigatório; áudio/vídeo suportado e não vazio. Limites `MAX_AUDIO_FILE_SIZE_MB` / `MAX_VIDEO_FILE_SIZE_MB`; OpenAI API limita ambos a 25 MB. Excesso retorna 413. |
| `project` / `project_id` | Obrigatório salvo API key vinculada; exclusivos. Nome cria/reutiliza projeto próprio. |
| `folder` / `folder_id` | Opcionais, exclusivos; pasta deve pertencer ao projeto. |
| `name` | Nome do arquivo quando ausente. |
| `tags` | Texto separado por vírgulas, até 20 tags de 50 caracteres. |
| `language` | Detectado automaticamente quando ausente; código como `pt`. |
| `operation` | `transcribe` (transcrição/tradução), `detect_language` ou `inspect` (metadados sem inferência). |
| `decoding_options` | Objeto JSON serializado; controles tipados em `AudioDecodingOptions`. Parâmetros não aceitos pelo provider retornam 422 antes de criar job. |
| `operation` | `transcribe`; também `detect_language` e `inspect`. |
| `decoding_options` | Objeto JSON serializado. Campos suportados, tipos e limites em `GET /audio/capabilities`. |
| `include_timestamps` | `true`. |
| `include_word_timestamps` | `false`. |
| `output_format` | `markdown`; também `vtt`, `srt`, `txt`, `json`. |
| `purge_source` | `false`; `true` apaga a origem interna depois do sucesso. |
| `datalake_connection_id`, `datalake_bucket`, `datalake_prefix` | Destino externo opcional; conexão e bucket são enviados juntos. |
| `datalake_partitioning`, `datalake_partition_values` | JSON serializado; estratégia por job e contexto personalizado. |

```bash
curl --fail-with-body 'https://dev.ingestify.ai/api/transcribe' \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F 'file=@conversation.mp3' \
  -F 'project=Atendimento' \
  -F 'language=pt' \
  -F 'output_format=markdown'
```

Áudio: MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC.
Vídeo: MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP;
somente a faixa de áudio é transcrita. Provider/modelo são configuração do
servidor/engine, não campos aceitos por esta rota. Identificação de falantes não
é prometida pelo contrato atual.

## Descobrir capacidades antes de enviar

`GET /audio/capabilities` exige a mesma autenticação do upload. Retorna `enabled`,
`provider`, `model`, `operations`, `tasks`, `formats`, `max_audio_size_mb`,
`max_video_size_mb`, `parameters_schema` e `restrictions`. Consulte o schema do
provider ativo: um campo de outro provider gera **422 antes de criar o job**.
`workers_running` e `execution_reason` descrevem o heartbeat, sem reservar uma vaga;
workers pausados podem deixar uma solicitação válida na fila.

```bash
curl --fail-with-body 'https://dev.ingestify.ai/api/audio/capabilities' \
  -H "X-API-Key: $INGESTIFY_API_KEY"
```

| Operação | O que entrega | Solicitação |
| --- | --- | --- |
| `transcribe` | Texto, segmentos e, opcionalmente, palavras com tempos. | `decoding_options.task=transcribe` (padrão). |
| `transcribe` + `task=translate` | Tradução para inglês com modelo compatível. | Confira `tasks`; modelos turbo e `.en` rejeitam tradução. |
| `detect_language` | Idioma e probabilidade quando fornecida pelo provider; sem segmentos. | Omita `language`; não combine com `task=translate`. |
| `inspect` | Duração, formato, canais, sample rate, codec, tamanho e metadados disponíveis. | Não executa inferência; ainda usa o fluxo assíncrono e os workers. |

No `openai-api`, detecção de idioma usa uma chamada de transcrição ao serviço e
não fornece probabilidades. Não trate essa operação como inspeção local gratuita.
As operações de análise podem produzir legendas vazias porque não têm segmentos;
use `format=json` ou Markdown para ler o resultado.

### Controles de decodificação

Os defaults e limites completos estão no `parameters_schema` e no modelo
`AudioDecodingOptions` da [referência gerada](../api-reference.md). O catálogo
filtra os campos por provider; não envie todos os campos do schema global.

| Grupo | Campos principais |
| --- | --- |
| Idioma e tarefa | `language`, `task` |
| Busca | `beam_size`, `best_of`, `patience`, `length_penalty`, `temperature` |
| Contexto | `initial_prompt`, `prefix`, `condition_on_previous_text`; `hotwords` no faster-whisper; `prompt` e `carry_initial_prompt` no openai-whisper |
| Repetição e silêncio | `repetition_penalty`, `no_repeat_ngram_size`, `compression_ratio_threshold`, `log_prob_threshold` (faster-whisper) ou `logprob_threshold` (openai-whisper), `no_speech_threshold`, `hallucination_silence_threshold` |
| Voz e recortes | `vad_filter`, `vad_parameters`, `clip_timestamps`, `chunk_length` |
| Tokens e tempos | `suppress_blank`, `suppress_tokens`, `max_new_tokens` (faster-whisper), `sample_len` (openai-whisper), `without_timestamps`, `max_initial_timestamp` |
| Pontuação e detecção | `prepend_punctuations`, `append_punctuations`, `multilingual`, `language_detection_threshold`, `language_detection_segments`, `prompt_reset_on_temperature`, `log_progress` |
| Execução do openai-whisper | `fp16` |

`temperature` fica entre 0 e 1; providers locais aceitam uma lista de até 100
valores para fallback. `beam_size`/`best_of` vão de 1 a 20. Texto de prompt tem
limite de 10.000 caracteres. Recortes usam segundos não negativos em ordem
crescente, como `[0,30,60,90]`; não são números de página nem timestamps em ms.
`without_timestamps=true` não pode ser combinado com `include_word_timestamps`.
`language` no formulário e em `decoding_options` deve coincidir.
Nos providers locais, o catálogo lista os códigos aceitos pelo modelo e a API
rejeita códigos desconhecidos antes de criar o job. Modelos `.en` aceitam
somente `en`; cantonês (`yue`) exige o vocabulário introduzido no large-v3.

Em `/upload` e `/convert`, arquivos ou URLs com extensão de áudio/vídeo conhecida
e sem opções de documento usam os padrões de `/transcribe`, com configuração
salva antes do despacho. Opções Docling ou presets de documento em mídia
retornam `422`; selecione Whisper e envie `audio_options`. Se um download de
identificador opaco revelar mídia, o worker salva a configuração de áudio antes
da inferência, ou falha se foram solicitados controles Docling explícitos.

`vad_parameters` aceita `threshold`, `neg_threshold`, `min_speech_duration_ms`,
`max_speech_duration_s`, `min_silence_duration_ms` e `speech_pad_ms`.
O `openai-api` aceita somente `task`, `language`, `temperature` escalar e
`initial_prompt` textual; tradução não fornece tempos por palavra. Campos
incompatíveis ou desconhecidos são recusados em vez de ignorados.

```bash
# Contexto e palavras: exemplo para faster-whisper.
curl --fail-with-body 'https://dev.ingestify.ai/api/transcribe' \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F 'file=@conversation.mp3' -F 'project=Atendimento' \
  -F 'include_word_timestamps=true' \
  --form-string 'decoding_options={"language":"pt","beam_size":3,"hotwords":"Ingestify","initial_prompt":"Reunião técnica sobre ingestão de dados","vad_parameters":{"threshold":0.4}}'

# Inspeção sem gerar uma transcrição.
curl --fail-with-body 'https://dev.ingestify.ai/api/transcribe' \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F 'file=@conversation.mp3' -F 'project=Atendimento' \
  -F 'operation=inspect' -F 'output_format=json'

# Detecção automática do idioma.
curl --fail-with-body 'https://dev.ingestify.ai/api/transcribe' \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F 'file=@conversation.mp3' -F 'project=Atendimento' \
  -F 'operation=detect_language' -F 'output_format=json'
```

Esses controles se aplicam a arquivos enviados a `/transcribe`. Não alteram
automaticamente as sessões [live](live-transcription.md). Identificação de
falantes não é um campo implementado desse contrato.

### Configuração persistida e deduplicação

`GET /jobs/{job_id}` inclui `configuration`, com `operation`, `provider`, `model`
e `options`. Essa configuração registra o pedido aceito e seus defaults, antes
da publicação na fila; a API retorna 503 se não conseguir gravá-la. Ela continua
legível depois que os caches expiram. O modelo reportado no resultado identifica
a execução efetiva; `configuration` é o snapshot da solicitação.

Sem destino externo explícito, mesmo checksum, usuário, projeto e **configuração
efetiva** reutilizam um job não falho e somam tags. Alterar operação, provider,
modelo, decodificação, timestamps, formato ou retenção cria outro job; jobs antigos
sem configuração verificável também são reprocessados. Não se reaproveita texto
em português para uma solicitação de tradução por ter o mesmo arquivo.
Job falho ou destino datalake explícito cria novo job. `conversation_id` não é
chave de idempotência. A pasta do job reaproveitado é preservada.

## Ler status, parciais e resultados

`GET /jobs/{job_id}/transcript/partial?since=0` devolve
`{job_id, status, segments, next}`. Use `next` como `since` na próxima consulta.
O provider precisa produzir segmentos parciais; uma lista vazia não representa
o texto final. Este endpoint não abre uma sessão de microfone; veja
[captura live](live-transcription.md).

Depois de `completed`, use `GET /jobs/{job_id}/result?format=...`:

| Formato | Content-Type | Corpo |
| --- | --- | --- |
| `markdown` | `application/json` | Envelope com `result.markdown` e `result.metadata`. |
| `vtt` | `text/vtt` | Legenda WebVTT bruta. |
| `srt` | `application/x-subrip` | Legenda SRT bruta. |
| `txt` | `text/plain` | Texto bruto. |
| `json` | `application/json` | JSON bruto da transcrição, com segmentos. |

Sem `format`, vale o `output_format` original. Todos os formatos são gerados;
essa opção escolhe o padrão de leitura, não restringe a produção.
Não use `.json()` para VTT/SRT/TXT.

```bash
curl --fail-with-body -H "X-API-Key: $INGESTIFY_API_KEY" \
  "https://dev.ingestify.ai/api/jobs/$JOB_ID/result?format=vtt" -o conversation.vtt
```

O resultado completo e os formatos persistidos no MinIO interno permitem leitura
após expiração do Redis. A leitura durável de transcrições não depende do
Elasticsearch; resultados antigos podem ter metadados incompletos.
Job pendente/processando retorna 400; job falho, 500; recurso ausente/alheio ou
formato não disponível, 404; formato inválido, 422.

## Entrega e análise por cliente

Os mesmos controles podem ser usados para áudio/vídeo externo. Em `/convert`,
envie `audio_options` como JSON no multipart; em `/datalakes/import`, envie esse
objeto no corpo JSON. O schema `AudioConversionOptions` contém `operation`,
`decoding`, `include_timestamps`, `include_word_timestamps`, `output_format` e
`purge_source`. `decoding` segue o catálogo `/audio/capabilities` do provider
configurado. Não combine com `conversion_options`, que configura Docling.

```bash
curl --fail-with-body 'https://dev.ingestify.ai/api/convert' \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F 'source_type=url' -F 'source=https://example.com/conversation.wav' \
  -F 'project=Conversas' \
  --form-string 'audio_options={"operation":"transcribe","decoding":{"language":"pt","beam_size":3,"hotwords":"Ingestify"},"include_word_timestamps":true,"output_format":"json","purge_source":true}'
```

Drive/Dropbox usam o mesmo objeto e continuam exigindo `X-Source-Token` do
provedor. Solicitações explícitas de áudio usam a fila de transcrição, incluindo
downloads externos; com workers pausados, permanecem enfileiradas. A importação
do datalake identifica mídia pelo nome do arquivo e valida os controles antes
de baixar os bytes. Arquivos repetidos com parâmetros diferentes geram outro
job; as opções ficam salvas no banco e consultáveis após F5.

A conexão datalake salva uma estratégia padrão; cada envio pode substituí-la.
Use `tenant_id`/`client_id` para agrupar e preserve `conversation_id`, `agent_id`
e `occurred_at` como valores de contexto. `analytics:"jsonl"` produz um registro
por job, com todos os valores em `partition_values_json` (string JSON), inclusive
os que não criam diretórios. O consumidor reúne os registros para análise.

`GET /jobs/{job_id}/datalake` acompanha a entrega. Depois de corrigir uma falha
de acesso, `POST /jobs/{job_id}/datalake/retry` repete apenas a entrega, usando
caminhos/contexto congelados, sem transcrever novamente.
Exemplos e configuração dos quatro provedores em [datalakes.md](datalakes.md).
