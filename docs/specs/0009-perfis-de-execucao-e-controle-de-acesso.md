# 0009 — Perfis de execução com RBAC e ABAC

| | |
|---|---|
| **Status** | Aprovada; implementação validada na branch, merge e rollout pendentes |
| **Autor** | Geda Valentim / Codex |
| **Criada em** | 2026-10-06 |
| **Atualizada em** | 2026-10-06 |
| **Relacionadas** | [0003](0003-motores-de-execucao-roteamento-e-orcamento.md), [0004](0004-projects-and-folders.md), [0007](0007-operacao-de-engines-pelo-admin.md) |
| **Substituída por** | — |

## 1. Problema

Ao tentar operar uma engine, o usuário encontra `RUNTIME_PROFILE_REQUIRED`,
mas não sabe onde configurar modelo, host, réplicas, concorrência e warmup.
Hoje o formulário fica dentro de `/admin/engines/{id}`, na aba Configuração.
O mesmo painel mistura conexão com o provedor, configuração de execução e
operação física. Cada configuração desejada pertence a uma engine/feature;
não há biblioteca nomeada de perfis que o usuário possa escolher e reutilizar.

O acesso também é amplo: `User.is_admin` ou `ADMIN_USER_IDS` libera as rotas
admin. Não é possível permitir leitura, edição de perfil ou operação de uma
engine específica sem conceder poderes administrativos mais abrangentes.

Esta spec propõe **perfis de execução** reutilizáveis e **papéis de acesso**
separados. Um perfil de execução define como executar. Um papel define o que
uma pessoa pode fazer; uma política ABAC restringe sobre quais recursos e
sob quais limites ela pode exercer essa permissão. O catálogo de modelos
aprovados existente continua sendo uma terceira entidade, distinta das duas.

### Código existente que será reutilizado

| Área | Código em `main` | Decisão |
|---|---|---|
| Configuração de execução | `RuntimeSettings` em `backend/shared/engine_control/contracts.py` | Manter schema fechado e regras de capacidade; não criar outro payload de runtime |
| Revisões desejadas e aplicadas | `RuntimeProfile`, `latest_profile`, `save_profile`, `runtime_status` | Continuar sendo o estado de uma engine/feature; biblioteca cria uma origem para essas revisões |
| Modelos e providers | `catalog.py`, `registry.py`, `capacity.py`, validadores local/Modal | Manter perfis aprovados, schemas declarativos, UUIDs e validação por adapter |
| Operações | `OperationPlan`, `EngineOperation`, outbox, leases, `runner.Context` | Preservar plano congelado, idempotência, execução assíncrona e recovery |
| Recursos compartilhados | `ControlResource`, admission e guards | Preservar propriedade canônica e drenagem; ACL não substitui locks |
| Autenticação | `shared/auth.py`, `shared/admin.py`, `require_admin_session` | Reusar sessão e bootstrap admin; acrescentar autorização granular |
| Segredos e auditoria | sealing/redaction, `AdminAudit`, eventos de operação | Perfis não guardam credenciais; registrar decisões sem tokens |
| UI | `EngineControl`, `engine-control-api.ts`, formulários por descriptor | Extrair e reusar formulários; manter console e comandos Docker existentes |
| Projetos | `Project.user_id`, ownership de jobs | Não presumir tenancy ou memberships que ainda não existem |

## 2. Objetivo

Permitir criar, escolher e vincular perfis de execução pelo painel, com
permissões por papel e limites por recurso aplicados na API e nos executores.

### Fora de escopo

- Implementar AWS, GCP ou Vast AI; o contrato continua extensível por adapters.
- Trocar scheduler, ledger, fila, console ou agente local da spec 0007.
- Editor livre de código, expressões Python/JavaScript, shell ou políticas DSL.
- Implantar organizações, SSO ou compartilhamento de projetos nesta entrega.
- Transformar acesso a um projeto em permissão para parar um worker global.
- Habilitar capacidades físicas/modelos ainda não qualificados, como perfis
  WhisperX de controle; RBAC não remove gates de adapter, orçamento ou GPU.
