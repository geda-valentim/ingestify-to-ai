# Habilitar o controle de engines

O merge mantém `ENGINE_CONTROL_ENABLED=false`. `CONTROL_NOT_ENABLED` indica
que a API ainda está com esse valor; habilitar exige o bootstrap abaixo.

1. Preserve os manifests, perfis e a escala usados pela instalação e acrescente
   `docker-compose.engine-control.yml`. Runner e watchdog usam o perfil
   `engine-control`; os serviços remotos existentes usam `engines`.
   Persista essa combinação em `COMPOSE_FILE` e `COMPOSE_PROFILES` no `.env`,
   sem remover os overlays de GPU, portas, live ou tunnel já usados.
2. Execute a migração explícita no ambiente da API:

   ```bash
   docker compose exec -T api python -c 'from shared.database import engine; from shared.engine_control.migration import upgrade; upgrade(engine)'
   ```

   A migração também acrescenta `maintenance_operation_id` e seu índice em
   instalações que criaram as tabelas durante o desenvolvimento da spec 0007.
   Preserva dados, operações em voo e gates de admissão. Rode-a de novo em instalações
   existentes ao atualizar (é idempotente): ela acrescenta índices novos às tabelas que já
   existem, como `ix_control_admissions_resource_released`, usado pela política de ociosidade.
   O índice é criado online, mas espera um lock de metadados curto; a migração desiste depois
   de 30 s em vez de enfileirar a admissão das tasks atrás de uma transação longa. Se ela
   falhar com `Lock wait timeout exceeded`, nada ficou pela metade: rode de novo fora de pico.
   Rollback do índice: nada a fazer (o código anterior convive com ele).
3. Registre o host com `scripts/register_engine_host.py`: forneça `--host-id`,
   `--api-url`, todos os manifests efetivos, os serviços permitidos e os UUIDs
   das GPUs. Use loopback ou HTTPS verificado para a API. Cada serviço precisa
   de uma imagem instalada; serviços parados podem declarar `image` no overlay
   local para que o registro resolva o digest sem iniciá-los. O registro não
   imprime tokens e recusa sobrescrever uma identidade existente.
   Serviços com profile (`worker-live`: `live`; `worker-dispatch` e `worker-remote`:
   `engines`) são renderizados com o próprio profile, mesmo que o `COMPOSE_PROFILES`
   do `.env` não o inclua. Os demais seguem o `COMPOSE_PROFILES` do `.env`, como no
   `make deploy` (que roda sob `env -i`): qualquer `COMPOSE_*` exportado no shell
   (`COMPOSE_PROFILES`, `COMPOSE_ENV_FILES`…) é ignorado pelo registro. Com
   `--use-built-image`, um serviço que, depois de juntar os manifests, fica sem `build:`
   (por exemplo, declarado só num override local, ou com `build: !reset`) é recusado,
   porque o deploy não construiu imagem para ele. Um `image:` somado a um serviço com
   `build:` continua valendo como a tag construída. Também é recusado, com a flag, um
   serviço com profile fora do `COMPOSE_PROFILES` (exceto o `worker-live`, que o
   `BUILD_LIVE=1` constrói), porque o deploy só constrói o que esse profile ativa: ponha o
   profile no `COMPOSE_PROFILES` do `.env` e rode `make deploy FORCE_REBUILD=1` (o `.env` não
   é versionado, então um deploy simples pode não detectar mudança e não construir nada; o
   `FORCE_REBUILD=1` reconstrói tudo, recria os não gerenciados em execução e reconstrói o
   frontend), ou registre sem a flag. O registro não tem como saber se houve deploy depois
   da mudança: sempre que mexer no `COMPOSE_PROFILES` (inclusive no passo 1), rode
   `make deploy FORCE_REBUILD=1` antes de usar `--use-built-image`. Do mesmo modo, sem
   `BUILD_LIVE=1` antes, a flag grava a imagem existente do `worker-live`. Um override local com `depends_on`
   num serviço de outro profile pode fazer o render com `--profile` falhar.
4. O arquivo de identidades montado na API contém hashes dos tokens. Ele fica
   sob controle de root, mas precisa ser legível pelo usuário da API. Para a
   imagem padrão, que executa como UID/GID `10001`:

   ```bash
   chgrp 10001 secrets/engine_host_identities.json
   chmod 0640 secrets/engine_host_identities.json
   ```

   Confirme o GID da imagem se usar outro usuário. O registro com o token
   original em `/etc/ingestify/engine-host.json` permanece root, modo `0600`.
5. Configure `ENGINE_CONTROL_ENABLED=true` no `.env`. Garanta imagens para
   `worker-control` e `worker-control-watchdog`: construa esses serviços ou
   declare no overlay local a imagem instalada de `worker-remote`.
   Recrie a API e os workers de conteúdo com o overlay de controle, preservando
   as réplicas e aguardando o trabalho em voo terminar. Suba runner e watchdog
   com `--no-deps`; não ative áudio/live apenas para registrar suas imagens.
