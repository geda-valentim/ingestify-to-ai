# Detecção de falantes — teste de 2026-10-05

**O Ingestify atual transcreve, mas não identifica nem conta falantes.** Um áudio
público de 30 segundos, anotado com duas pessoas e fala sobreposta, gerou texto e
timestamps sem qualquer identificação de pessoa. Uma alternativa leve testada
separadamente conseguiu comparar vozes com amostras de referência, mas falhou em
contar automaticamente as pessoas e em um controle de alteração de tom. Isso
não libera diarização nem estabelece suporte a essa funcionalidade no produto.

## Evidência do código existente

- `backend/workers/engines/whisper_core.py`: caminho compartilhado entre
  transcrição local e remota; segmentos têm `start`, `end`, `text` e, quando
  solicitado, `words`. Não há embedding de voz, agrupamento, `speaker_id` ou
  contagem de pessoas. O VAD seleciona fala; não identifica quem fala.
- `backend/workers/audio/faster_whisper_transcriber.py`: delega a esse mesmo core.
- `backend/workers/live/decoder.py`: eventos finais têm `segment_id`,
  `utterance_id`, timestamps e texto. `utterance_id` aumenta a cada bloco
  confirmado; não representa a identidade de uma pessoa.
- `docs/specs/0005-transcricao-ao-vivo.md`: diarização está explicitamente fora
  do escopo da live implementada.

Revisão base inspecionada: `073291b2e9abcd69f5bde5bf1cd4b9ed7125ea76`, com a árvore
de trabalho de desenvolvimento de 2026-10-05. O teste executou o core real, sem
simular a saída do modelo e sem criar jobs ou chamar a API.

## Áudio e referência

