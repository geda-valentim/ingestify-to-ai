# Validação de perfis de execução e RBAC/ABAC

Data: **2026-10-06**. Escopo: implementação da [spec 0009](../specs/0009-perfis-de-execucao-e-controle-de-acesso.md)
na branch `feat/runtime-profiles-access`, baseada em `main` `68f8350`.
Uso: [guia funcional](../features/execution-profiles.md). Implantação:
[runbook](../runbooks/execution-profiles-access.md).

## Revisão de código

Os agentes de revisão examinaram biblioteca, grants, delegação, leituras,
vinculação, runner, agente de host, caminhos legados, CLI e migração. Correções
incorporadas incluem filtragem antes da paginação, identidades físicas do
desejado/aplicado, permissões de credenciais separadas, isolamento de cache entre
logins e liberação de transações antes do build/RPC.

Na revisão final, foram encontrados e corrigidos três problemas:

- O deploy Modal de uma operação admitia o subprocesso, mas não revalidava cada
  RPC posterior. Agora `deploy:meta` e `deploy:record` passam por admissões próprias,
  com ator atual, geração, lease/fence e commit antes da rede.
- A descoberta de capabilities sem feature podia consultar o último perfil de
  outra feature. Agora escolhe uma feature autorizada antes de calcular estado,
  filtra os modelos do descriptor e oculta runtime não legível.

- O teste de conexão Modal podia criar seu Dict e gravar identidade após
  revogação. Agora admite conexão e identidade separadamente; a gravação verifica
  autoridade, geração/lease, cancelamento e deadline na mesma transação.

O agente `final_review_profiles` conferiu as correções e não encontrou
bloqueadores restantes na revisão dirigida. Isso é evidência de revisão do código,
não certificação de um provider real.

## Backend

A rodada inicial passou **214 casos**: 60 da nova funcionalidade e 154 de
regressão. Usou SQLite e MariaDB/InnoDB descartável com prefixo
`engine_control_test_`, removido ao final. Não escreveu na base da instalação.

A rodada final dirigida passou **153 casos** em 205,63 s: biblioteca/API (58),
CLI Modal (12), migração 0009 (12), engine control (22), concorrência InnoDB (3),
migração 0007 (6), accounts (15) e remote engine (25). Depois passaram **12 casos
adicionais** em 9,45 s: dez de identidade Modal e dois de metadados/confirmação das
admissões. As rodadas se sobrepõem à inicial; não somar os números como casos distintos.

O SDK fake comprovou epoch/principal livres durante build, meta e record,
revogação bloqueando a próxima RPC, fences/admissões incertas preservados e replay
recusado. No teste de identidade, foram simuladas revogação antes/durante hydrate,
perda de geração, cancelamento e deadline: nenhuma gravação indevida de identidade
ou versão aconteceu. Admissão só foi marcada confirmada após conclusão segura;
`needs_attention` preservou incerteza. Catálogo divergente ou não aprovado foi
recusado nas fronteiras de plano, enqueue e novo efeito. Os testes de capabilities
verificaram descoberta de vision sem estado/modelos de outra feature.

Os contratos verificados incluem:

- Publicação por ID explícito, revisões imutáveis, origem/hash atômicos, import
  legado por whitelist, prazo de warmup resolvido uma vez e conflitos sem retry.
- Escopos de engine/provider/feature/ambiente/modelo/host/GPU e tetos numéricos;
  uma decisão exige um grant completo, sem somar permissões parciais.
- Envelope de delegação, revisões de política fixadas, revogação/expiração
  parental, ausência de autoridade por autoria e sujeitos inativos.
- Leitura filtrada, cursores/IDs fora de escopo, SSE revalidado, API keys recusadas
  para controle humano e identidades de máquina separadas.
- Recursos canônicos e todos os consumidores do desejado/aplicado; epoch de
  autorização, efeitos incertos, cancelamento/recovery por ator próprio.
- Migração aditiva/idempotente, preservação de perfis/operações/gates/auditoria,
  bloqueio de schema incompleto e recusa de downgrade destrutivo.

