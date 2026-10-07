# Transcrição ao vivo

> Contratos dos endpoints revisados em 2026-10-06. Campos, modelos e autorização:
> [referência completa da API](../api-reference.md). As datas abaixo também registram revisões da implementação/operação.

A captura de microfone envia áudio PCM durante a sessão e recebe legendas antes
do EOF. `POST /transcribe` e seus jobs de arquivo continuam com o contrato atual.
A live permanece **desabilitada por padrão**; a implementação não autoriza sua
ativação em produção antes dos gates da [spec 0005](../specs/0005-transcricao-ao-vivo.md).

## Modal e prévia de transcrições de arquivo

A captura em `/live` usa o worker GPU local por WebSocket. **Captura ao vivo no
Modal ainda não está implementada**: a spec 0005 exclui esse roteamento da fase
inicial. Cadastrar um engine Modal para `transcription` não muda o destino das
sessões live. O contrato Modal atual recebe um arquivo completo por chamada.

Para arquivos enviados, a página `/jobs/{id}` já mostra texto durante o
processamento. O faster-whisper local grava segmentos no Redis; no Modal,
o container publica lotes na Queue da tentativa, e `worker-remote` transfere
esses lotes para o mesmo Redis. A tela consulta
`GET /jobs/{id}/transcript/partial?since=N` a cada 3 segundos. Não é necessário
capturar áudio nem manter um WebSocket para visualizar esses trechos.

No Modal, a publicação tem janela de 2 segundos e a leitura da Queue ocorre
entre esperas de 3 segundos; somam-se inferência, cold start, rede e consulta
da tela. Esses intervalos não garantem uma latência máxima. Providers que
retornam o arquivo inteiro de uma vez não produzem prévia incremental. Ao
concluir, a tela troca a prévia pelo resultado persistido.

Para suportar captura no Modal, será necessário acrescentar admissão e reserva
de uma sessão remota, readiness após aquecer o modelo, transporte contínuo de
PCM e eventos, limites de backlog, cancelamento e contabilização de duração/custo.
Devem ser qualificados cold start, primeira legenda antes de encerrar o áudio,
concorrência, desconexão e persistência final. O envio de arquivos e sua Queue
de legendas não comprovam esses comportamentos.

## Uso

Abra `/live`, selecione projeto, pasta e idioma, ajuste os controles opcionais do modelo, permita o microfone e inicie. A captura
começa após `session.ready`; texto provisório substitui a revisão anterior, e
segmentos confirmados aparecem imediatamente. **Finalizar** envia a cauda e espera
persistência; o resultado abre na página existente do job, com TXT/JSON/VTT/SRT.
**Cancelar** encerra a sessão e descarta parciais. Queda de conexão exige nova sessão.
O navegador precisa de HTTPS ou localhost; AudioWorklet converte a captura mono para
16 kHz s16le. O áudio original não é armazenado.

## Opções por sessão

Consulte o catálogo autenticado antes de criar uma sessão. `enabled` é a configuração
do serviço; `ready` exige heartbeat de um modelo residente. Não garante vaga ou a
prontidão do armazenamento. `options_supported` identifica workers atualizados.
Um worker antigo anuncia apenas português; opções não padrão retornam
`503 LIVE_OPTIONS_UPGRADE_REQUIRED`, com a reserva liberada. Um idioma fora de
`languages` retorna `422` sem criar job.

```bash
curl --fail-with-body "$INGESTIFY_API_URL/transcribe/live/sessions/capabilities" \
  -H "X-API-Key: $INGESTIFY_API_KEY"

curl --fail-with-body "$INGESTIFY_API_URL/transcribe/live/sessions" \
  -H "X-API-Key: $INGESTIFY_API_KEY" -H 'Content-Type: application/json' \
  -d '{"project":"Meetings","language":"en","options":{"decoding":{"beam_size":3,"initial_prompt":"Product names: Ingestify.","hotwords":"lakehouse","vad_parameters":{"threshold":0.6}},"interval_seconds":1,"max_context_seconds":12}}'
```

