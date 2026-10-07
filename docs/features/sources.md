# Fontes de documentos: arquivo, URL, Google Drive, Dropbox

> Contratos dos endpoints revisados em 2026-10-06. Campos, modelos e autorização:
> [referência completa da API](../api-reference.md). As datas abaixo também registram revisões da implementação/operação.

> Verificado contra o código em 2026-10-04. Fonte da verdade:
> [backend/workers/sources.py](../../backend/workers/sources.py),
> [backend/api/routes.py](../../backend/api/routes.py) (`POST /convert`),
> [backend/workers/tasks.py](../../backend/workers/tasks.py) (`_resolve_uploaded_file`).

## O que faz

`POST /convert` aceita quatro tipos de fonte (`source_type`). Cada um tem um handler
(`SourceHandler`) que, dentro do worker, transforma a fonte num arquivo local antes da
conversão Docling (ver [conversion.md](conversion.md)). `POST /upload` é equivalente a
`source_type=file`.

Arquivos em S3/MinIO/GCS/Azure usam `POST /datalakes/import`, não um novo
`source_type` no `/convert`. Origem e destino são independentes; veja
[datalakes.md](datalakes.md). As chamadas exigem projeto salvo API key vinculada.

| `source_type` | `source` | Credencial | Status |
|---|---|---|---|
| `file` | ignorado | — | Funciona (`/upload` ou `/convert`). |
| `url` | URL `http(s)` pública | — | Funciona, com proteção SSRF. |
| `gdrive` | file ID do Google Drive | token OAuth2 no header `X-Source-Token` | Handler disponível; veja limites abaixo. |
| `dropbox` | path (ex.: `/docs/a.pdf`) | access token no header `X-Source-Token` | Handler disponível; exige o token do provedor. |

## Como usar

### Arquivo

```bash
curl -X POST http://localhost:8000/convert -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "source_type=file" -F "file=@documento.docx" -F "project=Documentos"
```

Para `source_type=file`, a API **descarta** qualquer `source` enviado pelo cliente: o
worker só lê o arquivo que a própria API gravou em `{TEMP_STORAGE_PATH}/uploads/{job_id}/`
(`_resolve_uploaded_file` recusa caminhos fora desse diretório). O nome do arquivo é
sanitizado (`sanitize_upload_filename`) para impedir path traversal.

### URL

```bash
curl -X POST http://localhost:8000/convert -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "source_type=url" -F "source=https://example.com/relatorio.pdf" -F "name=Relatório Q3" -F "project=Documentos"
```

O `URLHandler`:

- aceita só `http`/`https`, sem credenciais na URL;
- resolve o host e **recusa** endereços não públicos (loopback, redes privadas,
  link-local/metadata de nuvem, NAT64 que embute IPv4 privado, etc.);
- conecta no IP já validado (evita DNS rebinding), mantendo `Host` e SNI originais;
- segue até 5 redirects, revalidando cada destino;
- timeout de 30 s; interrompe o download acima de `MAX_FILE_SIZE_MB`;
- nomeia o arquivo pelo último segmento do path; sem extensão, assume `.pdf`.

O frontend expõe essa fonte na aba "URL" do dashboard.

### Google Drive / Dropbox

```bash
curl -X POST http://localhost:8000/convert \
  -H "Authorization: Bearer <jwt-do-ingestify>" \
  -H "X-Source-Token: <token-do-provedor>" \
  -F "source_type=gdrive" -F "source=<file-id>" -F "project=Documentos"
```

`Authorization` (ou `X-API-Key`) autentica no Ingestify e **nunca** é repassado ao provedor nem
colocado na mensagem do Celery (correção do S-01, [SECURITY_REVIEW.md](../SECURITY_REVIEW.md)). O
token do provedor vai no header próprio `X-Source-Token` (`400` se ausente nessas fontes); a API o
guarda numa chave Redis de vida curta (`job:{id}:source_token`, 6 h), o worker o lê na hora do
download e a apaga assim que o download dá certo (uma falha de download a mantém para o retry).
Ele não aparece nos argumentos da task, no result backend nem em reentregas. O handler do Drive
usa `googleapiclient` (`files().get_media`); o do Dropbox usa o SDK `dropbox` (`files_download`).

## O que acontece por dentro

1. A API valida `source_type` (`400` se inválido) e a presença de `source`/`file`.
2. Cria o job (MySQL + Redis), guarda o `X-Source-Token` (Drive/Dropbox) no Redis e enfileira
   `process_conversion` com `source_type` e `source` — nenhuma credencial na mensagem.
3. No worker, `get_source_handler(source_type).download(...)` produz o arquivo local; a
   partir daí o fluxo é o mesmo da conversão.

Somente arquivos enviados (`file`) vão para o MinIO (`ingestify-uploads`); documentos
baixados de URL/Drive/Dropbox ficam apenas no diretório temporário do job.

## Configuração

| Variável | Default | Efeito |
|---|---|---|
| `MAX_FILE_SIZE_MB` | `50` | Limite do upload e do download por URL. |
| `GOOGLE_DRIVE_CREDENTIALS_PATH` | `/secrets/gdrive.json` | Declarada, **não lida** por nenhum código. |
| `DROPBOX_APP_KEY` / `DROPBOX_APP_SECRET` | vazio | Declaradas, **não lidas** por nenhum código. |

## Limites e lacunas conhecidas

- Downloads do Drive e do Dropbox não respeitam `MAX_FILE_SIZE_MB` (o arquivo inteiro é
  lido em memória).
- O arquivo do Drive é salvo como `gdrive_<file-id>`, sem extensão; o Docling depende da
  extensão para detectar o formato.
- Não há validação de tipo/MIME na API para nenhuma fonte.
- Não há fonte de crawler/scraping: ver [crawler.md](crawler.md).
