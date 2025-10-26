# Migration Guide: Legacy → Clean Architecture

Este guia mostra como migrar gradualmente do código antigo para Clean Architecture.

---

## 🎯 Estratégia de Migração

### Abordagem: **Strangler Fig Pattern**

Não deletar código antigo imediatamente. Criar **versão 2 dos endpoints** (Clean Architecture) em paralelo com versão 1 (legacy).

```
/convert         → Legacy (mantém funcionando)
/v2/convert      → Clean Architecture (novo)

Gradualmente:
1. Criar v2 endpoints
2. Testar v2 endpoints
3. Migrar clientes para v2
4. Deprecar v1 endpoints
5. Deletar v1 endpoints
```

---

## 📋 Checklist de Migração

### Fase 1: Setup ✅ (Concluído)
- [x] Criar estrutura de diretórios (domain, application, infrastructure, presentation)
- [x] Implementar Domain Layer
- [x] Implementar Application Layer
- [x] Implementar Infrastructure Layer
- [x] Criar DI Container
- [x] Criar exemplo de controller v2

### Fase 2: Endpoints v2 (Em Progresso)
- [x] POST /v2/convert
- [x] GET /v2/jobs/{job_id}
- [x] GET /v2/jobs/{job_id}/result
- [ ] GET /v2/jobs/{job_id}/pages
- [ ] POST /v2/jobs/{job_id}/pages/{page_number}/retry
- [ ] DELETE /v2/jobs/{job_id}
- [ ] GET /v2/jobs
- [ ] GET /v2/search

### Fase 3: Workers (Pendente)
- [ ] Refatorar `process_conversion` task
- [ ] Refatorar `split_pdf_task`
- [ ] Refatorar `convert_page_task`
- [ ] Refatorar `merge_pages_task`

### Fase 4: Testes (Pendente)
- [ ] Testes unitários de Domain
- [ ] Testes de Use Cases
- [ ] Testes de Repositories
- [ ] Testes de Adapters
- [ ] Testes de integração

### Fase 5: Deprecação (Futuro)
- [ ] Marcar v1 endpoints como deprecated
- [ ] Adicionar warnings nos logs
- [ ] Deletar v1 endpoints

---

## 🔄 Exemplo de Migração: Endpoint

### ❌ ANTES (Legacy - api/routes.py)

```python
@router.post("/convert", response_model=JobCreatedResponse)
async def convert_document(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    # 150+ linhas de código misturando:
    # - Validação
    # - Lógica de negócio
    # - Acesso a Redis direto
    # - Acesso a MySQL direto
    # - Chamadas Celery diretas
    # - Tratamento de erros

    redis_client = get_redis_client()  # ❌ Dependência direta

    # Lógica de negócio no controller ❌
    if file_size_mb > settings.max_file_size_mb:
        raise HTTPException(...)

    job_id = uuid4()  # ❌ Geração de ID no controller

    # Redis direto ❌
    redis_client.set_job_status(...)

    # MySQL direto ❌
    db_job = Job(...)
    db.add(db_job)
    db.commit()

    # Celery direto ❌
    from workers.tasks import process_conversion
    process_conversion.delay(...)

    return JobCreatedResponse(...)
```

**Problemas:**
- ❌ Controller tem 150+ linhas
- ❌ Lógica de negócio misturada com infraestrutura
- ❌ Impossível testar sem Redis/MySQL/Celery
- ❌ Acoplamento forte
- ❌ Difícil de manter

---

### ✅ DEPOIS (Clean Architecture - presentation/api/controllers/conversion_controller.py)

```python
@router.post("/v2/convert", response_model=JobCreatedResponse)
async def convert_document(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    use_case: ConvertDocumentUseCase = Depends(get_convert_document_use_case)
):
    """
    Controller MAGRO: apenas 30 linhas!
    """
    # 1. Validação simples
    file_contents = await file.read()
    file_size_mb = len(file_contents) / (1024 * 1024)

    if file_size_mb > settings.max_file_size_mb:
        raise HTTPException(status_code=413, detail="File too large")

    # 2. Salvar arquivo temporário
    temp_file_path = save_temp_file(file_contents, file.filename)

    # 3. Converter para DTO
    dto = ConvertRequestDTO(
        user_id=current_user.id,
        source_type="file",
        source=str(temp_file_path),
        filename=file.filename,
        file_size_bytes=len(file_contents),
        mime_type=file.content_type,
        name=name,
    )

    # 4. Executar Use Case (lógica de negócio)
    try:
        response_dto = await use_case.execute(dto)
    except ConvertDocumentError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 5. Retornar response
    return JobCreatedResponse(
        job_id=response_dto.job_id,
        status=response_dto.status,
        created_at=response_dto.created_at,
        message=response_dto.message
    )
```

