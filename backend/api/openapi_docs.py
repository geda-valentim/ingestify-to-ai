"""Describe authentication from route dependencies and the image workflow contract."""
from fastapi.routing import APIRoute, APIWebSocketRoute


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