- Executar uma operação como consequência de criar, publicar ou vincular perfil.

## 3. Critérios de aceitação

- [x] CA1. Sem perfil desejado, a tela explica a configuração necessária e oferece
  “Escolher perfil” e, para quem tem permissão, “Criar perfil”. Não mostra apenas
  `RUNTIME_PROFILE_REQUIRED` nem indica que um agente saudável está indisponível.
- [x] CA2. Um perfil nomeado concentra modelo, host/provider, GPU, réplicas,
  concorrência, CPU/memória e política de warmup/cooldown já suportados pelo adapter.
- [x] CA3. Vincular uma revisão publicada cria uma revisão desejada por
  engine/feature usando `save_profile`. Aplicado/observado continuam separados;
  nenhum container, deploy ou reserva paga é criado nessa ação.
- [x] CA4. Nova revisão da biblioteca não atualiza engines já vinculadas. Cada
  uma mantém a revisão escolhida até nova vinculação explícita e autorizada.
- [x] CA5. Observador lê apenas seus recursos; editor edita apenas os perfis
  permitidos; configurador vincula perfis; operador executa apenas ações concedidas.
  Esconder um botão sem proteger a rota correspondente não atende este critério.
- [x] CA6. Papel de operador limitado a uma engine de desenvolvimento não
  opera outra engine, produção ou recurso canônico compartilhado fora do escopo.
- [x] CA7. Limites ABAC de modelo, host/GPU, feature, réplicas, concorrência,
  memória, prazo aquecido e custo máximo são verificados no servidor; alterar
  JSON, IDs ou chamadas diretas aos endpoints legados não contorna esses limites.
- [x] CA8. Revogar um grant impede novas admissões de efeito. Um efeito admitido
  antes da revogação pode já estar em voo: cancelar quando possível e tratar
  resultado desconhecido como incerto, mantendo gates/reservas até observação
  ou limpeza autorizada. Não prometer desfazer um RPC já aceito pelo provedor.
- [x] CA9. Listagens, histórico, logs e SSE respeitam o mesmo escopo; IDs adivinhados
  não revelam recurso, credencial, perfil, versão ou eventos de outro escopo.
- [x] CA10. Migração preserva perfis de runtime, revisões aplicadas, operações e
  auditoria. O admin atual continua com acesso de bootstrap e não há autoescalada.
- [x] CA11. Novo provider registrado reutiliza a biblioteca, autorização e UI;
  não exige condicionais AWS/GCP/Vast nos componentes de perfil.

## 4. Solução proposta

### 4.1 Fluxo de configuração e operação

1. Em **Admin → Perfis de execução** (`/admin/execution-profiles`), listar somente perfis acessíveis. Mostrar
   nome, provider, feature, modelo, revisão, status e engines vinculadas acessíveis.
2. Criar ou clonar um perfil usando os campos existentes de `RuntimeSettings` e
   o descriptor do adapter. Campos de credenciais ficam na conexão da engine.
3. Publicar uma revisão imutável. Validar schema/modelo aprovado na publicação;
   validar binding e dependências físicas novamente contra a engine ao vincular.
4. Em **Engine → Perfil de execução**, escolher perfil e revisão publicados.
   Mostrar parâmetros resolvidos, mudanças e incompatibilidades antes de vincular.
5. Vincular cria o desejado com optimistic locking da engine, sem aplicar o runtime.
6. Operar mantém o fluxo da 0007: prévia → confirmação → outbox → executor →
   observação. A prévia mostra qual perfil/revisão está sendo usado.

O atalho “Criar perfil” preserva engine e feature como contexto de retorno.
Quem pode operar, mas não configurar, vê a dependência e o papel necessário;
não recebe um formulário que falhará por autorização. As abas da engine ficam
focadas em visão geral, perfil vinculado, operações e conexão. Os comandos
Docker continuam disponíveis aos usuários autorizados a lê-los.

### 4.2 Biblioteca e revisões

