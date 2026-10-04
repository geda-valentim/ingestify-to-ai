# Requisitos Não-Funcionais (RNF) - Doc2MD API

> **Documento histórico (out/2025).** Metas não verificadas; algumas afirmações não valem mais (não há `GET /metrics`/Prometheus; as imagens usam Python 3.13; `JWT_SECRET_KEY` e as credenciais do MinIO são obrigatórias, então a configuração padrão não sobe sozinha). Comportamento atual: [features/](features/) — índice em [README.md](README.md).

## RNF001 - Performance

### RNF001.1 - Tempo de Resposta da API
**Prioridade:** Alta
**Categoria:** Performance

**Requisitos:**
- ✅ Endpoint POST /convert DEVE responder em < 200ms (p95)
- ✅ Endpoint GET /jobs/{job_id} DEVE responder em < 100ms (p95)
- ✅ Endpoint GET /jobs/{job_id}/result DEVE responder em < 150ms (p95)
- ✅ Endpoint GET /health DEVE responder em < 50ms (p95)

**Métricas:**
- p50 (mediana): 50% das requisições
- p95: 95% das requisições
- p99: 99% das requisições

**Cenários de Teste:**
```
DADO que sistema está sob carga normal (10 req/s)
QUANDO medimos latência de 1000 requisições
ENTÃO p95 de POST /convert < 200ms
E p99 < 500ms
```

---

### RNF001.2 - Tempo de Processamento
**Prioridade:** Alta
**Categoria:** Performance

**Requisitos por Tipo de Documento:**
- PDF (10 páginas): < 30 segundos
- DOCX (50 páginas): < 45 segundos
- HTML (1MB): < 15 segundos
- PPTX (30 slides): < 40 segundos

**Critérios de Aceitação:**
- ✅ 90% das conversões completam dentro do tempo esperado
- ✅ Timeout configurável (default: 5 minutos)
- ✅ Progress é atualizado a cada 10% de progresso

---

### RNF001.3 - Throughput
**Prioridade:** Alta
**Categoria:** Performance

**Requisitos:**
- ✅ Sistema DEVE processar mínimo 50 conversões/minuto
- ✅ Sistema DEVE aceitar mínimo 100 requisições/segundo na API
- ✅ Worker DEVE processar 1-3 documentos simultâneos (dependendo do tamanho)

**Cenários de Stress Test:**
```
DADO que temos 5 workers ativos (concurrency=2 cada)
QUANDO submetemos 100 jobs simultaneamente
ENTÃO todos completam em < 10 minutos
E nenhum job falha por timeout de fila
```

---

### RNF001.4 - Cache Performance
**Prioridade:** Média
**Categoria:** Performance

**Requisitos:**
- ✅ Cache hit DEVE reduzir latência em > 80%
- ✅ Redis DEVE responder em < 5ms (p99)
- ✅ Cache miss DEVE adicionar < 10ms de overhead

---

## RNF002 - Escalabilidade

### RNF002.1 - Escalabilidade Horizontal
**Prioridade:** Alta
**Categoria:** Escalabilidade

**Requisitos:**
- ✅ API DEVE ser stateless (sem sessão local)
- ✅ Workers DEVEM ser stateless e independentes
- ✅ Sistema DEVE funcionar com N workers (1 a 100+)
- ✅ Adicionar worker DEVE aumentar capacidade linearmente

**Critérios de Aceitação:**
```
DADO que sistema está com 3 workers (30 jobs/min)
QUANDO escalamos para 6 workers
ENTÃO throughput aumenta para ~60 jobs/min
```

---

### RNF002.2 - Escalabilidade Vertical
**Prioridade:** Média
**Categoria:** Escalabilidade

**Requisitos:**
- ✅ Worker DEVE usar no máximo 2 CPU cores
- ✅ Worker DEVE usar no máximo 1GB RAM por conversão
- ✅ API DEVE usar no máximo 512MB RAM
- ✅ Redis DEVE usar no máximo 2GB RAM

**Limites de Recursos:**
```yaml
# docker-compose.yml
services:
  worker:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 512M
```

---

### RNF002.3 - Capacidade de Fila
**Prioridade:** Alta
**Categoria:** Escalabilidade

**Requisitos:**
- ✅ Fila DEVE suportar mínimo 10.000 jobs pendentes
- ✅ Redis DEVE persistir fila em disco (AOF)
- ✅ Sistema DEVE alertar quando fila > 5.000 jobs
- ✅ Jobs na fila NÃO DEVEM expirar se < 24 horas

---

## RNF003 - Disponibilidade

### RNF003.1 - Uptime
**Prioridade:** Alta
**Categoria:** Disponibilidade

