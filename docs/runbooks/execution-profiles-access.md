# Ativar perfis de execução e acesso granular

Verificado contra o código em **2026-10-06**. Use junto do [bootstrap de controle](engine-control-bootstrap.md). O código é
opt-in; este runbook não inicia engines/modelos nem cria grants automaticamente.

## 1. Preparação e migração

Registre backup do SQL e as revisões atuais de runtime, operações incertas,
locks, gates e reservas. Aguarde operações ativas ou preserve explicitamente a
exposição antes da janela. Impeça novos escritores durante a troca de release.
Não faça `docker compose down` em toda a instalação para isso.

A release acrescenta origem/hash ao runtime e autores de cancelamento/recovery.
Essas colunas precisam ser migradas **mesmo com `ENGINE_ACCESS_ENABLED=false`**
quando o controle da 0007 está ativo. A API falha no startup se faltarem as colunas
necessárias; não tenta alterar automaticamente um banco existente.

Com o código desta release disponível, execute a migração explícita. Use o
conjunto real de arquivos Compose da instalação, incluindo seus overlays locais:

```bash
docker compose run --rm --no-deps api python -c \
  'from shared.database import engine; from shared.access.migration import upgrade; upgrade(engine)'
```

Se a instalação já usa Alembic com a árvore corretamente estampada, a revisão é
`f0b40009c4d3`, depois de `c7e10007a1f0`. A função direta é idempotente e evita
inferir/stampar migrações históricas da instalação.

A migração cria biblioteca, revisões, políticas, grants, epoch, consumidores,
admissões e contexto legado. Preserva registros antigos e não infere consumidores,
ambiente confiável, publicação ou estado aplicado. Downgrade destrutivo é recusado
para preservar auditoria e exposição.

## 2. Rollout coordenado

Defina no `.env`:

```dotenv
ENGINE_CONTROL_ENABLED=true
ENGINE_ACCESS_ENABLED=true
# Opcional; só para a CLI bootstrap registrada abaixo:
ENGINE_INSTALLATION_PRINCIPAL_ID=installation:dev
```

`docker-compose.engine-control.yml` repassa as opções à API e aos workers de
controle/remote e demais serviços relacionados. `.env` sozinho não injeta uma
variável num container já existente. Recrie os serviços afetados com o overlay
em uso e mantenha as escalas originais; não suba workers de áudio/live só por
ativar esta biblioteca. Confirme o environment final sem imprimir segredos.

O overlay mudou nesta release. Instalações com agente local que verifica hash
de manifests precisam registrar novamente o conjunto real de Compose antes de
operar. O `manifest_hash` anterior não deve ser reaproveitado se seus arquivos
mudaram. Siga a seção de registro no runbook de controle, mantendo identidade,
permissões de arquivos e inicialização via serviço já configuradas.

Verifique saúde da API, heartbeat do worker-control/watchdog e agente local.
O watchdog permanece necessário para exposição paga; a feature não remove
readiness, orçamento, modelo aprovado, manifest, UUID de GPU ou gates da 0007.

## 3. Configuração inicial pelo bootstrap

1. Em `/admin/access`, classifique o ambiente das engines que receberão grants.
2. Crie um perfil na biblioteca, publique a revisão e faça o primeiro vínculo de
   bootstrap. Isso registra os recursos canônicos sem executar nem reservar custo.
3. Em consumidores, declare todas as engines/features afetadas por cada serviço
   e GPU, incluindo o worker genérico. Marque qualificado somente após conferir
   o inventário e os usos reais. Até isso acontecer, atuação delegada falha fechada.
4. Crie uma política pequena, começando por uma engine de desenvolvimento e os
   modelos/hosts/UUIDs necessários. Escolha valores explícitos de CPU e memória.
5. Conceda `observer` com validade curta e confira que outra engine/produção,
   detalhes, histórico e SSE não aparecem. Depois conceda configurador/operador
   apenas com ações necessárias. Um grant completo deve cobrir cada decisão.
6. Para `access_admin`, defina o envelope de delegação; não conceda execução
   implicitamente. Políticas/grants não alteram o bootstrap atual.

Não use propriedade de projeto para qualificar um worker compartilhado. Não
remova consumidores da lista apenas para permitir uma operação negada.

## 4. CLI de instalação opcional

Registre o ID pelo endpoint bootstrap `POST /admin/access/installation-principals`
com corpo `{"id":"installation:dev"}` e sessão JWT. O ID deve corresponder ao
environment da API/worker em que a CLI roda; prefixo `installation:` e tamanho
máximo de 36 caracteres. O registro não concede sessão humana nem altera usuários.

```bash
docker compose exec api python scripts/engines.py \
  --installation-principal installation:dev list --json
```

Para comandos que precisam das chaves privadas, use worker-remote conforme a
instalação, mantendo a opção antes do subcomando. Usuários delegados usam os
endpoints de planos com sua sessão; não recebem acesso de SO/CLI por um grant.

Deploy CLI de engine já gerenciada continua recusado: use a operação pela API.
Um deploy bootstrap em engine não gerenciada gera admissão durável e fence dos
recursos, sem segurar transação durante a rede. Se o processo cair, ou o principal
for revogado durante o build, conserve os locks e a admissão incerta. Observe o
estado do provedor e custos com uma autoridade administrativa vigente antes de
confirmar/liberar essa exposição. Não repita o deploy nem limpe fences por um
retry automático. O diagnóstico está no `AdminAudit` e
`access_effect_admissions`; admissão CLI tem geração zero e ID próprio.

Desative o principal com `PUT /admin/access/installation-principals/{id}` usando
`version` e `active:false`; isso incrementa o epoch. Alterações de usuário pelo
endpoint `/access/subjects/{id}/state` também comparam o estado esperado e atualizam
epoch/auditoria. `make_admin.py` continua sendo o bootstrap explícito da instalação
e registra sua promoção no epoch quando a funcionalidade está ativa.

## 5. Canário e rollback

Execute primeiro um fluxo sem custo: biblioteca → publicação → vínculo → leitura
scopada. Confira que aplicado/observado não mudaram. Em seguida, numa janela
controlada, teste a prévia e uma operação da engine selecionada, com limites e
confirmação explícitos. Verifique revogação antes de novo passo, cancelamento,
recovery por outro ator e SSE encerrado. Infraestrutura real não foi executada
pelos testes automatizados desta entrega.

Para desativar delegação, defina `ENGINE_ACCESS_ENABLED=false` e recrie API e
executores de forma coordenada. O bootstrap conserva os controles anteriores;
a biblioteca/IAM deixa de aceitar uso. Desabilitar não concede um grant pendente:
operações que já guardam autoridade delegada revalidam o ator e não ganham poderes
de bootstrap. Preserve watchdog/exposição e a migração aditiva. Voltar código
anterior exige revisão específica da compatibilidade; não apague tabelas nem
locks/reservas para fazer rollback.
