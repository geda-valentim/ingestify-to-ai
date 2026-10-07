#!/usr/bin/env python3
"""Generate the published OpenAPI snapshot and complete Markdown reference.

Run in an environment with backend dependencies, or pass --schema to use a
fresh schema exported from the API container. --check never writes files.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = {'get', 'post', 'put', 'patch', 'delete', 'options', 'head', 'trace'}
ACCESS = {
    'public': 'Público', 'user': 'JWT ou API key', 'jwt': 'JWT',
    'admin': 'Administrador (JWT ou API key)', 'admin-session': 'Administrador (somente JWT)',
    'engine-host': 'X-Engine-Host-Token do host',
}


def operations(schema):
    return [(path, method, op) for path, item in schema['paths'].items()
            for method, op in item.items() if method in METHODS]


def resolve(schema, item):
    while '$ref' in item:
        item = schema['components']['schemas'][item['$ref'].rsplit('/', 1)[1]]
    return item


def typename(item):
    if '$ref' in item:
        name = item['$ref'].rsplit('/', 1)[1]
        return f'[{name}](#model-{name.lower()})'
    if 'anyOf' in item or 'oneOf' in item:
        return ' / '.join(typename(part) for part in item.get('anyOf', item.get('oneOf')))
    if item.get('type') == 'array':
        return 'array de ' + typename(item.get('items', {}))
    return item.get('type', 'objeto livre') + (f" ({item['format']})" if 'format' in item else '')


def constraints(item):
    return '; '.join(f'{key}={json.dumps(item[key], ensure_ascii=False)}' for key in
        ['default', 'enum', 'const', 'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum',
         'minLength', 'maxLength', 'minItems', 'maxItems', 'pattern', 'additionalProperties'] if key in item)


def cell(value):
    return str(value).replace('|', '&#124;').replace('\n', ' ').replace('\r', '')


def table(head, rows):
    return ['| ' + ' | '.join(head) + ' |', '| ' + ' | '.join('---' for _ in head) + ' |'] + [
        '| ' + ' | '.join(cell(value) for value in row) + ' |' for row in rows] + ['']


def fields(schema, model):
    model = resolve(schema, model)
    required = model.get('required', [])
    return [(f'`{key}`', 'sim' if key in required else 'não', typename(value), constraints(value), value.get('description', ''))
            for key, value in model.get('properties', {}).items()]


def render_reference(schema):
    entries = operations(schema)
    lines = ['# Referência completa dos endpoints', '',
        'Gerado do OpenAPI da aplicação por `scripts/generate_api_docs.py`. Não edite este arquivo à mão.', '',
        f"API `{schema['info']['version']}`: **{len(entries)} operações HTTP** e **{len(schema.get('x-websockets', []))} WebSocket(s)**.", '',
        'Base pública de desenvolvimento: `https://dev.ingestify.ai/api`. Os caminhos abaixo são relativos à base.', '',
        'Guia publicado: [PT](https://dev.ingestify.ai/pt/docs/api-reference) / [EN](https://dev.ingestify.ai/docs/api-reference). '
        '[Swagger](https://dev.ingestify.ai/api/docs), [OpenAPI JSON](https://dev.ingestify.ai/api/openapi.json).', '',
        '## Convenções', '',
        '- JWT: `Authorization: Bearer <token>`; API key: `X-API-Key: <chave>`. Com ambos, vale o JWT nas rotas de usuário.',
        '- Rotas que exigem sessão de administrador recusam API key, inclusive junto com JWT. Hosts internos usam a identidade própria.',
        '- Jobs exigem projeto: `project` ou `project_id`, salvo API key vinculada. `folder`/`folder_id` são opcionais e mutuamente exclusivos.',
        '- “Obrigatório” nas tabelas representa validação estrutural; regras condicionais estão nas notas e guias.',
        '- As respostas listadas são as declaradas no contrato. Erros de autenticação, propriedade e infraestrutura podem acrescentar 401/403/404/409/413/429/503.',
        '- Um esquema livre `{}` não promete campos fixos; consulte a descrição e o guia da funcionalidade para respostas dinâmicas.',
        '- Erros HTTP geralmente usam `detail` (texto, objeto ou lista de validação). Falhas globais usam `error`, `detail` e `timestamp`.',
        '- DELETE com 204 não tem corpo. Formatos TXT/VTT/SRT/PDF e SSE não devem ser interpretados como envelopes JSON.', '',
        '## Índice', '']
    lines += table(['Método', 'Caminho', 'Autorização', 'Resumo'],
        [(method.upper(), f'`{path}`', ACCESS[op['x-access']], op.get('summary', '')) for path, method, op in entries])
    groups = {}
    for path, method, op in entries:
        groups.setdefault((op.get('tags') or ['General'])[0], []).append((path, method, op))
    for tag, group in groups.items():
        lines += [f'## {tag}', '']
        for path, method, op in group:
            lines += [f'### {method.upper()} {path}', '', op.get('summary', ''), '',
                      f"Autorização: **{ACCESS[op['x-access']]}**. Operation ID: `{op.get('operationId', '')}`.", '']
            if op.get('description'):
                lines += [op['description'], '']
            for note in op.get('x-contract-notes', []):
                lines += [note, '']
            if op.get('parameters'):
                lines += ['Parâmetros:', ''] + table(['Nome', 'Local', 'Obrigatório', 'Tipo', 'Padrões/limites', 'Descrição'],
                    [(f"`{p['name']}`", p['in'], 'sim' if p.get('required') else 'não', typename(p.get('schema', {})),
                      constraints(p.get('schema', {})), p.get('description', '')) for p in op['parameters']])
            body = op.get('requestBody')
            if body:
                lines += [f"Corpo obrigatório: {'sim' if body.get('required') else 'não'}.", '']
                for media, content in body.get('content', {}).items():
                    model = content.get('schema', {})
                    lines += [f'Content-Type: `{media}`. Esquema: {typename(model)}.', '']
                    rows = fields(schema, model)
                    if rows:
                        lines += table(['Campo', 'Obrigatório', 'Tipo', 'Padrões/limites', 'Descrição'], rows)
            lines += ['Respostas declaradas:', ''] + table(['Status', 'Content-Type', 'Esquema', 'Descrição'],
                [(code, media, typename(content.get('schema', {})), response.get('description', ''))
                 for code, response in op['responses'].items()
                 for media, content in (response.get('content') or {'—': {}}).items()])
    lines += ['## WebSocket', '']
    for ws in schema.get('x-websockets', []):
        lines += [f"### WS {ws['path']}", '', ws['authentication'], '', ws['protocol'], '',
                  'Protocolo completo: [captura ao vivo](features/live-transcription.md).', '']
    lines += ['## Modelos', '']
    for name, model in sorted(schema['components']['schemas'].items()):
        lines += [f'<a id="model-{name.lower()}"></a>', '', f'### {name}', '']
        if model.get('description'):
            lines += [model['description'], '']
        if fields(schema, model):
            lines += table(['Campo', 'Obrigatório', 'Tipo', 'Padrões/limites', 'Descrição'], fields(schema, model))
        lines += ['Esquema JSON completo:', '', '```json', json.dumps(model, indent=2, ensure_ascii=False), '```', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema', type=Path, help='Fresh exported OpenAPI JSON; otherwise imports api.main')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.schema:
        schema = json.loads(args.schema.read_text())
    else:
        sys.path.insert(0, str(ROOT / 'backend'))
        from api.main import app
        schema = app.openapi()
    outputs = {
        ROOT / 'frontend/docs/doc2md_openapi.json': json.dumps(schema, indent=2, ensure_ascii=False) + '\n',
        ROOT / 'docs/api-reference.md': render_reference(schema),
    }
    stale = []
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content)
    if stale:
        print('Documentation is stale: ' + ', '.join(stale), file=sys.stderr)
        return 1
    print(f"{'Checked' if args.check else 'Generated'} {len(operations(schema))} HTTP endpoints and {len(schema['components']['schemas'])} models")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