Adicionar `ExecutionProfile` com UUID, nome, descrição, adapter, feature,
status (`draft`, `published`, `archived`), versão, autor, autoridade de origem e
`latest_published_revision_id`. `ExecutionProfileRevision` tem payload imutável,
`(profile_id, revision)` único, estado `draft/published`, `published_at`,
`RuntimeSettings`, hash canônico, autor e timestamps. Publicar exige ID de revisão
explícito e versão esperada do perfil. Criar revisão 2 não publica seu conteúdo
nem retira a publicação da revisão 1; vinculação nunca escolhe rascunho.

A revisão guarda parâmetros concretos, inclusive `host_id` local quando usado.
Clonar para outro host/GPU produz nova revisão; não há substituição arbitrária
ou interpolação enviada pelo browser. `gpu_ref` é validado no contexto da
engine, não tratado como identificador global. Credenciais e chave privada
nunca entram no perfil; o provedor continua usando a conexão da engine.

Fixar também o fingerprint dos metadados aprovados do modelo na publicação:
backend, modelo/repo, revisão e parâmetros de inferência. Aliases como
`whisper-local` dependem de settings mutáveis hoje; se o catálogo mudar, a
vinculação rejeita a divergência e exige revisão publicada com o novo fingerprint.
Não atualizar modelos de vínculos antigos implicitamente.

Para reutilizar uma política temporal, o envelope da biblioteca acrescenta
`warm_for_seconds` tipado e limitado pelo adapter (máximo inicial de 24 horas);
seu `RuntimeSettings.warm_until` permanece nulo. Na vinculação explícita, resolver
uma única vez `warm_until = agora UTC + duração` e congelar no runtime desejado.
Operar/retry não renova esse prazo. Um prazo vencido exige nova vinculação
explícita, podendo usar a mesma revisão publicada, e nova prévia. Assim não se
duplica o contrato de execução nem se publica um template com deadline absoluto.
Retry do PUT de vinculação preserva a versão esperada original: se o primeiro
commit ocorreu e a resposta se perdeu, retornar conflito de versão e consultar
o desejado atual, sem criar outra revisão ou renovar prazo. Não atualizar a
versão e repetir a escrita automaticamente após erro de rede.

Acrescentar a `RuntimeProfile` um `source_profile_revision_id` opcional e o hash
original. O payload resolvido continua imutável na tabela existente, de modo que
arquivar um perfil não apaga o estado aplicado nem quebra replay/auditoria.
Arquivamento impede novas vinculações, mas não altera runtime em execução.
Não há hard delete de revisões utilizadas por runtime, plano ou operação.

Estender a transação de `save_profile` para gravar origem, hash da revisão,
snapshot resolvido, ownership, incremento da versão da engine e auditoria juntos.
O método já faz commit interno; nunca preencher a origem numa segunda transação.

### 4.3 RBAC: papéis e permissões

Catálogo fechado de permissões; novos adapters declaram ações de domínio,
não criam permissões arbitrárias vindas do browser. Os papéis iniciais são:

| Papel | Permissões básicas |
|---|---|
| Administrador de plataforma | Bootstrap atual; administra papéis, políticas, perfis e engines |
| Administrador de acesso | Gerencia grants/políticas dentro da autoridade delegada; não recebe execução, segredos ou publicação por esse papel |
| Editor de perfis | Lê, cria, revisa, publica e arquiva perfis em seu escopo |
| Configurador de runtime | Lê perfis/engines e vincula uma revisão publicada ao desejado |
| Operador de engines | Lê perfis/engines e cria planos/executa as ações explicitamente concedidas; cancelamento/recovery têm permissões próprias |
| Gestor de conexão | Lê a engine e altera credenciais com senha atual e escopo; não recebe orçamento/configuração bruta |
| Observador | Lê perfis, engines e operações/logs autorizados; nenhuma mutação |

Permissões incluem `execution_profiles.read/create/update/publish/archive`,
`engine_runtime.bind`, `engines.read`, `engine_operations.plan`,
`engine_operations.execute.<action>`, `engine_operations.read/cancel/recover`,
`engine_connections.credentials.manage` e `access.grants.manage`.

