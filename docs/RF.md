# Requisitos Funcionais (RF) - Doc2MD API

> **Documento histórico (out/2025).** Os requisitos aqui eram aspiracionais e várias marcações não batem com o código (ex.: `callback_url` em `/convert` e rate limit por token com headers `X-RateLimit-*` não existem; a limpeza não é horária). O comportamento real está em [features/](features/) — índice em [README.md](README.md).

## RF001 - Conversão de Documentos

### RF001.1 - Suporte a Múltiplas Fontes
**Prioridade:** Alta
**Descrição:** O sistema DEVE aceitar documentos de diferentes fontes através de um único endpoint.

**Critérios de Aceitação:**
- ✅ Sistema aceita upload direto de arquivos (multipart/form-data)
- ✅ Sistema aceita URL pública de documentos
- ✅ Sistema aceita ID de arquivo do Google Drive
- ✅ Sistema aceita path de arquivo do Dropbox
- ✅ Sistema identifica automaticamente o tipo de fonte baseado no parâmetro `source_type`

**Cenários de Teste:**
```
DADO que o usuário faz upload de um PDF de 2MB
QUANDO envia requisição POST /convert com source_type=file
ENTÃO sistema aceita o arquivo e retorna job_id

DADO que o usuário fornece URL https://example.com/doc.pdf
QUANDO envia requisição POST /convert com source_type=url
ENTÃO sistema valida URL e retorna job_id

DADO que o usuário fornece file_id do Google Drive
QUANDO envia requisição POST /convert com source_type=gdrive e token válido
ENTÃO sistema aceita e retorna job_id

DADO que o usuário fornece path do Dropbox
QUANDO envia requisição POST /convert com source_type=dropbox e token válido
ENTÃO sistema aceita e retorna job_id
```

---

### RF001.2 - Formatos Suportados
**Prioridade:** Alta
**Descrição:** O sistema DEVE suportar conversão dos formatos de documento mais comuns.

**Formatos Obrigatórios:**
- ✅ PDF (.pdf)
- ✅ Microsoft Word (.docx, .doc)
- ✅ HTML (.html, .htm)
- ✅ Rich Text Format (.rtf)
- ✅ OpenDocument Text (.odt)

**Formatos Desejáveis:**
- ✅ Microsoft PowerPoint (.pptx, .ppt)
- ✅ Microsoft Excel (.xlsx, .xls)
- ✅ Markdown (.md) - validação/normalização

**Critérios de Aceitação:**
- Sistema detecta formato baseado em extensão e MIME type
- Sistema rejeita formatos não suportados com erro 422
- Sistema retorna mensagem clara sobre formatos aceitos

---

### RF001.3 - Conversão para Markdown
**Prioridade:** Alta
**Descrição:** O sistema DEVE converter documentos para formato Markdown preservando estrutura e conteúdo.

**Elementos Preservados:**
- ✅ Cabeçalhos (H1-H6)
- ✅ Parágrafos e quebras de linha
- ✅ Listas ordenadas e não-ordenadas
- ✅ Negrito, itálico, sublinhado
- ✅ Links e URLs
- ✅ Tabelas (quando `preserve_tables=true`)
- ✅ Imagens (quando `include_images=true`)
- ✅ Blocos de código

**Critérios de Aceitação:**
- Markdown gerado é válido segundo CommonMark spec
- Estrutura hierárquica do documento é mantida
- Formatação básica de texto é preservada
- Tabelas são convertidas para formato Markdown table

---

## RF002 - Processamento Assíncrono

### RF002.1 - Enfileiramento de Jobs
**Prioridade:** Alta
**Descrição:** O sistema DEVE processar conversões de forma assíncrona através de fila de tarefas.

**Critérios de Aceitação:**
- ✅ API retorna job_id imediatamente após validação
- ✅ Job é adicionado à fila do Redis
- ✅ Múltiplos jobs podem ser processados em paralelo
- ✅ Jobs são processados na ordem FIFO (First In, First Out)
- ✅ API não bloqueia aguardando conversão

**Cenários de Teste:**
```
DADO que o usuário envia 10 requisições de conversão
QUANDO todas são aceitas pela API
ENTÃO sistema retorna 10 job_ids diferentes em < 100ms cada
E jobs são enfileirados para processamento
E workers processam jobs em paralelo
```

---

### RF002.2 - Geração de Job ID
**Prioridade:** Alta
**Descrição:** O sistema DEVE gerar identificador único para cada job de conversão.

