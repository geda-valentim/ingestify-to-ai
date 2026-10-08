"""Describe authentication from route dependencies and the image workflow contract.

Also holds the API-wide OpenAPI metadata: ``info.description``, ``info.version`` and
the ``tags`` list (order and description of every Swagger group). Every operation
must carry one of these tags and a Portuguese summary (tests/test_openapi_metadata.py).
"""
from fastapi.routing import APIRoute, APIWebSocketRoute

# 1.1.0: first bump since 1.0.0. The contract only grew backward-compatibly
# (projects, IAM, purge_source, image analysis, live...); see docs/CHANGELOG.md.
# 1.2.0: image assets of a document conversion (image_mode, page_images,
# GET /jobs/{job_id}/assets/{name}), backward compatible.
# 1.3.0: figure descriptions / OCR inlined in the markdown (describe_images,
# ocr_images; figures_* counts and assets[].description / ocr_text in the result),
# docling_preset on /convert, backward compatible.
API_VERSION = "1.3.0"

API_DESCRIPTION = """
API assíncrona que converte documentos (PDF, DOCX, HTML, PPTX, XLSX...) em Markdown,
transcreve áudio e vídeo e analisa imagens. Todo pedido vira um **job**: a resposta
traz o `job_id` na hora e o trabalho segue em workers Celery. Guias completos no
portal de documentação (`/pt/docs`); referência gerada em `/redoc` e `/openapi.json`.

## Autenticação

- **JWT** (`bearerAuth`): `POST /auth/login` devolve `access_token`; envie
  `Authorization: Bearer <token>`. `POST /auth/refresh` renova a sessão.
- **API key** (`apiKeyAuth`): crie em `POST /api-keys/` (com JWT) e envie
  `X-API-Key: <chave>`. Uma key pode ser vinculada a um projeto
  (`PATCH /api-keys/{key_id}`).
- Com os dois no mesmo request, vale o JWT. Rotas marcadas como sessão de
  administrador (`x-access: admin-session`) ou só JWT (`x-access: jwt`) recusam API key.
- No Swagger, clique em **Authorize** e preencha `bearerAuth` (só o token, sem o
  prefixo `Bearer`) e/ou `apiKeyAuth`. A autorização persiste entre recargas.
- **Primeira instalação**: `GET /auth/setup` (público) diz se a instalação ainda não tem
  usuário (`root_pending`) e se o registro exige token. O primeiro `POST /auth/register`
  de uma instalação vazia cria o **root**, a identidade de bootstrap do IAM. Em produção
  isso exige `setup_token` igual ao `ROOT_SETUP_TOKEN` do servidor (fora de produção,
  só quando ele está configurado).

## Permissões (IAM)

Cada usuário é dono dos próprios jobs, projetos, tags, API keys e conexões de datalake:
recurso de outro usuário responde 404. Rotas `/admin/*` exigem permissões de plataforma
concedidas por papéis IAM (`platform_admin`, `platform_operator`, `platform_auditor`,
`remote_engine_user`), e as rotas de engines usam os papéis de engines (`observer`,
`engine_operator`, `access_admin`...), hoje guardados como vínculos IAM em
`/admin/iam/bindings`. Root e os administradores de bootstrap equivalem a
`platform_admin`. `POST /iam/check` diz o que o chamador pode fazer; `GET /iam/permissions`
lista o catálogo. O campo `x-access` de cada operação diz a credencial exigida. Guia:
[Acesso e IAM](/pt/docs/engine-access).

## Projetos e pastas

Todo job pertence a um **projeto** (obrigatório) e, opcionalmente, a uma **pasta** do
projeto (um nível). Os endpoints que criam jobs (`/upload`, `/convert`, `/transcribe`,
`/images/*`) aceitam:

- `project`: nome do projeto. É criado se não existir (*get-or-add*). Caixa, espaços e
  acentos sobre letras latinas não contam: `Reunião` e ` reuniao ` são o mesmo projeto;
- `project_id`: ID de um projeto existente (nunca cria);
- `folder` / `folder_id`: a pasta dentro do projeto (o nome não pode ter `/`).

Sem `project`/`project_id`, o job vai para o projeto **vinculado à API key** (veja
`PATCH /api-keys/{key_id}`). Isso só vale para requests autenticados apenas pela key: com
JWT, o vínculo é ignorado. Sem projeto no request e sem vínculo, a resposta é **422**.
Um arquivo repetido só é reaproveitado dentro do mesmo projeto (`duplicate: true`).

```bash
curl -H "X-API-Key: ..." -F "file=@aula.mp3" -F "project=Aulas" -F "folder=Setembro" .../transcribe
```

## Ciclo de vida do job

`POST` devolve `job_id`; acompanhe com `GET /jobs/{job_id}` (`status`, `progress`) e
busque o resultado em `GET /jobs/{job_id}/result`. Estados (`status`):

- `pending` / `queued`: aceito, aguardando worker;
- `processing`: em execução (PDF de várias páginas: split → páginas em paralelo → merge;
  `GET /jobs/{job_id}/pages` mostra cada página);
- `completed`: concluído;
- `partial`: terminou com lacunas (ex.: algumas páginas falharam); o resultado
  preservado fica disponível e as páginas com falha podem ser refeitas
  (`POST /jobs/{job_id}/pages/{n}/retry`);
- `failed`: falhou depois das tentativas automáticas; `error` explica;
- `cancelled`: cancelado (sessões ao vivo, análise composta de imagem).

## Arquivos de origem (`purge_source`)

`/upload`, `/convert`, `/transcribe` e as oito rotas `/images/*` aceitam
`purge_source` (padrão `false`). Com `true`, os arquivos de origem (o arquivo enviado,
os PDFs por página, as cópias da imagem) são apagados quando o job termina, depois das
tentativas automáticas; o resultado fica. Para apagar depois, use
`DELETE /jobs/{job_id}/source` (200; 404 sem origem; 409 `JOB_STILL_PROCESSING`;
503 `SOURCE_DELETE_FAILED`). `GET /jobs/{job_id}` informa `source_available`,
`source_deleted_at` e `source_deletable`. Sem origem, o PDF de página responde 410
`SOURCE_PURGED` e o retry de página 409 `SOURCE_NOT_AVAILABLE`.

## Imagens da conversão (`image_mode`, `page_images`)

`/upload` e `/convert` aceitam `image_mode` (`none`, padrão: o markdown mantém
`<!-- image -->`; `referenced`: cada figura vira um PNG referenciado no markdown como
`![Image](/jobs/{job_id}/assets/{name})`) e `page_images` (`true`: cada página do PDF
renderizada como PNG). `GET /jobs/{job_id}/result` lista `assets` (`name`, `kind`
`picture`|`page`, `page`, `bbox`, `sha256`, `mime`, `width`, `height`, `size_bytes`,
`url`) e `assets_skipped`; cada imagem sai em `GET /jobs/{job_id}/assets/{name}` (sempre
o job principal, também num PDF dividido). Com `purge_source=true` as imagens ficam
`ASSET_RETENTION_SECONDS` depois do fim do job (`assets_expire_at` em
`GET /jobs/{job_id}`) e então são apagadas; `DELETE /jobs/{job_id}/source` apaga na hora.
Depois disso a rota responde 410 `SOURCE_PURGED`.

## Idempotência (Full Analysis e rostos)

`/images/analyze` com `mode=full` e `/images/faces` exigem o header `Idempotency-Key`
(1..128 caracteres). A mesma chave com o mesmo pedido devolve o mesmo job enquanto a
tentativa está na fila, rodando ou concluída; depois que ela falha de vez, a mesma chave
abre a tentativa seguinte (`attempt` + 1, job novo). Chave usada com outro pedido: 409;
job da chave excluído: 410 (use outra chave). `purge_source` não entra na comparação.

## Erros

Erros HTTP vêm em `{"detail": ...}`: texto, lista de validação (422) ou objeto. Recusas
com código (jobs, engines, perfis de execução, acesso, IAM, root) trazem
`{"detail": {"code": "...", "message": "...", "next_steps": [...]}}`, com `cause`
(o gate interno quando um código genérico embrulha outro) e `technical` (texto original)
quando houver. Use `code` para decidir; `message` é para pessoas. Falhas não tratadas
respondem 500 com `{"error": {"code": "INTERNAL_ERROR", "message": "..."}}`.

## Limites de taxa

Login: `RATE_LIMIT_PER_MINUTE` tentativas por IP por minuto (padrão 10) e bloqueio
temporário da conta após `LOGIN_MAX_FAILED_ATTEMPTS` falhas (padrão 5, por
`LOGIN_LOCKOUT_SECONDS`, padrão 900 s). Registro: `REGISTER_LIMIT_PER_HOUR` por IP (padrão
5). Excedido, a resposta é **429**. Uploads respeitam `MAX_FILE_SIZE_MB` (413).
"""

