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


---

## RF012 - Engines, operações, perfis e acesso

Contratos implementados conferidos em **2026-10-06** nas specs [0003](specs/0003-motores-de-execucao-roteamento-e-orcamento.md),
[0007](specs/0007-operacao-de-engines-pelo-admin.md) e [0009](specs/0009-perfis-de-execucao-e-controle-de-acesso.md).
Os IDs correspondem aos requisitos publicados na documentação web em português e inglês.
Eles descrevem comportamento da implementação; ativação das flags não comprova readiness ou qualificação de produção.

| Grupo | Guia público | Aplicações |
|---|---|---|
| ENG | [/docs/engines](https://dev.ingestify.ai/pt/docs/engines) | PDFs por página, OCR/visão local, rajadas de áudio, roteamento e custo Modal |
| OPS | [/docs/engine-operations](https://dev.ingestify.ai/pt/docs/engine-operations) | Manutenção com drain, escala/perfil, aquecer/liberar modelo e recuperar exposição |
| PRF | [/docs/execution-profiles](https://dev.ingestify.ai/pt/docs/execution-profiles) | Configuração reutilizável, revisões imutáveis, publicação e vínculo explícito |
| ACL | [/docs/engine-access](https://dev.ingestify.ai/pt/docs/engine-access) | Observabilidade, separação de funções, dev sem produção, delegação e credenciais |

### RF012.1 - Requisitos verificáveis

| ID | Comportamento e condição de aceitação |
|---|---|
| ENG-01 · Inventário | Listar engines e adapters permitidos, bindings, configured × alive, health e deployments. Leitura delegada e catálogos são filtrados pelo escopo; métricas desconhecidas não significam zero. |
| ENG-02 · Conexões | Bootstrap cria conexão Modal pausada, grava ou exclui credenciais seladas com senha atual, testa uma ou todas as conexões e registra auditoria. A API não devolve segredos; conta gerenciada respeita locks e exposição pendente. |
| ENG-03 · Capacidade e VRAM | Validar soma das pegadas e reserva por GPU física, limites do adapter e capacidade remota do executor. GPU local e Modal aceitam E=1; binding local sem GPU pode admitir E>1. Declaração legada não escala processos. |
| ENG-04 · Roteamento | Aceitar passos ordenados, grupos priority/fill_first, condições de espera/backlog e spend_cap. Sem rota, manter o caminho local habitual. Rotas de documento/visão aceitam apenas local; captura live não usa feature_routes. |
| ENG-05 · Despacho e recuperação | Persistir backlog FIFO e ledger por tentativa, limitar em voo, usar lease do líder e claim/heartbeat do executor. Recolocar claims abandonados, aplicar backoff e max_attempts; remover rota drena para o caminho habitual. |
| ENG-06 · Lifecycle | Ativar libera novas colocações; pausar bloqueia novas e preserva trabalhos em voo; reset-health limpa falhas registradas. Estas ações de escalonamento não iniciam, drenam nem desligam containers. |
| ENG-07 · Orçamento | Admitir remoto somente se max(ledger, reportado) + reservado + estimativa couber no limite menos a margem. Aplicar período/fuso, limite por usuário quando habilitado e caps de rota; reconciliar gasto e alertar antes/esgotamento. |
| ENG-08 · Qualificação e desempenho | Conferir fingerprint do deploy e readiness, consultar benchmarks e velocidade aprendida. Benchmark CLI tem plano, amostra, teto remoto e confirmação; recommendation com --apply exige redeploy se mudar o remoto. |
| OPS-01 · Capabilities | Exibir somente features e ações suportadas/autorizadas com razão do bloqueio. Consultar capabilities para a feature selecionada; ação não descrita não pode ser executada. |
| OPS-02 · Prévia | Criar plano sem iniciar recursos: congelar versão da engine, revisão, hash, identidade, recursos afetados, efeitos, etapas, custo e expiração de cinco minutos. |
| OPS-03 · Execução idempotente | Executar plan_id + plan_hash com Idempotency-Key; retornar 202 e operation_id. Retry da mesma requisição usa a mesma chave e não duplica efeitos. Outra intenção exige nova chave/plano. |
| OPS-04 · Locks, drenagem e readiness | Reservar recursos canônicos, cobrir desejado e aplicado, bloquear colocações afetadas e aguardar ledger/live/Celery. Timeout de drain falha sem desligar à força. Verificar inferência, imagem e réplica; processo vivo não basta. |
| OPS-05 · Eventos e auditoria | Persistir histórico, snapshot e eventos com seq. Polling after/next ou SSE com Authorization recupera eventos após reconexão. Filtrar e revalidar sessão/escopo por lote; nunca pôr token na URL. |
| OPS-06 · Cancelar e recuperar | can_cancel/can_recover dependem de estado e permissão atual. Cancelamento cooperativo não desfaz RPC aceito. Recovery observa exposição antes de continuar e usa o solicitante atual sem apagar o iniciador. |
| OPS-07 · Exposição e revogação | Revalidar autoridade antes de cada efeito; revogação impede novos passos. Resultado incerto mantém locks/reservas; watchdog limpa exposição registrada sem iniciar recursos com uma sessão revogada. |
| PRF-01 · Biblioteca e metadata | Listar/detalhar somente perfis autorizados. Criar nome (1–100 caracteres), descrição (até 1.000), adapter, feature e ambiente; editar nome/descrição com versão esperada. |
| PRF-02 · Revisões e publicação | Salvar novo payload como revisão imutável, publicar revision_id explícito com version. Rascunho posterior não substitui publicação anterior; catálogo aprovado é fixado por fingerprint. |
| PRF-03 · Vínculo | POST bind aceita versão da engine, feature e revisão publicada. Resolver host/GPU/modelo e gravar origem/hash/snapshot atomicamente. Não iniciar container, deploy ou reserva de orçamento. |
| PRF-04 · Histórico, clone e importação | Detalhe mostra revisões e vínculos permitidos. Clone pela UI cria perfil novo em rascunho; bootstrap pode importar desejado legado retirando campos resolvidos. Arquivar barra novos vínculos e preserva histórico/aplicado. |
| PRF-05 · Compatibilidade | Validar schema/adapter, réplicas, VRAM, host/UUID, ambiente, modelo e fingerprint. Alteração do catálogo ou manifest exige revisão/vínculo explícito, não troca silenciosa em operação. |
| PRF-06 · Prazo e concorrência de edição | warm_for_seconds até 86.400; template warm_until=null. Resolver deadline uma vez no vínculo. Retry não renova prazo; VERSION_CONFLICT pede leitura e revisão da intenção. |
| ACL-01 · Sessão e navegação | /access/me e /auth/me retornam estado e permissões; servidor autoriza cada ação e filtra listagens/catálogos/logs/SSE. Cache isolado por sessão não reaproveita dados entre logins. |
| ACL-02 · Políticas revisionadas | Criar política e revisões de constraints imutáveis; o grant fixa policy_revision_id. Revisão nova não amplia grants existentes. |
| ACL-03 · Grants e validade | Conceder a usuário ativo papel/subconjunto, revisão de política e expires_at UTC. Revogar com version; usuário inativo, grant vencido/revogado ou pai inválido perde autoridade. |
| ACL-04 · Uma decisão completa | Um único grant precisa cobrir todas as permissões, identidades e limites da decisão. Não combinar host de um grant com custo ou feature de outro. |
| ACL-05 · Delegação limitada | Envelope limita permissões concedíveis, escopo, tetos e max_grant_seconds. Grant filho não amplia pai nem prazo; revogação/expiração parental invalida descendentes. |
| ACL-06 · Recursos compartilhados | Bootstrap classifica ambiente e todos os consumidores de cada recurso. Autorizar união do desejado e aplicado; consumidor desconhecido, não qualificado ou fora do grant bloqueia operação delegada. |
| ACL-07 · Revogação e auditoria | Autorizar novamente no enqueue, runner, agente e antes de RPC. Admission/epoch duráveis ordenam revogação e efeitos. Auditar publicação, vínculo, grant, estado, cancelamento e recovery, sem segredos. |
| ACL-08 · Bootstrap e CLI | Gestão global de GPU, rota, orçamento, configuração bruta e lifecycle permanece bootstrap-only. Registrar/ativar/desativar installation principals e alterar estado de sujeitos com comparação esperada; CLI direta não usa sessão delegada. |

### RF012.2 - Pré-condições, interfaces e limites

- Biblioteca/delegação: schemas de acesso e IAM (0009, 0014, 0018) migrados, `IAM_MODE=enforce` (ou o alias depreciado `ENGINE_ACCESS_ENABLED=true`) e sessão JWT.
- Controle físico: schema de controle migrado, `ENGINE_CONTROL_ENABLED`, runner e dependências do adapter.
- Local: agente com manifests/comandos/imagens e serviços registrados, heartbeat ≤30 s e inventário válido.
- Modal: credenciais, identidade testada, orçamento, worker remoto, watchdog e artifact/protocolo compatíveis.
- Binding legado declara capacidade sem escalar containers; ativar/pausar governa novas colocações.
- Runtime gerenciado: criar/publicar/vincular não executa efeitos; prévia e execução são separadas e aplicado exige verificação.
- Rotas de documento/visão permanecem locais; Modal atende transcrição de arquivos. Microfone tem worker/piloto próprio.
- AWS, GCP e Vast AI dependem de adapters futuros; WhisperX não está qualificado para controle Modal.
- Enum `benchmark` não significa suporte no modal de operações: a medição continua na CLI.

Campos, limites, papéis, API, erros e exemplos estão nos quatro guias públicos.
Bootstrap e rollback: [controle](runbooks/engine-control-bootstrap.md) e [perfis/acesso](runbooks/execution-profiles-access.md).
Evidências e canários pendentes: [validação](benchmarks/execution-profiles-validation.md).