Credenciais continuam exigindo reautenticação já existente, além da permissão.
O administrador de acesso recebe um **envelope de delegação** explícito com
permissões concedíveis, escopos, limites e duração máxima, separado de seus
direitos de execução. Não pode conceder além desse envelope, inclusive para si.
Sem envelope não concede nada. Grants derivados registram o pai; revogar ou
expirar a autoridade parental invalida os derivados. Mudanças têm versão e
auditoria; permissões visíveis no menu não constituem autoridade delegável.
Admin efetivo atual (`is_admin`/`ADMIN_USER_IDS`) é autoridade de bootstrap.
Perfis de acesso delegados não podem remover esse acesso de emergência.
Revogar bootstrap ocorre pelo mecanismo explícito existente da instalação,
não pelo editor de grants. UI explica essa distinção.

### 4.4 ABAC: escopo e limites tipados

Adicionar `AccessScopePolicy` com revisões imutáveis e `RoleGrant` ligando usuário,
papel, revisão explícita da política, validade UTC, concedente e autoridade
parental. Nova revisão de uma política não expande grants existentes; rebinding
de grant é alteração autorizada, com versão e auditoria. A política pode restringir:

- IDs de engines e perfis, features e tipos de adapter autorizados.
- Ambiente do recurso (`development`, `staging`, `production`), atributo
  persistido e gerido por administração da plataforma, nunca pelo solicitante.
- Hosts registrados, UUIDs de GPU e modelos aprovados.
- Limites de réplicas, concorrência, CPU/memória, prazo de warmup e `max_usd`.
- Tipos de operação permitidos e validade do grant.

Atributos vêm do SQL, perfil resolvido e inventário registrado, não de claims
editáveis do JWT, labels arbitrárias ou parâmetros de projeto da requisição.
`Project.user_id` não prova propriedade de uma engine global. Controle físico
restrito a um projeto exige recurso dedicado e associação confiável em uma
entrega posterior. Nesta entrega o escopo físico é de engine/recursos explícitos.

Decisão: usuário ativo + grant vigente + permissão RBAC + condições ABAC +
capacidade do adapter + gates operacionais. Falta de regra permite nada.
Múltiplos grants podem conceder permissões, mas uma configuração/operação deve satisfazer
**integralmente um grant**; não combinar host de um grant com teto de custo de
outro. Restrições obrigatórias de plataforma se aplicam a todos, inclusive admins.

Criação tem escopo por atributos permitidos de adapter, feature e ambiente,
pois o novo perfil ainda não possui ID. Registrar autoridade de origem e direitos
iniciais somente dentro desse envelope; autoria não concede poder irrestrito.
Leitura usa permissão e escopo do recurso, sem aplicar tetos de execução ao
conteúdo histórico: um observador autorizado pode ler operação de custo maior
que seu próprio limite de execução.

Autorizar a engine e todos os `resource_keys` afetados. Uma engine autorizada
não permite parar um serviço/GPU compartilhado com engine fora do escopo.
Registrar escopo canônico no plano, resolvido pelo adapter no servidor, e exigir
que todo o conjunto afetado pertença à autoridade do solicitante.

Adicionar associação confiável recurso → engines, features, ambiente e
consumidores, distinta de `ControlResource.owner_engine_id`. Resolver a união
dos recursos desejados e aplicados, incluindo o worker genérico e outras features
que compartilham GPU/serviço. Inventário/propriedade não provam exclusividade.
Consumidor desconhecido ou associação não qualificada bloqueia delegação;
esses recursos ficam restritos ao bootstrap até qualificar a associação.

### 4.5 Autorização durante operações duráveis

Introduzir um serviço de autorização de domínio reutilizável. Dependências de
API consultam esse serviço; o domínio também verifica, pois CLI/tasks e rotas
legadas são caminhos de escrita. `require_admin_session` evolui para sessão
JWT + permissões específicas nas rotas abrangidas. Bootstrap continua compatível.
O layout admin e `/auth/me` não podem continuar barrando todo usuário sem
`is_admin`: expor permissões de navegação e avaliar acesso no backend.

Aplicar checks em criação/publicação/vinculação de perfil, prévia, enqueue,
cancelamento e recovery. Reusar locks e versão da engine. O plano registra
ator, ação, recursos, revisão do perfil e versão/hash da política para auditoria;
essa fotografia não vira autorização permanente.

