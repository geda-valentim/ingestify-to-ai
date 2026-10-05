# 00NN — Título da spec

| | |
|---|---|
| **Status** | Rascunho \| Em revisão \| Aprovada \| Implementada \| Rejeitada \| Substituída |
| **Autor** | Nome |
| **Criada em** | AAAA-MM-DD |
| **Atualizada em** | AAAA-MM-DD |
| **Relacionadas** | 00NN, 00NN (ou —) |
| **Substituída por** | — |

---

## 1. Problema

Qual dor concreta motiva isso? Quem sente, com que frequência, e o que acontece hoje quando
sente. Seja específico — "melhorar a experiência" não é um problema, "o usuário não consegue
reprocessar uma página que falhou sem reenviar o PDF de 200 MB" é.

Se houver dados (logs, tempo de conversão, tickets), coloque aqui.

## 2. Objetivo

Uma frase. O estado do mundo depois que isso existir.

### Fora de escopo

Liste explicitamente o que **não** será feito. Esta seção evita mais retrabalho que qualquer
outra — é ela que impede o escopo de crescer durante a implementação.

- …
- …

## 3. Critérios de aceitação

Condições verificáveis. Se não dá para escrever um teste a partir do item, ele está vago demais.

- [ ] Dado …, quando …, então …
- [ ] Dado …, quando …, então …

## 4. Solução proposta

Como funciona. Prefira o fluxo concreto ao vocabulário abstrato.

### Fluxo

```
Descreva o caminho feliz, passo a passo, com os componentes reais do sistema
(API → Redis → Celery → Worker → MinIO/ES → …).
```

### Mudanças por camada

Preencha só as que se aplicam; apague as demais.

**API** (`backend/api/`)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| POST | `/exemplo` | JWT ou API key | … |

Request / Response:

```jsonc
// POST /exemplo
{ "campo": "valor" }

// 202 Accepted
{ "job_id": "uuid", "status": "queued" }
```

Erros: `400` …, `403` …, `404` …

**Domínio / Workers** (`backend/workers/`)
- Nova task? Idempotente? Quantos retries? Timeout?

**Dados** (`backend/shared/models.py` + Alembic)
- Tabelas/colunas novas, índices, nullability. A migration é reversível?

**Chaves Redis**
- `job:{id}:...` — formato, TTL, quem escreve, quem lê.

**Frontend** (`frontend/`)
- Telas/componentes afetados, novos estados de carregamento e de erro.

## 5. Alternativas consideradas

Pelo menos uma. Se não houver alternativa, o problema provavelmente não foi entendido.

| Alternativa | Por que foi descartada |
|---|---|
| … | … |

## 6. Impactos

- **Compatibilidade:** quebra algum contrato existente? Como migrar clientes atuais?
- **Performance:** custo esperado por requisição/job. Muda o tempo de conversão?
- **Segurança:** quem pode chamar isso? Como a propriedade do recurso é verificada?
  (ver `docs/CODE_REVIEW.md` § 5.1 — autorização deve vir do MySQL, não do cache Redis)
- **Operação:** nova variável de ambiente, novo serviço, nova métrica ou alerta?
- **Custo:** chamadas a API paga (OpenAI, etc.), armazenamento, CPU de worker.

## 7. Plano de testes

Como isso será verificado automaticamente — não manualmente.

- **Unitários:** …
- **Integração:** …
- **Manual/exploratório:** só o que genuinamente não dá para automatizar.

## 8. Plano de implementação

Fatias entregáveis, na ordem. Cada item deve caber num PR.

- [ ] …
- [ ] …

## 9. Questões em aberto

Marque como resolvida com a decisão em vez de apagar a linha — o registro é útil.

- [ ] Pergunta? → **Decisão (AAAA-MM-DD):** …