**Critérios de Aceitação:**
- ✅ Job ID é UUID v4
- ✅ Job ID é único (colisão < 1 em 10^36)
- ✅ Job ID é retornado imediatamente na resposta
- ✅ Job ID pode ser usado para consultar status e resultado

---

### RF002.3 - Rastreamento de Status
**Prioridade:** Alta
**Descrição:** O sistema DEVE permitir consulta de status de jobs em andamento.

**Estados Possíveis:**
- `queued` - Job na fila aguardando processamento
- `processing` - Job sendo processado por worker
- `completed` - Conversão concluída com sucesso
- `failed` - Conversão falhou (com mensagem de erro)

**Critérios de Aceitação:**
- ✅ Endpoint GET /jobs/{job_id} retorna status atual
- ✅ Status é atualizado em tempo real
- ✅ Progress (0-100%) é fornecido para jobs em processamento
- ✅ Timestamps são incluídos (created_at, started_at, completed_at)
- ✅ Erros incluem mensagem descritiva

**Cenários de Teste:**
```
DADO que um job foi criado
QUANDO consulto GET /jobs/{job_id}
ENTÃO recebo status="queued"

DADO que um job está sendo processado
QUANDO consulto GET /jobs/{job_id}
ENTÃO recebo status="processing" e progress entre 0-100

DADO que um job foi concluído
QUANDO consulto GET /jobs/{job_id}
ENTÃO recebo status="completed" e completed_at timestamp
```

---

## RF003 - Recuperação de Resultados

### RF003.1 - Consulta de Resultados
**Prioridade:** Alta
**Descrição:** O sistema DEVE permitir recuperação do resultado da conversão.

**Critérios de Aceitação:**
- ✅ Endpoint GET /jobs/{job_id}/result retorna markdown gerado
- ✅ Resultado só disponível quando status="completed"
- ✅ Resultado inclui metadata do documento (páginas, palavras, etc.)
- ✅ Resultado expira após TTL configurado (default: 1 hora)
- ✅ Tentativa de acessar resultado expirado retorna 404

**Estrutura do Resultado:**
```json
{
  "job_id": "uuid",
  "status": "completed",
  "result": {
    "markdown": "# Conteúdo...",
    "metadata": {
      "pages": 10,
      "words": 2500,
      "format": "pdf",
      "size_bytes": 524288,
      "title": "Título do Documento",
      "author": "Autor"
    }
  },
  "completed_at": "2025-10-01T18:00:00Z"
}
```

---

### RF003.2 - Cache de Resultados
**Prioridade:** Média
**Descrição:** O sistema DEVE cachear resultados temporariamente para acesso rápido.

**Critérios de Aceitação:**
- ✅ Resultados armazenados no Redis com TTL
- ✅ TTL padrão de 1 hora (configurável)
- ✅ Após expiração, cliente precisa reprocessar documento
- ✅ Sistema limpa resultados expirados automaticamente

---

## RF004 - Autenticação e Autorização

### RF004.1 - Autenticação Google Drive
**Prioridade:** Alta
**Descrição:** O sistema DEVE autenticar requisições para Google Drive via OAuth2.

**Critérios de Aceitação:**
- ✅ Aceita Bearer token no header Authorization
- ✅ Valida token com Google OAuth antes de processar
- ✅ Rejeita tokens inválidos com erro 401
- ✅ Token deve ter permissão `drive.readonly`
- ✅ Verifica se arquivo é acessível pelo token fornecido

**Cenários de Teste:**
```
DADO que o usuário fornece token válido
QUANDO envia requisição para arquivo acessível
ENTÃO sistema aceita e processa

DADO que o usuário fornece token inválido
QUANDO envia requisição
ENTÃO sistema retorna 401 Unauthorized

DADO que o usuário fornece token sem permissão
QUANDO envia requisição
ENTÃO sistema retorna 403 Forbidden
```

---

### RF004.2 - Autenticação Dropbox
**Prioridade:** Alta
**Descrição:** O sistema DEVE autenticar requisições para Dropbox via access token.

**Critérios de Aceitação:**
- ✅ Aceita Bearer token no header Authorization
- ✅ Valida token com Dropbox API antes de processar
- ✅ Rejeita tokens inválidos com erro 401
- ✅ Token deve ter permissão `files.content.read`
- ✅ Verifica se arquivo existe no path fornecido

---

## RF005 - Opções de Conversão

