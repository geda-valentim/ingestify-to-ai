# Dois workers Docling no servidor de desenvolvimento

O servidor usa dois containers `worker`, cada um com `--concurrency=1`,
`DEVICE=cuda` e hostname Celery exclusivo (`ingestify-worker@%h`). Ambos
consomem `ingestify`, com prefetch 1. Não aumente a concorrência dentro do
container: cada processo mantém seu próprio modelo e contexto CUDA.

## Configuração persistida

No `docker-compose.override.yml` local, `worker.deploy.replicas` é `2` e
`worker-audio.deploy.replicas` é `0`. O worker geral tem `WHISPER_DEVICE=cpu`
e `WHISPER_COMPUTE_TYPE=int8` para que uma URL identificada como áudio não
recarregue Whisper na GPU. O compute type precisa acompanhar o override de CPU;
herdar `float16` do overlay GPU faz CTranslate2 recusar a transcrição.
No `.env` privado:

```dotenv
AUDIO_WORKER_REPLICAS=0
LIVE_TRANSCRIPTION_ENABLED=false
LIVE_WORKER_REPLICAS=0
```

Isso pausa a transcrição dedicada e o Live para priorizar documentos. Mensagens
na fila `ingestify-audio` permanecem no Redis, e os modelos permanecem no cache.
Não interrompa capturas ou tarefas ativas: confirme `inspect active`,
`inspect reserved` e `/health` do worker Live antes de reduzir as réplicas.

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  -f docker-compose.override.yml -f docker-compose.live.yml \
  -f docker-compose.tunnel.yml --profile live \
  up -d --no-build --no-deps api worker worker-audio worker-live
```

O Docker está habilitado no boot e os dois containers usam
`restart: unless-stopped`. Não existe unidade Ingestify com `--scale` que
sobrescreva essas réplicas. Reaplique os mesmos overlays para recriar a stack;
o comando acima não altera Elasticsearch, MinIO, Vision ou workers remotos.

## Validação de 5 de outubro de 2026

Dois PDFs sintéticos de uma página foram enviados pelo endpoint `/upload`,
com o preset `fast`. Cada container recebeu e concluiu um job distinto,
usando `cuda:0`, e gravou o resultado no Elasticsearch com HTTP 201:

| Container | Job | Tempo incluindo carga |
|---|---|---|
| `ingestify-to-ai-worker-1` | `4ed0fdcc-5a78-49e9-aab0-8078946a541a` | 12,9 s |
| `ingestify-to-ai-worker-2` | `3a737da6-2652-4545-86b9-7aea34b182cc` | 13,4 s |

Após carregar ambos os modelos, a GPU usava 5.727 MiB de
16.311 MiB, incluindo outros serviços. Esse teste comprova consumo real pelos
dois workers; não representa um benchmark de PDFs grandes, OCR ou tabelas.

Os dois jobs sintéticos foram removidos pelo endpoint normal de exclusão após
validar o texto no Redis e Elasticsearch e o estado `completed` no SQL.
A evidência operacional local fica em
`tmp/docling-two-workers-evidence.json`.

## Restaurar áudio e Live

Após drenar tarefas Docling, estes comandos restauram a distribuição anterior:
um Docling, dois workers de áudio e um Live. Executar na raiz do repositório.

```bash
python3 - <<'PY'
import re
from pathlib import Path

env = Path('.env')
text = env.read_text()
for key, value in {
    'AUDIO_WORKER_REPLICAS': '2',
    'LIVE_WORKER_REPLICAS': '1',
    'LIVE_TRANSCRIPTION_ENABLED': 'true',
}.items():
    text = re.sub(rf'(?m)^{key}=.*$', f'{key}={value}', text)
env.write_text(text)

override = Path('docker-compose.override.yml')
text = override.read_text()
for service, replicas in [('worker', 1), ('worker-audio', 2)]:
    pattern = rf'(?ms)^  {service}:\n.*?(?=^  \S|\Z)'
    def restore(match):
        block = re.sub(r'replicas: \d+', f'replicas: {replicas}', match[0])
        return block.replace('WHISPER_DEVICE=cpu', 'WHISPER_DEVICE=auto')
    text, count = re.subn(pattern, restore, text)
    assert count == 1, f'Missing local service: {service}'
override.write_text(text)
PY

docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  -f docker-compose.override.yml -f docker-compose.live.yml \
  -f docker-compose.tunnel.yml --profile live \
  up -d --no-build --no-deps api worker worker-audio worker-live

docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  -f docker-compose.override.yml -f docker-compose.live.yml \
  --profile live exec worker-live python -c \
  'import urllib.request; print(urllib.request.urlopen("http://localhost:8091/health").read().decode())'
nvidia-smi
```

Confirme readiness/capacidade antes de iniciar uma captura e confira a VRAM
antes de aumentar novamente as réplicas Docling com Whisper residente.