**Benefícios:**
- ✅ Controller com apenas 30 linhas
- ✅ Lógica de negócio no Use Case
- ✅ Testável (mock do Use Case)
- ✅ Baixo acoplamento
- ✅ Fácil de manter

---

## 🧪 Como Testar Use Cases

### ❌ ANTES: Impossível testar sem infraestrutura

```python
# Não consegue testar convert_document() sem:
# - Redis rodando
# - MySQL rodando
# - Celery rodando
# - FastAPI app rodando

# Testes lentos e frágeis
```

---

### ✅ DEPOIS: Testes unitários rápidos

```python
import pytest
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_convert_document_use_case():
    # Arrange: Mock dependencies (SEM infraestrutura!)
    job_repo_mock = MagicMock(spec=JobRepository)
    job_repo_mock.save = AsyncMock()

    queue_mock = MagicMock(spec=QueuePort)
    queue_mock.enqueue_conversion = AsyncMock(return_value="task-123")

    use_case = ConvertDocumentUseCase(
        job_repository=job_repo_mock,
        queue=queue_mock
    )

    dto = ConvertRequestDTO(
        user_id="user-123",
        source_type="file",
        source="/path/to/file.pdf",
        filename="file.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf"
    )

    # Act
    response = await use_case.execute(dto)

    # Assert
    assert response.status == "queued"
    assert response.job_id is not None
    job_repo_mock.save.assert_called_once()
    queue_mock.enqueue_conversion.assert_called_once()


# Teste roda em < 1ms (sem infraestrutura!)
# Teste determinístico (sem race conditions)
# Teste fácil de escrever (mock via interfaces)
```

---

## 🔧 Como Adicionar Novo Use Case

### Passo 1: Criar Use Case (Application Layer)

```python
# application/use_cases/delete_job.py

class DeleteJobUseCase:
    def __init__(
        self,
        job_repository: JobRepository,
        page_repository: PageRepository,
        storage: StoragePort
    ):
        self.job_repository = job_repository
        self.page_repository = page_repository
        self.storage = storage

    async def execute(self, job_id: str, user_id: str) -> None:
        # 1. Buscar job
        job = await self.job_repository.find_by_id(job_id)

        if not job:
            raise JobNotFoundError(f"Job {job_id} not found")

        # 2. Verificar ownership
        if job.user_id != user_id:
            raise UnauthorizedError("Access denied")

        # 3. Deletar páginas
        await self.page_repository.delete_by_job_id(job_id)

        # 4. Deletar resultado do storage
        await self.storage.delete_job_result(job_id)

        # 5. Deletar job
        await self.job_repository.delete(job_id)
```

### Passo 2: Adicionar ao DI Container

```python
# infrastructure/di_container.py

def get_delete_job_use_case(self) -> DeleteJobUseCase:
    return DeleteJobUseCase(
        job_repository=self.get_job_repository(),
        page_repository=self.get_page_repository(),
        storage=self.get_storage()
    )
```

### Passo 3: Adicionar Dependency

```python
# presentation/api/dependencies.py

def get_delete_job_use_case(
    container: DIContainer = Depends(get_container)
) -> DeleteJobUseCase:
    return container.get_delete_job_use_case()
```

### Passo 4: Criar Controller

```python
# presentation/api/controllers/conversion_controller.py

@router.delete("/v2/jobs/{job_id}")
async def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    use_case: DeleteJobUseCase = Depends(get_delete_job_use_case)
):
    try:
        await use_case.execute(job_id=job_id, user_id=current_user.id)
        return {"message": "Job deleted successfully"}
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedError as e:
        raise HTTPException(status_code=403, detail=str(e))
```

