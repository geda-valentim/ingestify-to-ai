# Ingestify - Plataforma de Conversão de Documentos para Markdown

Plataforma full-stack para conversão de documentos e URLs para formato Markdown usando Docling. Inclui interface web Next.js e API REST assíncrona em arquitetura monorepo.

## 📋 Visão Geral

O Ingestify é uma API REST que permite converter diversos tipos de documentos (PDF, DOCX, HTML, etc.) para Markdown. A conversão é processada de forma assíncrona através de workers distribuídos, permitindo escalabilidade e processamento em paralelo.

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

Com Ingestify, você transforma documentos complexos em Markdown estruturado, otimizado para engenharia de contexto, sistemas RAG e treinamento de modelos.

## 🏗️ Arquitetura

### Componentes (Monorepo)

```
┌─────────────────────┐
│  Frontend Next.js   │ ◄─── Interface web (React)
│   (localhost:3000)  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   API FastAPI       │ ◄─── REST API (localhost:8080)
│   (backend/api/)    │      Recebe requisições e retorna job_id
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Redis + ES         │ ◄─── Broker, cache e busca
│                     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Workers Celery     │ ◄─── Processam conversões com Docling
│  (backend/workers/) │      (escaláveis)
└─────────────────────┘
```

### Stack Tecnológica

**Frontend:**
- **Next.js 15** - Framework React com App Router
- **React 19** - UI library
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **TanStack Query** - Data fetching
- **Zustand** - State management
- **shadcn/ui** - Component library

**Backend:**
- **FastAPI** - Framework web assíncrono e moderno
- **Celery** - Sistema de filas distribuído para processamento assíncrono
- **Redis** - Message broker e cache de resultados
- **Elasticsearch** - Full-text search
- **MySQL** - Database (users, jobs, api keys)
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
curl -X POST http://localhost:8080/convert \
  -F "file=@document.pdf" \
  -F "source_type=file"
```

**Conversão de URL:**
```bash
curl -X POST http://localhost:8080/convert \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "url",
    "source": "https://example.com/document.pdf"
  }'
```

**Google Drive:**
```bash
curl -X POST http://localhost:8080/convert \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "source_type": "gdrive",
    "source": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
  }'
```

**Dropbox:**
```bash
curl -X POST http://localhost:8080/convert \
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

- **frontend** - Next.js web app (porta 3000)
- **api** - API FastAPI (porta 8000)
- **worker** - Workers Celery (escalável, 2 réplicas por padrão)
- **redis** - Message broker e cache (porta 6379)
- **elasticsearch** - Search engine (porta 9200)

### Comandos

**Modo Desenvolvimento (Padrão - com hot reload):**
```bash
# Gerar JWT_SECRET_KEY no .env (obrigatório; só gera se ainda não existir)
./scripts/ensure_jwt_secret.sh

# Iniciar todos os serviços em modo desenvolvimento
# docker-compose.override.yml é aplicado automaticamente!
docker compose up -d --build

# Acesse:
# - Frontend: http://localhost:3000 (hot reload ativado!)
# - API: http://localhost:8000 (hot reload ativado!)
# - API Docs: http://localhost:8000/docs

# Ver logs em tempo real (útil para ver hot reload)
docker compose logs -f frontend
docker compose logs -f api
docker compose logs -f worker

# Parar serviços
docker compose down
```

**Modo Produção:**
```bash
# Iniciar em modo produção (sem hot reload, otimizado)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Escalar workers em produção
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale worker=5

# Parar serviços
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

**Hot Reload:**
- ✅ **Frontend**: Edite arquivos em `frontend/` e veja mudanças instantaneamente
- ✅ **API**: Edite arquivos em `backend/api/` e veja mudanças instantaneamente
- ✅ **Workers**: Edite arquivos em `backend/workers/` e workers reiniciam automaticamente

## 🔗 Infraestrutura Compartilhada (Novo!)

O Ingestify agora suporta **auto-detecção de infraestrutura compartilhada**! Isso significa:

- 🚀 **Zero Configuração**: Funciona automaticamente em qualquer máquina
- 💾 **Economia de Recursos**: Compartilhe Redis, MinIO e Elasticsearch entre múltiplos projetos
- ⚡ **Startup Rápido**: Reutilize infraestrutura já rodando
- 🖥️ **Multi-Máquina**: Mesmos comandos no desktop, laptop ou servidor

### Quick Start - Modo Inteligente (Recomendado)

```bash
# Simplesmente execute - o script detecta tudo automaticamente!
./start.sh

# Ou use o Makefile
make start
```

O script `start.sh` detecta automaticamente:
- ✅ Se existe infraestrutura compartilhada rodando → reutiliza
- ✅ Se não existe → inicia infraestrutura local
- ✅ Configura tudo automaticamente sem perguntar nada!

### Modo Compartilhado Explícito

```bash
# Terminal 1: Inicie a infraestrutura compartilhada UMA VEZ
make infra-start
# Ou: ./infra.sh start

# Terminal 2: Inicie o Ingestify (detecta e usa infra compartilhada)
./start.sh