`options.decoding` expõe beams, alternativas, penalidades de repetição/comprimento,
temperatura/fallback, limiares de confiança, prompt textual, prefixo, hotwords,
filtros de tokens, pontuação, VAD e limite de novos tokens. O schema
`LiveDecodingOptions` documenta tipos, padrões e limites completos. Prompts,
prefixos e hotwords aceitam até 1.024 caracteres; tokens suprimidos, até 256 itens.

`interval_seconds` aceita 0,2–5 s de áudio entre inferências (padrão 0,6);
`max_context_seconds` aceita 4–30 s antes de aparar áudio confirmado (padrão 8).
O intervalo não pode exceder o contexto. `segment_no_speech_threshold` filtra
segmentos pela probabilidade de silêncio (0–1, padrão 0,9). Mais beams ou contexto
podem aumentar latência e provocar backpressure; estes controles não alteram os
limites de duração ou de fila do protocolo.

O idioma é explícito durante toda a sessão. Tradução, detecção/troca automática
de idioma, recortes, desligamento de timestamps e contexto automático de Whisper
não são oferecidos neste protocolo: a política LocalAgreement depende de palavras
com timestamps e do relógio PCM original. A aplicação mantém o contexto confirmado
junto do prompt inicial. Use `/transcribe` para operações de arquivo com outro
contrato. Campos não suportados retornam `422`.

A configuração resolvida é gravada na transação do job antes de entregar o ticket.
Pode ser consultada em `GET /jobs/{id}.configuration`, no status da sessão e no
JSON/metadata do resultado, inclusive sem cache. O formulário `/live` consome o
catálogo e a página do resultado mostra a configuração após recarregar.

## API e protocolo 1

- `POST /transcribe/live/sessions`: JWT ou API key, mesmas regras de projeto/pasta,
  tags e precedência JWT dos uploads. JSON inclui `project`/`project_id`,
  `folder`/`folder_id`, `name`, `tags`, `language` (padrão `pt`, entre os idiomas do worker), `options` e opcionalmente
  `audio={"encoding":"pcm_s16le","sample_rate":16000,"channels":1}`.
- `GET /transcribe/live/sessions/capabilities`: disponibilidade, idiomas do modelo residente, schema de opções e restrições do protocolo.
- `GET /transcribe/live/sessions/{job_id}`: estado, duração, motivo de término e configuração persistida.
- `DELETE /transcribe/live/sessions/{job_id}`: cancelamento idempotente.
- WS `/transcribe/live/sessions/{job_id}/stream`: primeiro frame
  `{"type":"authenticate","protocol":1,"ticket":"<ticket do POST>"}`.
  Ticket aleatório, hash Redis, 60 s, consumido atomicamente uma vez; nunca na URL.

O POST retorna `201` com `job_id`, `ws_url`, ticket, formato e limites; use exatamente
essa URL sem acrescentar credenciais. O job e seu dono são reconferidos no MySQL.
Origin do navegador deve estar em `CORS_ALLOWED_ORIGINS`; clientes nativos podem
omitir Origin. Em produção a API exige WSS e proxy confiável para o scheme correto.
Resposta de admissão tem `Cache-Control: no-store`.

Após `session.ready`, envie um frame a cada 200 ms: cabeçalho little-endian de 12 bytes
(`seq:uint32`, começando 0; `offset_samples:uint64`, começando 0), seguido de 3.200
amostras / 6.400 bytes PCM. Último bloco pode ser menor, nunca vazio; máximo 500 ms.
Sequência/offset são consecutivos; limite 20 frames/s com burst 10. As filas em ambos
os hops têm backlog máximo de 2 s; nenhuma amostra é descartada silenciosamente.
Áudio recebido é contado por amostras, incluindo silêncio. 20 s sem áudio interrompe.

Eventos têm `event_seq` crescente. `transcript.partial` contém `utterance_id`,
`revision`, `text` e substitui o provisório. `transcript.final` contém `segment_id`,
`utterance_id`, `start`, `end`, `text`; confirmados são imutáveis e ordenados.
`session.progress` informa duração recebida e backlog. Envie
`{"type":"finish","last_seq":<última sequência>}` e continue lendo.
`session.completed` só aparece depois dos quatro formatos duráveis, Markdown
indexado e commit SQL. `{"type":"cancel"}` equivale ao DELETE. Fechar sem finish
é falha, com confirmados acessíveis pelo endpoint parcial durante o TTL.

