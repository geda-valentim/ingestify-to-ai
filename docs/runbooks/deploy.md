# Deploy de produção (`make deploy`)

`make deploy` chama `scripts/deploy.sh` sob `env -i` (o Makefile exporta o `.env` e
`REDIS_HOST ?= localhost` para os alvos `check-*`; um compose herdando isso já apontou
containers para localhost). O compose lê `COMPOSE_FILE`/`COMPOSE_PROFILES` do `.env` sozinho.

## Fluxo

1. Exige a branch `main` e aborta, listando os arquivos, se houver mudança local em arquivo
   rastreado que o pull tocaria.
2. `git pull --ff-only`.
3. Detecta mudanças desde o **último deploy bem-sucedido** (`.git/deploy-last-success`, nunca
   rastreado). Sem o arquivo, usa o HEAD anterior ao pull e avisa.
4. Por categoria, só em serviços de `compose config --services` e **só os que estão rodando**:
   - requirements/`*.lock`, `docker/` (Dockerfiles, `entrypoint.sh`) ou scripts copiados nas
     imagens: `build` + `up -d --no-build --no-deps --scale <svc>=<rodando>`;
   - `docker-compose*.yml`: `up -d --no-build --no-deps` dos serviços não gerenciados;
   - só código em `backend/`: `docker restart` dos containers em execução (inclui gerenciados);
   - `frontend/`: `build`, e `up` só se estiver rodando;
   - `worker-live` (código dentro da imagem): só `build`.
5. Health: porta de `compose port api 8000`, `GET /health` com HTTP 200 e `"status":"healthy"`
   (40 tentativas x 3 s). Só então grava `.git/deploy-last-success`.

## Regras

- Nunca sobe serviço parado nem remove réplicas (`--scale` só com contagem > 0; se `ps`
  falhar, aborta).
- "Gerenciado" é o serviço com overlay `/var/lib/ingestify-engine-agent/<svc>.json` (ignora
  `observe-` e `state.json`); a lista estática (`worker`, `worker-audio`, `worker-vision`,
  `worker-live`) só vale se esse diretório não for legível. O host agent aplica esses serviços
  com overlay (imagem fixada, GPU, perfil) fora do `COMPOSE_FILE`, então eles nunca recebem `up`:
  - mudou só código montado de `backend/`: os containers gerenciados **em execução** recebem
    `docker restart` (não recria; mantém o overlay e carrega o código novo);
  - mudou imagem ou compose: só `build`, e o script avisa para reaplicar o perfil pelo engine
    control (operação `apply_profile`/`restart` na API/UI admin);
  - `worker-live` (código dentro da imagem) só recebe `build`.
  Serviços parados de propósito continuam parados.
- Antes de reiniciar `worker`/`worker-audio` avisa, best-effort, se há tarefas ativas.
- Não detectável: mudança em `docker-compose.override.yml` ou `.env` (não rastreados). Depois
  de editá-los rode `docker compose up -d --no-build --no-deps <svc>` nos serviços afetados.

## Opções e falhas

- `make deploy DRY_RUN=1` imprime as ações de pull/build/up/restart sem executá-las.
- `make deploy FORCE_REBUILD=1` reconstrói tudo (use após rollback ou sem marcador).
- Em falha o script imprime o estágio, o HEAD atual/anterior e o último deploy bom. Repetir:
  `make deploy` (a detecção recomeça do último deploy bom). Voltar: `git reset --hard
  <último deploy bom>` na `main` e `make deploy FORCE_REBUILD=1`.
