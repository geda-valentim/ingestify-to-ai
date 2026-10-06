# WhisperX e falantes — canário da spec 0006

Atualizado em 2026-10-05. Implementação atrás de configuração explícita; o provider
padrão continua `faster-whisper` até passar pelos gates da
[spec 0006](../specs/0006-whisperx-e-identificacao-de-falantes.md).

## Contrato de arquivos

`POST /transcribe`, `/upload` e `/convert` recebem `diarize`, `min_speakers`,
`max_speakers` e `include_word_timestamps` como multipart. Limites são opcionais,
inteiros de 1 a 20, com mínimo ≤ máximo. Sem limites, a contagem é livre; mais de
20 pessoas falha com `SPEAKER_LIMIT_EXCEEDED`. Providers legados não aceitam
`diarize=true`. Pedido conhecido em documento recebe 422; descoberta posterior
incompatível falha o job. Configuração sem prontidão recebe 503.

Antes do enqueue, SQL guarda o perfil efetivo e seu SHA256: provider, modelos e
revisões, idioma, beam/temperatura, VAD, opções de falantes e exposição de palavras.
O mesmo arquivo em um projeto só reutiliza uma transcrição com perfil igual.
Retry e URLs cujo tipo aparece após download mantêm o snapshot original.
Tags, pasta, nome e formato de download não entram no hash.

O novo JSON contém `schema_version: 2`, catálogo `speakers`, `diarization.turns`,
`alignment` e provenance. `SPEAKER_00` só identifica uma voz nesse job.
Palavras sem tempo/falante usam null; `alignment_score` não substitui probability.
Sobreposição permanece nos turnos. Empate ou ausência de interseção não atribui
falante por proximidade. Segmentos só são divididos quando as palavras alinhadas
sustentam a mudança. Texto sem alinhamento continua presente.

A UI mostra catálogo/contagem e rótulos; Markdown, TXT, SRT e VTT usam `Falante N:`
quando existe atribuição. JSON mantém texto limpo e IDs separados. Resultados
antigos continuam legíveis. Durante o processamento, os estados são transcribing,
aligning, diarizing e saving; as parciais só representam ASR.

## Operação e pesos

Aplicar a [migração 0006](../../scripts/migrate_0006_transcription_profiles.py)
antes do enqueue novo. Ela acrescenta perfil/hash nullable e fence de tentativa;
nenhum resultado antigo é reescrito. Ver opções do script antes de aplicar.

A imagem `docker/Dockerfile.audio` usa Python 3.11 e locks específicos CPU/CUDA,
sem mudar os workers Docling/Florence. O overlay `docker-compose.whisperx.yml` é
opt-in. O worker executa com pesos locais, `HF_HUB_OFFLINE=1` e
`TRANSFORMERS_OFFLINE=1`; credenciais HF servem somente ao provisionamento.

`WHISPERX_MODEL_DIR/manifest.json` descreve diretórios/arquivos relativos à própria
raiz, com revisões imutáveis de 40 ou 64 hexadecimais. Estrutura:

```json
{
  "qualified": false,
  "asr": {"path": "asr", "model": "turbo", "revision": "<commit>"},
  "vad": {"path": "silero", "revision": "<commit>"},
  "aligners": {
    "pt": {"path": "align/pt", "model": "<modelo>", "revision": "<commit>"},
    "en": {"path": "align/en", "model": "<modelo>", "revision": "<commit>"}
  },
  "diarizer": {"path": "diarizer/config.yaml", "model": "pyannote/speaker-diarization-community-1", "revision": "<commit>"}
}
```

O config local do diarizador deve apontar também os pesos dependentes locais.
Para alinhador torchaudio, declarar `backend: "torchaudio"`, `model` igual ao
bundle oficial e `path` do checkpoint com o nome original; o hash identifica o
checkpoint. Silero carrega somente um checkout local fixado, com `source=local`.
Aceitar termos e disponibilizar token é ação do operador; nenhum segredo vai no
manifesto, perfil, tasks, Redis ou Git.

Copiar as mesmas revisões para `WHISPERX_ASR_REVISION`,
`WHISPERX_DIARIZATION_REVISION`, `WHISPERX_VAD_REVISION` e
`WHISPERX_ALIGNER_MANIFEST` (mapa JSON idioma→entry). Divergência do snapshot SQL
recusa a execução, em vez de trocar o modelo silenciosamente.

