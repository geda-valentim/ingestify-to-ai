# Deploy de produção (`make deploy`)

`make deploy` chama `scripts/deploy.sh` sob `env -i`. O Makefile exporta o `.env` e
`REDIS_HOST ?= localhost` para os alvos `check-*`, e um compose que herdou isso já apontou
containers para localhost. O compose lê `COMPOSE_FILE`/`COMPOSE_PROFILES` do `.env` sozinho.

## Ambiente repassado (`env -i`)

Só o que está na lista chega ao script, e só se estiver definido e não vazio: `PATH`, `HOME`,
`DOCKER_HOST`, `DOCKER_CONFIG`, `DOCKER_CONTEXT`, `DOCKER_TLS_VERIFY`, `DOCKER_TLS`,
`DOCKER_CERT_PATH`, `DRY_RUN`, `FORCE_REBUILD`, `DEPLOY_BASE`, `DEPLOY_REF`, `NO_PULL`,
`BUILD_LIVE`, `DEPLOY_AGENT_DIR`, `DEPLOY_ENGINE_HOST_CONFIG`, `SSH_AUTH_SOCK` e
`GIT_SSH_COMMAND`. Qualquer outra variável é descartada. Para um novo parâmetro, ele precisa
entrar na lista do Makefile.

- `DEPLOY_AGENT_DIR`: diretório de estado do host agent. Padrão
  `/var/lib/ingestify-engine-agent`.
- `DEPLOY_ENGINE_HOST_CONFIG`: config do host registrado. Padrão
  `/etc/ingestify/engine-host.json`.

## O que o deploy faz, por estágio

Ao falhar, o script imprime `DEPLOY FAILED at stage: <estágio>`.

1. **preconditions**: exige a branch `main`. Fixa a base de detecção **antes** de mexer no
   git: `DEPLOY_BASE`, senão o marcador `.git/deploy-last-success`, senão `FORCE_REBUILD=1`
   (parte do HEAD atual e liga o aviso de compose). Sem nenhum dos três, aborta sem alterar
   nada (`no deploy marker`). Marcador que aponta para commit desconhecido conta como ausente.
   Lê também `deploy-pending` e `deploy-pending-inventory` (ver "Deploy interrompido").
2. **fetch**: `git fetch origin main` e escolhe o alvo (`origin/main`, `DEPLOY_REF` ou o
   HEAD atual com `NO_PULL=1`). Aborta, listando os arquivos, se uma mudança local em arquivo
   rastreado conflita com o que chega; mudança local fora do alvo só gera aviso. Lê o
   `API_VERSION` do alvo. Calcula as mudanças como a união de `base..alvo`, `HEAD atual..alvo`
   e `commit pendente..alvo` para cada commit de `deploy-pending`.
3. **pull**: aborta se o `main` local está à frente do alvo. Antes de mudar o git, anexa o HEAD
   atual e o alvo a `deploy-pending`. Depois `git merge --ff-only` do commit já analisado (sem
   segundo fetch) ou, no rollback, `git reset --keep`.
4. **inventory**: valida `compose config --quiet` e lista os serviços. Registra o
   `COMPOSE_FILE` do `.env` (e avisa se `docker-compose.override.yml` existe fora dele).
   Descobre os serviços **gerenciados** pelo engine control: cada `*.json` de `DEPLOY_AGENT_DIR`
   (tira o prefixo `observe-`; ignora `state`). Se o diretório existe mas não é legível, ou não existe e o `DEPLOY_ENGINE_HOST_CONFIG`
   existe (engine control instalado, estado inutilizável), aborta sem tocar em nada.
   Sem engine control instalado, não há gerenciados. Conta as
   réplicas **em execução** de cada serviço (se `compose ps` falhar, aborta). Grava o
   inventário só na primeira execução do deploy e restaura o que uma execução interrompida
   deixou parado (ver "Deploy interrompido").
