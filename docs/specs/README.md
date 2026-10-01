# Specs — convenção do Ingestify

Uma **spec** é o registro curto e versionado de *uma* decisão de funcionalidade: o que vai ser
construído, por quê, e o que fica de fora. Vive ao lado do código, num arquivo por spec.

Isso substitui dois padrões que não funcionaram no projeto:

- **PRDs monolíticos** (ex.: `docs/WEBSCRAPPING_PRD.md`, 80 KB) — grandes demais para revisar,
  sem status, impossíveis de fechar.
- **Docs de estado** (`STATUS.md`, `TASKS.md`, `TEST_RESULTS.md`) — nascem desatualizados porque
  descrevem um instante, não uma decisão. Esses devem virar issues, não arquivos.

O código já conta *o que* o sistema faz. A spec existe para contar **por que** ele faz assim e
**o que foi descartado** — a única parte que se perde.

---

## Quando escrever uma spec

**Escreva** quando a mudança:
- adiciona ou altera um endpoint público da API;
- muda o modelo de dados (nova tabela, coluna, migration Alembic);
- introduz um novo tipo de job, source handler ou dependência de infraestrutura;
- altera o contrato entre frontend e backend;
- envolve um trade-off que alguém vai questionar em 3 meses.

**Não escreva** para: correção de bug, refatoração sem mudança de comportamento, ajuste de
copy/UI, bump de dependência. Um bom commit resolve.

> Regra prática: se você precisaria explicar a decisão numa reunião, escreva a spec.
> Se explicaria num comentário de PR, não escreva.

---

## Como criar

```bash
cp docs/specs/_TEMPLATE.md docs/specs/0007-nome-curto-em-kebab-case.md
```

- **Numeração** sequencial de 4 dígitos, nunca reutilizada. O próximo número é o maior existente + 1.
- **Nome** curto e descritivo do *resultado*, não da tarefa (`0007-retry-por-pagina`,
  não `0007-arrumar-retry`).
- Nasce com `Status: Rascunho`. Vira `Aprovada` quando o PR da spec é mergeado, `Implementada`
  quando o código está em `main`.
- **Uma spec nunca é editada depois de `Implementada`.** Se a decisão mudar, escreva uma nova
  spec que a substitui e marque a antiga como `Substituída por: 00NN`. O histórico das decisões
  é o que dá valor ao conjunto.

---

## Ciclo de vida

```
Rascunho ──▶ Em revisão ──▶ Aprovada ──▶ Implementada
                 │                            │
                 └──▶ Rejeitada               └──▶ Substituída por 00NN
```

| Status | Significa |
|---|---|
| `Rascunho` | Sendo escrita. Ninguém deve implementar ainda. |
| `Em revisão` | PR aberto. Comentários bem-vindos. |
| `Aprovada` | Decidida. Pode implementar. |
| `Implementada` | Está em `main`. Congelada. |
| `Rejeitada` | Decidiu-se não fazer. **Mantenha o arquivo** — evita rediscutir o mesmo tema. |
| `Substituída` | Uma spec mais nova a substitui. |

---

## Índice

| # | Spec | Status | Data |
|---|---|---|---|
| 0001 | [Remover as camadas de Clean Architecture não utilizadas](0001-remover-clean-architecture-morta.md) | Implementada | 2026-08-26 |
| 0002 | [Dispositivo único (`DEVICE`) e a migração do Whisper para CPU→CUDA](0002-dispositivo-unico-e-migracao-do-whisper.md) | Implementada | 2026-08-26 |
| 0003 | [Projetos e pastas: o Ingestify como portal de ingestão](0003-projects-and-folders.md) | Rascunho | 2026-10-01 |

<!-- Adicione uma linha aqui ao criar cada spec. -->
