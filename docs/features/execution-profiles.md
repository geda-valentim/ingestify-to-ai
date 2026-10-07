# Perfis de execução e acesso a Compute

Implementação da [spec 0009](../specs/0009-perfis-de-execucao-e-controle-de-acesso.md),
verificada contra o código em **2026-10-06**; opt-in com `ENGINE_ACCESS_ENABLED`. Ativação e migração:
[runbook](../runbooks/execution-profiles-access.md). Controles físicos continuam
exigindo a configuração da [spec 0007](../runbooks/engine-control-bootstrap.md).

## Onde configurar

| Tela | Uso |
|---|---|
| `/admin/execution-profiles` | Criar, clonar, revisar, publicar e arquivar perfis de execução |
| `/admin/engines/{id}` → Configuração | Escolher a revisão publicada e vincular ao desejado |
| `/admin/engines/{id}` → Visão geral / Operações | Ver desejado, aplicado e observado; preparar e executar uma operação |
| `/admin/access` | Políticas, revisões, grants, validade e revogação; bootstrap também classifica ambientes e consumidores |

Um **perfil de execução** contém os parâmetros de runtime. Um **modelo aprovado**
é uma entrada do catálogo instalado. Um **papel de acesso** contém permissões;
sua política ABAC delimita recursos e limites. São entidades distintas.

## Criar, publicar, vincular e operar

1. Abra a biblioteca e crie um perfil nomeado. Escolha provider, feature, ambiente,
   modelo aprovado, host/GPU, réplicas, execuções por worker, CPU, memória e warmup.
   O formulário usa os descriptors dos adapters existentes; não aceita código,
   repositório de modelo ou credencial livre.
2. Salve o rascunho e publique uma revisão explícita. Novos rascunhos não
   substituem uma publicação anterior. Revisões publicadas são imutáveis.
3. Na engine, escolha perfil e revisão publicada, confira as mudanças e vincule
   ao desejado. Adapter, feature e ambiente devem corresponder. GPU e host são
   validados novamente contra o inventário registrado e as regras de capacidade.
4. Revise a prévia de uma operação e confirme sua execução. Outbox, runner,
   leases, drenagem, reservas, readiness e recuperação continuam sendo os da 0007.

**Criar, publicar e vincular não iniciam containers, fazem deploy nem reservam
orçamento.** O vínculo cria um `RuntimeProfile` desejado com origem, hash e
snapshot resolvido na mesma transação de `save_profile`. Aplicado só muda após
verificação do executor; observado registra o que foi comprovado.

Publicar uma revisão nova não muda engines vinculadas. Arquivar impede novos
vínculos, preservando revisões, runtime aplicado, planos e auditoria. Clonar cria
outro perfil em rascunho. O admin pode importar o desejado legado como rascunho:
campos resolvidos (`model`, `service`, `gpu_uuid`, `manifest_hash`) não entram no
novo template, e o registro original continua intacto.

O catálogo é fixado por fingerprint de seus metadados aprovados. Se o modelo
configurado por um alias mudar, publique uma nova revisão compatível; um vínculo
com metadados divergentes é rejeitado. Planos, enqueue e novos efeitos também
verificam esse fingerprint; uma mudança posterior do catálogo exige revisão explícita.
O adapter local preserva UUIDs dos snapshots aplicados e rejeita inventário/manifesto
divergente do desejado na prévia, exigindo novo vínculo. O perfil não transforma um modelo não
qualificado em suportado — inclusive WhisperX ou live remotos ainda sujeitos aos
gates existentes do adapter.

## Prazo aquecido e conflitos

A biblioteca usa `warm_for_seconds`, opcional e limitado a 86.400 segundos.
`RuntimeSettings.warm_until` é nulo no template. O vínculo resolve o prazo em UTC
uma única vez; operações e retries não renovam esse prazo. Para aquecer novamente,
faça outra vinculação explícita e prepare outro plano.

Criação de revisão, publicação, arquivamento, vínculo, grants e qualificação usam
versões esperadas. Em `VERSION_CONFLICT`, consulte o estado atual e revise sua
intenção antes de outra escrita. O frontend não atualiza a versão e repete o
vínculo automaticamente: uma resposta perdida após commit não cria outra revisão
nem renova o aquecimento.

## Papéis e escopos