6. Instale e habilite o agente:

   ```bash
   install -m 0644 deploy/systemd/ingestify-engine-host-agent.service /etc/systemd/system/ingestify-engine-host-agent.service
   systemctl daemon-reload
   systemctl enable --now ingestify-engine-host-agent.service
   ```

   Ajuste o caminho do script na unit se o checkout estiver em outro diretório.
   O agente precisa dos diretórios de registro e estado criados pelo bootstrap.
7. Verifique um heartbeat recente do host, a fila `ingestify-engine-control`
   consumida pelo runner e o heartbeat `engine-control:watchdog` no Redis.
   Com uma sessão de admin, capabilities, runtime-profile, runtime-status e
   histórico de operações devem responder `200`, inclusive pelo proxy público.
   Atualize a página e selecione o host registrado ao salvar o perfil desejado.

O bootstrap habilita a infraestrutura de controle. A disponibilidade de ações
continua dependente do perfil, credenciais e capacidades do adapter. Os gates
de qualificação da spec 0007
continuam aplicáveis, inclusive aos perfis WhisperX.

## Diagnosticar `HOST_AGENT_NOT_READY`

A página da engine e a API dizem há quanto tempo o host não envia heartbeat.
O motivo fica no journal do agente, que registra o tipo, o código e uma dica
(nunca o token):

```bash
journalctl -u ingestify-engine-host-agent -n 50 --no-pager
```

- `REGISTERED_MANIFEST_CHANGED`: algum arquivo compose registrado mudou desde o
  registro (deploy, overlay novo, edição do `.env` que altera o compose). O
  agente recusa operar até o host ser registrado de novo (abaixo).
- `HTTP 403 HOST_IDENTITY_REQUIRED`: a API não reconhece o
  token. Confira se `secrets/engine_host_identities.json` está montado e
  legível pela API (passo 4) e se o host não foi rotacionado só de um lado.
- `API unreachable`: a API não responde no `--api-url` registrado.

O agente volta a registrar `Agent recovered` quando o heartbeat é aceito.

## Drenagem que termina em `DRAIN_TIMEOUT`

Durante a drenagem, o runner libera sozinho o ticket de admissão de uma task cujo
processo morreu, desde que o nó Celery que a executava responda sem ela. Dois casos
ficam sem essa prova, e a drenagem espera até o timeout:

- tickets gravados antes desta versão, com holder `task:<id>` sem pid nem nó;
- o container do worker foi recriado com a task em execução (deploy, `--force-recreate`):
  o nó antigo nunca mais responde.

O evento final da operação lista quantos tickets ficaram abertos e os holders mais
antigos. Este procedimento é **provisório**, até existir o cancelamento forçado pelo
painel. Ele só libera um ticket com prova de que nenhum processo vivo executa aquela task.
Se qualquer passo não confirmar, não libere: recuse e tente a operação de novo mais tarde.

1. **Liste os tickets abertos** dos recursos da operação (só leitura; as chaves estão no
   plano da operação). Anote `id`, `holder` e o task id, que é o trecho entre `task:` e o
   primeiro `|`, se houver:

   ```sql
   SELECT id, resource_key, holder, created_at
   FROM engine_control_admissions
   WHERE released_at IS NULL AND resource_key IN ('<chave 1>', '<chave 2>');
   ```

2. **Liste os containers Celery vivos** da instalação, com os mesmos `-f` do registro.
   O nome do nó de cada um termina com o id curto do container (`<fila>@<id>`).
   O `worker-live` não é Celery e fica de fora:

   ```bash
   docker compose <os mesmos -f> ps --status running --format '{{.Service}} {{.ID}}' \
     | grep -E '^worker' | grep -v '^worker-live ' > /tmp/celery-containers.txt
   cat /tmp/celery-containers.txt
   ```

   Se a instalação tem workers em mais de um host, rode isto em cada host e junte as
   listas no mesmo arquivo: um container que ficou fora da lista não é cobrado no passo 3.

3. **Pergunte a todos os nós quais tasks estão ativas** e confira, para cada task id do
   passo 1, que todos os containers responderam e que nenhum a executa:

   ```bash
   # <serviço>: qualquer um da lista do passo 2 (por exemplo, worker-control)
   docker compose <os mesmos -f> exec -T <serviço> \
     celery -A workers.celery_app inspect active --json --timeout 10 > /tmp/celery-active.json
   python3 - /tmp/celery-active.json /tmp/celery-containers.txt '<task id>' <<'PY'
   import json, sys
   replies = json.load(open(sys.argv[1]))
   containers = {line.split()[1][:12] for line in open(sys.argv[2]) if line.strip()}
   answered = {node.split("@", 1)[1][:12] for node in replies}
   silent = containers - answered
   running = [n for n, tasks in replies.items() if any(t.get("id") == sys.argv[3] for t in tasks or [])]
   if silent or running:
       sys.exit(f"NÃO LIBERE: sem resposta={sorted(silent)} executando={running}")
   print("todos os containers responderam e nenhum executa a task")
   PY
   ```

   Um container que não responde (ocupado num pool `solo`, travado, broker fora) não prova
   nada: espere e repita o passo 3. Não libere com base em quanto tempo o ticket está aberto.