5. **backend**:
   - mudou imagem (`requirements*.txt`/`*.lock`, `docker/Dockerfile.*` exceto frontend,
     `docker/entrypoint.sh`, `scripts/{make_admin,engines,seed_execution_profiles}.py`) **ou**
     o compose: avisa de tarefas ativas, faz `build` de todos os serviços de código (os
     gerenciados só são construídos) e recria os **não gerenciados em execução** com
     `up -d --no-build --no-deps --force-recreate --scale <svc>=<rodando>`. Um serviço de
     código sem `build:` no config final (por exemplo, `build: !reset` ou um serviço definido
     só num override) é pulado pelo `compose build` com saída 0: o script avisa
     `no build: section for: <svc> … NOT rebuilt`, repete no fim (`ATTENTION - NOT rebuilt`) e
     segue com a imagem antiga dele. O próximo deploy não detecta a mudança de novo: corrija o
     override (ou construa a imagem fixada à mão) e só então re-registre um gerenciado com
     `--use-built-image`. O mesmo vale para o `frontend`;
   - só o compose (sem imagem): os gerenciados em execução levam `docker restart`;
   - só código (`backend/{api,shared,workers}/`): `docker restart` dos em execução, gerenciados
     inclusive;
   - se houver serviço a restaurar: `up -d --no-build --no-deps` sem recriar.
6. **worker-live**: ver "worker-live" abaixo.
7. **frontend**: `build` se mudou `frontend/` ou `Dockerfile.frontend`, ou se o compose mudou
   e ele está rodando; `up` só se estiver rodando. Em seguida vem o aviso de gerenciados.
8. **health**: porta de `compose port api 8000`, `GET /health` com HTTP 200,
   `"status":"healthy"` e `"version"` igual ao `API_VERSION` do alvo (40 tentativas x 3 s).
9. **marker**: só depois do health grava `deploy-last-success` com o HEAD e apaga
   `deploy-pending` e `deploy-pending-inventory`.

Os arquivos ficam em `git rev-parse --git-path <nome>` (`.git/` do checkout).

## Regras

- Nunca sobe serviço parado, nem remove réplicas. `api` e `beat` nunca recebem `--scale`.
- Serviço gerenciado nunca recebe `up`. O host agent o aplica com overlay (imagem fixada,
  GPU, perfil) fora do `COMPOSE_FILE`. Serviços parados de propósito continuam parados.
- Com imagem nova, gerenciados só recebem `build` e o aviso. Código novo com imagem velha
  pode quebrar o import, então não há restart.
- O `deploy-last-success` só é gravado depois de um health que confere a versão.

## worker-live

O `worker-live` leva `backend/shared` e `backend/workers` dentro da imagem (sem bind mount).
O deploy **nunca** o sobe, reinicia ou restaura, e **nunca** o constrói sozinho.

- Se os insumos mudaram (`backend/{shared,workers}/`, requirements, Dockerfile do worker/live,
  entrypoint) **ou o compose mudou**, o script avisa `worker-live inputs changed: its image
  is stale`. O compose entra porque pode mexer em build args ou no Dockerfile.
- Para construir, rode `make deploy BUILD_LIVE=1` (só `build`, independente da detecção).
  Depois re-registre o host e rode `apply_profile`.
- O `worker-live` é `profiles: [live]`. O script o trata com `--profile live` (build, inventário
  e aviso de imagem velha), mesmo que o `COMPOSE_PROFILES` do `.env` não inclua `live`. Se nem
  assim o compose declara o serviço (falta o `docker-compose.live.yml` no `COMPOSE_FILE`), ou se
  o serviço declarado não tem `build:` (um override que só fixa `image:`, caso em que o `compose
  build` sairia com 0 sem construir nada), `BUILD_LIVE=1` falha no stage `inventory`: o código já está no HEAD novo, mas nenhum container
  foi tocado. Corrija o `COMPOSE_FILE` e rode de novo.

## Serviços gerenciados: re-registrar

O deploy não recria gerenciados. No fim, o aviso `ATTENTION - engine-control-managed services
were NOT recreated` lista os afetados e o que fazer:

- compose mudou: o host agent entra em `REGISTERED_MANIFEST_CHANGED`. Re-registre o host;
- imagem nova (ou `worker-live` construído): re-registre **com** `--use-built-image`.