Falhas de admissão retornam `503` com `Retry-After:5` e `LIVE_DISABLED`,
`LIVE_NOT_READY`, `LIVE_CAPACITY_FULL`, `LIVE_OPTIONS_UPGRADE_REQUIRED` ou `LIVE_INDEX_UNAVAILABLE`; a live nunca entra na fila de arquivos.
`LIVE_INDEX_UNAVAILABLE` indica que o Elasticsearch está indisponível para a
verificação ou possui um bloqueio de escrita no índice/cluster, inclusive por
falta de espaço em disco. A API verifica isso antes de reservar capacidade ou
criar o job. Essa verificação não garante espaço até o fim da captura: se a
indexação falhar depois, a sessão termina com `LIVE_INDEX_FAILED` e mantém apenas
os segmentos confirmados disponíveis como resultado parcial.
Erros de sequência/formato fecham com `4400`, ticket com `4401`, sessão inválida
com `4404`, backpressure com `4429`. Não faça retry automático do POST nem do áudio.

## Decoder e persistência

O worker privado mantém faster-whisper turbo residente na GPU e usa LocalAgreement-2:
hipóteses timestampadas em duas janelas sobrepostas confirmam apenas o prefixo estável,
com 200 ms de lookahead. Contexto de áudio é limitado; trim ocorre em fronteiras
confirmadas, retendo 1 s de overlap. Prompt inclui somente texto confirmado **antes**
do buffer, evitando repetir o contexto que já está no áudio. O EOF decodifica a cauda.
Hipóteses com compressão patológica não viram finais; contexto instável excedendo o
limite encerra com erro, preservando os segmentos confirmados em vez de truncar sucesso. O áudio em memória é liberado ao encerrar.
Loader, resolução de dispositivo e formatters são os existentes. Não há fallback CPU.

`live_sessions` guarda fatos da conexão, sem duplicar dono/localização/tags. Objetos
ficam em `transcripts/{job_id}/live/{generation}/`. O endpoint existente
`GET /jobs/{id}/result?format=...` seleciona a geração concluída no MySQL e funciona
após TTL Redis. A busca também só publica hits live da geração concluída e do dono conferidos em lote no MySQL; indexação anterior ao commit não expõe texto provisório. Cancelamento/DELETE revogam leases antes do cleanup; locks SQL e
fencing impedem publicação atrasada. Finalização com erro remove apenas os objetos
que aquela geração tentou escrever. Sessão não é reexecutada após restart.

## Operação opt-in

1. Faça backup e execute a migration explicitamente no ambiente do backend:
   `PYTHONPATH=backend python scripts/migrate_0005_live.py`.
   Boot normal não cria a tabela em banco que já tem `jobs`.
2. Configure uma credencial interna aleatória com pelo menos 32 caracteres em
   `LIVE_INTERNAL_TOKEN`, igual na API e worker. Não publique a porta do worker.
   O worker usa as mesmas conexões de Redis/MySQL/MinIO da API. Seu ambiente
   padrão é `production`; apenas no piloto de desenvolvimento configure
   `LIVE_ENVIRONMENT=development` para corresponder à API de desenvolvimento.
3. Declare a GPU por UUID e todos os workloads residentes no inventário do engine
   local. `LIVE_GPU_REF` (default `gpu0`) seleciona essa declaração. Em produção,
   o worker recusa footprint live + bindings + reserva/margem de 20% que não caibam.
4. Suba o perfil opt-in com os overlays base/GPU/live e `--profile live`. O worker
   aquece antes de publicar readiness, heartbeat 2 s / TTL 10 s. A API permanece
   desligada até `LIVE_TRANSCRIPTION_ENABLED=true`, após validação dos gates.
5. Confirme inventário em `/admin/gpus`: o footprint live entra no orçamento e
   aparece separado das lanes Celery. Verifique VRAM real sob concorrência planejada.

