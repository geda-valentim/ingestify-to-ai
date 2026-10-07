# Tunnel de desenvolvimento — dev.ingestify.ai

O hostname publica o frontend em `/` e a API em `/api`, com TLS terminado pelo
Cloudflare. Um Caddy exclusivo do Ingestify remove `/api` antes de encaminhar para
o FastAPI. O `root_path=/api` preserva as URLs do Swagger e do WebSocket live.

A criação do tunnel não publica automaticamente o hostname. Confirme que o
DNS e o HTTPS público funcionam antes de trocar o frontend em uso pela versão
com a URL pública da API. Enquanto aguarda autenticação de DNS, mantenha a API
e o frontend com a configuração de acesso local.

| URL pública | Destino |
|---|---|
| `https://dev.ingestify.ai/` | Frontend |
| `https://dev.ingestify.ai/docs` | Guia PT/EN do produto |
| `https://dev.ingestify.ai/api/docs` | Swagger |
| `https://dev.ingestify.ai/api/health` | Saúde da API |
| `https://dev.ingestify.ai/api/transcribe/live/sessions/{id}/stream` | WebSocket da API, quando o piloto estiver ativado |

O proxy só publica front e API. Redis, Elasticsearch, MySQL, workers e console
MinIO não têm ingress no tunnel. As prévias de PDF usam o endpoint autenticado
`/api/jobs/{id}/pages/{n}/pdf/content`, que transmite o arquivo do MinIO pela API.
O front envia `Authorization` à API; assim a prévia funciona em HTTPS sem expor
o MinIO da LAN. A URL assinada de acesso direto continua disponível no JSON de
`/pdf` para clientes com acesso à rede local. O tunnel não ativa o piloto live.

## Configuração neste servidor

- Tunnel: `ingestify-dev-slave01`.
- Connector: `cloudflared-ingestify-dev.service`, usuário `ingestify-tunnel`.
- Configuração real: `/var/lib/cloudflared-ingestify/config.yml`.
- Credencial do tunnel: JSON privado em `/var/lib/cloudflared-ingestify/`.
- Proxy: container `ingestify-tunnel-proxy`, porta host `127.0.0.1:8180`.
- Métricas/readiness do connector: `127.0.0.1:49313`.
- O certificado de administração de DNS fica fora do Git, no home desse usuário.
- Os serviços do Cloudflare de outros projetos usam unidades separadas.

No `.env` privado, configure `TUNNEL_HOSTNAME=dev.ingestify.ai`,
`NEXT_PUBLIC_API_URL=https://dev.ingestify.ai/api`, acrescente
`https://dev.ingestify.ai` a `CORS_ALLOWED_ORIGINS` e use como `TUNNEL_PROXY_IP`
um IP livre dentro da sub-rede real de `ingestify-network`:

```bash
docker network inspect ingestify-network --format '{{json .IPAM.Config}}'
```

O Compose reserva esse IP para o proxy, e o FastAPI confia nos headers apenas
desse endereço. O Uvicorn 0.24 instalado não interpreta CIDR nessa allowlist.
Confira os endpoints existentes antes de escolher o IP e mantenha-o reservado.
Configure também `TUNNEL_CONNECTOR_IP` com o gateway dessa rede: é o IP visto
pelo Caddy quando o connector do host acessa a porta loopback publicada. Apenas
essa origem pode fornecer `CF-Connecting-IP`; o proxy encaminha o IP real ao
FastAPI para preservar os limites de autenticação por cliente.
O frontend recebe a
URL pública durante o build; mudar somente a variável em runtime não a altera.

## Subir ou atualizar

O overlay de tunnel deve ser o **último**. Se também usar o overlay live, coloque
`docker-compose.live.yml` antes dele para manter `root_path`, limites WebSocket e
headers de proxy juntos. Não ative live sem os gates do [guia](../features/live-transcription.md).

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  -f docker-compose.override.yml -f docker-compose.tunnel.yml \
  --profile infra --profile engines build frontend

docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  -f docker-compose.override.yml -f docker-compose.tunnel.yml \
  --profile infra --profile engines up -d --no-build --no-deps api frontend tunnel-proxy

