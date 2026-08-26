# 0001 — Remover as camadas de Clean Architecture não utilizadas

| | |
|---|---|
| **Status** | Implementada |
| **Autor** | Geda Valentim |
| **Criada em** | 2026-08-26 |
| **Atualizada em** | 2026-08-26 |
| **Relacionadas** | — |
| **Substituída por** | — |

---

## 1. Problema

O `CLAUDE.md` e quatro documentos em `backend/docs/` afirmavam que o backend seguia
Clean Architecture, com `domain/ → application/ → infrastructure/ → presentation/`.

Não seguia. `backend/api/main.py` montava quatro routers, todos de `backend/api/`.
As quatro camadas — **47 arquivos, 3.998 LOC** — não eram importadas por nenhum módulo
vivo, e **nem eram copiadas para as imagens Docker**: `Dockerfile.api` copia apenas
`api/`, `shared/`, `workers/`, `tests/`; `Dockerfile.worker` apenas `workers/` e
`shared/`. Nenhum volume mount do compose as reintroduzia.

Não era uma arquitetura meio-ligada. Era um rascunho congelado desde **2025-11-01**,
enquanto o caminho vivo recebeu 9 commits e ganhou MinIO, transcrição de áudio,
deduplicação por checksum, presets do Docling, API keys, rotas de admin, monitoring,
retry por página e um modelo de autorização novo.

O custo era duplo. Concreto: quem lia a documentação procurava a lógica em `use_cases/`
e a encontrava em `api/routes.py`. E enganoso: as camadas *pareciam* quase prontas, o
que fazia "ligar o fio" soar barato.

Não era. Se alguém as ligasse naquele dia, o primeiro job lido do banco estouraria —
`MySQLJobRepository._model_to_entity` faz `JobType(db_job.job_type)` com o `"MAIN"`
que `api/routes.py` grava, enquanto o enum do domínio é `"main"` minúsculo. Havia
ainda um `_mock_conversion()` no adapter do Docling devolvendo *"Lorem ipsum… MOCK
conversion"* como markdown do usuário.

Delta funcional, medido por arquivos que mencionam cada recurso:

| Recurso | Nas 4 camadas | Em `api/` + `workers/` + `shared/` |
|---|---:|---:|
| Transcrição de áudio | 0 | 18 |
| MinIO | 0 | 25 |
| API keys | 0 | 20 |
| Admin / `is_admin` | 0 | 21 |
| Monitoring | 0 | 15 |
| Dedup por checksum | 0 | 8 |
| `retry_count` | 0 | 21 |

## 2. Objetivo

A estrutura do backend no disco passa a corresponder ao que o sistema realmente é,
e a documentação para de descrever uma arquitetura que nunca executou.

### Fora de escopo

- Migrar os endpoints vivos para use cases (a Opção B abaixo).
- Quebrar `api/routes.py` em módulos por recurso — vale a pena, mas é independente
  desta decisão e agora está desbloqueado.
- Extrair a fórmula de progresso duplicada em `tasks.py:693` e `:959`.

## 3. Critérios de aceitação

- [x] `grep -rE "^\s*(from|import)\s+(domain|application|infrastructure|presentation)"` em `backend/` não retorna nada
- [x] A suíte continua passando sem alteração (103 testes)
- [x] `CLAUDE.md` descreve `api/` / `workers/` / `shared/` e não menciona Clean Architecture como vigente
- [x] Nenhum documento em `backend/docs/` descreve a arquitetura removida
- [x] O commit de restauração está registrado para quem precisar consultar o design

## 4. Solução adotada

`git rm -r` de `backend/domain/`, `backend/application/`, `backend/infrastructure/`,
`backend/presentation/` e `backend/test_clean_arch.py` — **48 arquivos, 4.235 LOC**.

`CLAUDE.md` passou a documentar a estrutura real, com uma nota histórica apontando
para esta spec e para o commit de restauração. Removidos `CLEAN_ARCHITECTURE.md`,
`README_CLEAN_ARCH.md`, `MIGRATION_GUIDE.md` e `IMPLEMENTATION_SUMMARY.md`.

**Recuperação:** nada foi destruído. O design continua legível em

```bash
git show 9b6b876:backend/domain/entities/job.py
git show 9b6b876 --stat
```

## 5. Alternativas consideradas

| Alternativa | Custo | Por que foi descartada |
|---|---:|---|
| **B — migrar os endpoints para os use cases** | 180–320 h | As camadas cobrem ~25% do produto atual. Não é migrar 14 endpoints para código pronto: é reescrever o produto dentro de um esqueleto que não conhece áudio, MinIO, API keys, admin nem dedup. Antes disso, 15–25 h só para as camadas *executarem*. |
| **D — manter só `domain/` e ligá-lo de fato** | 9–12 h | Defensável. Mas o único ganho concreto — deduplicar a fórmula de progresso, hoje copiada verbatim em `tasks.py:693` e `:959` — sai de um helper de 10 linhas em `shared/`. E `domain/` passaria a rodar, exigindo entrada nos dois Dockerfiles **e** nos volume mounts do compose; esquecer isso é `ImportError` em deploy, não em dev. |
| **C — manter as duas** | 0 h | É o estado que originou o problema. |

### Sobre o argumento de testabilidade

Foi o melhor caso a favor de manter as camadas, e este repositório o refuta sozinho:
os 103 testes atuais foram construídos **contra a arquitetura viva**, com fakes e
mocks, e funcionam. Enquanto isso `backend/test_clean_arch.py` — os 237 LOC que
existiam exatamente para colher o benefício da pureza hexagonal — **nunca foi
coletado pelo pytest uma única vez**, porque `pytest.ini` define `testpaths = tests`
e o arquivo morava em `backend/`.

O time já provou que consegue testar sem a pureza, e nunca rodou o teste que a
pureza lhe daria.

### Sobre portabilidade de infraestrutura

`StoragePort`, `QueuePort` e `ConverterPort` existiam. Mas 25 arquivos vivos falam
com MinIO diretamente e 19 com Elasticsearch, e nenhuma porta cobria isso. A churn
de infra dos últimos 10 meses foi de **adição** (MinIO, ES, áudio), não de troca —
hedge contra um risco sem evidência de materialização.

## 6. Impactos

- **Compatibilidade:** nenhuma. Zero importadores vivos, ausência nas imagens Docker,
  ausência no `Makefile` e no `pytest.ini`. Nenhum endpoint muda.
- **Performance:** nenhuma.
- **Segurança:** positiva por remoção. `GetJobStatusUseCase` devolvia **403** ao negar
  acesso, vazando a existência do recurso — exatamente o que a correção de IDOR em
  `api/deps.py` eliminou. Some um caminho que poderia reintroduzir o problema.
- **Operação:** nenhuma. Nada a implantar além do código.
- **Custo:** −4.235 LOC para manter.

## 7. Verificação

- `grep` de importadores: vazio
- `pytest backend/tests/ -q`: 103 passando, idêntico a antes da remoção
- `./validate-frontend.sh`: passa
- Build das imagens `api` e `worker`: passa
- `docker compose config -q` para base, infra e prod: passa

## 8. Questões em aberto

- [ ] A fórmula de progresso segue duplicada verbatim em `tasks.py:693` e `:959`.
      `ProgressCalculatorService` (removido) era o único lugar onde estava nomeada.
      → Extrair para um helper puro em `shared/`, com teste. Não feito aqui.
- [ ] `docs/ARCHITECTURE_JOBS.md` ainda documenta uma ponderação 10/80/10 que nunca
      foi implementada em lugar nenhum. A fórmula viva é `20 + int(completed/total*70)`.
