# Doc2MD - API de Conversão de Documentos para Markdown

API assíncrona para conversão de documentos e URLs para formato Markdown usando Docling.

## 📋 Visão Geral

O Doc2MD é uma API REST que permite converter diversos tipos de documentos (PDF, DOCX, HTML, etc.) para Markdown. A conversão é processada de forma assíncrona através de workers distribuídos, permitindo escalabilidade e processamento em paralelo.

### Por que Markdown?

Trabalhar com PDFs e documentos complexos em pipelines de IA apresenta desafios significativos:

- **Extração simples não preserva estrutura** - Métodos tradicionais de extração perdem formatação, hierarquia e contexto semântico
- **Dificuldade para LLMs processarem** - Texto bruto sem estrutura dificulta a compreensão de relações entre seções, listas e tabelas
- **Problemas em RAG** - Sistemas de recuperação precisam de chunks bem delimitados e contextualizados
- **Fine-tuning comprometido** - Modelos treinados com dados mal estruturados perdem qualidade

**Markdown como solução:**
- ✅ Preserva hierarquia semântica (headings, listas, tabelas)
- ✅ Ideal para chunking em RAG (divisão natural por seções)
- ✅ Melhor contexto para LLMs (estrutura explícita)
- ✅ Facilita pré-processamento para fine-tuning
- ✅ Formato universal, leve e versionável

Com Doc2MD, você transforma documentos complexos em Markdown estruturado, otimizado para engenharia de contexto, sistemas RAG e treinamento de modelos.

## 🏗️ Arquitetura

### Componentes

```
┌─────────────┐
│   Cliente   │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│   API FastAPI   │ ◄─── Recebe requisições e retorna job_id
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Redis (Broker) │ ◄─── Fila de tarefas
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Workers Celery  │ ◄─── Processam conversões com Docling
│  (escaláveis)   │
└─────────────────┘
```

### Stack Tecnológica

- **FastAPI** - Framework web assíncrono e moderno
- **Celery** - Sistema de filas distribuído para processamento assíncrono
- **Redis** - Message broker e cache de resultados
- **Docling** - Motor de conversão de documentos
- **Docker & Docker Compose** - Containerização e orquestração
- **Pydantic** - Validação e serialização de dados

## 🚀 Funcionalidades

### Fontes de Entrada Suportadas

- ✅ **Upload direto** - Envio de arquivo via multipart/form-data
- ✅ **URL pública** - Conversão de documento via URL HTTP/HTTPS
- ✅ **Google Drive** - Integração com Google Drive API
- ✅ **Dropbox** - Integração com Dropbox API

### Formatos de Documento Suportados

- PDF
- DOCX, DOC
- HTML
- PPTX
- XLSX
- RTF
- ODT
- E outros suportados pelo Docling

## 📡 API

### Endpoint Principal

#### `POST /convert`

Endpoint unificado que detecta automaticamente o tipo de fonte e realiza a conversão.

**Parâmetros:**

```json
{
  "source_type": "file|url|gdrive|dropbox",
  "source": "URL, ID ou path do arquivo",
  "options": {
    "format": "markdown",
    "include_images": true,
    "preserve_tables": true
  },
  "callback_url": "https://optional-webhook.com/callback"
}
```

**Upload de Arquivo:**
```bash
curl -X POST http://localhost:8000/convert \
  -F "file=@document.pdf" \
  -F "source_type=file"
```

**Conversão de URL:**
```bash
curl -X POST http://localhost:8000/convert \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "url",
    "source": "https://example.com/document.pdf"
  }'
```

**Google Drive:**
```bash
curl -X POST http://localhost:8000/convert \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "source_type": "gdrive",
    "source": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
  }'
```

**Dropbox:**
```bash
curl -X POST http://localhost:8000/convert \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "source_type": "dropbox",
    "source": "/documents/report.pdf"
  }'
```

**Resposta:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2025-10-01T17:45:00Z",
  "message": "Job enfileirado para processamento"
}
```

### Endpoints de Consulta

#### `GET /jobs/{job_id}`

Consulta o status do job de conversão.

**Resposta:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing|completed|failed|queued",
  "progress": 75,
  "created_at": "2025-10-01T17:45:00Z",
  "started_at": "2025-10-01T17:45:05Z",
  "completed_at": null,
  "error": null
}
```