Siga "Re-registrar o host" de `docs/runbooks/engine-control-bootstrap.md`, repetindo os
argumentos do registro original e acrescentando a flag:

```bash
python3 scripts/register_engine_host.py <argumentos originais> --use-built-image
```

Depois rode `apply_profile` dos serviços. Com `--use-built-image`, o script registra a
imagem recém-construída `<project>-<service>` (`--project`, padrão `ingestify-to-ai`), e não
a do container existente. **Premissa:** o compose nomeia a imagem construída assim, quando o
serviço não tem `image:`. Se a tag não existir, `docker image inspect` falha e o registro
aborta com erro: confira com `docker images` antes de contornar. Serviço com `image:` e
`build:` no compose usa essa imagem (é a tag construída), com ou sem a flag. Com a flag, o
registro recusa um serviço sem `build:` e um serviço com profile que o deploy não construiu
(ver `engine-control-bootstrap.md`, passo 3).

## Flags

```bash
make deploy DRY_RUN=1                 # imprime as ações; pula health e marcador
make deploy FORCE_REBUILD=1           # trata tudo como mudado (sem marcador, ou após dúvida)
make deploy DEPLOY_BASE=<sha>         # base de detecção explícita (sem marcador)
make deploy DEPLOY_REF=<sha>          # rollback: sem pull, reset --keep (ver Falhas e rollback)
make deploy NO_PULL=1                 # sem fetch nem merge: faz deploy do HEAD atual
make deploy BUILD_LIVE=1              # constrói a imagem do worker-live (nunca sobe)
```

- `FORCE_REBUILD=1` liga imagens, código, frontend e a detecção do `worker-live`, mas **não**
  implica `BUILD_LIVE`. Sem marcador, parte do HEAD atual e liga o aviso de compose.
- `DEPLOY_REF` implica `NO_PULL` e exige commit ancestral de `origin/main`.
- `DRY_RUN=1`: o `fetch`, o `merge`/`reset`, os `build`, `up` e `restart` só são impressos
  (`[dry-run] ...`). Não grava `deploy-pending`, nem o inventário, nem o marcador, e pula o
  health. Ainda roda as leituras: `compose config`, `compose ps`, o aviso de tarefas ativas
  (`docker exec ... inspect active`). O alvo vem do `origin/main` **já buscado**, que pode
  estar velho.

## Primeiro deploy (produção em c5cdcef)

O checkout de produção está em `c5cdcef` com o `make deploy` antigo no `Makefile` local
(`compose restart` sem filtro). **Não comece por `make deploy`.** Faça o pull manual antes.
Rode na raiz do checkout, na ordem.

1. Semeie o marcador. A detecção parte de `c5cdcef`, então nada se perde:

```bash
git cat-file -e c5cdcef^{commit} && git rev-parse c5cdcef > "$(git rev-parse --git-path deploy-last-success)"
```

2. Decida **por arquivo** as mudanças locais em arquivos rastreados:

| Arquivo | Decisão | Motivo |
|---|---|---|
| `CLAUDE.md` | descartar | agora versionado em #101 (com o caminho de pin certo) |
| `Makefile` | descartar | o `deploy` novo vem versionado |
| `docker-compose.gpu.yml` | descartar | o `main` já traz `--max-memory-per-child=${DOCLING_MAX_MEMORY_PER_CHILD_KB:-5000000}` |

3. Descarte e faça o pull manual **no mesmo passo**. O deploy não pode rodar com o compose
local antigo:

```bash
git checkout -- CLAUDE.md Makefile docker-compose.gpu.yml && git pull --ff-only
```

4. Veja o plano e revise as ações:

```bash
make deploy DRY_RUN=1
```

5. Faça o deploy:

```bash
make deploy
```

6. O compose e o `requirements-base.txt` mudaram. Re-registre o host com `--use-built-image`
   (seção "Serviços gerenciados: re-registrar" acima) e **depois** rode
   `apply_profile` do `worker-audio` (o único gerenciado hoje). O `worker` docling não é
   gerenciado e recebe a imagem com o pin.

### Não versionados: decisão do operador