Depois de validar importação/pip check/pesos/inferência real no alvo, o manifesto
pode declarar `qualified: true` para o canário. Isso **não aprova** os gates de
qualidade/VRAM/concorrência para alterar o default global. Usar readiness explícita
`WHISPERX_DIARIZATION_READY=true` somente quando o deployment está apto a servir
as opções solicitadas. `WHISPERX_DIARIZATION_DEFAULT=false` conserva opt-in.

Builds isolados, sem subir serviços:

```bash
docker build -f docker/Dockerfile.audio --build-arg AUDIO_TARGET=cpu -t ingestify-audio-whisperx:cpu .
docker build -f docker/Dockerfile.audio --build-arg AUDIO_TARGET=cuda -t ingestify-audio-whisperx:cuda .
```

Locks foram resolvidos com UV para Python 3.11 Linux x86_64; build/import/inferência
CUDA, PT-BR e diarização real ainda precisam das evidências exigidas na spec.

## Persistência e Compute

Resultados schema 2 usam `transcripts/{job}/attempts/{id}/transcript.{format}`.
Quatro uploads confirmados e indexação ES precedem conclusão SQL e purge_source.
SQL serializa a publicação com cancelamento/retry/exclusão; tentativa antiga não
pode substituir a ativa. A API só expõe o resultado concluído da tentativa ativa.
Falhas limpam somente os objetos daquela tentativa e conservam o áudio para retry.
A exclusão limpa o prefixo inteiro, incluindo staging abandonado.

Modal protocolo 4 preserva schema 2 e palavras nullable. Deployment anuncia
capabilities; perfis WhisperX não são colocados em deployment legado. Configure
`whisperx_manifest` no engine com o mesmo manifesto local provisionado para
construir imagem de áudio Python 3.11. Fontes, lock e manifesto entram no fingerprint.
`WHISPERX_MODEL_DIR` só é caminho de build e não contém token. Deployment mudou:
benchmarks anteriores não qualificam a nova pipeline; placement exige override de
VRAM medido e estimativas WhisperX não reutilizam velocidade histórica do legado.

Rollback altera provider/config/imagem para novos jobs e mantém leitores schema 2.
Perfis WhisperX já enfileirados exigem modelo compatível: drenar ou encerrar essas
tentativas antes de retirar a imagem. Não reencaminhar o perfil para o legado.

## Evidência atual

Teste real do iterador WhisperX 3.8.6 em CPU, áudio público de 30 s: um lote,
80 palavras, 10,167 s de ASR e pico RSS de 2.599 MiB. Texto e offsets iguais ao
upstream; opções/tokenizer residentes preservados; cancelamento antes do decode
verificado. É uma fixture curta em inglês, não valida diarização nem latência live.
O acesso Community-1 permanece bloqueado por HF 401 no ambiente de teste.

Os testes de contrato cobrem palavras sem tempo, scores, sobreposição/empate,
segmentos, formatos, Modal, perfil/deduplicação e fault injection dos quatro uploads,
ES, cancelamento e tentativa superada. Builds limpos, corpus PT-BR, DER/WER,
2 h/concorrência/VRAM e rollout continuam gates abertos. A captura com falantes usa
a fatia online separada da spec, com Diart isolado; não roda WhisperX batch no EOF.

Segundo probe de progresso/cancelamento: a mesma fixture repetida três vezes
(90 s, sem representar três gravações distintas) gerou três chunks de 80 palavras
em 8,142 / 16,402 / 24,862 s desde o início; cancelamento após o primeiro chunk
impediu o decode do próximo. Pico RSS: 2.501 MiB. Evidência isolada de emissão
incremental entre lotes; não é corpus para DER/WER nem prova de memória em 2 h.

Probe adicional do runtime completo, com o lock CPU do worker instalado e rede
isolada: ASR + alinhamento torchaudio + validação schema 2 produziram 80 palavras
com tempos no mesmo áudio de 30 s. Foram 31,662 s incluindo carregamento dos
modelos, em CPU limitada a dois núcleos; pico RSS de 2.474 MiB sob limite de 3 GiB.
Essa execução revelou e corrigiu a normalização de escalares NumPy do alinhador
para números JSON, mantendo a validação estrita na fronteira remota. O manifesto
de teste permaneceu `qualified: false`; a revisão do checkout Silero foi registrada
como hash de conteúdo, não como commit upstream. Diarização estava desativada.
Não é medição aquecida, build limpo Docker, validação CUDA ou qualificação de falantes.