| Papel API | Permissões |
|---|---|
| Bootstrap | Admin efetivo existente (`is_admin` ou `ADMIN_USER_IDS`), ativo; acesso de emergência |
| `observer` | Leitura de perfis, engines e operações dentro do escopo |
| `profile_editor` | Criar, revisar, publicar e arquivar perfis permitidos |
| `runtime_configurator` | Leitura e vínculo de revisão publicada ao desejado |
| `engine_operator` | Planos, ações explicitamente concedidas, cancelamento e recovery |
| `connection_manager` | Leitura e gestão de credenciais da conexão; exige senha atual |
| `access_admin` | Gerenciar políticas/grants dentro do envelope de delegação; não recebe execução pelo papel |

O grant fixa uma **revisão da política**, permissões de um papel e validade UTC.
Nova revisão da política não amplia grants existentes. Para alterar a autoridade,
conceda um novo grant e revogue o anterior. A autoria de um perfil não dá poder
fora da política; criação usa os atributos permitidos porque ainda não existe ID.

As políticas têm listas de engines, perfis, adapters, features, ambientes, hosts,
UUIDs físicos de GPU e modelos, além de tetos de réplicas, execuções por worker,
CPU, memória, tempo aquecido e `max_usd`. Listas obrigatórias vazias não autorizam
recursos; listas opcionais nulas não impõem restrição adicional. Um usuário
precisa satisfazer **um grant inteiro** por decisão: não pode somar o host permitido
por um grant ao teto de custo de outro.

Templates delegados precisam declarar CPU e memória: defaults de um provider não
podem ultrapassar um teto sem que isso seja verificado. `gpu_ref` local é um alias
da engine, resolvido ao UUID registrado no vínculo; a GPU remota do Modal é um
tipo de GPU, não um UUID físico local.

Leitura verifica identidades e escopo, mas não aplica tetos numéricos de execução
ao histórico. Observer pode ler uma operação autorizada cujo custo excedeu seu
próprio teto de execução. Detalhes e cursores de outro escopo retornam 404;
listagens, catálogo, hosts, bindings, logs e SSE são filtrados. `can_cancel` e
`can_recover` combinam estado com a permissão atual. A UI isola o cache por sessão
para não reaproveitar dados de outro login.

## Delegação e recursos compartilhados

O bootstrap concede ao `access_admin` um envelope separado de delegação: permissões
concedíveis, política máxima e duração máxima. Esse envelope não concede direitos
de operação ao titular. Sem envelope ele não concede nada. Grants derivados têm
um pai; revogar, expirar ou desativar a autoridade parental invalida os derivados.

Ambiente é um atributo confiável da engine, classificado pelo bootstrap; não vem
de um JWT, projeto ou label enviado pelo operador. Na área de consumidores,
declare **todos** os usuários físicos de cada recurso canônico, incluindo outras
features do worker genérico e engines que compartilham GPU/serviço. A associação
é separada da propriedade `ControlResource.owner_engine_id`.

Uma decisão cobre os recursos do desejado **e** do último aplicado. Consumidor
não classificado, desconhecido, não qualificado ou fora do grant bloqueia atuação
delegada. A autorização cobre hosts/GPU/modelos do conjunto afetado. Qualificar
uma lista incompleta para contornar o bloqueio não é um fluxo válido: essa lista
é responsabilidade administrativa da plataforma. Propriedade de projeto/job
não concede permissão para parar um worker global.

## Revogação e efeitos externos

API, domínio, enqueue, runner e agente consultam a autoridade SQL atual. Redis e
claims do JWT não concedem acesso por si. Antes de enviar novos comandos, o
executor registra uma admissão durável com operação, geração, passo, ator,
executor, epoch, ação, alvos e decisão. Revogação e admissão se ordenam pelo mesmo
epoch SQL; nenhuma transação fica aberta durante build ou RPC.

Revogação impede novos passos. Um comando admitido antes dela pode estar em voo:
resultado desconhecido fica incerto, mantendo locks/reservas até observação ou
limpeza autorizada. Não há promessa de desfazer um RPC já aceito. O watchdog só
limpa exposição registrada; não inicia/aquecerá recursos com a sessão revogada.
Recovery usa o solicitante atual e preserva o ator iniciador; cancelamento e
recovery têm auditoria própria. SSE revalida por lote e encerra após revogação.

## Compatibilidade e bootstrap CLI

Os cards Docker continuam disponíveis. Alterações legadas de capacidade, GPU,
orçamento, lifecycle e JSON bruto de runtime permanecem bootstrap-only. Usuários
delegados configuram pela biblioteca e operam pela API de planos. Credenciais
possuem papel específico, reautenticação e os locks já existentes.