**Requisitos:**
- ✅ Sistema DEVE ter 99.5% uptime mensal (SLA)
- ✅ Downtime planejado < 4 horas/mês
- ✅ Recovery de falha em < 5 minutos
- ✅ Zero data loss em caso de falha

**Cálculo de Uptime:**
- 99.5% = ~3.6 horas de downtime/mês
- 99.9% = ~43 minutos/mês (aspiracional)

---

### RNF003.2 - Resiliência a Falhas
**Prioridade:** Alta
**Categoria:** Disponibilidade

**Requisitos:**
- ✅ Falha de 1 worker NÃO DEVE afetar outros workers
- ✅ Falha de API container DEVE ser auto-recuperável (restart)
- ✅ Falha de Redis DEVE ter backup e restore automático
- ✅ Jobs em processamento DEVEM ser re-enfileirados após crash

**Estratégias:**
- Health checks a cada 30s
- Restart policy: always
- Redis persistence: AOF + RDB
- Celery acks_late=True (para retry)

---

### RNF003.3 - Graceful Degradation
**Prioridade:** Média
**Categoria:** Disponibilidade

**Requisitos:**
- ✅ Se Redis falhar, API DEVE retornar 503 mas não crashar
- ✅ Se todos workers falharem, jobs DEVEM permanecer na fila
- ✅ Se conversão falhar, sistema DEVE marcar job como failed (não crash)
- ✅ Se download externo falhar, retry 3x antes de falhar job

---

## RNF004 - Segurança

### RNF004.1 - Autenticação e Autorização
**Prioridade:** Alta
**Categoria:** Segurança

**Requisitos:**
- ✅ Tokens OAuth NUNCA devem ser logados
- ✅ Tokens DEVEM ser validados antes de enfileirar job
- ✅ Tokens DEVEM ser transmitidos via HTTPS apenas
- ✅ API DEVE suportar CORS configurável

---

### RNF004.2 - Proteção de Dados
**Prioridade:** Alta
**Categoria:** Segurança

**Requisitos:**
- ✅ Arquivos temporários DEVEM ser deletados após processamento
- ✅ Resultados DEVEM expirar automaticamente (TTL)
- ✅ Documentos sensíveis NÃO DEVEM ser cacheados além do TTL
- ✅ Logs NÃO DEVEM conter conteúdo de documentos

**Critérios:**
- Arquivos em /tmp deletados < 1 hora após conclusão
- Resultados no Redis expiram em 1 hora (default)
- Cleanup job roda a cada hora

---

### RNF004.3 - Proteção contra Ataques
**Prioridade:** Alta
**Categoria:** Segurança

**Requisitos:**
- ✅ Rate limiting por IP e por token
- ✅ Validação rigorosa de input (tamanho, tipo, formato)
- ✅ Sanitização de filenames (path traversal protection)
- ✅ Timeout em downloads externos (anti-DDoS)
- ✅ Limite de redirecionamentos (max 5)
- ✅ Rejeição de URLs maliciosas (localhost, IPs privados em prod)

**Proteções:**
```python
# Bloqueios em produção
BLOCKED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    '10.*',      # Private IPs
    '172.16.*',
    '192.168.*',
    '169.254.*', # Link-local
]
```

---

### RNF004.4 - Isolamento de Processos
**Prioridade:** Média
**Categoria:** Segurança

**Requisitos:**
- ✅ Workers DEVEM rodar em containers isolados
- ✅ Cada job DEVE ter diretório temporário isolado
- ✅ Workers NÃO DEVEM ter acesso root
- ✅ Containers DEVEM rodar com usuário não-privilegiado

---

## RNF005 - Confiabilidade

### RNF005.1 - Retry e Recovery
**Prioridade:** Alta
**Categoria:** Confiabilidade

**Requisitos:**
- ✅ Jobs falhados DEVEM ser retentados automaticamente (max 3x)
- ✅ Retry DEVE usar backoff exponencial (60s, 120s, 240s)
- ✅ Falhas permanentes DEVEM ser marcadas como "failed"
- ✅ Jobs NUNCA devem ficar em estado inconsistente

**Cenários de Retry:**
- Download timeout → Retry
- Conversão falhou (transient error) → Retry
- Redis temporariamente indisponível → Retry
- Erro permanente (formato inválido) → Não retry

---

### RNF005.2 - Idempotência
**Prioridade:** Média
**Categoria:** Confiabilidade

**Requisitos:**
- ✅ Reenviar mesma requisição DEVE criar novo job_id (não idempotente por design)
- ✅ Consultar status múltiplas vezes DEVE retornar mesmo resultado
- ✅ Retry de job DEVE sobrescrever resultado anterior

**Nota:** Sistema é idempotente para leituras, mas não para criação de jobs (cada requisição = novo job).

---

