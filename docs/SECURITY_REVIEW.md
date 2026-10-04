# Revisão de segurança — Ingestify

Data: 2026-09-28. Base: estado atual do worktree, commit `ec8989c` mais alterações locais ainda não commitadas. Método: inspeção estática dos endpoints FastAPI, autenticação/autorização, fontes externas, workers, armazenamento, frontend e arquivos Docker Compose. Não foi feito teste de invasão nem auditoria de dependências ou do ambiente implantado. Severidade considera uma API acessível a usuários autenticados; riscos de infraestrutura dependem da topologia real.

## Resumo e ordem de correção

| ID | Severidade | Achado | Estado |
| --- | --- | --- | --- |
| S-01 | Alta | JWT do Ingestify é enviado como credencial a Google Drive/Dropbox | Confirmado no fluxo de código |
| S-02 | Média | Criação de jobs de conversão sem limite por usuário ou concorrência | Confirmado no código; impacto depende da capacidade implantada |
| S-03 | Média | Limite de login/cadastro usa IP do proxy e falha aberto se Redis cair | Confirmado no código; impacto depende de proxy/Redis |
| S-04 | Média | Elasticsearch/Redis sem autenticação obrigatória e conexões internas sem TLS | Confirmado na configuração; exposição depende da rede implantada |

### S-01 — Confusão de credenciais nas fontes Google Drive e Dropbox

