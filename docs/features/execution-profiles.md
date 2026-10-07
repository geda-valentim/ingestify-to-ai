# Perfis de execução e acesso a Compute

Implementação da spec 0009,
verificada contra o código em **2026-10-07**; opt-in com `IAM_MODE=enforce` (ou o alias
depreciado `ENGINE_ACCESS_ENABLED=true`). Ativação e migração:
[runbook](../runbooks/execution-profiles-access.md).

Desde a spec 0018 os grants
abaixo são `iam_bindings` da **família `engines`**, administrados com os de plataforma
numa só tela e numa só API; a decisão da 0009 não mudou. Controles físicos continuam
exigindo a configuração da [spec 0007](../runbooks/engine-control-bootstrap.md).

## Onde configurar

| Tela | Uso |
|---|---|
| `/admin/execution-profiles` | Criar, clonar, revisar, publicar e arquivar perfis de execução |
| `/admin/engines/{id}` → Configuração | Escolher a revisão publicada e vincular ao desejado |
| `/admin/engines/{id}` → Visão geral / Operações | Ver desejado, aplicado e observado; preparar e executar uma operação |
| `/admin/access` (Admin → Acesso) | Abas Concessões (bindings de plataforma e de engines), Políticas, Atributos de engine, Recursos e Principais de instalação; as três últimas só para o bootstrap |

Um **perfil de execução** contém os parâmetros de runtime. Um **modelo aprovado**
é uma entrada do catálogo instalado. Um **papel de acesso** contém permissões;
sua política ABAC delimita recursos e limites. São entidades distintas.

## Perfis padrão da instalação (spec 0020)

Uma instalação não começa com a biblioteca vazia. O root cria, publica e — quando a
engine permite — vincula perfis de execução padrão, sem nenhum efeito físico (nenhum
plano, operação, outbox ou reserva; aplicar continua sendo uma operação explícita).

| Perfil | Quando | Conteúdo |
|---|---|---|
| `Padrão — <modelo>` | Para cada modelo `approved` do catálogo e cada adapter dele | Local: 1 worker sem GPU, `host_id` do único host agent registrado que serve a feature (com mais de um, só os vistos nos últimos 30 s contam; ainda mais de um ⇒ `HOST_AMBIGUOUS`). Modal: `gpu_type` L4, 1 worker, `memory_mb` nulo, sem `cpu`, `min_ready_replicas` 0. Ponto de partida: revise GPU e réplicas antes de vincular |
| `<engine> — <feature>` | Para cada engine × feature com binding configurado (ou perfil desejado legado) | Reproduz a configuração atual: binding da engine, modelo aprovado do adapter/feature, `desired = max = workers`, `min_ready` 0, cooldown = `scaledown_window` da engine (limitado a 2–3600 s; 60 s quando a engine não define), `on_start`, `memory_mb` nulo, `host_id` do host que serve a feature e tem a GPU do binding. Um perfil desejado legado é importado por whitelist (como o import da tela), com `warm_until` nulo |

O perfil de engine é **vinculado** quando a engine ainda não tem perfil desejado na
feature. Antes de vincular, a semeadura compara a revisão publicada com a configuração
**atual** da engine (o perfil pode ter sido criado quando o vínculo ainda não era
possível e a engine ter sido reajustada depois). Se mudou e o perfil continua só da
semeadura (toda auditoria dele com `origin: seed` e a mesma `seed_key`, toda revisão do
mesmo autor), publica uma nova revisão com a configuração atual e vincula essa; se um
administrador já mexeu no perfil (revisão, publicação, renomeação), pula com
`SEEDED_PROFILE_STALE`.

Uma engine sem atributos recebe o ambiente da instalação só depois que as validações do
adapter passaram, na mesma transação do vínculo: se o vínculo falhar, a classificação é
desfeita. `ENVIRONMENT` é mapeado explicitamente (`development`/`dev`/`local` →
development, `staging` → staging, `production`/`prod` → production); qualquer outro
valor pula tudo com `ENVIRONMENT_UNKNOWN`. Vincular passa a engine para "gerenciada":
escritores legados de capacidade passam a exigir operação. Falhas de vínculo não
interrompem a semeadura e são repetidas na próxima execução, porque a engine continua
sem perfil desejado.

**Quando roda:** na criação do root (no cadastro da instalação vazia, em background
depois da resposta; `make_admin.py --root` roda síncrono), em todo boot da API com root
existente, quando um host agent se registra, volta após ficar sem heartbeat (> 30 s) ou
muda de manifest (esta última no máximo uma vez por minuto por host, por processo da
API), e
manualmente com `scripts/seed_execution_profiles.py [--dry-run] [--json]` (ou
`python -m shared.access.seed`). Sem root nada acontece; nenhum gatilho derruba o boot,
o cadastro ou o heartbeat.

**Idempotência:** a chave (`catalog:<modelo>:<adapter>` ou `engine:<id>:<feature>`) fica
no `AdminAudit` `execution_profile.created`, gravado na mesma transação do perfil. Renomear
não duplica; um perfil semeado **arquivado** não é recriado. Mudanças posteriores de
catálogo não atualizam perfis existentes (crie uma revisão); mudanças de binding só
atualizam o perfil de engine ainda não vinculado e intocado (acima). Cada passo
toma o lock do epoch de autorização, então vários workers da API bootando juntos não
duplicam nada.