Antes de cada novo efeito, runner e agente verificam a autoridade atual do ator.
`Context.check` e `/internal/engine-hosts/.../check` são pontos de extensão;
identidade de máquina continua distinta do grant do humano. Acrescentar admissão
durável de efeito por `(operation_id, generation, step, authorization_epoch)`,
com executor, ação, alvo, validade e estado. Ordenar revogação e admissão pelo
mesmo lock/versionamento da autoridade SQL, antes de acessar locks de engine e
recursos; nunca manter a transação aberta durante RPC/build/warmup.
Usar inicialmente um epoch por instalação: grants, políticas, desativação de
usuário e alteração de atributos confiáveis atualizam essa autoridade pelo
mesmo serviço. Isso serializa somente os passos administrativos curtos, não jobs
ou inferência. Atualizar caminhos de promoção/demissão de admin e registrar
mudanças de bootstrap; configuração externa exige rollout coordenado.

Revogação impede novas admissões. Efeito admitido antes dela pode estar em voo;
rever antes do envio e cancelar quando possível, mas tratar a janela até a
confirmação como efeito incerto. Não redisparar uma admissão cujo envio é
desconhecido. Lease/generation existente continua sendo o fencing do executor.

Sem efeito: revogação encerra a operação sem aplicar. Depois de efeito:
interromper novos efeitos, manter estado incerto e realizar apenas observação/
limpeza segura. Watchdog e recovery de sistema conservam a autoridade mínima
para liberar exposição já criada e contabilizar custos; nunca iniciam/aquecem
recursos usando um grant revogado. Outro operador precisa de autorização atual
para recovery; não pode repetir um deploy como consequência de reconciliar.

Preservar o ator iniciador (`EngineOperation.actor_id`) imutável; registrar
`cancel_requested_by`, `recovery_requested_by` e autoridade vigente por geração.
Não reutilizar o ator revogado como autoridade do recovery nem substituí-lo
apagando autoria. Cleanup usa principal de serviço independente, limitado à
exposição já registrada; cancelar/recover devem receber o usuário no domínio.

Listagens filtram na consulta; detalhes fazem check antes de serializar. Filtrar
hosts, GPUs, modelos, aliases, vínculos e cursores pelo escopo antes de expô-los.
`can_cancel/can_recover` combinam estado e permissão atual. SSE verifica sessão,
grant e validade antes do primeiro lote e a cada lote, encerrando após revogação.
Não usar Redis como autoridade.
Auditar concessões, revogações, negativas relevantes e decisões de operação,
com IDs e versões, sem tokens, senhas ou material de credenciais.

Legados humanos `test/reconcile/test-all` enviam contexto durável contendo ator,
ação e IDs autorizados, revalidado no worker. `test-all` não expande “todos” após
a aceitação. Ator ausente nunca significa admin. CLI delegada usa sessão humana
e a API; CLI direta permanece bootstrap explícito, com principal de instalação
registrado, controles de SO e auditoria, inclusive deploy Modal direto.
Billing/sweeper/scheduler têm principais sistêmicos próprios e capacidades
limitadas; não herdam uma sessão humana ou permissão geral de operação.

### 4.6 API e dados

Contratos entregues, sob `/admin`, com autorização granular:

| Método | Rota | Permissão/efeito |
|---|---|---|
| GET / POST | `/execution-profiles` | Listar filtrado / criar perfil |
| GET / PUT | `/execution-profiles/{id}` | Ler / editar metadados com versão |
| POST | `/execution-profiles/{id}/revisions` | Criar revisão sem alterar vínculos |
| POST | `/execution-profiles/{id}/publish` | Publicar revisão explícita com versão |
| POST | `/execution-profiles/{id}/archive` | Impedir novas vinculações |
| POST | `/engines/{id}/runtime-profile/bind` | Vincular revisão + feature + versão da engine |
| GET | `/access/roles` | Papéis/permissões concedíveis pelo solicitante |
| GET / POST | `/access/policies` | Ler/criar política autorizada |
| POST | `/access/policies/{id}/revisions` | Revisar política com versão, sem migrar grants |
| GET / POST | `/access/grants` | Listar/conceder com revisão fixa |
| POST | `/access/grants/{id}/revoke` | Revogar com versão |