**Evidência.** `POST /convert` usa `Authorization: Bearer` para autenticar o usuário via `get_current_active_user` e também o exige para `gdrive`/`dropbox` ([routes.py](../backend/api/routes.py#L671), [auth.py](../backend/shared/auth.py#L228)). A mesma string é copiada para `task_kwargs["auth_token"]` ([routes.py](../backend/api/routes.py#L870)), serializada na chamada ao Celery e passada ao handler ([tasks.py](../backend/workers/tasks.py#L173)). Os handlers usam esse valor como token do Google/Dropbox ([sources.py](../backend/workers/sources.py#L212), [sources.py](../backend/workers/sources.py#L271)).

**Impacto.** Qualquer requisição a `/convert` com JWT Bearer coloca o JWT no argumento da task/broker, mesmo quando a fonte não precisa dele. Com `source_type=gdrive` ou `dropbox`, o worker ainda o apresenta ao SDK do provedor externo. O provedor deve rejeitar o token, portanto a função tende a falhar; ainda assim, a credencial da aplicação sai do seu domínio. Um token OAuth do provedor colocado no mesmo header não autentica no Ingestify, então o contrato documentado pelo endpoint não funciona. Não há evidência de que o token seja persistido no MySQL; a exposição confirmada é no argumento da task e na chamada ao SDK.

**Correção.** Separar rigorosamente as credenciais: `Authorization` deve servir somente ao Ingestify; aceitar a credencial do provedor em campo próprio, com política explícita de armazenamento e expiração. Evitar colocar tokens em argumentos duráveis do Celery; usar referência a segredo com acesso restrito e descarte após o job. Até a correção, desabilitar essas duas fontes em ambientes que não aceitam essa exposição. Adicionar teste que prove que o JWT da aplicação nunca chega ao handler do provedor.

### S-02 — Jobs sem orçamento por usuário

**Evidência.** Os endpoints autenticados `/upload`, `/convert`, `/transcribe` e `/images/*` recebem trabalho e enfileiram processamento ([routes.py](../backend/api/routes.py#L60), [routes.py](../backend/api/routes.py#L351), [routes.py](../backend/api/routes.py#L671), [image_routes.py](../backend/api/image_routes.py#L618)). Há limites de tamanho para arquivos e imagens, mas não aparece cota por usuário, limite de jobs ativos, nem limite de requisições nesses endpoints. Os limites de Redis em [auth_routes.py](../backend/api/auth_routes.py#L25) e [auth_routes.py](../backend/api/auth_routes.py#L95) protegem apenas cadastro/login. O Compose configura cinco réplicas do worker de conversão ([docker-compose.yml](../docker-compose.yml#L209)).

**Impacto.** Um usuário com conta válida pode ocupar fila, CPU/GPU, armazenamento temporário e serviços de terceiros com muitos jobs, degradando os demais usuários e elevando custo. O tamanho máximo por arquivo limita uma entrada, não o número de entradas ou páginas processadas.

**Correção.** Aplicar limite distribuído por identidade a criação de jobs, cota de jobs pendentes/ativos e orçamento de armazenamento/tempo; contabilizar também API keys do mesmo usuário. Definir comportamento de 429 e medir fila, consumo por usuário e rejeições. Testar concorrência e liberação de cota em falha/cancelamento.

### S-03 — Rate limit por IP do par imediato e indisponibilidade do Redis

**Evidência.** [rate_limit.py](../backend/shared/rate_limit.py#L21) usa `request.client.host`; o código não interpreta cabeçalhos de encaminhamento nem define proxies confiáveis. Atrás de proxy reverso sem tratamento confiável de proxy no servidor ASGI, esse valor é o endereço do proxy, compartilhado por todos os clientes. O limite padrão de login é 10/minuto/IP e o de cadastro é 5/hora/IP ([config.py](../backend/shared/config.py#L267)); ambos são aplicados em [auth_routes.py](../backend/api/auth_routes.py#L46) e [auth_routes.py](../backend/api/auth_routes.py#L127). Falhas de Redis permitem a requisição prosseguir ([rate_limit.py](../backend/shared/rate_limit.py#L52)).

**Impacto.** Numa implantação atrás de proxy, alguns clientes podem consumir a cota de todos, gerando 429 para usuários legítimos. Durante falha do Redis, esses controles deixam de limitar tentativas. O bloqueio adicional por conta permanece dependente do mesmo Redis. O risco exato deve ser confirmado na topologia do deploy; sem proxy, o IP do par é o do cliente direto.

**Correção.** Configurar middleware de proxy com lista de proxies confiáveis e validar o IP efetivo no ponto de entrada; nunca confiar em `X-Forwarded-For` vindo diretamente da internet. Separar cotas por IP e conta, e adicionar proteção no ingress que continue funcionando se o Redis estiver indisponível. Testar o comportamento através do proxy real.

### S-04 — Confiança excessiva na rede interna do Compose

**Evidência.** Elasticsearch sobe com `xpack.security.enabled=false` ([docker-compose.yml](../docker-compose.yml#L18)); Redis permite senha vazia ([docker-compose.yml](../docker-compose.yml#L47)); MinIO exige credenciais, mas usa `MINIO_SECURE=false` para clientes da aplicação ([docker-compose.yml](../docker-compose.yml#L122), [config.py](../backend/shared/config.py#L200)). As portas de Redis/Elasticsearch/MinIO estão vinculadas a `127.0.0.1`, o que reduz exposição externa pelo host, mas os serviços continuam acessíveis na rede Compose. `docker-compose.prod.yml` não altera essas propriedades. O backend também tem `elasticsearch_verify_certs=False` por padrão ([config.py](../backend/shared/config.py#L195)).

**Impacto.** Outro processo com acesso à rede interna ou ao host pode ler ou alterar dados e filas; tráfego interno ou entre hosts não tem proteção criptográfica nessa configuração. Isto **não** prova que as portas estejam públicas na implantação atual. A severidade aumenta se a rede Compose for compartilhada, se algum serviço for publicado por outro arquivo ou se os serviços estiverem em hosts diferentes.

**Correção.** Para produção, exigir autenticação de Elasticsearch e Redis, habilitar TLS e validação de certificados quando o tráfego atravessar fronteiras de confiança, restringir redes e privilégios por serviço e remover defaults inseguros dos arquivos de produção. Verificar a configuração efetiva com `docker compose config` e uma inspeção de portas/rede do ambiente antes de declarar mitigado.

## Controles observados e limites do review

- A autorização dos endpoints de job passa por `get_owned_job`, que exige correspondência positiva do dono e responde 404 para recurso alheio; as rotas administrativas usam `require_admin` ([deps.py](../backend/api/deps.py#L140), [admin_routes.py](../backend/api/admin_routes.py#L37)). O review antigo em [CODE_REVIEW.md](CODE_REVIEW.md) descreve versões anteriores desses controles e não deve ser usado como estado atual.
- O download de URL pública valida IPs, redirecionamentos e fixa o endereço de conexão, com testes próprios de SSRF ([sources.py](../backend/workers/sources.py#L50), [test_url_source_ssrf.py](../backend/tests/test_url_source_ssrf.py)).
- Uploads passam por sanitização de nome e limite de bytes; buckets MinIO têm política pública removida, e o PDF de página requer autenticação antes da URL assinada ([utils.py](../backend/shared/utils.py#L25), [minio_client.py](../backend/shared/minio_client.py#L78), [routes.py](../backend/api/routes.py#L2151)).
- O `callback_url` existe no schema e há um helper de webhook sem validação de destino, mas o endpoint `/convert` atual não o recebe nem o envia à task. Portanto, **não** é um SSRF explorável por essa rota no estado revisado. Os adapters de crawler fazem requisições sem a proteção de IP do downloader de URL, mas não há rota de crawler registrada em `api/main.py`; devem ser revisados antes de ativação.
- O frontend persiste JWT em `localStorage` ([auth.ts](../frontend/lib/store/auth.ts#L20)). Isso aumenta o impacto de eventual XSS, mas este review não confirmou um ponto de injeção no frontend. Migrar para sessão com cookie `HttpOnly` requer projeto de proteção CSRF e não é correção isolada.

## Verificação

Este documento foi confrontado com o código do worktree. A suíte focada (`tests/test_url_source_ssrf.py`, `test_deps_authorization.py`, `test_admin_authz.py`, `test_login_rate_limit.py`) foi executada em 2026-09-28 no container `ingestify-api` com `pytest 7.4.3`: **63 testes passaram** (`docker exec ingestify-api python -m pytest -q tests/test_url_source_ssrf.py tests/test_deps_authorization.py tests/test_admin_authz.py tests/test_login_rate_limit.py`). Foram conferidos os hashes dos quatro arquivos de teste e dos módulos principais envolvidos; correspondiam aos arquivos do worktree. Houve 106 avisos de depreciação, sem falhas. O Python do host continua sem as dependências do projeto, mas o container já as inclui. A configuração efetiva de produção não foi inspecionada. Os achados não alegam exploração verificada em produção.
