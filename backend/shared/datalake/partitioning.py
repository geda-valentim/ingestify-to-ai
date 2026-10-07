"""Provider-independent, immutable storage layouts and normalized JSONL v1."""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BUILTINS = ('date', 'year', 'month', 'day', 'hour', 'project_id', 'folder_id', 'source_type')
DATA_COLUMNS = {'schema_version': 'integer', 'job_id': 'string', 'created_at': 'string',
    'project_id': 'string', 'folder_id': 'string', 'source_type': 'string', 'filename': 'string',
    'text': 'string', 'metadata_json': 'string', 'payload_json': 'string', 'partition_values_json': 'string'}


class PartitionError(ValueError):
    pass


class PartitionField(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: Literal['date', 'year', 'month', 'day', 'hour', 'project_id', 'folder_id', 'source_type', 'custom']
    key: str | None = Field(None, max_length=32, pattern=r'^[a-z][a-z0-9_]*$')

    @model_validator(mode='after')
    def field_key(self):
        if self.field == 'custom':
            if not self.key or self.key in BUILTINS or self.key in DATA_COLUMNS:
                raise ValueError('Escolha uma chave personalizada única, sem usar nomes reservados')
        elif self.key is not None and self.key != self.field:
            raise ValueError('A chave de um campo do job deve manter seu nome')
        else:
            self.key = self.field
        return self


class PartitionStrategy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['none', 'date', 'project_date', 'custom'] = 'none'
    fields: list[PartitionField] = Field(default_factory=list, max_length=8)
    granularity: Literal['month', 'day', 'hour'] = 'day'
    timezone: str = Field('UTC', max_length=100)
    missing: Literal['fallback', 'require'] = 'fallback'
    fallback: str = Field('_unassigned', min_length=1, max_length=128)
    analytics: Literal['none', 'jsonl'] = 'none'

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Informe um fuso horário IANA válido') from None
        return value

    @field_validator('fallback')
    @classmethod
    def valid_fallback(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError('Informe um valor substituto válido')
        return value

    @model_validator(mode='after')
    def ordered_fields(self):
        if self.mode == 'none':
            self.fields = []
        elif self.mode == 'date':
            self.fields = [PartitionField(field='date')]
        elif self.mode == 'project_date':
            self.fields = [PartitionField(field='project_id'), PartitionField(field='date')]
        elif not self.fields:
            raise ValueError('Selecione ao menos um campo de particionamento')
        keys = self.keys()
        if len(set(keys)) != len(keys):
            raise ValueError('As chaves de particionamento não podem se repetir')
        if len(keys) > 10:
            raise ValueError('Use até 10 chaves de particionamento, incluindo ano, mês, dia e hora')
        return self

    def date_keys(self):
        return ['year', 'month'] + ([] if self.granularity == 'month' else ['day']) + (['hour'] if self.granularity == 'hour' else [])

    def keys(self):
        return [key for f in self.fields for key in (self.date_keys() if f.field == 'date' else [f.key])]

    def layout_id(self):
        # Version by behavior rather than editable revision numbers. Equivalent
        # preset/custom layouts share a root; overrides cannot collide.
        layout = {'version': 1, 'fields': [f.model_dump() for f in self.fields],
            'keys': self.keys(), 'granularity': self.granularity, 'timezone': self.timezone,
            'missing': self.missing, 'fallback': self.fallback, 'analytics': self.analytics, 'schema': 1}
        return 'layout-' + hashlib.sha256(json.dumps(layout, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]


PartitionValues = dict[str, str]


def validate_values(values):
    import re
    if len(values) > 20:
        raise ValueError('Informe até 20 campos personalizados')
    for key, value in values.items():
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', key) or key in BUILTINS or key in DATA_COLUMNS:
            raise ValueError('Chave personalizada inválida ou reservada')
        if len(value) > 128 or any(ord(c) < 32 for c in value):
            raise ValueError('Valor personalizado inválido ou maior que 128 caracteres')
    return values


def utc_datetime(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc))


def job_context(job, source_type=None):
    return {'job_id': job.id, 'created_at': utc_datetime(job.created_at).isoformat(),
        'project_id': job.project_id, 'folder_id': job.folder_id,
        'source_type': source_type or job.source_type, 'filename': job.filename}


def resolve_layout(strategy, prefix, context, values):
    date = utc_datetime(context['created_at']).astimezone(ZoneInfo(strategy.timezone))
    date_values = {'year': f'{date.year:04d}', 'month': f'{date.month:02d}', 'day': f'{date.day:02d}', 'hour': f'{date.hour:02d}'}
    partitions = {}
    for field in strategy.fields:
        keys = strategy.date_keys() if field.field == 'date' else [field.key]
        for key in keys:
            value = date_values[key] if key in date_values else values.get(key) if field.field == 'custom' else context.get(key)
            if value is None or not str(value).strip():
                if strategy.missing == 'require':
                    raise PartitionError(f'Preencha o campo obrigatório de particionamento: {key}')
                value = strategy.fallback
            partitions[key] = str(value)
    layout_id = strategy.layout_id()
    segments = '/'.join(key + '=' + quote(value, safe='-_') for key, value in partitions.items())
    base = '/'.join(part for part in [prefix, layout_id if strategy.mode != 'none' else '', segments, context['job_id']] if part)
    dataset = '/'.join(part for part in [prefix, 'datasets', layout_id, segments, context['job_id'] + '.jsonl'] if part) if strategy.analytics == 'jsonl' else None
    schema = '/'.join(part for part in [prefix, 'schemas', layout_id + '.json'] if part) if dataset else None
    for key in [base + '/transcript.json', dataset, schema]:
        if key and len(key.encode('utf-8')) > 1024:
            raise PartitionError('O caminho completo excede 1.024 bytes. Reduza a pasta ou os campos personalizados.')
    return {'layout_id': layout_id, 'resolved_path': base, 'partitions': partitions,
            'dataset_path': dataset, 'schema_path': schema}


def analytic_outputs(snapshot, payload):
    """Single normalized row per job; query root contains only JSONL files."""
    context, partitions = snapshot.context, snapshot.partitions
    # Keep conversation/agent identifiers even when they are not directory
    # dimensions. Frozen resolved values win, including missing-value fallbacks.
    analytic_values = {**snapshot.values, **partitions}
    transcript = payload.get('transcript') or {}
    text = transcript.get('txt') or payload.get('text') or payload.get('markdown') or ''
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, sort_keys=True)
    record = {'schema_version': 1, **{k: context.get(k) for k in ('job_id', 'created_at', 'project_id', 'folder_id', 'source_type', 'filename')},
        'text': text, 'metadata_json': json.dumps(payload.get('metadata') or {}, ensure_ascii=False, sort_keys=True),
        'payload_json': json.dumps(payload, ensure_ascii=False, sort_keys=True),
        'partition_values_json': json.dumps(analytic_values, ensure_ascii=False, sort_keys=True)}
    # Hive exposes these as columns from the path. Duplicating them inside the
    # data creates conflicting table schemas in external query engines.
    columns = {k: v for k, v in DATA_COLUMNS.items() if k not in partitions}
    record = {k: v for k, v in record.items() if k in columns}
    ordered_keys = PartitionStrategy.model_validate(snapshot.strategy).keys()
    schema = {'schema_version': 1, 'format': 'jsonl', 'record': 'one completed job per line',
        'columns': columns, 'partition_columns': [{'name': key, 'type': 'string'} for key in ordered_keys],
        'timestamp': 'ISO 8601 UTC', 'dataset_root': snapshot.dataset_path.rsplit('/', len(ordered_keys) + 1)[0]}
    return {snapshot.dataset_path: ((json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n').encode(), 'application/x-ndjson'),
            snapshot.schema_path: (json.dumps(schema, ensure_ascii=False, sort_keys=True).encode(), 'application/json')}