sudo systemctl restart cloudflared-ingestify-dev.service
```

No piloto live deste servidor, use todos os overlays:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  -f docker-compose.override.yml -f docker-compose.live.yml \
  -f docker-compose.tunnel.yml --profile infra --profile engines --profile live \
  up -d --no-build --no-deps worker-live

# Espere o worker aquecer e ficar saudável antes de habilitar a API no .env.
docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  -f docker-compose.override.yml -f docker-compose.live.yml \
  -f docker-compose.tunnel.yml --profile infra --profile engines --profile live \
  up -d --no-build --no-deps api frontend tunnel-proxy

sudo systemctl enable --now docker.service mariadb.service cloudflared-ingestify-dev.service
```

Docker restaura os containers com `restart: unless-stopped` no boot, incluindo
frontend, API, proxy e worker live. Containers parados manualmente continuam
parados. A configuração foi verificada sem reiniciar a máquina.

Não substitua estes comandos por um `compose up` que omita o overlay: isso
retiraria o prefixo da API usado pela versão publicada do frontend.

## Instalar o connector em outro servidor

Use `deploy/cloudflare/config.example.yml` e a unidade systemd em
`deploy/cloudflare/cloudflared-ingestify-dev.service` como modelos. Instale o
binário `cloudflared`, crie o usuário de serviço com home
`/var/lib/cloudflared-ingestify` e permissão `0700`, crie um tunnel próprio e
substitua `TUNNEL_UUID` nos dois campos do arquivo de configuração. A credencial
JSON deve ser legível apenas pelo usuário do connector (`0400`). A configuração
real pode usar `0640`; nunca salve o certificado ou o JSON de credenciais no repo.

Para autenticar DNS, rode `cloudflared tunnel login` como esse usuário e selecione
**ingestify.ai**. Um certificado obtido para outro domínio pode criar tunnels
na mesma conta, mas não concede acesso ao DNS de `ingestify.ai`. Verifique o
registro `dev` existente antes de substituí-lo. Com o certificado correto:

```bash
sudo runuser -u ingestify-tunnel -- cloudflared tunnel route dns ingestify-dev-slave01 dev.ingestify.ai
sudo cloudflared --config /var/lib/cloudflared-ingestify/config.yml tunnel ingress validate
sudo install -m 0644 deploy/cloudflare/cloudflared-ingestify-dev.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared-ingestify-dev.service
```

O DNS precisa de um CNAME **proxied** para `<UUID>.cfargotunnel.com`. O connector
deve registrar conexões antes de testar a URL pública.

## Verificação e rollback

```bash
systemctl is-active cloudflared-ingestify-dev.service
curl --fail http://127.0.0.1:49313/ready
curl --fail -H 'Host: dev.ingestify.ai' http://127.0.0.1:8180/api/health
curl --fail https://dev.ingestify.ai/api/health
curl --fail https://dev.ingestify.ai/api/openapi.json
```

O OpenAPI deve declarar `servers: [{"url":"/api"}]`, e o Swagger deve carregar
`/api/openapi.json`. No navegador, valide HTTPS, ausência de mixed content e que
as chamadas de login apontam para `https://dev.ingestify.ai/api/auth/login`.

Com a live habilitada, o POST autenticado deve retornar `201` com URL `wss://`
em `/api/transcribe/live/sessions/{id}/stream`. Confirme o `worker-live` saudável
antes de testar áudio. A finalização também precisa de escrita no Elasticsearch:
um `/health` saudável não comprova que os índices aceitam gravação. Antes de
builds CUDA, confira espaço no disco (`df -h /var/lib/docker`); a proteção
`read_only_allow_delete` pode ser aplicada quando o disco cruza o flood-stage.
Mantenha os limites de proteção e libere espaço antes de recuperar a escrita.

O `/health` consulta Redis, Elasticsearch e Celery de forma síncrona e deve
executar no thread pool do FastAPI. Executar essas consultas no loop de eventos
bloqueia o repasse de áudio durante os checks automáticos e pode causar
`LIVE_BACKPRESSURE` ou `LIVE_FRAME_RATE`, mesmo com o decoder ocioso.

Para desligar o acesso público, pare `cloudflared-ingestify-dev.service`. Isso
não reinicia os tunnels de outros projetos. Para voltar ao acesso LAN, restaure
o `.env` do backup privado, recompile o frontend e recrie API/frontend sem o
overlay de tunnel; remova somente `tunnel-proxy` se ele não for mais utilizado.
Não remova volumes de armazenamento durante o rollback.

Referências: [tunnel local e DNS](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/create-local-tunnel/),
[FastAPI atrás de proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/),
[Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