**Pronto! 4 passos simples.**

---

## 📊 Comparação: Legacy vs Clean Architecture

| Aspecto | Legacy (v1) | Clean Architecture (v2) |
|---------|-------------|-------------------------|
| **Linhas por endpoint** | 150-200 | 30-50 |
| **Testabilidade** | ❌ Precisa infraestrutura | ✅ Mocks via interfaces |
| **Tempo de testes** | ~10s por teste | ~1ms por teste |
| **Acoplamento** | ❌ Alto (Redis, MySQL direto) | ✅ Baixo (via abstrações) |
| **Manutenibilidade** | ❌ Difícil (lógica espalhada) | ✅ Fácil (lógica isolada) |
| **Reutilização** | ❌ Código só em API | ✅ Use Cases em API, CLI, Workers |
| **Flexibilidade** | ❌ Trocar Redis = mudar tudo | ✅ Trocar Redis = mudar 1 adapter |

---

## 🚀 Roadmap de Migração (Sugerido)

### Sprint 1 (Semana 1-2)
- [x] Implementar estrutura Clean Architecture
- [x] Criar v2 de endpoints principais (convert, status, result)
- [ ] Testar v2 endpoints em paralelo com v1

### Sprint 2 (Semana 3-4)
- [ ] Criar v2 de endpoints restantes (pages, retry, delete, list, search)
- [ ] Escrever testes unitários de Use Cases
- [ ] Escrever testes de integração

### Sprint 3 (Semana 5-6)
- [ ] Refatorar Workers para usar Use Cases
- [ ] Adicionar métricas de comparação v1 vs v2
- [ ] Documentar APIs v2 (OpenAPI)

### Sprint 4 (Semana 7-8)
- [ ] Migrar frontend para usar v2 endpoints
- [ ] Adicionar deprecation warnings em v1
- [ ] Preparar comunicação para usuários

### Sprint 5 (Semana 9-10)
- [ ] Deletar v1 endpoints
- [ ] Cleanup de código legacy
- [ ] Celebrar! 🎉

---

## 💡 Dicas

### 1. Mantenha v1 Funcionando
Não quebre nada existente. Clean Architecture é adição, não substituição inicial.

### 2. Teste Incremental
Cada novo Use Case deve ter testes unitários **antes** de ir para produção.

### 3. Monitore Métricas
Compare performance v1 vs v2:
- Tempo de resposta
- Taxa de erro
- Uso de recursos

### 4. Documente Decisões
Use ADRs (Architecture Decision Records) para documentar escolhas importantes.

### 5. Envolva o Time
Clean Architecture é mudança cultural. Treine o time nos conceitos.

---

## 📚 Recursos de Aprendizado

1. **Clean Architecture (Robert C. Martin)**
   - Livro: https://www.amazon.com/Clean-Architecture-Craftsmans-Software-Structure/dp/0134494164
   - Blog: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html

2. **Hexagonal Architecture**
   - https://alistair.cockburn.us/hexagonal-architecture/

3. **Domain-Driven Design (Eric Evans)**
   - Livro: https://www.amazon.com/Domain-Driven-Design-Tackling-Complexity-Software/dp/0321125215

4. **SOLID Principles**
   - https://en.wikipedia.org/wiki/SOLID

---

## ❓ FAQ

**Q: Preciso reescrever tudo agora?**
A: Não! Migração é gradual. v1 e v2 coexistem.

**Q: E se v2 tiver bugs?**
A: v1 continua funcionando. Rollback é simples.

**Q: Clean Architecture não deixa código mais complexo?**
A: Inicialmente mais arquivos, mas cada arquivo é mais simples. Trade-off vale a pena para projetos médios/grandes.

**Q: Quanto tempo leva para migrar tudo?**
A: Depende do tamanho. Para Ingestify: estimativa de 8-10 semanas (com testes).

**Q: Posso usar Clean Architecture parcialmente?**
A: Sim! Alguns endpoints v2, outros v1. Migração gradual.

---

## 🎯 Próximo Passo

**Comece pequeno:** Escolha 1 endpoint simples e migre para v2. Teste. Aprenda. Repita.

Boa sorte na migração! 🚀