Erros: `401` sessão inválida; `403` ação não permitida no recurso conhecido;
`404` recurso fora de escopo, sem confirmar sua existência; `409` versão/plano
obsoleto ou conflito canônico; `422` perfil incompatível/limite excedido.
Capabilities distinguem autorização, perfil ausente, host indisponível e
capacidade não suportada. Retornam somente detalhes que o solicitante pode ler.

Inventariar e proteger também PUT legado de runtime/binding/GPUs, credenciais,
budget, activate/pause/test/reconcile/test-all, rotas, CLI, detalhes/histórico/logs
por ID e endpoints de cancelamento/recovery. O PUT legado de payload bruto fica
restrito ao bootstrap durante a transição; usuários delegados só vinculam revisão
publicada autorizada. `engine_runtime.bind` sozinho nunca permite criar um payload
que contorne a publicação do editor. Operações legadas recebem também permissão
da ação física equivalente e contexto de autoridade no domínio/executor.

Novas tabelas têm FKs para usuários/perfis, índices por escopo e timestamps;
revision/grant/policy usam optimistic locking. `RuntimeProfile` mantém suas
chaves/constraints atuais. Não criar fila ou serviço operacional adicional.
O schema inclui revisões de política, envelope/grant parental, epoch de
autorização, admissões de efeito e associações confiáveis de consumidores.

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Manter formulário somente dentro da engine | Não resolve descoberta nem reutilização; repete configuração |
| Perfil de execução e papel como uma entidade | Mistura parâmetros operacionais com autoridade; editar réplicas poderia mudar permissões |
| Continuar apenas com `is_admin` | Não delega leitura/operação com limites por recurso |
| RBAC sozinho | Papel operador não limita host, ambiente, modelo e gasto |
| Política DSL ou serviço IAM externo imediato | Introduz linguagem/infra e uma fonte adicional de autoridade antes de definir o domínio |
| Criar outro executor para perfis | Duplica operações, locks, billing e recovery já existentes |

## 6. Impactos e migração

- **Compatibilidade:** adicionar biblioteca sem reescrever o runtime da 0007.
  Perfis antigos ficam identificados como legados, com `source_profile_revision_id`
  nulo. Importá-los como drafts para revisão, sem inferir aplicado a partir do
  desejado nem ativar operações. Vínculos novos passam a apontar revisões publicadas.
  Extrair apenas os campos de `RuntimeSettings` por whitelist: o JSON persistido
  contém extras resolvidos `model/service/gpu_uuid/manifest_hash` que não são
  entrada do contrato. Preservar o snapshot antigo e origem do import; deadlines
  absolutos legados exigem revisão explícita da duração antes da publicação.
- **Rollout:** primeiro introduzir schema/políticas mantendo bootstrap admin;
  depois aplicar enforcement a todos os caminhos abrangidos antes de conceder
  os primeiros grants a não admins. Nunca liberar UI delegada com rotas sem check.
- **Segurança:** IAM gerido no SQL, menor privilégio e proteção contra autoescalada;
  APIs keys não ganham acesso a control/IAM por essa entrega. Agente mantém seu token.
- **Performance:** decisões por request/etapa, com consultas indexadas; não por
  chunk de áudio nem por token de transcrição. Sem cache de autorização positivo
  que adie revogações. Capabilities/console usam decisões em lote.
- **Operação/custo:** só acrescentar estado SQL; nenhuma GPU/deploy paga é criada
  por configuração. Gates físicos e limite financeiro existentes continuam válidos.
- **Rollback:** desabilitar grants delegados e preservar bootstrap/dados/auditoria;
  não remover tabelas/revisões referenciadas nem reinterpretar operações pendentes.

## 7. Plano de testes

- Unitários de matriz papel/ação e limites ABAC; múltiplos grants sem composição
  indevida; autoatribuição, validade UTC e atributos adulterados.
