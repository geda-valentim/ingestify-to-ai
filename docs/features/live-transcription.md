# Transcrição ao vivo

A captura de microfone envia áudio PCM durante a sessão e recebe legendas antes
do EOF. `POST /transcribe` e seus jobs de arquivo continuam com o contrato atual.
A live permanece **desabilitada por padrão**; a implementação não autoriza sua
ativação em produção antes dos gates da [spec 0005](../specs/0005-transcricao-ao-vivo.md).

## Uso

Abra `/live`, selecione projeto e pasta, permita o microfone e inicie. A captura
começa após `session.ready`; texto provisório substitui a revisão anterior, e
segmentos confirmados aparecem imediatamente. **Finalizar** envia a cauda e espera
persistência; o resultado abre na página existente do job, com TXT/JSON/VTT/SRT.
**Cancelar** encerra a sessão e descarta parciais. Queda de conexão exige nova sessão.
O navegador precisa de HTTPS ou localhost; AudioWorklet converte a captura mono para
16 kHz s16le. O áudio original não é armazenado.

## API e protocolo 1

- `POST /transcribe/live/sessions`: JWT ou API key, mesmas regras de projeto/pasta,
  tags e precedência JWT dos uploads. JSON inclui `project`/`project_id`,
  `folder`/`folder_id`, `name`, `tags`, `language="pt"` e opcionalmente
  `audio={"encoding":"pcm_s16le","sample_rate":16000,"channels":1}`.
- `GET /transcribe/live/sessions/{job_id}`: estado, duração e motivo de término.
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
`LIVE_NOT_READY` ou `LIVE_CAPACITY_FULL`; a live nunca entra na fila de arquivos.
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

Reserva inicial expira em 60 s; lease ativa em 45 s, renovada a cada 5 s. Slots também
expiram, inclusive se a API cair antes do commit. Sweeper marca órfãs em até 60 s.
Troca de modelo exige drenar/cancelar sessões e reiniciar somente o worker live.
Rollback: desabilitar admissão, drenar/cancelar ativas, desligar worker; manter tabela
para resultados/auditoria. Downgrade só aceita sessões terminais e não apaga fisicamente jobs/artefatos, mas remove a associação com a geração live e impede seus downloads após TTL. Use rollback mantendo a tabela para conservar os resultados.

## Validação

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