# Swagger order: user workflows first, then administration, then machine routes.
OPENAPI_TAGS = [
    {"name": "Authentication", "description": "Registro, login, renovação do JWT, usuário atual e o estado de primeira instalação (root)."},
    {"name": "Projects", "description": "Projetos e pastas que organizam os jobs; resolução de nomes para *get-or-add*."},
    {"name": "Conversion", "description": "Criar jobs (upload, conversão por URL/Drive/Dropbox, transcrição), acompanhar estado, páginas e resultado, buscar, excluir jobs e apagar os arquivos de origem."},
    {"name": "Vision", "description": "Análise de imagens: descrição, OCR, tarefas de visão, Full Analysis e detecção facial; capacidades e cancelamento."},
    {"name": "Live transcription", "description": "Sessões de transcrição ao vivo: criar (ticket do WebSocket), consultar e cancelar."},
    {"name": "Tags", "description": "Tags do usuário e tags de cada job."},
    {"name": "Datalakes", "description": "Conexões S3/MinIO de destino, buckets, prévia de particionamento e entrega do resultado de um job."},
    {"name": "API Keys", "description": "Criar, listar, vincular a um projeto e revogar API keys (requer JWT)."},
    {"name": "IAM", "description": "Catálogo de permissões, verificação das permissões do chamador e vínculos (bindings) de papéis de plataforma e de engines."},
    {"name": "Admin & Monitoring", "description": "Administração da plataforma: estatísticas, jobs travados, retry em massa, limpeza e saúde do broker e do monitoramento."},
    {"name": "Admin - Engines", "description": "Engines de processamento: cadastro, funcionalidades, GPUs, orçamento, credenciais, testes, benchmarks e rotas por funcionalidade."},
    {"name": "Admin - Engine control", "description": "Controle de runtime das engines: adaptadores, capacidades, perfis de runtime, planos e operações (com eventos e stream SSE)."},
    {"name": "Admin - Execution profiles and access", "description": "Perfis de execução (revisões, publicação, vínculo) e acesso às engines: políticas, papéis, concessões, atributos de ambiente e principais."},
    {"name": "Engine hosts", "description": "Rotas internas de máquina para o agente de host das engines (`X-Engine-Host-Token`); não são para usuários."},
    {"name": "Status", "description": "Identificação e saúde da API (públicas)."},
]