Configurações: `LIVE_MAX_SESSIONS=1`, `LIVE_MAX_DURATION_SECONDS=1800`,
`LIVE_MAX_AUDIO_BACKLOG_SECONDS=2`, `LIVE_VRAM_FOOTPRINT_GB=3`,
`LIVE_VRAM_RESERVE_GB=3.2`, `LIVE_WORKER_ID=live-local` e URL privada do worker.
`WHISPER_MODEL`, `WHISPER_DEVICE` e `WHISPER_COMPUTE_TYPE` seguem a resolução existente.
O profile piloto fixa faster-whisper 1.2.1 e CTranslate2 4.8.2. A versão do modelo
precisa ser fixada/registrada no perfil operacional; pesos não são gravados no Git.

Atrás do tunnel de `dev.ingestify.ai`, aplique `docker-compose.live.yml` antes de
`docker-compose.tunnel.yml` e acrescente `--profile live` aos comandos Compose.
Primeiro suba `worker-live`, espere `/health` privado e o heartbeat estarem prontos;
depois recrie `api` com `LIVE_TRANSCRIPTION_ENABLED=true`. O worker tem
`restart: unless-stopped`, e Docker e `cloudflared-ingestify-dev.service` devem
estar habilitados no systemd para voltarem no boot. Uma conexão interrompida pelo
reboot termina e exige uma nova sessão; o processo reiniciado aquece o modelo
antes de voltar a aceitar áudio.

No servidor de desenvolvimento, o Elasticsearch usa
`ELASTICSEARCH_DATA_PATH=/data/ingestify/elasticsearch`, em um filesystem
persistente separado. Sem essa configuração, o Compose mantém o volume nomeado
`ingestify-elasticsearch-data`. Para mudar o caminho de uma instalação existente,
pare somente o Elasticsearch, copie os dados preservando permissões e ownership,
recrie o serviço e confira contagens dos índices, espaço livre e escrita real.
Mantenha a origem para recuperação; depois de novas escritas no destino, ela é
uma cópia antiga e não pode ser reativada como rollback sem reconciliar os dados.
Não remova o bloqueio de disco enquanto o filesystem continuar acima do limite:
ao voltar abaixo do high watermark, o Elasticsearch libera a escrita automaticamente.

Reserva inicial expira em 60 s; lease ativa em 45 s, renovada a cada 5 s. Slots também
expiram, inclusive se a API cair antes do commit. Sweeper marca órfãs em até 60 s.
Troca de modelo exige drenar/cancelar sessões e reiniciar somente o worker live.
Rollback: desabilitar admissão, drenar/cancelar ativas, desligar worker; manter tabela
para resultados/auditoria. Downgrade só aceita sessões terminais e não apaga fisicamente jobs/artefatos, mas remove a associação com a geração live e impede seus downloads após TTL. Use rollback mantendo a tabela para conservar os resultados.

## Validação

Em 2026-10-06, os 59 testes de `test_remote_live_captions.py`,
`test_transcription_progress.py`, `test_modal_adapter.py` e
`test_transcript_result_endpoint.py` passaram. Eles usam substitutos de Modal,
Redis e inferência; não constituem uma execução real no provedor.
`frontend/tests/transcript-progress-browser.py` exercita a página real no Chromium
com respostas HTTP controladas: chegada incremental, cursor sem duplicação,
reset após retry, resultado final e rede lenta. O caso lento reproduziu consultas
simultâneas na versão anterior; o hook agora aguarda a consulta em andamento.
Não foram medidos nesta rodada GPU remota, cold start ou latência ponta a ponta.

### Testes reais no Modal — 2026-10-06

Três jobs executaram no engine `modal_1`, GPU L4, turbo/float16, protocolo 3.
Usamos o clipe local de 30 segundos do piloto repetido 20 vezes, totalizando
600 segundos, mono16k PCM WAV. SHA256:
`7fc45ed9de6e8a47e4eefc06a081f3dc5b45ca50776ee803c2ff1148faadbc67`.
O áudio e o texto das transcrições permanecem fora do Git.

