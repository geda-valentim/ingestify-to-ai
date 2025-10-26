# Clean Architecture - Ingestify Backend

## 📐 Visão Geral

O backend do Ingestify foi refatorado para seguir princípios de **Clean Architecture** (Uncle Bob). A arquitetura separa responsabilidades em camadas concêntricas, onde **camadas internas não dependem de camadas externas**.

```
┌─────────────────────────────────────────────────┐
│          Presentation (API/Controllers)          │  ← Frameworks & Drivers
├─────────────────────────────────────────────────┤
│      Infrastructure (Adapters & Repositories)    │  ← Interface Adapters
├─────────────────────────────────────────────────┤
│         Application (Use Cases & Ports)          │  ← Application Business Rules
├─────────────────────────────────────────────────┤
│       Domain (Entities & Business Logic)         │  ← Enterprise Business Rules
└─────────────────────────────────────────────────┘
```

## 🎯 Princípios Aplicados

### 1. **Dependency Inversion Principle (DIP)**
- Camadas internas definem **interfaces** (abstrações)
- Camadas externas implementam essas interfaces
- Domain e Application **nunca** dependem de Infrastructure

### 2. **Single Responsibility Principle (SRP)**
- Cada Use Case tem **uma única responsabilidade**
- Entities contêm apenas **regras de negócio**
- Controllers apenas **adaptam** requisições/respostas

### 3. **Interface Segregation Principle (ISP)**
- Interfaces pequenas e específicas (Ports)
- Repositórios separados por agregado

### 4. **Testability**
- Use Cases testáveis sem infraestrutura
- Mocks via interfaces (Ports/Repositories)

---

## 📂 Estrutura de Camadas

### Layer 1: **Domain** (Núcleo - Regras de Negócio Puras)

```
domain/
├── entities/           # Entidades de negócio
│   ├── job.py         # Job entity com validações
│   ├── page.py        # Page entity
│   └── user.py        # User entity
├── value_objects/     # Objetos de valor imutáveis
│   ├── job_id.py      # JobId (validação de UUID)
│   ├── progress.py    # Progress (0-100 com validações)
│   └── document_info.py  # DocumentInfo metadata
├── repositories/      # Interfaces (abstrações)
│   ├── job_repository.py
│   ├── page_repository.py
│   └── user_repository.py
└── services/          # Serviços de domínio
    ├── pdf_analysis_service.py      # should_split_pdf(), count_pages()
    └── progress_calculator_service.py  # Cálculo de progresso
```

**Características:**
- ✅ Zero dependências externas
- ✅ Contém toda lógica de negócio
- ✅ Entidades com validações automáticas
- ✅ Value Objects imutáveis

**Exemplos:**

```python
# Entity with business rules
job = Job(id=job_id, user_id=user_id, job_type=JobType.MAIN, status=JobStatus.QUEUED)
job.mark_as_processing()  # Business rule: updates status + timestamps

# Value Object with validation
progress = Progress(value=50)  # Validates 0-100
progress = Progress.from_pages(completed=5, total=10)  # Business logic

# Domain Service
should_split = PDFAnalysisService.should_split_pdf(file_path, min_pages=2)
```

---

### Layer 2: **Application** (Casos de Uso - Orquestração)

```
application/
├── use_cases/         # Casos de uso (1 arquivo = 1 funcionalidade)
│   ├── convert_document.py      # Converte documento
│   ├── get_job_status.py        # Retorna status
│   └── get_job_result.py        # Retorna resultado
├── dto/               # Data Transfer Objects
│   ├── convert_request_dto.py
│   ├── job_response_dto.py
│   └── page_response_dto.py
└── ports/             # Interfaces para dependências externas
    ├── converter_port.py   # Interface para Docling
    ├── storage_port.py     # Interface para Redis/ES
    └── queue_port.py       # Interface para Celery
```

**Características:**
- ✅ Orquestra lógica de negócio
- ✅ Depende apenas de **abstrações** (Ports/Repositories)
- ✅ Testável sem infraestrutura
- ✅ Um Use Case = Uma funcionalidade

**Exemplo de Use Case:**

```python
class ConvertDocumentUseCase:
    def __init__(
        self,
        job_repository: JobRepository,  # Abstração (interface)
        queue: QueuePort                # Abstração (interface)
    ):
        self.job_repository = job_repository
        self.queue = queue

    async def execute(self, request: ConvertRequestDTO) -> JobResponseDTO:
        # 1. Criar job entity
        job = Job(id=JobId.generate(), user_id=request.user_id, ...)

        # 2. Persistir (via abstração)
        await self.job_repository.save(job)

        # 3. Enfileirar (via abstração)
        await self.queue.enqueue_conversion(job.id, ...)

        # 4. Retornar DTO
        return JobResponseDTO(job_id=job.id, status="queued", ...)
```

---

### Layer 3: **Infrastructure** (Implementações Concretas)

```
infrastructure/
├── repositories/      # Implementações de repositórios
│   ├── mysql_job_repository.py      # JobRepository com SQLAlchemy
│   ├── redis_job_repository.py      # JobRepository com Redis
│   └── elasticsearch_repository.py  # Para busca
├── adapters/          # Adaptadores para serviços externos
│   ├── docling_adapter.py           # Implementa ConverterPort
│   ├── celery_adapter.py            # Implementa QueuePort
│   └── source_handlers/
│       ├── file_handler.py
│       ├── url_handler.py
│       └── gdrive_handler.py
├── orm/               # SQLAlchemy models (apenas persistência)
│   └── models.py      # Tabelas: jobs, pages, users
└── config/
    └── settings.py    # Configurações (env vars)
```