### RNF005.3 - Persistência
**Prioridade:** Alta
**Categoria:** Confiabilidade

**Requisitos:**
- ✅ Redis DEVE ter persistência habilitada (AOF)
- ✅ Fila de jobs DEVE sobreviver restart do Redis
- ✅ Jobs em processamento DEVEM ser recuperáveis após restart
- ✅ Backup do Redis DEVE ocorrer diariamente

---

## RNF006 - Manutenibilidade

### RNF006.1 - Logs e Observabilidade
**Prioridade:** Alta
**Categoria:** Manutenibilidade

**Requisitos:**
- ✅ Todos logs DEVEM ser estruturados (JSON)
- ✅ Logs DEVEM incluir correlation ID (job_id)
- ✅ Logs DEVEM ter níveis apropriados (DEBUG, INFO, WARN, ERROR)
- ✅ Logs sensíveis DEVEM ser mascarados

**Formato de Log:**
```json
{
  "timestamp": "2025-10-01T18:00:00Z",
  "level": "INFO",
  "service": "worker",
  "job_id": "550e8400-...",
  "event": "conversion_completed",
  "duration_ms": 2500,
  "source_type": "url",
  "file_size_mb": 5.2
}
```

---

### RNF006.2 - Métricas
**Prioridade:** Média
**Categoria:** Manutenibilidade

**Requisitos:**
- ✅ Sistema DEVE expor métricas Prometheus-compatible
- ✅ Métricas DEVEM incluir:
  - Contador de conversões (por status, source_type)
  - Histograma de duração
  - Gauge de jobs ativos
  - Gauge de tamanho da fila

**Endpoint de Métricas:**
```
GET /metrics

# TYPE conversions_total counter
conversions_total{source_type="url",status="completed"} 1523

# TYPE conversion_duration_seconds histogram
conversion_duration_seconds_bucket{le="10"} 800
conversion_duration_seconds_bucket{le="30"} 1200
```

---

### RNF006.3 - Documentação
**Prioridade:** Média
**Categoria:** Manutenibilidade

**Requisitos:**
- ✅ API DEVE ter documentação OpenAPI/Swagger automática
- ✅ README DEVE incluir guia de setup e uso
- ✅ Código DEVE ter docstrings (PEP 257)
- ✅ Exemplos de uso DEVEM estar documentados

**Documentação Obrigatória:**
- API docs em /docs (Swagger UI)
- README.md com quickstart
- SPECS.md com arquitetura
- RF.md e RNF.md (este documento)

---

### RNF006.4 - Code Quality
**Prioridade:** Média
**Categoria:** Manutenibilidade

**Requisitos:**
- ✅ Código DEVE seguir PEP 8 (Python style guide)
- ✅ Type hints DEVEM ser usados (Python 3.10+)
- ✅ Cobertura de testes DEVE ser > 70%
- ✅ Linter e formatter configurados (ruff, black)

**Tools:**
- Formatter: black
- Linter: ruff
- Type checker: mypy
- Test: pytest

---

## RNF007 - Portabilidade

### RNF007.1 - Containerização
**Prioridade:** Alta
**Categoria:** Portabilidade

**Requisitos:**
- ✅ Todos componentes DEVEM rodar em containers Docker
- ✅ Containers DEVEM ser multi-platform (amd64, arm64)
- ✅ Imagens DEVEM ser otimizadas (< 500MB cada)
- ✅ Docker Compose DEVE permitir setup com 1 comando

---

### RNF007.2 - Configuração
**Prioridade:** Alta
**Categoria:** Portabilidade

**Requisitos:**
- ✅ Configuração DEVE ser via variáveis de ambiente
- ✅ Secrets NÃO DEVEM estar hardcoded
- ✅ Configuração default DEVE funcionar para desenvolvimento
- ✅ .env.example DEVE documentar todas variáveis

**Variáveis Essenciais:**
```bash
REDIS_HOST=redis
REDIS_PORT=6379
CELERY_BROKER_URL=redis://redis:6379/0
MAX_FILE_SIZE_MB=50
CONVERSION_TIMEOUT_SECONDS=300
```

---

### RNF007.3 - Independência de Plataforma
**Prioridade:** Média
**Categoria:** Portabilidade

**Requisitos:**
- ✅ Sistema DEVE rodar em Linux (Ubuntu, Debian, Alpine)
- ✅ Sistema DEVE rodar em macOS (para desenvolvimento)
- ✅ Sistema DEVE rodar em WSL2 (Windows)
- ✅ Dependências de sistema DEVEM estar documentadas

---

## RNF008 - Usabilidade

### RNF008.1 - API Design
**Prioridade:** Alta
**Categoria:** Usabilidade