Não havia rota global de `transcription` configurada. Os fixtures receberam
reservas isoladas no ledger, sob lock do engine, com verificação de capacidade,
deployment e orçamento; cada reserva foi de US$ 0,033036, abaixo do teto de
US$ 0,05 por chamada. As tarefas passaram pela fila Celery e executor remoto
existentes, com persistência real em MySQL/Redis/MinIO/Elasticsearch e leitura
na página pública `dev.ingestify.ai`, sem respostas HTTP simuladas. Este teste
não valida admissão por upload nem placement automático de uma rota global.

| Execução | Primeira prévia HTTP após publicar | Job concluído, observado pelo cliente | Custo registrado no ledger |
| --- | ---: | ---: | ---: |
| Primeira, carregamento de modelo reportado | 24,06 s | 30,22 s | US$ 0,007163 |
| Seguinte, modelo aquecido | 12,09 s | 17,06 s | US$ 0,003771 |
| Nova instância, captura visual confirmada | 78,04 s | 84,04 s | US$ 0,021395 |

O carregamento do modelo reportado foi de 3,118 / 0 / 1,492 segundos;
esse campo não inclui todo o provisionamento/espera até a função executar.
A latência observada é desde a publicação da tarefa, não desde captura de
microfone. O custo total registrado foi US$ 0,032329, calculado com as tarifas
configuradas e duração conservadora do executor; não é reconciliação da fatura
do Modal nem inclui eventual cauda ociosa do container.

Na terceira execução, o Chromium mostrou texto decodificado ainda em
`processing` aos 78,91 segundos e depois abriu o resultado final, sem erro
JavaScript. Os 19 segmentos recebidos como prévia eram exatamente o prefixo do
JSON final, que continha 22 segmentos. Os cinco formatos retornaram HTTP 200,
os três resultados foram indexados no Elasticsearch e os ledgers terminaram em
`settled/succeeded`. Consulta de transcrição parcial sem autenticação retornou
401. Os jobs, projeto e conta exclusivos do teste foram removidos após validar;
o ledger de custo é preservado.

**Achado de qualidade temporal:** nas duas primeiras execuções, o último
timestamp chegou a 604,47 segundos para um áudio de 600 segundos. Na terceira,
terminou em 599,83 segundos. Os timestamps estavam ordenados, mas o limite da
duração falhou em duas chamadas. A duração real precisa limitar os cues antes
de declarar as legendas qualificadas. Não houve correção/redeploy do modelo
nesta rodada; não foi medido WER humano, e repetir o clipe não valida qualidade
de reuniões longas.

Captura PCM ao vivo no Modal continua sem implementação. A diferença entre
17 e 84 segundos para concluir o mesmo arquivo mostra por que readiness,
aquecimento e admissão de capacidade precisam ser medidos antes de oferecer
esse fluxo: a Queue de legendas de arquivos não fornece esse contrato.

`backend/tests/test_live_transcription.py` cobre protocolo, admissão/auth/location,
tickets, estados, corrupção de sequência, leases/restart, cancel/DELETE durante upload,
persistência e leitura depois do TTL. `frontend/tests/live-pcm-worklet.test.mjs` testa
contagem/resampling/cauda; o teste Chromium cobre captura com microfone sintético.

Runner real:

```bash
# LIVE_API_KEY ou LIVE_BEARER_TOKEN deve estar apenas no ambiente.
python scripts/benchmark_live_transcribe.py \
  --audio /caminho/local/clip.pcm --api-url http://localhost:18103 \
  --project Benchmark --output /tmp/live-report.json
```

O runner envia depois da disponibilidade da última amostra, usa deadlines cumulativos,
recebe em paralelo, aborta jitter cliente excessivo sem catch-up e confere JSON final
contra eventos imutáveis. Os stand-ins do harness isolado testam escrita/erro/durabilidade,
mas não comprovam comportamento de um cluster MySQL/MinIO/ES de produção. Resultados e
limitações medidos estão no [relatório do piloto](../benchmarks/live-transcribe-pilot.md).
Não há WER humano nem comparação Voxtral sem os respectivos testes/corpus revisado.
