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
   Preserva dados, operações em voo e gates de admissão.
3. Registre o host com `scripts/register_engine_host.py`: forneça `--host-id`,
   `--api-url`, todos os manifests efetivos, os serviços permitidos e os UUIDs
   das GPUs. Use loopback ou HTTPS verificado para a API. Cada serviço precisa
   de uma imagem instalada; serviços parados podem declarar `image` no overlay
   local para que o registro resolva o digest sem iniciá-los. O registro não
   imprime tokens e recusa sobrescrever uma identidade existente.
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
de qualificação da [spec 0007](../specs/0007-operacao-de-engines-pelo-admin.md)
continuam aplicáveis, inclusive aos perfis WhisperX.