**Auditoria:** perfil criado, revisado, publicado, engine classificada e vínculo (`engine.profile_created`)
levam `{"origin": "seed", "seed_key": ...}` no `after`.

**Com acesso a engines desligado** (`IAM_MODE` diferente de `enforce` e sem o alias
`ENGINE_ACCESS_ENABLED`) a biblioteca está fechada: a semeadura registra
`ACCESS_NOT_ENABLED` e roda no próximo boot com o acesso ligado.

**Instalação nova sem host agent:** perfis locais exigem um `host_id` concreto; até um
host se registrar, `Padrão — …` locais e perfis da engine `local` ficam pendentes com
`NO_REGISTERED_HOST`. O primeiro heartbeat do host dispara a semeadura, que cria e vincula.

O relatório (`SeedReport`) lista `created`, `published` (com `refreshed: true` para a
revisão nova de um perfil desatualizado), `bound`, `classified` (engines que receberam o
ambiente) e `skipped`; cada item
pulado traz `key`, `stage` (`seed`, `create` ou `bind`), o código estável (`reason`) e
uma explicação em português (`message`), por exemplo `HOST_AGENT_NOT_READY`,
`TEST_CONNECTION_FIRST` (Modal sem "Testar conexão"), `MODEL_NOT_APPROVED`,
`RUNTIME_PROFILE_EXISTS`, `SEEDED_PROFILE_STALE`, `HOST_AMBIGUOUS`, `ENVIRONMENT_UNKNOWN`.

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

O grant (binding de engines) fixa uma **revisão da política** como condição
(`condition_ref`), um subconjunto materializado das permissões do papel e validade UTC.
Um usuário pode ter vários bindings do mesmo papel, cada um com sua condição.
Ninguém concede papel de engines a si mesmo (`422 SELF_GRANT`, desde a 0018).
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
| GET / POST | `/iam/bindings` | Listar / conceder papel de engines (`condition_ref`, `permissions`, `delegation`) ou de plataforma |
| POST | `/iam/bindings/{id}/revoke` | Revogar com versão esperada; já revogado → `409 ALREADY_REVOKED` |
| GET / POST | `/access/grants` | **Depreciado** (0018): alias com o contrato da 0009, só papéis de engines |
| POST | `/access/grants/{id}/revoke` | **Depreciado** (0018): alias, aceita re-revogação |
| GET / PUT | `/access/engine-attributes[/{id}]` | Bootstrap: ambientes confiáveis |
| GET / PUT | `/access/resources` | Bootstrap: consumidores completos e qualificação |
| GET / POST / PUT | `/access/installation-principals[/{id}]` | Bootstrap: registrar, listar, ativar/desativar principal CLI |
| PUT | `/access/subjects/{id}/state` | Bootstrap: ativo/admin com comparação de estado esperado e epoch |

`/auth/me` também retorna permissões de navegação e `engine_access_enabled`.
Alterações externas de `ADMIN_USER_IDS` precisam de rollout coordenado de API e
executores. Não altere bindings, usuários ou atributos confiáveis diretamente no
banco durante operações; use os caminhos que atualizam o epoch, a auditoria
(`iam_binding`) e o espelho `access_role_grants`, mantido só para rollback.

Erros úteis: `ACCESS_NOT_ENABLED`, `ACCESS_DENIED`, `DELEGATION_EXCEEDED`, `SELF_GRANT`,
`PUBLISHED_REVISION_REQUIRED`, `ENGINE_ENVIRONMENT_REQUIRED`,
`PROFILE_INCOMPATIBLE`, `MODEL_METADATA_CHANGED`, `VERSION_CONFLICT` e os gates
anteriores `CONTROL_NOT_ENABLED`, `HOST_AGENT_NOT_READY`, `CLEANUP_WATCHDOG_NOT_READY`.

### Corpo de erro

As rotas de controle de engines (`/admin/engines/{id}/…`), perfis/acesso (`/admin/…`) e
IAM (`/iam/…`) respondem `{"detail": {"code", "message", "next_steps", "cause"?,
"technical"?}}`. `code` é o contrato estável e não mudou; `message` vem do catálogo único
`backend/shared/error_catalog.py` e **agora é sempre em português** (antes algumas rotas
de IAM/acesso devolviam texto em inglês ou só o código); `next_steps` é um vocabulário
fechado que o admin transforma em botões; `cause` é o gate interno quando um código
genérico o embrulha (`INVALID_CONFIGURATION` → `HOST_AGENT_NOT_READY`). Clientes devem
decidir por `code`, nunca por `message`.

Ao criar um plano (`POST /admin/engines/{id}/operation-plans`), uma capability desabilitada responde
com o status do motivo, não mais sempre `503`:

| Motivo | Antes | Agora |
|---|---|---|
| `RUNTIME_PROFILE_REQUIRED` (Modal/local sem perfil desejado) | 503 | **422** |
| `ACCESS_DENIED` | 503 | **403** |
| `NOTHING_TO_COOL_DOWN` (cooldown sem perfil desejado: nada para liberar) | 422 `RUNTIME_PROFILE_REQUIRED` | **409** |
| `ACTION_UNSUPPORTED` | 422 | 422 |
| demais gates (`CONTROL_NOT_ENABLED`, `HOST_AGENT_NOT_READY`, `CREDENTIALS_REQUIRED`, `CLEANUP_WATCHDOG_NOT_READY`, …) | 503 | 503 |

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
Os mesmos IDs PRF/ACL/OPS/ENG estão em RF012.