**Características:**
- ✅ Implementa interfaces definidas em Domain/Application
- ✅ Detalhes técnicos (SQL, Redis, Celery)
- ✅ Substituível sem afetar negócio

**Exemplo de Adapter:**

```python
class CeleryQueueAdapter(QueuePort):
    """Implementação concreta do QueuePort usando Celery"""

    async def enqueue_conversion(
        self, job_id: str, source_type: str, source: str, options: dict, ...
    ) -> str:
        # Detalhe de implementação: Celery
        task = process_conversion.delay(job_id, source_type, source, options)
        return task.id
```

---

### Layer 4: **Presentation** (API/Controllers)

```
presentation/
├── api/
│   ├── controllers/
│   │   ├── conversion_controller.py  # POST /convert, GET /jobs/{id}
│   │   ├── auth_controller.py
│   │   └── health_controller.py
│   ├── dependencies.py    # FastAPI dependency injection
│   └── main.py           # FastAPI app setup
└── schemas/              # Pydantic models (API contracts)
    ├── requests.py
    └── responses.py
```

**Características:**
- ✅ Controllers **magros** (apenas adaptação)
- ✅ Delegam para Use Cases
- ✅ Validam input com Pydantic
- ✅ Serializam output

**Exemplo de Controller:**

```python
@router.post("/convert")
async def convert_document(
    request: ConvertRequest,  # Pydantic schema
    current_user: User = Depends(get_current_user),
    use_case: ConvertDocumentUseCase = Depends(get_convert_use_case)  # DI
):
    # 1. Converter Pydantic para DTO
    dto = ConvertRequestDTO(
        user_id=current_user.id,
        source_type=request.source_type,
        source=request.source,
        ...
    )

    # 2. Executar Use Case (lógica de negócio)
    response = await use_case.execute(dto)

    # 3. Converter DTO para Pydantic response
    return JobCreatedResponse(
        job_id=response.job_id,
        status=response.status,
        ...
    )
```

---

## 🔄 Fluxo de Dados (Request → Response)

```
1. HTTP Request
   ↓
2. Controller (Presentation)
   - Valida input (Pydantic)
   - Converte para DTO
   ↓
3. Use Case (Application)
   - Orquestra lógica
   - Usa Entities (Domain)
   - Chama Repositories/Ports (abstrações)
   ↓
4. Repository/Adapter (Infrastructure)
   - Implementação concreta
   - Acessa Redis/MySQL/Celery
   ↓
5. Controller (Presentation)
   - Converte DTO para Response
   - Serializa para JSON
   ↓
6. HTTP Response
```

**Exemplo concreto:**

```
POST /convert
    ↓
ConversionController.convert_document()
    ├─> Valida ConvertRequest (Pydantic)
    ├─> Converte para ConvertRequestDTO
    ↓
ConvertDocumentUseCase.execute(dto)
    ├─> Cria Job entity (domain)
    ├─> job_repository.save(job)  ← chama MySQLJobRepository
    ├─> queue.enqueue_conversion()  ← chama CeleryQueueAdapter
    ↓
JobResponseDTO retornado
    ↓
Controller serializa para JobCreatedResponse
    ↓
JSON response
```

---

## 🧪 Testabilidade

### Testes de Domínio (Sem mocks)

```python
def test_job_entity_validates_progress():
    with pytest.raises(ValueError):
        Job(id="123", progress=150)  # Invalid: > 100

def test_progress_value_object():
    progress = Progress.from_pages(completed=5, total=10)
    assert progress.value == 50
```

### Testes de Use Cases (Com mocks)

```python
@pytest.mark.asyncio
async def test_convert_document_use_case():
    # Arrange: Mock dependencies
    job_repo_mock = MagicMock(spec=JobRepository)
    queue_mock = MagicMock(spec=QueuePort)

    use_case = ConvertDocumentUseCase(
        job_repository=job_repo_mock,
        queue=queue_mock
    )

    dto = ConvertRequestDTO(user_id="user1", source_type="file", ...)

    # Act
    response = await use_case.execute(dto)

    # Assert
    job_repo_mock.save.assert_called_once()
    queue_mock.enqueue_conversion.assert_called_once()
    assert response.status == "queued"
```

---

## 🎁 Benefícios da Clean Architecture

| Benefício | Descrição |
|-----------|-----------|
| **Testabilidade** | Use Cases testáveis sem infraestrutura (mocks via interfaces) |
| **Manutenibilidade** | Mudanças isoladas por camada |
| **Flexibilidade** | Trocar Redis por Memcached sem afetar Domain/Application |
| **Clareza** | Separação clara entre negócio e infraestrutura |
| **Reusabilidade** | Entities e Use Cases reutilizáveis |
| **Independência de Framework** | Domain não depende de FastAPI, SQLAlchemy, Celery |

---

## 🚀 Próximos Passos

1. **Implementar Infrastructure Layer**
   - MySQLJobRepository
   - RedisJobRepository
   - ElasticsearchRepository
   - DoclingAdapter
   - CeleryQueueAdapter

2. **Refatorar Presentation Layer**
   - Controllers delegam para Use Cases
   - Dependency Injection via FastAPI Depends

3. **Refatorar Workers**
   - Tasks chamam Use Cases
   - Celery como detalhe de infraestrutura

4. **Adicionar Testes**
   - Testes unitários de Domain
   - Testes de Use Cases com mocks
   - Testes de integração de Infrastructure

---

## 📚 Referências

- [Clean Architecture (Robert C. Martin)](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Hexagonal Architecture (Alistair Cockburn)](https://alistair.cockburn.us/hexagonal-architecture/)
- [Domain-Driven Design (Eric Evans)](https://www.domainlanguage.com/ddd/)
