# 0019 — Usuário root na primeira inicialização

| | |
|---|---|
| **Status** | Em implementação |
| **Autor** | Geda Valentim / Claude |
| **Criada em** | 2026-10-07 |
| **Atualizada em** | 2026-10-07 |
| **Relacionadas** | [0013](0013-iam-da-plataforma.md), [0014](0014-iam-nucleo-de-decisao-e-papeis-de-plataforma.md), [0018](0018-iam-convergencia-do-rbac-abac-de-engines.md) |
| **Substituída por** | — |

---

## 1. Problema

Uma instalação nova não tem administrador. O primeiro admin só nasce rodando
`scripts/make_admin.py` no shell do servidor depois de alguém se cadastrar como usuário
comum (`backend/api/auth_routes.py` `register` cria todo usuário com `is_admin=False`).
Até isso acontecer, ninguém consegue conceder papéis do IAM (0014/0018), configurar
engines ou ver `/admin`. Além disso, "admin" é só uma coluna: qualquer admin pode,
por SQL ou script, deixar a plataforma sem nenhum, e não há uma identidade que o IAM
reconheça como dona da instalação.

## 2. Objetivo

O primeiro usuário cadastrado em uma instalação sem root nasce **root**: a identidade
única, irrevogável pela aplicação, que é o acesso de emergência (bootstrap) do IAM. Em
produção, criar o root exige um token de instalação.

### Fora de escopo

- Transferir ou trocar o root pela API (fica por script de operação, §4.6).
- Convites, SSO, MFA.
- Mudanças em papéis/bindings do IAM: root continua sendo bootstrap, não um binding.

## 3. Critérios de aceitação

- [ ] CA1. Em uma instalação sem root, `POST /auth/register` cria o usuário com
  `is_root=true` e `is_admin=true`; os cadastros seguintes criam usuários comuns.
- [ ] CA2. Existe no máximo um root, garantido pelo banco: dois cadastros simultâneos
  na instalação vazia produzem exatamente um root; o outro vira usuário comum (ou falha
  por e-mail/username duplicado, se for o caso), nunca um segundo root nem um 500.
- [ ] CA3. Com `ENVIRONMENT=production` e `ROOT_SETUP_TOKEN` vazio, enquanto não houver
  root todo cadastro é recusado com `403 {"code": "ROOT_SETUP_TOKEN_REQUIRED"}` e o boot
  registra um aviso. Com o token configurado (qualquer ambiente), o cadastro que criaria
  o root exige `setup_token` igual (comparação em tempo constante); ausente ou diferente →
  `403 {"code": "ROOT_SETUP_TOKEN_INVALID"}`. Fora de produção sem token, o primeiro
  cadastro vira root sem token. Depois que o root existe, `setup_token` é ignorado.
- [ ] CA4. Root é bootstrap para o IAM em qualquer `IAM_MODE`: `is_effective_admin`
  retorna verdadeiro para o root mesmo que `is_admin` tenha sido zerado.
- [ ] CA5. Nenhum caminho da aplicação desativa o root, tira seu `is_admin` ou cria um
  segundo root: as escritas existentes recusam com `409 {"code": "ROOT_IMMUTABLE"}`
  (ou erro equivalente no script), e há teste para cada caminho encontrado.
- [ ] CA6. `GET /auth/setup` (público) devolve `{"root_exists": bool,
  "setup_token_required": bool}` sem revelar mais nada; está na allowlist pública do
  teste de cobertura da 0014.
- [ ] CA7. `/auth/me` e a resposta do cadastro incluem `is_root`.
- [ ] CA8. A criação do root grava `AdminAudit` (`platform.root.created`) na mesma
  transação, sem senha nem token.
- [ ] CA9. A tela de cadastro, quando `root_exists=false`, explica que a conta será o
  root da plataforma e mostra o campo de token se `setup_token_required=true`; depois
  do cadastro o usuário entra com acesso ao `/admin`.
- [ ] CA10. `scripts/make_admin.py --root` designa root um usuário existente somente
  quando ainda não há root (instalações antigas); nunca sobrescreve um root existente.