- Integração SQL: publicação/vinculação concorrente, referências imutáveis,
  revogação concorrente ao enqueue/check de efeito e leitura entre escopos.
  Nova revisão não publicada não vincula; falha no commit não deixa origem
  ausente. Modelo com fingerprint alterado e prazo vencido exigem nova decisão.
  Resposta de binding perdida após commit não cria nova revisão nem renova prazo.
  Revisão de política compartilhada não amplia grants; revogação parental corta
  os derivados. Criar perfil exige envelope de criação, não um ID antecipado.
- Contrato API: todos os endpoints legados e novos, IDs adivinhados, listagens,
  credenciais, cancelamento/recovery e revogação durante SSE.
- Runner/agente: revogar antes de aceitar, antes do efeito e após efeito incerto;
  mostrar que watchdog limpa exposição sem adquirir permissão de iniciar.
  Testar revogação entre admissão/envio/confirmação, recovery por segundo ator,
  principal sistêmico sem humano e consumidor compartilhado não registrado.
- Chromium desktop/mobile: criar/publicar/escolher perfil, retorno à engine,
  desired/applied separados, falta de permissão e tratamento de ausência de perfil.
  Preservar HTTP/LAN com `getRandomValues`, retry idempotente e cards Docker.
- Adapter de contrato de terceiro provider: schema/capacidade/recursos distintos
  passam pela mesma biblioteca e autorização, sem alteração do formulário genérico.
- Migração com perfis legados e operações em voo, preservando gates/auditoria e
  permitindo leitura e atuação administrativa de bootstrap.

## 8. Plano de implementação

- [x] 1. Fechar semântica de perfis, papéis, políticas e plano de migração com revisão.
- [x] 2. Schema da biblioteca, revisões e referência opcional no runtime; import legado.
- [x] 3. API/formulário de biblioteca reutilizando adapters e `RuntimeSettings`;
  escolha/vinculação na engine, sem aplicação automática.
- [x] 4. Schema RBAC/ABAC e serviço de decisão; testes de grants/escopos/revogação.
- [x] 5. Enforcement completo de rotas/domínio/CLI/runner/agente e exposição segura
  de capabilities/navegação; ainda sem grants delegados em produção.
- [x] 6. UI de administração de acesso e qualificação isolada de ações, logs,
  cancelamento e cleanup.
- [ ] 7. Rollout opt-in dos primeiros papéis limitados no ambiente e canário físico
  Local/Modal, após migração e qualificação de consumidores.

## 9. Questões em aberto

- [x] Intenção de “perfis”: biblioteca de execução com papéis/políticas separados.
  Implementação autorizada pelo autor em 2026-10-06, seguida de revisão e testes.
- [x] Criar um runtime paralelo? → **Decisão (2026-10-06):** não; a biblioteca
  origina revisões do runtime existente e usa o executor/ledger da 0007.
- [x] Grants de projeto controlam worker global? → **Decisão (2026-10-06):** não;
  engine/recursos físicos têm escopo explícito; isolamento por projeto fica posterior.
- [x] Revisão de arquitetura (2026-10-06): incorporados publicação por revisão,
  origem atômica, import por whitelist, pinning de modelo e duração de warmup.
- [x] Revisão de autorização (2026-10-06): incorporados admissão de efeito,
  ator próprio de recovery, consumidores canônicos, envelope de delegação,
  políticas imutáveis, contexto legado e leitura separada dos tetos de execução.

Revisões realizadas pelos agentes `review_runtime_profiles_architecture` e
`review_runtime_profiles_authorization`, comparando com `main` em `3dc5bf2`.
A implementação foi autorizada posteriormente pelo autor. Revisão de código e
agentes de teste verificaram a biblioteca, o acesso e a execução em ambiente isolado.
O [relatório de validação](../benchmarks/execution-profiles-validation.md) registra
evidências e limites: os critérios acima são verificados com banco descartável e
providers simulados; canário físico e ativação continuam pendentes.
O [guia funcional](../features/execution-profiles.md) descreve o comportamento
entregue; o [runbook](../runbooks/execution-profiles-access.md) cobre a migração.