**Requisitos:**
- ✅ API DEVE seguir padrões REST
- ✅ Endpoints DEVEM ser intuitivos e auto-descritivos
- ✅ Responses DEVEM ser consistentes em formato
- ✅ Erros DEVEM incluir mensagens claras e acionáveis

**Boas Práticas:**
- Use substantivos para recursos (/jobs, não /getJob)
- Use HTTP verbs apropriados (GET, POST)
- Use status codes corretos (200, 400, 404, 500)
- JSON com snake_case

---

### RNF008.2 - Documentação da API
**Prioridade:** Alta
**Categoria:** Usabilidade

**Requisitos:**
- ✅ Swagger UI DEVE estar disponível em /docs
- ✅ Exemplos de requisição DEVEM estar incluídos
- ✅ Schemas DEVEM estar documentados
- ✅ Códigos de erro DEVEM estar documentados

---

### RNF008.3 - Developer Experience
**Prioridade:** Média
**Categoria:** Usabilidade

**Requisitos:**
- ✅ Setup local DEVE ser < 5 minutos
- ✅ Hot reload DEVE funcionar em desenvolvimento
- ✅ Logs DEVEM ser human-readable em desenvolvimento
- ✅ Exemplos de curl DEVEM estar no README

---

## RNF009 - Compliance e Legal

### RNF009.1 - Privacidade (LGPD/GDPR)
**Prioridade:** Alta
**Categoria:** Compliance

**Requisitos:**
- ✅ Documentos NÃO DEVEM ser armazenados além do necessário
- ✅ Resultados DEVEM ter TTL configurável
- ✅ Sistema DEVE permitir deleção de jobs sob demanda
- ✅ Logs NÃO DEVEM conter dados pessoais

**Retenção de Dados:**
- Arquivos temporários: deletados imediatamente após conversão
- Resultados: 1 hora (default, configurável)
- Logs: 30 dias
- Métricas agregadas: indefinido (sem PII)

---

### RNF009.2 - Auditoria
**Prioridade:** Média
**Categoria:** Compliance

**Requisitos:**
- ✅ Todas conversões DEVEM ser logadas
- ✅ Logs DEVEM incluir timestamp, fonte, resultado
- ✅ Logs DEVEM ser imutáveis
- ✅ Acesso a logs DEVE ser restrito

---

## RNF010 - Custo e Eficiência

### RNF010.1 - Uso de Recursos
**Prioridade:** Média
**Categoria:** Eficiência

**Requisitos:**
- ✅ Worker DEVE usar no máximo 2GB RAM por job
- ✅ API DEVE usar no máximo 512MB RAM
- ✅ Redis DEVE usar no máximo 2GB RAM
- ✅ Armazenamento temporário < 10GB

**Monitoramento:**
- Alertas quando uso > 80% dos limites
- Cleanup automático de espaço

---

### RNF010.2 - Otimização de Custos
**Prioridade:** Baixa
**Categoria:** Eficiência

**Requisitos:**
- ✅ Workers DEVEM escalar automaticamente baseado na fila
- ✅ Workers idle DEVEM ser desligados após 10 minutos
- ✅ Cache DEVE reduzir processamento redundante
- ✅ Resultados expirados DEVEM ser removidos automaticamente

---

## RNF011 - Testabilidade

### RNF011.1 - Testes Automatizados
**Prioridade:** Alta
**Categoria:** Testabilidade

**Requisitos:**
- ✅ API DEVE ter testes de integração
- ✅ Workers DEVEM ter testes unitários
- ✅ Source handlers DEVEM ter testes mockados
- ✅ Cobertura de testes > 70%

**Tipos de Teste:**
- Unit tests: funções isoladas
- Integration tests: API + Redis + Worker
- E2E tests: fluxo completo de conversão

---

### RNF011.2 - Ambiente de Testes
**Prioridade:** Média
**Categoria:** Testabilidade

**Requisitos:**
- ✅ Testes DEVEM rodar em CI/CD
- ✅ Testes NÃO DEVEM depender de serviços externos
- ✅ Testes DEVEM usar mocks para APIs externas (Google Drive, Dropbox)
- ✅ Testes DEVEM ser determinísticos (não flaky)

---

## Resumo de Prioridades

### Alta Prioridade (Must Have)
- Performance: Latência < 200ms, throughput > 50/min
- Disponibilidade: 99.5% uptime, auto-recovery
- Segurança: Autenticação, rate limiting, validação
- Escalabilidade: Horizontal scaling, stateless
- Confiabilidade: Retry, persistência, recovery

### Média Prioridade (Should Have)
- Métricas e observabilidade
- Graceful degradation
- Documentação completa
- Testes automatizados
- Otimização de custos

### Baixa Prioridade (Nice to Have)
- Webhooks de callback
- Métricas avançadas
- Dashboards de monitoramento
- Autoscaling avançado