def dependency_names(dependant):
    names = {getattr(dependant.call, '__name__', '')}
    for child in dependant.dependencies:
        names.update(dependency_names(child))
    return names


def platform_declaration(dependant):
    """
    The spec 0014 `require(...)` of a platform/IAM permission in the route's tree,
    if any: what `require_admin` / `require_admin_session` were before, so the
    published access labels stay the same (CA12).
    """
    from api.iam_deps import declaration_of
    from shared.iam import catalog

    stack = [dependant]
    while stack:
        current = stack.pop()
        decl = declaration_of(current.call)
        if decl is not None and decl.kind == 'require' and catalog.permission(decl.permission).level != catalog.OWNER:
            return decl
        # Spec 0018: /admin/iam/bindings* are administrative routes of either family.
        if decl is not None and decl.kind == 'iam_or_engine_access':
            return decl
        stack.extend(current.dependencies)
    return None


def annotate_openapi(schema, routes):
    from shared.schemas import ImageAnalyzeOptions, VisionGenerationOptions
    for model in (ImageAnalyzeOptions, VisionGenerationOptions):
        definition = model.model_json_schema(ref_template='#/components/schemas/{model}')
        schema['components']['schemas'].update(definition.pop('$defs', {}))
        schema['components']['schemas'][model.__name__] = definition
    schema['components']['securitySchemes']['engineHostAuth'] = {
        'type': 'apiKey', 'in': 'header', 'name': 'X-Engine-Host-Token',
        'description': 'Identidade privada do host; tokens de usuário não a substituem.',
    }
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        names = dependency_names(route.dependant)
        platform = platform_declaration(route.dependant)
        for method in route.methods:
            operation = schema['paths'].get(route.path, {}).get(method.lower())
            if operation is None:
                continue
            if route.path.startswith('/internal/engine-hosts/'):
                operation.update(security=[{'engineHostAuth': []}], **{'x-access': 'engine-host'})
            elif 'require_admin_session' in names or (platform is not None and platform.session):
                operation.update(security=[{'bearerAuth': []}], **{'x-access': 'admin-session'})
            elif 'access_session' in names:
                operation.update(security=[{'bearerAuth': []}], **{'x-access': 'jwt'})
            elif 'require_admin' in names or platform is not None:
                operation['x-access'] = 'admin'
            else:
                operation['x-access'] = ('jwt' if operation['security'] == [{'bearerAuth': []}] else 'user') if operation.get('security') else 'public'
    for path in ('/images/analyze', '/images/analyze/upload', '/images/faces', '/images/faces/upload'):
        operation = schema['paths'][path]['post']
        operation['x-contract-notes'] = ['Operações compostas exigem Idempotency-Key. Mesma chave e payload retornam o mesmo job; payload divergente retorna 409 e job excluído retorna 410. wait=false retorna 202; wait=true pode retornar 504 mantendo o job. Full sem perfil conserva v1; v2 inclui rostos e expressões.']
        operation['responses'].update({'409': {'description': 'Chave utilizada com outra solicitação.'}, '410': {'description': 'Job da chave excluído; envie uma chave nova.'}})
    # Public status routes: their own group instead of Conversion / "default"
    for path in ('/', '/health'):
        schema['paths'][path]['get']['tags'] = ['Status']
    schema['paths']['/jobs/{job_id}/result']['get']['responses']['202'] = {'description': 'Análise composta em andamento; consulte poll_url/result_url.'}
    schema['paths']['/images/{job_id}/cancel']['post']['x-contract-notes'] = ['Cancela Full Analysis ou análise facial do próprio usuário, preservando checkpoints concluídos. Não cancela tarefas de visão single.']
    schema['x-websockets'] = [{
        'path': route.path,
        'authentication': 'Ticket descartável obtido em POST /transcribe/live/sessions; primeiro frame JSON '
            '{"type":"authenticate","protocol":1,"ticket":"..."}. A versão deve corresponder à sessão; não envie credenciais na URL.',
        'protocol': 'Protocolos 1 e 2 usam PCM s16le, 16 kHz, mono e cabeçalho little-endian '
            'seq:uint32/offset_samples:uint64. Protocolo 2 exige diarize=true e os gates de qualificação '
            'de diarização; consulte o guia de live. Controle finish/cancel em JSON.',
    } for route in routes if isinstance(route, APIWebSocketRoute)]
    return schema