O script não toca nestes itens e o `git pull` os ignora. Decida antes do deploy se cada um
fica, é versionado ou é removido:

- `AGENTS.md`
- `deploy/cloudflare/`
- `docker-compose.tunnel.yml`
- `docker-compose.override.yml.bak-memlimit-20261011`
- `docker-compose.tunnel.yml.bak-memlimit-20261011`

## Deploy interrompido

Em falha, o script imprime o estágio, o HEAD atual e o anterior, o último deploy bom e se algo
mudou:

| Estágio | Estado |
|---|---|
| `start`, `preconditions`, `fetch` | nada mudou |
| `pull` | o merge/reset é atômico: o HEAD não mudou ou mudou por inteiro (`git status`) |
| `inventory` | código no HEAD novo, nenhum container tocado |
| `backend`, `worker-live`, `frontend` | **parcial**: parte dos serviços foi construída ou recriada |
| `health` | tudo rodou, mas a API está doente ou em outra versão (log do `api`) |
| `marker` | saudável, sem marcador |

Para repetir, rode o mesmo comando de novo. Um `make deploy` sem variáveis faz deploy do
`origin/main`, então numa retentativa de **rollback** ele poderia reimplantar justamente a
release que se queria abandonar. Repita **exatamente** as variáveis de alvo do comando
original, a cada retentativa:

```bash
make deploy                           # deploy normal (origin/main)
make deploy DEPLOY_REF=<ref>          # rollback: mesmo <ref> do primeiro comando
make deploy NO_PULL=1                 # se o original usou NO_PULL=1
```

O script se lembra do que ficou pendente:

- `deploy-pending` guarda um commit por linha: todo HEAD que um deploy não terminado tocou.
  Cada um entra na detecção (`commit..alvo`), então o que falhou é refeito mesmo que o
  marcador já iguale o alvo, inclusive num rollback.
- `deploy-pending-inventory` guarda `serviço réplicas`, o que rodava **antes do primeiro**
  deploy não terminado. É gravado uma vez e não é sobrescrito na retentativa. Se um serviço
  não gerenciado voltou com menos réplicas do que o inventário, a retentativa o restaura com
  `up -d --no-build --no-deps --scale` (sem recriar, e nunca `api`/`beat` com `--scale`).
- `worker-live` e gerenciados **nunca** são restaurados. O script só avisa
  (`ran N replica(s) ... re-apply its profile`): reaplique o perfil pelo engine control.
- Sucesso (health OK e marcador gravado) apaga os dois arquivos.

Se o estágio foi `marker`, grave à mão (e apague os dois arquivos pendentes):

```bash
git rev-parse HEAD > "$(git rev-parse --git-path deploy-last-success)"
rm -f "$(git rev-parse --git-path deploy-pending)" "$(git rev-parse --git-path deploy-pending-inventory)"
```

## Rollback

Para voltar ao último commit bom, sem pull:

```bash
make deploy DEPLOY_REF=<último deploy bom>
```

O script valida o commit e o ancestral em `origin/main` e roda `git reset --keep`, que recusa
se perderia mudança local. Gerenciados e `worker-live` seguem as regras acima: re-registre e
reaplique o perfil se o aviso pedir. Use `DRY_RUN=1` antes para ver o plano. Numa retentativa,
repita o mesmo `DEPLOY_REF` (ver "Deploy interrompido").

**Alvo suportado.** `make deploy DEPLOY_REF=...` só vale para alvos que já contêm
`scripts/deploy.sh`, isto é, o merge do PR #107 (`22dd189`) ou posterior. Confira com
`git log --oneline -- scripts/deploy.sh` e `git merge-base --is-ancestor 22dd189 <ref>`. Um
alvo mais antigo remove `scripts/deploy.sh` e o `deploy` do `Makefile` no `reset`, e o script
não tem como recuperar esse rollback: use o procedimento manual abaixo.

### Rollback manual (alvo sem `scripts/deploy.sh`)

Rode na raiz do checkout. O script não participa, então `deploy-last-success` e
`deploy-pending` não são atualizados.

1. Registre antes, para cada serviço **não gerenciado em execução**, o número de réplicas
   (`docker compose ps --status running -q <svc> | wc -l`). Serviço com `n=0` fica parado.