Os fakes de provider e host não iniciam GPU, containers ou infraestrutura paga.
O adapter sintético usado na suíte verifica que os contratos não dependem de
condicionais específicas de AWS/GCP/Vast na biblioteca.

## Frontend

O agente de teste executou Chromium com API simulada nos tamanhos desktop e
mobile. Os fluxos iniciais cobrem criação, publicação explícita, nova revisão,
clone, vínculo somente ao desejado, conflito sem retry, navegação por papel,
políticas/grants, validade UTC, revogação e qualificação de consumidores.
A regressão da tela de controle de engines também passou.

Após as últimas correções, **seis testes dirigidos adicionais passaram**:

1. Logout e login de outro usuário na mesma aba, sem recarregar: cache, bootstrap
   e botões de escrita do primeiro usuário não reaparecem; consultas são refeitas.
2. Editor com apenas Modal: o formulário normaliza provider e salva payload válido.
3. Troca Local vision para Modal: feature e modelo são redefinidos.
4. `connection_manager`: altera credenciais com senha, sem acesso a orçamento,
   vínculo ou JSON bruto de runtime.
5. Engine vazia com apenas vision: descobre features primeiro e consulta o runtime
   de vision, sem emitir requisição de transcription.

6. Duas renovações JWT do mesmo usuário: formulário, identidade DOM e cache
   preservados, mantendo a árvore montada. Logout/login A→B foi repetido e
   continuou isolado. A captura live depende dessa continuidade; não foi usado
   microfone real nesse teste.

Houve um timeout inicial de hidratação sob carga do host; a repetição serial
completa passou. Os testes verificam contratos e interação, com interceptação de
rede; não representam autenticação ou execução de infraestrutura real.

Arquivos reproduzíveis:

- `backend/tests/test_execution_profiles*.py`
- `frontend/tests/execution-profiles-browser.py`
- `frontend/tests/engine-control-browser.py`

Para reproduzir a seleção sem provider real:

```bash
PYTHONPATH=backend pytest backend/tests/test_execution_profiles.py \
  backend/tests/test_execution_profiles_cli.py \
  backend/tests/test_execution_profiles_migration.py -q

python frontend/tests/execution-profiles-browser.py \
  --url http://127.0.0.1:3119 --api-url http://localhost:8080
```

O browser exige Playwright/Chromium e um frontend iniciado; a suíte intercepta as
chamadas da API. Casos InnoDB exigem `ENGINE_CONTROL_TEST_DATABASE_URL` apontando
**somente** para um banco descartável com o prefixo obrigatório; sem isso são
skipados. Não use a URL da base da instalação.

## Verificações de entrega

`tsc --noEmit` e o build de produção Next.js passaram, incluindo as páginas
`/admin/access`, `/admin/execution-profiles` e a documentação em português/inglês.
AST dos arquivos Python alterados, `git diff --check` e links locais dos novos
documentos também passaram.

## Ativação no dev

Após backup consistente do SQL, a migração 0009 foi aplicada e validada.
API e executores foram recriados com controle/acesso habilitados. O registro
do host foi atualizado com hashes atuais dos manifests e imagens, preservando
a identidade de máquina. As cinco engines da instalação foram classificadas
como desenvolvimento pela API auditada. Biblioteca, IAM e capabilities responderam
com sessão de bootstrap, incluindo a biblioteca pelo tunnel público.
A API ficou saudável; nenhum perfil, grant delegado ou deploy pago foi criado.
A documentação da funcionalidade é publicada em `/docs/compute` e `/pt/docs/compute`.

## Limites e rollout

`ENGINE_ACCESS_ENABLED` continua falso por padrão. O PR #45 foi mergeado e a feature foi ativada no dev em 2026-10-06.
A rodada automatizada acima ocorreu antes da ativação. Não foram testados efeitos reais no host
ou uma conta Modal; AWS, GCP e Vast ainda não ganham adapters por esta entrega.
O canário físico, consumidores completos, atualização do manifest do agente e
primeiros grants limitados precisam seguir o runbook antes do rollout.

Revogar impede novas admissões; um RPC já admitido pode terminar depois da
revogação. Resultado desconhecido conserva exposição e exige observação ou
cleanup autorizado. O código não promete desfazer comandos aceitos pelo provider.