4. **Só com a confirmação do passo 3**, libere pelos `id` anotados no passo 1, nunca por
   chave de recurso. Confira que o número de linhas afetadas é o de tickets daquela task:

   ```sql
   UPDATE engine_control_admissions
   SET released_at = UTC_TIMESTAMP()
   WHERE id IN ('<id 1>', '<id 2>') AND released_at IS NULL;
   ```

Depois, rode a operação de novo pelo painel.

## Re-registrar o host

Use após mudar manifests compose, serviços permitidos, imagens ou GPUs. É uma
rotação deliberada: o registro antigo é substituído por um token novo.

Com `--use-built-image`, confira antes de apagar o registro que cada serviço gerenciado
aparece no render padrão (`docker compose <os mesmos -f> config --services`) ou é o
`worker-live`; senão o registro recusa e o host fica sem registro até restaurar o backup
(veja abaixo).

```bash
systemctl stop ingestify-engine-host-agent
stamp=$(date +%Y%m%d%H%M%S)
cp -p /etc/ingestify/engine-host.json /etc/ingestify/engine-host.json.$stamp
cp -p secrets/engine_host_identities.json secrets/engine_host_identities.json.$stamp
rm /etc/ingestify/engine-host.json
# remova só a entrada deste host, mantendo modo e grupo do arquivo
python3 - <<'PY'
import json
path, host = "secrets/engine_host_identities.json", "SEU_HOST_ID"
with open(path, "r+") as f:  # reescreve no lugar: mesmo inode, modo e grupo
    data = json.load(f)
    data.pop(host, None)
    f.seek(0); f.write(json.dumps(data)); f.truncate()
PY
python3 scripts/register_engine_host.py <os mesmos argumentos do registro original>
systemctl start ingestify-engine-host-agent
```

Se o registro falhar (por exemplo, uma recusa do `--use-built-image`), restaure o anterior e
volte o agente: `cp -p /etc/ingestify/engine-host.json.$stamp /etc/ingestify/engine-host.json`,
`cp -p secrets/engine_host_identities.json.$stamp secrets/engine_host_identities.json` (o `cp`
sobre o arquivo existente mantém o inode montado na API) e
`systemctl start ingestify-engine-host-agent`.

Use exatamente os mesmos `--host-id`, `--api-url`, `--manifest`, `--service`
e `--gpu-uuid` do registro original (os perfis vinculados apontam para o
`host_id`; os valores anteriores estão no backup `/etc/ingestify/engine-host.json.$stamp`). O script valida o JSON, prepara o conteúdo num temporário
no mesmo diretório (fsync), guarda o conteúdo anterior em `<arquivo>.bak` e reescreve o
arquivo de identidades no lugar: mantém o
inode (a API o monta como arquivo único; um `mv`/rename deixaria o container
lendo a versão antiga), o modo e o grupo (por exemplo `0640 root:10001`). Se o
arquivo for novo, ele nasce `0600`; passe `--identities-group 10001` para criá-lo já
`0640` com o grupo da API, ou aplique o passo 4. Não edite esse arquivo com ferramentas que
substituem o arquivo (por exemplo `sed -i`). A API relê as identidades a cada requisição do host; não é preciso
reiniciá-la. Se o inventário do host mudou (GPU ou manifests), vincule de novo
o perfil de execução das engines locais (`PROFILE_INVENTORY_CHANGED`).

Se o registro falhar, ele não deixa arquivo pela metade: um `engine-host.json` criado nesta
execução é removido quando a identidade não chegou ao arquivo de identidades, e o rerun
passa. Nos outros casos o config fica e o erro diz o que fazer:
- a identidade já entrou no arquivo vivo: o config é a única cópia do token; o registro está
  feito, inicie o agente (depois de um erro de E/S, confira os dois arquivos antes);
- esta execução começou a reescrever o arquivo vivo e ele ficou com JSON inválido: restaure-o
  de `<arquivo>.bak` com `cp` (mantém o inode montado na API), remova o `engine-host.json` e
  rode de novo. Só nesse caso o `.bak` é desta execução;
- não deu para reler o arquivo de identidades: confira-o à mão, **sem** restaurar um backup
  antigo (ele revogaria os hosts registrados depois dele). Se o `host_id` estiver lá, o
  registro está feito; se não, remova o `engine-host.json` e rode de novo.

No re-registro do procedimento acima, a restauração dos `.$stamp` desfaz a rotação inteira
(config e identidades daquele momento); a orientação do erro vale para o registro novo.
`--identities-group` só vale para um arquivo novo.