Usamos `tutorials/assets/sample.wav` e `sample.rttm` do
[tutorial oficial pyannote.audio](https://github.com/pyannote/pyannote-audio/blob/b749285c5cdd4636b2edc7f766f1352c8dde9369/tutorials/applying_a_pipeline.ipynb),
revisão `b749285c5cdd4636b2edc7f766f1352c8dde9369`. O repositório publica
[licença MIT](https://github.com/pyannote/pyannote-audio/blob/b749285c5cdd4636b2edc7f766f1352c8dde9369/LICENSE).
Não redistribuímos o áudio; o runner baixa o asset original e valida seu hash.

| Propriedade | Referência |
|---|---|
| Formato | WAV, mono, 16 kHz, 30 s |
| Pessoas anotadas | `speaker90`, `speaker91` |
| Turnos anotados | 10 |
| Fala sobreposta anotada | 1,89 s |
| WAV SHA256 | `c319b4abca767b124e41432d364fd7df006cb26bb79d09326c487d606a134e6e` |
| RTTM SHA256 | `d78fe62c69d8e6dcbb42c26adfce83faccb374c5a1e6d987fe37f85f1c173c87` |

Os IDs vêm da anotação RTTM, não da percepção de voz grave/aguda. O áudio é em
inglês. A fixture portuguesa já existente não tem referência humana de falantes;
por isso não serve para provar diarização. Nenhum áudio privado foi enviado a
serviço externo e nenhum texto de transcrição foi incluído no Git.

## Resultado do backend atual

Executamos `whisper_core.transcribe` com turbo, CPU/int8, idioma `en`, beam 1 e
timestamps por palavra. O modelo veio do cache local, revisão
`0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` de
`mobiuslabsgmbh/faster-whisper-large-v3-turbo`. faster-whisper 1.2.1,
CTranslate2 4.8.2 e NumPy 2.5.3.

| Resultado observado | Valor |
|---|---|
| Segmentos de transcrição | 13 |
| Palavras retornadas | 80 |
| Campos dos segmentos | `start`, `end`, `text`, `words` |
| Campos das palavras | `start`, `end`, `word`, `probability` |
| Identificação de falantes | Ausente |
| Contagem de falantes | Ausente |

Os 13 segmentos são divisões da transcrição, não 13 pessoas nem os dez turnos da
referência. Não avaliamos WER ou recuperação de fala simultânea: o RTTM fornece
tempos e identidades, mas não uma transcrição humana para medir reconhecimento.

## Alternativa local: embeddings de voz

Testamos [Resemblyzer 0.1.4](https://github.com/resemble-ai/Resemblyzer), modelo
de embeddings de 256 dimensões, em CPU, separado dos workers do produto. Pesos
SHA256 `39373b86598fa3da9fcddee6142382efe09777e8d37dc9c0561f41f0070f134e`.
O pacote e o modelo usados estão sob a licença Apache 2.0 do projeto.

Criamos duas amostras de referência sem sobreposição: pessoa 90 em
18,70–21,40 s e pessoa 91 em 22,00–24,50 s. Cinco trechos de avaliação vieram de
intervalos diferentes, sem reutilizar o áudio dessas referências. Os limites
foram escolhidos usando o RTTM; esta etapa não testa segmentação automática.

| Pessoa real | Trecho | Similaridade com 90 | Similaridade com 91 | Atribuição |
|---|---|---:|---:|---|
| 90 | 8,40–9,80 s | 0,808 | 0,701 | 90 |
| 90 | 11,20–14,40 s | 0,888 | 0,712 | 90 |
| 90 | 28,60–30,00 s | 0,739 | 0,715 | 90 |
| 91 | 14,90–17,90 s | 0,794 | 0,859 | 91 |
| 91 | 24,60–27,70 s | 0,761 | 0,874 | 91 |

Comparar cada trecho às duas referências acertou **5/5**. O terceiro trecho tem
margem de apenas 0,024; esse pequeno teste não estabelece um limiar confiável.
Agrupamento sem informar o número de pessoas, com distância cosseno, average
linkage e limiar previamente fixado em 0,35, retornou **um grupo**, apesar de
haver duas pessoas; ARI = 0. Não ajustamos o limiar depois de ver o resultado.

Também alteramos o tom de dois trechos em −2 e +2 semitons, mantendo a origem na
mesma pessoa. A atribuição acertou **3/4** controles: a pessoa 90 com +2 semitons
foi atribuída à pessoa 91. Essa transformação sintética também altera o espectro
vocal; não equivale perfeitamente a uma pessoa mudando a entonação naturalmente.
É um controle de robustez e demonstra por que tom diferente não prova outra
identidade. A execução de embeddings, incluindo compilação inicial e alterações
de tom, levou 13,17 s, sem utilização de GPU.

## Implicação para uma implementação futura

É tecnicamente viável acrescentar diarização para produzir `SPEAKER_00`,
`SPEAKER_01` etc. e associar esses IDs aos timestamps já existentes. **Essa
funcionalidade ainda não está implementada nem validada no Ingestify.**
Embeddings com limites conhecidos e referências não substituem uma pipeline que
detecta turnos, sobreposições e quantidade de falantes de forma automática.

Uma candidata é
[pyannote speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1),
que documenta diarização local e saída de falantes. Não executamos essa pipeline:
os pesos exigem aceitação das condições e token Hugging Face. Não aceitamos
condições ou cadastramos dados em nome do usuário. Antes de escolher a solução,
precisamos medir DER com sobreposição, português, três ou mais pessoas, ruído,
mesma pessoa com prosódia diferente, e o custo de GPU em concorrência com a live.
O relatório não afirma latência ou acurácia de uma pipeline que não foi testada.

## Reprodução isolada

Runner: `scripts/benchmark_speaker_detection.py`. Ele verifica os hashes e
retorna apenas metadados/métricas; não salva transcrições, embeddings ou áudio de
jobs do produto. Os comandos abaixo assumem o cache e a imagem já presentes no
host de desenvolvimento, executados na raiz do repositório.

```bash
speaker_probe_dir=/tmp/ingestify-speaker-validation
mkdir -p "$speaker_probe_dir"
chmod 700 "$speaker_probe_dir"
python3 scripts/benchmark_speaker_detection.py prepare --fixture-dir "$speaker_probe_dir"

docker run --rm --name ingestify-speaker-current-probe --cpus 2 --memory 4g --network none \
  -e HF_HUB_OFFLINE=1 -e HF_HOME=/models/huggingface \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e PYTHONPATH=/app \
  -v "$PWD/backend:/app:ro" \
  -v "$PWD/scripts/benchmark_speaker_detection.py:/benchmark.py:ro" \
  -v "$speaker_probe_dir:/probe" -v ingestify-hf-cache:/models/huggingface:ro \
  --entrypoint python ingestify-to-ai-worker-live:latest /benchmark.py current \
  --fixture-dir /probe --output /probe/current-summary.json \
  --model-path /models/huggingface/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/snapshots/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf

docker run --rm --name ingestify-speaker-deps-probe --cpus 2 --memory 2g \
  -v "$speaker_probe_dir:/probe" \
  -v "$PWD/scripts/requirements-speaker-benchmark.txt:/requirements.txt:ro" \
  --entrypoint python ingestify-to-ai-worker-live:latest \
  -m pip install --no-cache-dir --target /probe/python --no-deps -r /requirements.txt

docker run --rm --name ingestify-speaker-embedding-probe --cpus 2 --memory 3g --network none \
  -e PYTHONPATH=/probe/python -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
  -e NUMBA_CACHE_DIR=/probe/numba -v "$speaker_probe_dir:/probe" \
  -v "$PWD/scripts/benchmark_speaker_detection.py:/benchmark.py:ro" \
  --entrypoint python ingestify-to-ai-worker-live:latest /benchmark.py embeddings \
  --fixture-dir /probe --output /probe/embedding-summary.json
```

Imagem testada: `sha256:d96a66c5c2439c2a481816167694e49b8818a945c13a1d12e1e587bf3d181bff`.
A tag pode mudar; o hash identifica o ambiente usado. O teste opcional instala
dependências apenas no diretório temporário, sem alterar imagens ou workers.
Versões da alternativa: torch 2.13.0+cu129, NumPy 2.2.6, librosa 0.11.0,
scikit-learn 1.9.1, numba 0.68.0 e llvmlite 0.50.0. Nenhum serviço foi reiniciado.