- [ ] CA11. Suíte completa e `tsc` verdes (exceto falhas de ambiente conhecidas);
  documentação de API regenerada; `.env.example`, docs de auth e `CHANGELOG` atualizados.

## 4. Solução proposta

### 4.1 Dados

`users.root_slot` — `SmallInteger NULL`, **UNIQUE**. O root tem `root_slot=1`; todos os
outros, `NULL` (MySQL e SQLite permitem vários NULL num índice único). Uma coluna só
expressa "é root" e garante unicidade sem tabela extra nem lock global. Propriedade
`User.is_root` = `root_slot == 1`. Migration Alembic aditiva (`down_revision` = head
atual) e o mesmo padrão de coluna-se-ausente usado pelas migrations de app.

### 4.2 Cadastro

```
register(body):
  rate limit (inalterado); e-mail/username duplicados (inalterado)
  if not exists(User.root_slot == 1):
      exigir token conforme CA3
      criar User(is_admin=True, root_slot=1) + AdminAudit na mesma transação
      IntegrityError em root_slot (corrida) → rollback e seguir como usuário comum
  else:
      criar usuário comum (inalterado)
```

### 4.3 Regra de admin

`shared/admin.is_effective_admin`: `is_admin` **ou** `root_slot == 1` **ou**
`ADMIN_USER_IDS`. Continua sendo a única regra (a 0014 já a usa como bootstrap).

### 4.4 Imutabilidade

Inventariar toda escrita em `users.is_active`, `users.is_admin` e `users.root_slot`
(rotas, scripts, serviços) e recusar as que atingiriam o root. Escrita direta em SQL
fica fora do alcance da aplicação e é coberta pelo §4.3 (root continua admin).

### 4.5 API e frontend

- `GET /auth/setup` público (CA6). `UserCreate.setup_token: Optional[str]` (máx. 256).
- `UserResponse.is_root`.
- `frontend/app/register`: consulta `/auth/setup`; título e texto de root; campo de
  token condicional; mensagens em inglês, como o resto das páginas públicas desde o #52.
  `formatApiError` passa a exibir `detail.message` de erros estruturados.

### 4.6 Operação

- `ROOT_SETUP_TOKEN` (env, segredo): gere com `openssl rand -hex 32`, use uma vez,
  remova depois. Boot avisa quando produção não tem root nem token.
- `make_admin.py --root`: instalações que já tinham usuários antes desta spec.

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Primeiro usuário vira admin, sem token (Grafana, Gitea) | Instalação exposta pode ser tomada por quem se cadastrar primeiro; aceito só fora de produção |
| Só token/senha impressos no log (Jenkins) | Exige acesso aos logs para o primeiro uso no dev; aqui o token é opcional fora de produção |
| Root como binding `platform_admin` | Binding pode ser revogado/expira (≤ 365 dias); root precisa ser irrevogável pela aplicação |
| Tabela `platform_root` singleton | Duas fontes ("é admin" e "é root"); a coluna única resolve com uma escrita |
| Manter só `make_admin.py` | É o problema descrito em §1 |

## 6. Impactos

- **Compatibilidade:** cadastros após o primeiro não mudam. Instalações com usuários e
  sem root seguem como hoje até alguém rodar `make_admin.py --root`.
- **Segurança:** em produção, sem token não há como reivindicar a instalação pela web;
  token comparado em tempo constante e sob o rate limit de cadastro existente. Risco
  residual: um deploy exposto só com o `docker-compose.yml` base roda com
  `ENVIRONMENT=development`, onde o token é opcional — a doc de auth manda configurá-lo.
- **Operação:** nova env `ROOT_SETUP_TOKEN`; aviso de boot.

## 7. Plano de testes

Unitários/API: CA1–CA8 e CA10, incluindo corrida simulada (IntegrityError no
`root_slot`), produção sem token, token errado/ausente/certo, root com `is_admin=False`
ainda admin, cada caminho de escrita do §4.4. Frontend: `tsc` e contrato da API.

## 8. Plano de implementação

- [ ] 1. Coluna + migration, regra de admin, cadastro com token, `/auth/setup`, `is_root`,
  auditoria, imutabilidade, script, testes.
- [ ] 2. Tela de cadastro, docs, `.env.example`, `CHANGELOG`, docs de API.