### RF005.1 - Configuração de Output
**Prioridade:** Média
**Descrição:** O sistema DEVE permitir configurar opções de conversão.

**Opções Disponíveis:**
- `include_images` (boolean, default: true) - Incluir imagens no markdown
- `preserve_tables` (boolean, default: true) - Converter tabelas para markdown table
- `extract_metadata` (boolean, default: true) - Extrair metadata do documento
- `chunk_size` (int, optional) - Dividir documentos grandes em chunks

**Critérios de Aceitação:**
- ✅ Opções são passadas no corpo da requisição
- ✅ Valores default são aplicados quando não especificado
- ✅ Opções inválidas são rejeitadas com erro 422
- ✅ Opções são respeitadas durante conversão

**Cenários de Teste:**
```
DADO que o usuário define include_images=false
QUANDO documento é convertido
ENTÃO markdown não contém tags de imagem

DADO que o usuário define preserve_tables=false
QUANDO documento com tabelas é convertido
ENTÃO tabelas são convertidas para texto simples
```

---

### RF005.2 - Webhook de Callback
**Prioridade:** Baixa
**Descrição:** O sistema PODE notificar URL externa quando conversão for concluída.

**Critérios de Aceitação:**
- ✅ Aceita parâmetro opcional `callback_url`
- ✅ Valida formato de URL do callback
- ✅ Envia POST para callback_url quando job completa
- ✅ Payload inclui job_id e status
- ✅ Retry até 3x em caso de falha (com backoff)
- ✅ Falha no callback não afeta resultado do job

**Payload do Callback:**
```json
{
  "job_id": "uuid",
  "status": "completed|failed",
  "completed_at": "2025-10-01T18:00:00Z",
  "result_url": "https://api.doc2md.com/jobs/{job_id}/result",
  "error": null
}
```

---

## RF006 - Download de Arquivos

### RF006.1 - Download de URL Pública
**Prioridade:** Alta
**Descrição:** O sistema DEVE fazer download de arquivos de URLs públicas.

**Critérios de Aceitação:**
- ✅ Suporta protocolo HTTPS (HTTP apenas em dev)
- ✅ Segue redirecionamentos (máximo 5)
- ✅ Valida Content-Type do response
- ✅ Respeita timeout de 30 segundos
- ✅ Rejeita arquivos maiores que limite (50MB)
- ✅ User-Agent identificando o serviço

**Cenários de Teste:**
```
DADO que URL aponta para PDF válido
QUANDO worker faz download
ENTÃO arquivo é baixado com sucesso

DADO que URL tem redirect
QUANDO worker faz download
ENTÃO segue redirect e baixa arquivo

DADO que download excede timeout
QUANDO worker aguarda 30s
ENTÃO job falha com erro TIMEOUT
```

---

### RF006.2 - Download do Google Drive
**Prioridade:** Alta
**Descrição:** O sistema DEVE baixar arquivos do Google Drive via API.

**Critérios de Aceitação:**
- ✅ Usa Google Drive API v3
- ✅ Autenticação via Bearer token do cliente
- ✅ Suporta download de arquivos nativos e uploaded
- ✅ Converte Google Docs para formato exportável (PDF/DOCX)
- ✅ Respeita limite de tamanho

---

### RF006.3 - Download do Dropbox
**Prioridade:** Alta
**Descrição:** O sistema DEVE baixar arquivos do Dropbox via API.

**Critérios de Aceitação:**
- ✅ Usa Dropbox API v2
- ✅ Autenticação via Bearer token do cliente
- ✅ Baixa arquivo do path especificado
- ✅ Verifica existência antes de baixar
- ✅ Respeita limite de tamanho

---

## RF007 - Validação de Entrada

### RF007.1 - Validação de Arquivos
**Prioridade:** Alta
**Descrição:** O sistema DEVE validar arquivos enviados antes de processar.

**Validações:**
- ✅ Tamanho máximo: 50MB (configurável)
- ✅ MIME type permitido
- ✅ Extensão de arquivo válida
- ✅ Arquivo não está corrompido (header check)

**Critérios de Aceitação:**
- Arquivo > 50MB é rejeitado com 413 Payload Too Large
- MIME type não suportado é rejeitado com 422
- Arquivo corrompido é rejeitado com 422

---

### RF007.2 - Validação de URLs
**Prioridade:** Alta
**Descrição:** O sistema DEVE validar URLs antes de fazer download.