#### `GET /jobs/{job_id}/result`

Retorna o resultado da conversão (disponível apenas quando status = completed).

**Resposta:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "markdown": "# Documento Convertido\n\nConteúdo...",
    "metadata": {
      "pages": 10,
      "words": 2500,
      "format": "pdf",
      "size_bytes": 524288
    }
  },
  "completed_at": "2025-10-01T17:46:30Z"
}
```

#### `GET /health`

Health check da API.

**Resposta:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "workers": {
    "active": 3,
    "available": 5
  }
}
```

## 🐳 Docker

### Estrutura de Containers

- **api** - API FastAPI (porta 8000)
- **worker** - Workers Celery (escalável)
- **redis** - Message broker e cache (porta 6379)

### Comandos

```bash
# Iniciar todos os serviços
docker-compose up -d

# Escalar workers
docker-compose up -d --scale worker=5

# Ver logs
docker-compose logs -f api
docker-compose logs -f worker

# Parar serviços
docker-compose down
```

## 📂 Estrutura do Projeto

```
doc2md/
├── api/
│   ├── __init__.py
│   ├── main.py              # Aplicação FastAPI
│   ├── models.py            # Modelos Pydantic
│   ├── routes.py            # Definição de rotas
│   └── dependencies.py      # Dependências e injeção
│
├── workers/
│   ├── __init__.py
│   ├── celery_app.py        # Configuração Celery
│   ├── converter.py         # Lógica de conversão Docling
│   ├── sources.py           # Handlers de fontes (file, url, gdrive, dropbox)
│   └── tasks.py             # Definição de tasks Celery
│
├── shared/
│   ├── __init__.py
│   ├── config.py            # Configurações compartilhadas
│   ├── schemas.py           # Schemas compartilhados
│   └── utils.py             # Funções utilitárias
│
├── docker/
│   ├── Dockerfile.api       # Container da API
│   ├── Dockerfile.worker    # Container dos workers
│   └── docker-compose.yml   # Orquestração
│
├── tests/
│   ├── test_api.py
│   └── test_converter.py
│
├── requirements.txt         # Dependências Python
├── .env.example            # Exemplo de variáveis de ambiente
├── .gitignore
└── README.md
```

## ⚙️ Configuração

### Variáveis de Ambiente

```bash
# API
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# Conversão
MAX_FILE_SIZE_MB=50
CONVERSION_TIMEOUT_SECONDS=300
TEMP_STORAGE_PATH=/tmp/doc2md

# Integrações
GOOGLE_DRIVE_CREDENTIALS_PATH=/secrets/gdrive.json
DROPBOX_APP_KEY=your_app_key
DROPBOX_APP_SECRET=your_app_secret

# Storage
RESULT_TTL_SECONDS=3600
CLEANUP_INTERVAL_HOURS=24
```

## 🔒 Autenticação

Para acessar documentos do Google Drive e Dropbox, é necessário fornecer tokens de autenticação:

```bash
# Header de autenticação
Authorization: Bearer YOUR_ACCESS_TOKEN
```

Os tokens devem ter as seguintes permissões:
- **Google Drive**: `https://www.googleapis.com/auth/drive.readonly`
- **Dropbox**: `files.content.read`

## 📊 Monitoramento

### Flower (Celery Monitoring)

```bash
# Iniciar Flower
docker-compose exec worker celery -A workers.celery_app flower
```

Acesse: http://localhost:5555

## 🔧 Desenvolvimento

### Instalação Local

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Executar API
uvicorn api.main:app --reload

# Executar worker
celery -A workers.celery_app worker --loglevel=info
```

### Testes

```bash
pytest tests/ -v
```

## 📝 Licença

MIT

## 🤝 Contribuição

Contribuições são bem-vindas! Por favor, abra uma issue ou pull request.

## 📧 Suporte

Para questões e suporte, abra uma issue no repositório.