2. Vá para o commit, sem mover a branch: `git checkout --detach <ref>` (recusa se perderia
   mudança local).
3. Reconstrua e recrie **só os não gerenciados em execução**, com o `--scale` registrado
   (`api` e `beat` sem `--scale`), como em "O que o deploy não detecta":

```bash
docker compose build <serviços de código>
docker compose up -d --no-build --no-deps --force-recreate --scale <svc>=<n> <svc>
```

4. Gerenciados e `worker-live` só recebem `build`, nunca `up`. Re-registre o host com o script
   atual, como em "Re-registro após rollback", e rode `apply_profile`.
5. Confira `GET /health`. Para voltar ao fluxo normal, use `FORCE_REBUILD=1`:
   `git checkout main && make deploy FORCE_REBUILD=1`. Sem ele, se `origin/main` não mudou,
   `deploy-last-success` ainda aponta para `main` e não há commit pendente registrando o
   rollback: as duas detecções dão diff vazio, o script pula rebuild e restart, e as imagens
   e o código do rollback continuam rodando. `FORCE_REBUILD=1` reconstrói e recria tudo.

### Re-registro após rollback

O checkout voltado pode ter um `scripts/register_engine_host.py` antigo, sem
`--use-built-image` (confira com `grep -c use-built-image scripts/register_engine_host.py`; os
anteriores a `22dd189` não têm). Sem a flag, ele grava a imagem do container existente, que um
gerenciado não recriado ainda mantém, e não a recém-construída. Use o script atual, tirado do
commit anterior ao rollback (`HEAD before` na mensagem do script, ou `git rev-parse HEAD`
antes de voltar), como cópia ao lado dos demais scripts, pois ele importa `engine_host_agent`
de lá:

```bash
git show <commit anterior ao rollback>:scripts/register_engine_host.py > scripts/register_engine_host_current.py
python3 scripts/register_engine_host_current.py <argumentos originais> --use-built-image
rm scripts/register_engine_host_current.py
```

Se o commit anterior também não tiver a flag, use o `main` mais novo. Sem a flag, só vale o
caminho antigo: ele registra a imagem do container existente (ou a do `image:` do compose),
então recrie o serviço com o perfil certo antes, e não invente outras opções.

## SSH

O `origin` de produção é SSH (`git@github.com:...`). O `env -i` apaga o ambiente, então o
Makefile repassa `HOME` (vale `~/.ssh` e `known_hosts`) e `SSH_AUTH_SOCK`/`GIT_SSH_COMMAND`
quando definidos. Sem chave em `~/.ssh` e sem agente, o `fetch` falha no estágio `fetch`,
sem alterar nada.

## O que o deploy não detecta

- Edições em `.env` e em `docker-compose.override.yml` (não rastreados). Depois de editá-los,
  rode `docker compose up -d --no-build --no-deps --scale <svc>=<n> <svc>` **só** nos serviços
  **não gerenciados** afetados e **que estão rodando**. Registre `<n>` antes, com
  `docker compose ps --status running -q <svc> | wc -l`. Sem `--scale`, o compose volta ao
  número de réplicas configurado (ex.: `worker` declara `deploy.replicas: 1` no overlay GPU, e
  3 réplicas viram 1). Serviço com `n=0` foi parado de propósito: não suba. `api` e `beat` não
  recebem `--scale`. Nunca rode isso em gerenciado (ex.: `worker-audio`) nem no `worker-live`:
  o `up` do compose recria sem o overlay do host agent e perde imagem fixada, GPU e perfil.
  Para gerenciados (e para o `worker-live`), re-registre o host (`--use-built-image` se a
  imagem mudou, ver "Serviços gerenciados: re-registrar") e depois rode `apply_profile`.
- Override fora do `COMPOSE_FILE`: se o arquivo existe e o `.env` define `COMPOSE_FILE` sem
  incluí-lo, o script avisa (`compose ignores it`) e segue. Só avisa, nunca falha.
- Mudança de overlay feita pelo host agent (perfis aplicados): use o engine control.