**Validações:**
- ✅ Formato de URL válido
- ✅ Protocolo HTTPS (ou HTTP em dev)
- ✅ Domínio resolvível
- ✅ URL acessível (não retorna 4xx/5xx)

**Critérios de Aceitação:**
- URL malformada é rejeitada com 400
- URL inacessível falha job com erro claro
- URL com protocol HTTP em prod é rejeitada

---

## RF008 - Health Check e Monitoramento

### RF008.1 - Health Check
**Prioridade:** Alta
**Descrição:** O sistema DEVE fornecer endpoint de health check.

**Critérios de Aceitação:**
- ✅ Endpoint GET /health retorna status do sistema
- ✅ Verifica conectividade com Redis
- ✅ Verifica workers ativos
- ✅ Retorna 200 se saudável, 503 se degradado

**Resposta:**
```json
{
  "status": "healthy|degraded|unhealthy",
  "version": "1.0.0",
  "redis": true,
  "workers": {
    "active": 3,
    "available": 5
  },
  "timestamp": "2025-10-01T18:00:00Z"
}
```

---

### RF008.2 - Logs de Auditoria
**Prioridade:** Média
**Descrição:** O sistema DEVE registrar logs de todas operações importantes.

**Eventos Logados:**
- ✅ Criação de job (job_id, source_type, size)
- ✅ Início de processamento (job_id, worker_id)
- ✅ Conclusão de job (job_id, duration, success)
- ✅ Falhas e erros (job_id, error_type, message)
- ✅ Downloads externos (url, status_code, duration)

**Critérios de Aceitação:**
- Logs estruturados em JSON
- Logs incluem timestamp, level, context
- Logs sensíveis (tokens) são mascarados
- Logs são persistidos (stdout para Docker)

---

## RF009 - Limpeza e Manutenção

### RF009.1 - Cleanup Automático
**Prioridade:** Média
**Descrição:** O sistema DEVE limpar recursos temporários automaticamente.

**Critérios de Aceitação:**
- ✅ Arquivos temporários são deletados após processamento
- ✅ Resultados expirados são removidos do Redis
- ✅ Jobs antigos (>24h) são arquivados/removidos
- ✅ Cleanup roda a cada hora (Celery beat)

---

### RF009.2 - Gestão de Armazenamento
**Prioridade:** Média
**Descrição:** O sistema DEVE gerenciar espaço em disco eficientemente.

**Critérios de Aceitação:**
- ✅ Diretórios temporários por job (isolamento)
- ✅ Limpeza imediata após conclusão
- ✅ Limite máximo de espaço em disco monitorado
- ✅ Alertas quando espaço < 10% disponível

---

## RF010 - Tratamento de Erros

### RF010.1 - Mensagens de Erro Descritivas
**Prioridade:** Alta
**Descrição:** O sistema DEVE retornar mensagens de erro claras e acionáveis.

**Tipos de Erro:**
- `VALIDATION_ERROR` - Input inválido
- `DOWNLOAD_FAILED` - Falha no download da fonte
- `CONVERSION_FAILED` - Falha na conversão Docling
- `TIMEOUT` - Operação excedeu tempo limite
- `AUTHENTICATION_FAILED` - Token inválido
- `FILE_TOO_LARGE` - Arquivo excede limite
- `UNSUPPORTED_FORMAT` - Formato não suportado

**Critérios de Aceitação:**
- ✅ Erro inclui código e mensagem legível
- ✅ Erro inclui sugestão de ação quando possível
- ✅ Stack traces não expostos em produção
- ✅ Erros são logados com contexto completo

**Exemplo:**
```json
{
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "O arquivo excede o limite de 50MB",
    "details": {
      "file_size_mb": 75,
      "max_size_mb": 50
    },
    "suggestion": "Tente comprimir o arquivo ou dividir em partes menores"
  }
}
```

---

## RF011 - Rate Limiting

### RF011.1 - Limite de Requisições
**Prioridade:** Média
**Descrição:** O sistema DEVE limitar número de requisições por cliente.

**Limites:**
- 10 requisições por minuto por IP (anônimo)
- 100 requisições por minuto por token (autenticado)
- 100 jobs ativos simultâneos por cliente

**Critérios de Aceitação:**
- ✅ Limite é aplicado por IP ou token
- ✅ Exceder limite retorna 429 Too Many Requests
- ✅ Response inclui header `Retry-After`
- ✅ Contador reseta a cada janela de tempo

**Headers de Rate Limit:**
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1696184400
```
