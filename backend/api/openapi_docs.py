"""Documentation metadata derived from the actual route dependencies."""
from fastapi.routing import APIRoute, APIWebSocketRoute

from shared.transcripts import TRANSCRIPT_CONTENT_TYPES


def dependency_names(dependant):
    names = {getattr(dependant.call, '__name__', '')}
    for child in dependant.dependencies:
        names.update(dependency_names(child))
    return names


def annotate_openapi(schema, routes):
    from shared.audio_capabilities import AudioDecodingOptions
    audio_options = AudioDecodingOptions.model_json_schema(ref_template='#/components/schemas/{model}')
    schema['components']['schemas'].update(audio_options.pop('$defs', {}))
    schema['components']['schemas']['AudioDecodingOptions'] = audio_options
    from shared.document_capabilities import DocumentOptions, native_catalog, document_capabilities
    import copy
    def register_docling_model(name, original):
        model = copy.deepcopy(original)
        definitions = model.pop('$defs', {})
        def references(value):
            if isinstance(value, dict):
                return {key: '#/components/schemas/Docling' + item.rsplit('/', 1)[-1] if key == '$ref' and item.startswith('#/$defs/') else references(item) for key, item in value.items()}
            if isinstance(value, list):
                return [references(item) for item in value]
            return value
        schema['components']['schemas'].update({'Docling' + key: references(value) for key, value in definitions.items()})
        schema['components']['schemas'][name] = references(model)
    register_docling_model('DoclingPipelineOptions', document_capabilities().pipeline_schema)
    exports = {}
    for fmt, metadata in native_catalog()['exports'].items():
        name = 'DoclingExport' + ''.join(word.title() for word in fmt.split('_'))
        register_docling_model(name, metadata['parameters_schema'])
        exports[fmt] = {'$ref': '#/components/schemas/' + name}
    document_schema = DocumentOptions.model_json_schema(ref_template='#/components/schemas/{model}')
    document_schema['properties']['pipeline'] = {'$ref': '#/components/schemas/DoclingPipelineOptions'}
    document_schema['properties']['export_options'].update(properties=exports, additionalProperties=False)
    schema['components']['schemas']['DocumentOptions'] = document_schema
    schema['x-document-capabilities'] = native_catalog()
    schema['components']['securitySchemes']['engineHostAuth'] = {
        'type': 'apiKey', 'in': 'header', 'name': 'X-Engine-Host-Token',
        'description': 'Identidade privada do host cadastrado. JWT e API key de usuário não substituem este token.',
    }
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        names = dependency_names(route.dependant)
        for method in route.methods:
            operation = schema['paths'].get(route.path, {}).get(method.lower())
            if operation is None:
                continue
            if route.path.startswith('/internal/engine-hosts/'):
                operation['security'] = [{'engineHostAuth': []}]
                operation['x-access'] = 'engine-host'
                operation['x-contract-notes'] = ['Exige X-Engine-Host-Token correspondente ao host_id. '
                    'Depende de ENGINE_CONTROL_ENABLED; retorna 503 quando desabilitado.']
            elif 'access_session' in names:
                operation['security'] = [{'bearerAuth': []}]
                operation['x-access'] = 'jwt'
                operation['x-contract-notes'] = ['Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. '
                    'O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. '
                    'Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.']
            elif 'require_admin_session' in names:
                operation['security'] = [{'bearerAuth': []}]
                operation['x-access'] = 'admin-session'
                operation['x-contract-notes'] = ['Exige sessão JWT de administrador. API keys são recusadas, '
                    'inclusive quando enviadas junto com o JWT.']
            elif 'require_admin' in names:
                operation['x-access'] = 'admin'
            elif operation.get('security'):
                operation['x-access'] = 'jwt' if operation['security'] == [{'bearerAuth': []}] else 'user'
            else:
                operation['x-access'] = 'public'

    notes = {
        ('post', '/images/analyze'): 'mode=single (padrão) executa uma tarefa; mode=full compõe as 15 famílias, exige Idempotency-Key e aceita full_options/datalake. Mesma chave+payload retorna o mesmo job; divergência 409; job excluído 410. Full retorna 202 por padrão e resultados partial/failed/cancelled continuam consultáveis.',
        ('post', '/images/analyze/upload'): 'Mesmas regras de /images/analyze; full_options e datalake são campos JSON. mode=full rejeita presença explícita dos campos single task/text_input/region/generation.',
        ('post', '/images/{job_id}/cancel'): 'Somente Full Analysis do dono. Pedido idempotente: 202 em andamento; 200 terminal. Checkpoints já concluídos são preservados; não cancela tarefas single.',
        ('post', '/upload'): 'Multipart: file obrigatório; project/project_id obrigatório salvo API key vinculada. '
            'docling_preset padrão fast. Áudio/vídeo sem controles Docling usa os padrões de /transcribe; controles Docling em mídia retornam 422. '
            'Destino datalake explícito cria novo job e desativa reaproveitamento por checksum.',
        ('post', '/convert'): 'Multipart, não JSON. source_type=file exige file; url/gdrive/dropbox exigem source. '
            'gdrive/dropbox também exigem X-Source-Token. docling_preset e conversion_options são propagados em todas as fontes. '
            'audio_options (JSON AudioConversionOptions) escolhe áudio/vídeo, com controles validados por provider e fila própria. '
            'Extensão de mídia conhecida sem opções usa os padrões de áudio. Controles Docling não são ignorados quando a fonte revela mídia. '
            'Não combine audio_options e conversion_options. Aceita destino datalake e particionamento.',
        ('post', '/transcribe'): 'Multipart. Todos os formatos são produzidos; output_format escolhe o padrão de leitura. '
            'Destino datalake explícito preserva valores por conversa e cria novo job. conversation_id não é chave de idempotência.',
        ('get', '/jobs/{job_id}/result'): 'Para transcrições, format=markdown retorna o envelope JSON com result.markdown e metadata; '
            'vtt/srt/txt/json retornam o arquivo bruto. Sem format, vale o output_format original do job. '
            'Documentos: format=markdown retorna envelope JSON; demais exportações solicitadas retornam arquivo bruto. Sem format vale output_format. Configuração e exportações são duráveis. Job não concluído: 400; falho: 500; sem resultado: 404.',
        ('get', '/jobs'): 'Retorna objeto {total, limit, offset, jobs, counts}, não uma lista direta. '
            'tag é repetível e combina filtros com E. folder_id=root exige project_id.',
        ('get', '/api-keys/'): 'Retorna uma lista direta de chaves, sem o segredo, incluindo o vínculo project.',
        ('post', '/api-keys/'): 'Retorna a chave completa apenas nesta criação. project ou project_id são opcionais e mutuamente exclusivos. '
            'O vínculo é usado em novos jobs autenticados somente pela API key, sem projeto explícito.',
        ('patch', '/api-keys/{key_id}'): 'project_id é obrigatório: ID de projeto próprio altera o vínculo; null remove o vínculo.',
        ('patch', '/datalakes/{connection_id}'): 'Quando config é enviada, substitui toda a configuração; preserve endpoint, região, buckets e padrões. '
            'Omitir credentials mantém as credenciais atuais. O provedor não muda.',
        ('post', '/datalakes/discover'): 'Lista/verifica buckets sem salvar a conexão; aceita credenciais do rascunho ou connection_id do próprio usuário.',
        ('post', '/datalakes/buckets'): 'Cria o bucket/container imediatamente; cancelar o wizard não remove esse recurso. '
            'Retorna 409 para nome existente, 403 para permissão insuficiente, 502 se a criação não puder ser confirmada.',
        ('post', '/datalakes/partition-preview'): 'Prévia autenticada sem acessar storage. Ausência de partitioning herda a conexão. '
            'missing=require sem valor retorna 422. A data usa created_at do job no fuso configurado.',
        ('post', '/datalakes/import'): 'connection_id/bucket/key identificam a origem; datalake, se enviado, identifica o destino. '
            'Origem e destino podem ser conexões distintas. Retorna 202 e enfileira conversão ou transcrição conforme o arquivo. '
            'conversion_options tipado configura documentos; audio_options tipado configura áudio/vídeo com as mesmas operações/controles de /transcribe. '
            'Opções incompatíveis são rejeitadas antes do download.',
        ('get', '/jobs/{job_id}/datalake'): 'Entrega independente do processamento: pending/exporting/completed/failed. '
            'destination inclui partitioning, partition_values, partitions, resolved_path, dataset_path, schema_path e objects.',
        ('post', '/jobs/{job_id}/datalake/retry'): 'Repete somente a entrega do resultado preservado; não executa inferência. '
            'Usa estratégia, valores e caminhos congelados. Entregas concluídas não são regravadas automaticamente.',
        ('post', '/transcribe/live/sessions'): 'JSON, projeto obrigatório salvo API key vinculada. '
            'datalake aceita partitioning e partition_values. Retorna ticket descartável com validade de 60 segundos e URL WebSocket. '
            'Live depende da configuração, prontidão do worker e capacidade.',
        ('post', '/admin/engines/{engine_id}/operations'): 'Exige header Idempotency-Key e plan_id/plan_hash de um plano válido. '
            'confirm_paid_operation=true confirma custos quando o plano exige; retorna 202.',
        ('get', '/admin/engine-operations/{operation_id}/stream'): 'SSE: text/event-stream, cursor after, eventos operation com id=seq. '
            'A conexão termina em até 60 segundos ou ao concluir; reconecte com o último seq. JWT revalidado a cada poll.',
    }
    for (method, path), note in notes.items():
        schema['paths'][path][method].setdefault('x-contract-notes', []).append(note)

    for path in ('/images/analyze', '/images/analyze/upload'):
        operation = schema['paths'][path]['post']
        operation['responses']['409'] = {'description': 'Full: Idempotency-Key utilizada com outra solicitação.'}
        operation['responses']['410'] = {'description': 'Full: job desta chave foi excluído; envie uma chave nova.'}
    schema['paths']['/images/{job_id}/cancel']['post']['responses']['202'] = {'description': 'Cancelamento solicitado, aguardando persistência dos checkpoints.'}
    schema['paths']['/jobs/{job_id}/result']['get']['responses']['202'] = {'description': 'Full Analysis ainda em andamento, com poll_url/result_url.'}

    # Returned Response objects bypass response_model; document actual media types.
    result = schema['paths']['/jobs/{job_id}/result']['get']['responses']['200']
    for fmt, media in TRANSCRIPT_CONTENT_TYPES.items():
        media = media.split(';', 1)[0]
        if fmt == 'json':
            original = result['content']['application/json']['schema']
            result['content']['application/json']['schema'] = {'anyOf': [original, {'type': 'object',
                'description': 'JSON bruto da transcrição quando format=json.'}]}
        else:
            result['content'][media] = {'schema': {'type': 'string'}}
    result['content']['text/html'] = {'schema': {'type': 'string'}}
    for path in ['/jobs/{job_id}/assets/{name}', '/jobs/{job_id}/pages/{page_number}/assets/{name}']:
        schema['paths'][path]['get']['responses']['200']['content'] = {'image/png': {'schema': {'type': 'string', 'format': 'binary'}}}
    pdf = schema['paths']['/jobs/{job_id}/pages/{page_number}/pdf/content']['get']['responses']['200']
    pdf['content'] = {'application/pdf': {'schema': {'type': 'string', 'format': 'binary'}}}
    stream = schema['paths']['/admin/engine-operations/{operation_id}/stream']['get']['responses']['200']
    stream['content'] = {'text/event-stream': {'schema': {'type': 'string'}}}
    for path in ['/projects', '/projects/{project_id}/folders']:
        responses = schema['paths'][path]['post']['responses']
        success = responses.get('201') or responses['200']
        responses['201'] = {**success, 'description': 'Recurso criado (get-or-add).'}
        responses['200'] = {**success, 'description': 'Recurso equivalente já existente (get-or-add).'}
    schema['x-websockets'] = [{
        'path': route.path, 'authentication': 'Ticket descartável obtido em POST /transcribe/live/sessions; '
            'primeiro frame JSON {"type":"authenticate","protocol":1,"ticket":"..."}. Não envie credenciais na URL.',
        'protocol': 'Após session.ready, áudio binário PCM s16le, 16 kHz, mono, frames de 200 ms com '
            'cabeçalho little-endian de 12 bytes (seq:uint32, offset_samples:uint64). '
            'Eventos transcript.partial/final e session.progress/completed; finish/cancel em JSON. Sem retomada da sessão desconectada.',
        'guide': '/docs/live',
    } for route in routes if isinstance(route, APIWebSocketRoute)]
    return schema