Os legados humanos `test`, `reconcile` e `test-all` transportam uma requisição SQL
com ator, ação, IDs aceitos e validade; o worker revalida antes do RPC e de registrar
resultado. `test-all` não inclui engines criadas após sua aceitação. Billing,
probe e cancelamento sistêmico de usage conservam seus caminhos limitados e não
herdam uma sessão humana.

Com acesso granular ativo, CLI direta exige principal registrado
`installation:<nome>` (até 36 caracteres), configuração
`ENGINE_INSTALLATION_PRINCIPAL_ID` correspondente e opção
`--installation-principal` antes do comando. CLI direta é bootstrap de SO;
usuários delegados usam a sessão JWT e a API. O deploy CLI de engine não gerenciada
admite/audita efeitos e mantém fence canônico, liberando SQL antes da rede.
Um resultado incerto conserva locks e exige observação administrativa; engine
já gerenciada exige operação de runtime pela API. Consulte o runbook antes de
repetir um deploy interrompido.

## API principal

Biblioteca, controles e IAM exigem sessão JWT; API keys não substituem essa sessão.

| Método | Rota sob `/admin` | Uso |
|---|---|---|
| GET / POST | `/execution-profiles` | Listar / criar rascunho |
| GET / PUT | `/execution-profiles/{id}` | Detalhe / nome e descrição com versão |
| POST | `/execution-profiles/{id}/revisions` | Novo payload imutável com versão esperada |
| POST | `/execution-profiles/{id}/publish` | `version` + `revision_id` explícitos |
| POST | `/execution-profiles/{id}/archive` | Arquivar com versão esperada |
| POST | `/engines/{id}/runtime-profile/bind` | `version`, `feature`, `revision_id` publicado |
| POST | `/engines/{id}/runtime-profile/import` | Bootstrap: importar desejado legado como rascunho |
| GET | `/access/me` | Permissões de navegação e estado do rollout |
| GET / POST | `/access/policies` | Listar / criar política |
| POST | `/access/policies/{id}/revisions` | Nova revisão, grants anteriores permanecem fixados |
| GET / POST | `/access/grants` | Listar / conceder papel com revisão e validade |
| POST | `/access/grants/{id}/revoke` | Revogar com versão esperada |
| GET / PUT | `/access/engine-attributes[/{id}]` | Bootstrap: ambientes confiáveis |
| GET / PUT | `/access/resources` | Bootstrap: consumidores completos e qualificação |
| GET / POST / PUT | `/access/installation-principals[/{id}]` | Bootstrap: registrar, listar, ativar/desativar principal CLI |
| PUT | `/access/subjects/{id}/state` | Bootstrap: ativo/admin com comparação de estado esperado e epoch |

`/auth/me` também retorna permissões de navegação e `engine_access_enabled`.
Alterações externas de `ADMIN_USER_IDS` precisam de rollout coordenado de API e
executores. Não altere grants, usuários ou atributos confiáveis diretamente no
banco durante operações; use os caminhos que atualizam o epoch e a auditoria.

Erros úteis: `ACCESS_NOT_ENABLED`, `ACCESS_DENIED`, `DELEGATION_EXCEEDED`,
`PUBLISHED_REVISION_REQUIRED`, `ENGINE_ENVIRONMENT_REQUIRED`,
`PROFILE_INCOMPATIBLE`, `MODEL_METADATA_CHANGED`, `VERSION_CONFLICT` e os gates
anteriores `CONTROL_NOT_ENABLED`, `HOST_AGENT_NOT_READY`, `CLEANUP_WATCHDOG_NOT_READY`.

## Validação

Resultados e limites estão em
[benchmarks/execution-profiles-validation.md](../benchmarks/execution-profiles-validation.md).
A rodada automatizada não iniciou infraestrutura paga. Depois, o PR #45 foi
mergeado e a funcionalidade foi ativada no dev com migração explícita, restart
coordenado e verificação da API. A documentação web fica em `/docs/compute` e
`/pt/docs/compute`. Um canário físico de host/Modal e concessões limitadas
ainda precisam seguir o rollout descrito no runbook.

## Requisitos e aplicações publicados

Guias completos de [perfis](https://dev.ingestify.ai/pt/docs/execution-profiles),
[RBAC/ABAC](https://dev.ingestify.ai/pt/docs/engine-access),
[operações](https://dev.ingestify.ai/pt/docs/engine-operations) e
[engines](https://dev.ingestify.ai/pt/docs/engines) incluem requisitos identificados,
pré-condições, campos/limites, contratos da API, diagnóstico e exemplos.
Os mesmos IDs PRF/ACL/OPS/ENG estão em [RF012](../RF.md#rf012---engines-operações-perfis-e-acesso).