# Terminal 3: Inicie outro projeto (também usa a mesma infra!)
cd /path/to/outro-projeto
./start.sh
```

### Comandos Úteis

```bash
# Gerenciar infraestrutura compartilhada
./infra.sh start      # Iniciar
./infra.sh stop       # Parar
./infra.sh status     # Ver status
./infra.sh test       # Testar conectividade
./infra.sh logs       # Ver logs

# Ou use o Makefile
make infra-start      # Iniciar infraestrutura
make infra-stop       # Parar infraestrutura
make infra-status     # Status
make infra-logs       # Ver logs
```

### Benefícios

**Sem Infraestrutura Compartilhada:**
- Cada projeto usa ~1.2GB RAM (Redis + MinIO + Elasticsearch)
- 3 projetos = ~3.6GB RAM usado

**Com Infraestrutura Compartilhada:**
- TODOS os projetos compartilham a mesma infraestrutura
- 3 projetos = ~1.2GB RAM total (economia de 67%!)

### Documentação Completa

Para mais detalhes, consulte [docs/SHARED_INFRASTRUCTURE.md](docs/SHARED_INFRASTRUCTURE.md)

## 📂 Estrutura do Projeto (Monorepo)

```
ingestify-to-ai/
├── frontend/                # 🎨 Next.js Frontend
│   ├── app/                 # Next.js App Router
│   ├── components/          # React components
│   ├── lib/                 # API client & utilities
│   ├── hooks/               # Custom hooks
│   ├── types/               # TypeScript types
│   ├── package.json
│   ├── next.config.ts
│   └── .env.local
│
├── backend/                 # 🐍 Python Backend
│   ├── api/
│   │   ├── main.py          # Aplicação FastAPI
│   │   ├── routes.py        # Document conversion endpoints
│   │   ├── auth_routes.py   # Authentication
│   │   └── apikey_routes.py # API key management
│   ├── workers/
│   │   ├── celery_app.py    # Configuração Celery
│   │   ├── converter.py     # Lógica de conversão Docling
│   │   ├── sources.py       # Handlers (file, url, gdrive, dropbox)
│   │   └── tasks.py         # Celery tasks
│   ├── shared/
│   │   ├── config.py        # Settings
│   │   ├── schemas.py       # Pydantic models
│   │   ├── database.py      # SQLAlchemy setup
│   │   ├── models.py        # Database models
│   │   ├── auth.py          # JWT authentication
│   │   ├── redis_client.py  # Redis operations
│   │   ├── elasticsearch_client.py  # Search client
│   │   └── pdf_splitter.py  # PDF processing
│   ├── tests/               # Unit tests
│   ├── requirements.txt
│   └── pytest.ini
│
├── docker/
│   ├── Dockerfile.frontend  # Next.js container
│   ├── Dockerfile.api       # FastAPI container
│   └── Dockerfile.worker    # Celery worker container
│
├── docs/                    # Documentation
├── scripts/                 # Utility scripts
├── docker-compose.yml       # Full stack orchestration
├── .gitignore
├── CLAUDE.md               # AI coding assistant guide
└── README.md
```

## ⚙️ Configuração

### Variáveis de Ambiente

**Frontend (.env.local)**
```bash
NEXT_PUBLIC_API_URL=http://localhost:8080
```

**Backend (.env)**
```bash
# API
API_HOST=0.0.0.0
API_PORT=8000

# Database
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/ingestify

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# JWT Authentication (JWT_SECRET_KEY é obrigatório: a API não sobe sem ele)
# Gere com: openssl rand -hex 32  (ou ./scripts/ensure_jwt_secret.sh)
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# Conversão
MAX_FILE_SIZE_MB=50
CONVERSION_TIMEOUT_SECONDS=300
TEMP_STORAGE_PATH=/tmp/ingestify

# Integrações
GOOGLE_DRIVE_CREDENTIALS_PATH=/secrets/gdrive.json
DROPBOX_APP_KEY=your_app_key
DROPBOX_APP_SECRET=your_app_secret

# Storage
RESULT_TTL_SECONDS=3600
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

**Pré-requisitos:**
- Python 3.13+ (ou 3.10+, mas 3.13+ é recomendado)
- Node.js 20+
- Redis
- MySQL (ou use Docker para databases)

**Backend:**
```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Instalar dependências (setuptools incluído para compatibilidade Python 3.13+)
pip install -r backend/requirements.txt

# Executar API (porta 8080)
./run_api.sh

# Executar worker (terminal separado)
./run_worker.sh
```

**Frontend:**
```bash
cd frontend

# Instalar dependências
npm install

# Executar dev server
npm run dev
# Acesse: http://localhost:3000
```

**Com Docker (Recomendado):**
```bash
# Stack completo
docker compose up -d --build
```

### Testes

```bash
# Backend
cd backend
pytest tests/ -v

# Frontend
cd frontend
npm test
```

## 📝 Licença

MIT

## 🤝 Contribuição

Contribuições são bem-vindas! Por favor, abra uma issue ou pull request.

## 📧 Suporte

Para questões e suporte, abra uma issue no repositório.
