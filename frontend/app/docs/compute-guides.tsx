import Link from "next/link";
import { CodeBlock } from "./code-block";
import { DOCS_API_URL } from "./config";
import { DOCS_TOPICS, docsHref, type DocsLang } from "./topics";

type Text = [pt: string, en: string];
type Rows = Text[][];
type Part = {
  title: Text;
  paragraphs?: Text[];
  head?: Text[];
  rows?: Rows;
  steps?: Text[];
  code?: string;
};
type Guide = {
  title: Text;
  intro: Text;
  parts: Part[];
  endpoints: [string, string, Text][];
  related: string[];
};
const x = (pt: string, en: string): Text => [pt, en];
const requirementHead = [
  x("Requisito", "Requirement"),
  x(
    "Comportamento e condição de aceitação",
    "Behavior and acceptance condition",
  ),
];

// Requirements describe the installed contracts, not promises of provider support.
const guides: Record<string, Guide> = {
  engines: {
    title: x(
      "Engines: recursos, requisitos e aplicações",
      "Engines: features, requirements and use cases",
    ),
    intro: x(
      "Uma engine define onde uma feature executa. Compute reúne conexões, capacidade, rotas, orçamento, saúde e controle do runtime. Este guia descreve os contratos implementados nas specs 0003, 0007 e 0009, conferidos em 06/10/2026.",
      "An engine defines where a feature runs. Compute combines connections, capacity, routing, budgets, health and runtime control. This guide describes implemented contracts from specs 0003, 0007 and 0009, checked on October 6, 2026.",
    ),
    parts: [
      {
        title: x("Conceitos e telas", "Concepts and screens"),
        head: [
          x("Recurso", "Resource"),
          x("Responsabilidade", "Responsibility"),
        ],
        rows: [
          [
            x("Engine / conexão", "Engine / connection"),
            x(
              "Executor local criado pelo sistema ou conta Modal criada pausada. /admin/engines lista saúde, capacidade, em voo e orçamento; /admin/engines/{id} reúne configuração e operações.",
              "System-created local executor or a Modal account created paused. /admin/engines lists health, capacity, in-flight work and budget; /admin/engines/{id} contains configuration and operations.",
            ),
          ],
          [
            x("Binding de capacidade", "Capacity binding"),
            x(
              "Configuração por feature: workers, executions_per_worker, CPU e gpu_ref local ou gpu_type remoto. Capacidade declarada = workers × executions_per_worker.",
              "Per-feature settings: workers, executions_per_worker, CPU and local gpu_ref or remote gpu_type. Declared capacity = workers × executions_per_worker.",
            ),
          ],
          [
            x(
              "Perfil de execução / modelo aprovado",
              "Execution profile / approved model",
            ),
            x(
              "Perfil é uma revisão reutilizável de runtime em /admin/execution-profiles. Modelo aprovado é uma entrada do catálogo instalado; um papel em /admin/access concede permissões, não escolhe modelos.",
              "A profile is a reusable runtime revision in /admin/execution-profiles. An approved model is an installed catalog entry; a role in /admin/access grants permissions rather than choosing models.",
            ),
          ],
          [
            x("Rota / backlog / ledger", "Route / backlog / ledger"),
            x(
              "/admin/routing prioriza engines por feature. Backlog SQL guarda itens pendentes; ledger registra cada tentativa, reserva e custo. /admin/status mostra o despachante e workers.",
              "/admin/routing prioritizes engines per feature. SQL backlog stores pending items; the ledger records each attempt, reservation and cost. /admin/status shows dispatcher and workers.",
            ),
          ],
          [
            x("GPUs e dispositivo", "GPUs and device"),
            x(
              "/admin/gpus mostra declaração, detecção e VRAM. Binding legado não muda DEVICE/WHISPER_DEVICE ou reservas Docker; o controle gerenciado aplica o snapshot ao serviço registrado.",
              "/admin/gpus shows declared and detected GPUs and VRAM. A legacy binding does not change DEVICE/WHISPER_DEVICE or Docker reservations; managed control applies the snapshot to a registered service.",
            ),
          ],
        ],
      },
      {
        title: x("Adapters e compatibilidade", "Adapters and compatibility"),
        head: [
          x("Adapter", "Adapter"),
          x("Features e aplicação", "Features and use case"),
          x("Condições atuais", "Current conditions"),
        ],
        rows: [
          [
            x("local", "local"),
            x(
              "transcription → worker-audio; document_conversion → worker; vision → worker-vision; live-transcription → worker-live.",
              "transcription → worker-audio; document_conversion → worker; vision → worker-vision; live-transcription → worker-live.",
            ),
            x(
              "Fila local e agente de host para controle. GPU declarada precisa de UUID registrado. Live exige CUDA, uma réplica residente e uma execução por worker.",
              "Local queue and a host agent for control. A declared GPU needs a registered UUID. Live requires CUDA, one resident replica and one execution per worker.",
            ),
          ],
          [
            x("modal", "modal"),
            x(
              "Transcrição de arquivos com transcription; execução em containers remotos e legendas parciais do arquivo enviado.",
              "File transcription using transcription; remote containers and partial captions from the uploaded file.",
            ),
            x(
              "Credenciais, identidade testada, orçamento, artifact compatível e worker-remote. Não executa Docling, visão ou captura contínua live. Concorrência remota por container: E=1.",
              "Credentials, tested identity, budget, compatible artifact and worker-remote. It does not run Docling, vision or continuous live capture. Remote per-container concurrency: E=1.",
            ),
          ],
          [
            x("AWS / GCP / Vast AI", "AWS / GCP / Vast AI"),
            x(
              "Extensão futura pela interface de adapters.",
              "Future extension through the adapter interface.",
            ),
            x(
              "Não estão registrados nesta versão. Não basta preencher um perfil: cada adapter precisa de descriptors, validação, plano, execução, observação, reconciliação, cancelamento e modelos aprovados.",
              "Not registered in this release. A profile alone is insufficient: each adapter needs descriptors, validation, planning, execution, observation, reconciliation, cancellation and approved models.",
            ),
          ],
        ],
        paragraphs: [
          x(
            "O catálogo de modelos do controle contém whisper-local, whisper-turbo-modal, docling-local, vision-local e live-local. Aprovação depende das configurações instaladas: áudio local exige faster-whisper; visão exige Florence-2 habilitado; live exige o piloto habilitado. WhisperX não está qualificado para o perfil de controle Modal. Consulte capabilities e /admin/model-profiles antes de escolher.",
            "The control model catalog contains whisper-local, whisper-turbo-modal, docling-local, vision-local and live-local. Approval depends on installed settings: local audio requires faster-whisper; vision requires enabled Florence-2; live requires the enabled pilot. WhisperX is not qualified for the Modal control profile. Read capabilities and /admin/model-profiles before choosing.",
          ),
          x(
            "AUDIO_TRANSCRIBER_PROVIDER escolhe o backend de áudio local, não uma engine. openai-api pode enviar áudio para fora mesmo em engine local; suas cobranças não entram no orçamento Modal. A captura de microfone é separada das legendas parciais de arquivos.",
            "AUDIO_TRANSCRIBER_PROVIDER selects the local audio backend, not an engine. openai-api may send audio outside the installation even on a local engine; its charges are outside the Modal budget. Microphone capture is separate from partial file captions.",
          ),
        ],
      },
      {
        title: x("Requisitos funcionais", "Functional requirements"),
        head: requirementHead,
        rows: [
          [
            x("ENG-01 · Inventário", "ENG-01 · Inventory"),
            x(
              "Listar engines e adapters permitidos, bindings, configured × alive, health e deployments. Leitura delegada e catálogos são filtrados pelo escopo; métricas desconhecidas não significam zero.",
              "List permitted engines and adapters, bindings, configured versus alive, health and deployments. Delegated reads and catalogs are scoped; unknown metrics do not mean zero.",
            ),
          ],
          [
            x("ENG-02 · Conexões", "ENG-02 · Connections"),
            x(
              "Bootstrap cria conexão Modal pausada, grava ou exclui credenciais seladas com senha atual, testa uma ou todas as conexões e registra auditoria. A API não devolve segredos; conta gerenciada respeita locks e exposição pendente.",
              "Bootstrap creates a paused Modal connection, stores or removes sealed credentials with the current password, tests one or all connections and records an audit. The API never returns secrets; managed accounts enforce locks and outstanding exposure.",
            ),
          ],
          [
            x("ENG-03 · Capacidade e VRAM", "ENG-03 · Capacity and VRAM"),
            x(
              "Validar soma das pegadas e reserva por GPU física, limites do adapter e capacidade remota do executor. GPU local e Modal aceitam E=1; binding local sem GPU pode admitir E>1. Declaração legada não escala processos.",
              "Validate footprint sums and reserve per physical GPU, adapter limits and remote executor capacity. Local GPU and Modal accept E=1; a local binding without GPU may allow E>1. Legacy declarations do not scale processes.",
            ),
          ],
          [
            x("ENG-04 · Roteamento", "ENG-04 · Routing"),
            x(
              "Aceitar passos ordenados, grupos priority/fill_first, condições de espera/backlog e spend_cap. Sem rota, manter o caminho local habitual. Rotas de documento/visão aceitam apenas local; captura live não usa feature_routes.",
              "Accept ordered steps, priority/fill_first groups, wait/backlog conditions and spend_cap. Without a route, keep the usual local path. Document/vision routes accept local only; live capture does not use feature_routes.",
            ),
          ],
          [
            x(
              "ENG-05 · Despacho e recuperação",
              "ENG-05 · Dispatch and recovery",
            ),
            x(
              "Persistir backlog FIFO e ledger por tentativa, limitar em voo, usar lease do líder e claim/heartbeat do executor. Recolocar claims abandonados, aplicar backoff e max_attempts; remover rota drena para o caminho habitual.",
              "Persist FIFO backlog and an attempt ledger, limit in-flight work, use leader leases and executor claim/heartbeat. Requeue abandoned claims, apply backoff and max_attempts; removing a route drains to the usual path.",
            ),
          ],
          [
            x("ENG-06 · Lifecycle", "ENG-06 · Lifecycle"),
            x(
              "Ativar libera novas colocações; pausar bloqueia novas e preserva trabalhos em voo; reset-health limpa falhas registradas. Estas ações de escalonamento não iniciam, drenam nem desligam containers.",
              "Activation allows new placements; pausing blocks new placements while preserving in-flight work; reset-health clears recorded failures. These scheduler actions do not start, drain or stop containers.",
            ),
          ],
          [
            x("ENG-07 · Orçamento", "ENG-07 · Budget"),
            x(
              "Admitir remoto somente se max(ledger, reportado) + reservado + estimativa couber no limite menos a margem. Aplicar período/fuso, limite por usuário quando habilitado e caps de rota; reconciliar gasto e alertar antes/esgotamento.",
              "Admit remote work only when max(ledger, reported) + reserved + estimated fits the limit less margin. Enforce period/timezone, enabled per-user limits and route caps; reconcile spend and alert near/on exhaustion.",
            ),
          ],
          [
            x(
              "ENG-08 · Qualificação e desempenho",
              "ENG-08 · Qualification and performance",
            ),
            x(
              "Conferir fingerprint do deploy e readiness, consultar benchmarks e velocidade aprendida. Benchmark CLI tem plano, amostra, teto remoto e confirmação; recommendation com --apply exige redeploy se mudar o remoto.",
              "Check deployment fingerprint and readiness, read benchmarks and learned speed. CLI benchmarks have a plan, sample, remote cap and confirmation; applying a recommendation requires redeployment when remote settings change.",
            ),
          ],
        ],
      },
      {
        title: x("Opções de rota e gasto", "Routing and spending options"),
        head: [x("Opção", "Option"), x("Efeito", "Effect")],
        rows: [
          [
            x("steps / engine_ids", "steps / engine_ids"),
            x(
              "Prioridade na ordem. fill_first preenche a conta corrente; scale_out_after_seconds controla a abertura de outra conta quando cheia.",
              "Priority follows order. fill_first fills the current account; scale_out_after_seconds controls opening another full-account alternative.",
            ),
          ],
          [
            x("when / spend_cap", "when / spend_cap"),
            x(
              "min_wait_seconds OU min_backlog habilita o passo; spend_cap limita dia/período de gasto remoto.",
              "min_wait_seconds OR min_backlog enables a step; spend_cap limits daily/period remote spending.",
            ),
          ],
          [
            x("max_attempts / on_no_engine", "max_attempts / on_no_engine"),
            x(
              "Limita tentativas e escolhe hold ou fail após fail_after_seconds. dispatcher_fallback e dispatcher_down_seconds definem o fallback com despachante indisponível.",
              "Limit attempts and choose hold or fail after fail_after_seconds. dispatcher_fallback and dispatcher_down_seconds define behavior while the dispatcher is unavailable.",
            ),
          ],
          [
            x("remote_allowed_for", "remote_allowed_for"),
            x(
              "admins ou all. Liberar all exige senha atual, limite por usuário e aviso de dados externos. A autorização de jobs não concede controle administrativo de engines.",
              "admins or all. Allowing all requires the current password, per-user limit and external-data notice. Job authorization does not grant administrative engine control.",
            ),
          ],
          [
            x(
              "limit_usd / min_remaining_usd / soft_pct",
              "limit_usd / min_remaining_usd / soft_pct",
            ),
            x(
              "Teto da conta, margem e percentual de alerta. period_tz e period_anchor_day fixam o período. Relatório ilegível pode marcar degraded; esgotamento impede novas colocações.",
              "Account cap, margin and alert threshold. period_tz and period_anchor_day define the period. An unreadable report may mark degraded; exhaustion prevents new placements.",
            ),
          ],
        ],
        paragraphs: [
          x(
            "O ledger inclui reservas, tentativas e caudas ociosas; gasto de outros sistemas aparece pela reconciliação da conta. Estimativa e max_usd não garantem o teto da fatura do provider. Configure também controles de gasto na conta. Alertas podem ir ao log e ao ENGINE_ALERT_WEBHOOK_URL, sem segredos ou conteúdo de jobs.",
            "The ledger includes reservations, attempts and idle tails; other systems' spending appears through account reconciliation. Estimates and max_usd do not guarantee a provider invoice cap. Configure account spending controls as well. Alerts can go to logs and ENGINE_ALERT_WEBHOOK_URL without secrets or job contents.",
          ),
        ],
      },
      {
        title: x(
          "Aplicações e sequência de configuração",
          "Use cases and setup sequence",
        ),
        head: [
          x("Aplicação", "Use case"),
          x("Como configurar e validar", "How to configure and verify"),
        ],
        rows: [
          [
            x("PDFs e OCR no servidor", "PDFs and OCR on the server"),
            x(
              "Perfil docling-local, document_conversion e worker; dimensione VRAM/CPU e confirme workers vivos. Rota local controla páginas em backlog; sem rota continua a fila habitual.",
              "Use docling-local, document_conversion and worker; size VRAM/CPU and confirm live workers. A local route controls queued pages; without one the usual queue remains.",
            ),
          ],
          [
            x("Rajada de transcrições", "Transcription bursts"),
            x(
              "Priorize local; adicione Modal após espera/backlog, com spend_cap. Teste conexão, valide artifact, orçamento e worker-remote antes de salvar a rota.",
              "Prioritize local; add Modal after wait/backlog thresholds with spend_cap. Test the connection and validate artifact, budget and worker-remote before saving the route.",
            ),
          ],
          [
            x("Extração de imagens", "Image extraction"),
            x(
              "vision-local no worker-vision; a rota de visão escolhe local de forma síncrona, sem backlog de visão. Capacidade indisponível produz VISION_ENGINE_UNAVAILABLE.",
              "Use vision-local on worker-vision; a vision route selects local synchronously without a vision backlog. Unavailable capacity produces VISION_ENGINE_UNAVAILABLE.",
            ),
          ],
          [
            x("Legenda de microfone", "Microphone captions"),
            x(
              "live-local no worker-live, piloto e CUDA habilitados, perfil compatível e sessão live. Não mande captura contínua para a rota Modal de arquivos.",
              "Use live-local on worker-live with the pilot and CUDA enabled, a compatible profile and a live session. Do not send continuous capture to the Modal file route.",
            ),
          ],
        ],
        steps: [
          x(
            "Bootstrap: confira /admin/gpus, dispositivos reais, imagens e serviços instalados. Para controle, conclua o registro do agente e as migrações antes de habilitar flags.",
            "Bootstrap: check /admin/gpus, actual devices, installed images and services. For control, complete agent registration and migrations before enabling flags.",
          ),
          x(
            "Crie/teste a conexão remota quando necessária; classifique o ambiente. Crie e publique o perfil, vincule à engine e execute um plano para aplicá-lo.",
            "Create/test a remote connection when needed; classify its environment. Create and publish a profile, bind it to the engine and execute a plan to apply it.",
          ),
          x(
            "Confirme observado e readiness. Configure orçamento, ativação e rota quando usar o despachante. Acompanhe fila, em voo, VRAM e custo com uma amostra representativa.",
            "Confirm observation and readiness. Configure budget, activation and routing when using the dispatcher. Monitor backlog, in-flight work, VRAM and cost using a representative sample.",
          ),
        ],
      },
      {
        title: x("Diagnóstico e limites", "Diagnostics and limits"),
        paragraphs: [
          x(
            "Compare configured × alive em /admin/status e a fila consumida pelo serviço; /health saudável não comprova que existe worker para uma feature. needs_redeploy pede artifact atualizado, unhealthy pede diagnóstico de credenciais/worker, exhausted pede revisão do orçamento e degraded pede reconciliação.",
            "Compare configured versus alive in /admin/status and the service's consumed queue; a healthy /health does not prove a worker exists for a feature. needs_redeploy requires an updated artifact, unhealthy requires credential/worker diagnosis, exhausted requires budget review and degraded requires reconciliation.",
          ),
          x(
            "Os comandos Docker e CLI continuam disponíveis para bootstrap. Com acesso granular ativo, CLI direta usa principal installation:<nome> registrado e ENGINE_INSTALLATION_PRINCIPAL_ID; não substitui a API delegada. Benchmark ainda não é uma ação implementada pelos adapters do modal de operações, mesmo constando no enum geral.",
            "Docker and CLI commands remain available for bootstrap. With granular access enabled, direct CLI uses a registered installation:<name> principal and ENGINE_INSTALLATION_PRINCIPAL_ID; it does not replace the delegated API. Benchmark is not yet an implemented action in the operation dialog's adapters, despite appearing in the general enum.",
          ),
        ],
      },
    ],
    endpoints: [
      ["GET", "/admin/engine-adapters", x("GPUs e limites", "GPUs and limits")],
      [
        "GET",
        "/admin/engine-control-adapters",
        x("Descriptors de controle", "Control descriptors"),
      ],
      [
        "GET / POST",
        "/admin/engines",
        x("Inventário / conexão bootstrap", "Inventory / bootstrap connection"),
      ],
      ["GET", "/admin/engines/{id}", x("Detalhe", "Detail")],
      [
        "GET",
        "/admin/engines/{id}/capabilities",
        x(
          "Ações, gates e features; feature opcional",
          "Actions, gates and features; optional feature",
        ),
      ],
      [
        "GET",
        "/admin/model-profiles",
        x("Modelos aprovados", "Approved models"),
      ],
      ["GET", "/admin/gpus", x("VRAM e inventário", "VRAM and inventory")],
      [
        "PUT",
        "/admin/engines/{id}/gpus",
        x("Declaração bootstrap", "Bootstrap declaration"),
      ],
      [
        "PUT / DELETE",
        "/admin/engines/{id}/features/{feature}",
        x("Binding legado bootstrap", "Bootstrap legacy binding"),
      ],
      [
        "PUT / DELETE",
        "/admin/engines/{id}/credentials",
        x(
          "Senha atual e credencial write-only",
          "Current password and write-only credential",
        ),
      ],
      [
        "POST",
        "/admin/engines/{id}/test · /admin/engines/test-all",
        x("Testes legados bootstrap", "Bootstrap legacy tests"),
      ],
      [
        "POST",
        "/admin/engines/{id}/activate · /pause · /reset-health · /reconcile",
        x("Lifecycle / gasto bootstrap", "Bootstrap lifecycle / spend"),
      ],
      [
        "PUT",
        "/admin/engines/{id}/budget",
        x("Orçamento bootstrap", "Bootstrap budget"),
      ],
      [
        "GET",
        "/admin/engines/{id}/benchmarks",
        x("Resultados por feature", "Per-feature results"),
      ],
      [
        "GET",
        "/admin/routing · /admin/engines/status",
        x(
          "Rotas, backlog e despachante; bootstrap",
          "Routes, backlog and dispatcher; bootstrap",
        ),
      ],
      [
        "PUT / DELETE",
        "/admin/routing/{feature}",
        x(
          "Atualizar / drenar rota; bootstrap",
          "Update / drain route; bootstrap",
        ),
      ],
    ],
    related: [
      "compute",
      "engine-operations",
      "execution-profiles",
      "engine-access",
      "live",
    ],
  },
  "engine-operations": {
    title: x("Operações de engines", "Engine operations"),
    intro: x(
      "O controlador transforma uma intenção em prévia revisável, operação durável e verificação do executor. Salvar configuração, permitir novas colocações e iniciar recursos são etapas distintas.",
      "The controller turns intent into a reviewable preview, durable operation and executor verification. Saving settings, allowing new placements and starting resources are distinct steps.",
    ),
    parts: [
      {
        title: x("Requisitos e dependências", "Requirements and dependencies"),
        paragraphs: [
          x(
            "ENGINE_CONTROL_ENABLED ativa a API e o runner de controle após migração. ENGINE_ACCESS_ENABLED ativa biblioteca e delegação após sua migração. Sessão JWT é obrigatória para controles; API key não substitui a sessão. Os dois flags são independentes e vêm desabilitados por padrão.",
            "ENGINE_CONTROL_ENABLED enables the control API and runner after migration. ENGINE_ACCESS_ENABLED enables the library and delegation after its migration. Controls require a JWT session; an API key cannot replace it. These flags are independent and disabled by default.",
          ),
          x(
            "Local: host registrado, agente ativo, heartbeat de até 30 segundos, manifests íntegros, serviços permitidos, comandos e imagens instaladas fixados e UUIDs corretos. O agente opera somente serviços registrados, sem build/pull arbitrário ou shell recebido do navegador.",
            "Local: a registered host, active agent, heartbeat within 30 seconds, intact manifests, allowed services, pinned commands and installed images, and correct UUIDs. The agent only operates registered services without arbitrary builds/pulls or browser-supplied shell commands.",
          ),
          x(
            "Modal: worker-remote, runner e watchdog de cleanup vivos, credenciais seladas e identidade testada, runtime compatível, lock de modelo com hashes para redeploy e orçamento suficiente. Flags ou botões habilitados não provam readiness física nem substituem o canário. O watchdog zera overrides pagos vencidos ou sem orçamento e observa o pool; exposição não confirmada permanece registrada. cooldown marca standby e drain_stop marca stopped: novas admissões são bloqueadas com ENGINE_NOT_RUNNING até retomada explícita, sem wakeup automático.",
            "Modal: live worker-remote, runner and cleanup watchdog, sealed credentials and tested identity, compatible runtime, hashed model lock for redeployment and sufficient budget. Flags or enabled buttons do not prove physical readiness or replace a canary. The watchdog zeros expired or unfunded paid overrides and observes the pool; unconfirmed exposure remains recorded. cooldown marks standby and drain_stop marks stopped: new admissions are blocked with ENGINE_NOT_RUNNING until explicit resumption, without automatic wakeup.",
          ),
        ],
      },
      {
        title: x(
          "Desejado, aplicado e observado",
          "Desired, applied and observed",
        ),
        head: [x("Estado", "State"), x("Como interpretar", "How to interpret")],
        rows: [
          [
            x("Desejado", "Desired"),
            x(
              "Última revisão de runtime salva/vinculada para a feature. Não afirma que containers ou modelo mudaram.",
              "Latest saved/bound runtime revision for the feature. It does not claim containers or models changed.",
            ),
          ],
          [
            x("Aplicado", "Applied"),
            x(
              "Snapshot reconhecido pelo controlador após verificação do executor. Publicar outro perfil não atualiza esse snapshot.",
              "Snapshot acknowledged by the controller after executor verification. Publishing another profile does not update this snapshot.",
            ),
          ],
          [
            x("Observado", "Observed"),
            x(
              "Evidência com timestamp: réplicas, readiness, modelo/revisão, pool ou estado frio. Desconhecido ou antigo não equivale a parado ou pronto.",
              "Timestamped evidence: replicas, readiness, model/revision, pool or cold state. Unknown or stale does not mean stopped or ready.",
            ),
          ],
        ],
      },
      {
        title: x("Ações e efeitos por adapter", "Actions and adapter effects"),
        head: [x("Ação", "Action"), x("Local", "Local"), x("Modal", "Modal")],
        rows: [
          [
            x("test · Testar", "test · Test"),
            x(
              "Inspeciona o host/serviço; exige perfil local. Não aplica a configuração nem comprova inferência pronta.",
              "Inspects host/service; needs a local profile. Does not apply settings or prove inference readiness.",
            ),
            x(
              "Testa conexão/deploy e qualifica identidade; pode preceder o perfil.",
              "Tests connection/deployment and qualifies identity; may precede a profile.",
            ),
          ],
          [
            x("reconcile · Conciliar", "reconcile · Reconcile"),
            x(
              "Não suportado pelo controlador local.",
              "Not supported by the local controller.",
            ),
            x(
              "Consulta relatório de gasto; não aquece GPU.",
              "Reads the spending report; does not warm a GPU.",
            ),
          ],
          [
            x("deploy · Deploy", "deploy · Deploy"),
            x(
              "Não suportado: agente usa imagens já instaladas.",
              "Unsupported: the agent uses installed images.",
            ),
            x(
              "Constrói e publica artifact aprovado; pode gerar custo.",
              "Builds and publishes an approved artifact; may incur cost.",
            ),
          ],
          [
            x("start · Iniciar", "start · Start"),
            x(
              "Sobe desired_replicas e verifica readiness.",
              "Starts desired_replicas and verifies readiness.",
            ),
            x(
              "Faz deploy e configura pool; exige janela de aquecimento e teto pago.",
              "Deploys and configures the pool; needs a warm window and paid cap.",
            ),
          ],
          [
            x("drain_stop · Drenar e parar", "drain_stop · Drain and stop"),
            x(
              "Bloqueia novas colocações, espera em voo e escala a zero.",
              "Blocks new placements, waits for in-flight work and scales to zero.",
            ),
            x(
              "Drena, reduz pool a zero e para deployment. Plano é destrutivo.",
              "Drains, reduces the pool to zero and stops the deployment. The plan is destructive.",
            ),
          ],
          [
            x("restart · Reiniciar", "restart · Restart"),
            x(
              "Drena e recria o serviço com perfil fixado.",
              "Drains and recreates the service with pinned settings.",
            ),
            x(
              "Drena e faz redeploy do artifact fixado.",
              "Drains and redeploys the pinned artifact.",
            ),
          ],
          [
            x("scale · Aplicar escala", "scale · Apply scale"),
            x(
              "Aplica réplicas e recursos do desejado; não edita o perfil.",
              "Applies replicas and resources from desired state; does not edit the profile.",
            ),
            x(
              "Atualiza autoscaler de deploy com protocolo de controle compatível.",
              "Updates the autoscaler of a deployment with a compatible control protocol.",
            ),
          ],
          [
            x("warmup · Aquecer", "warmup · Warm up"),
            x(
              "Recria serviço e verifica modelo; usa o maior entre réplicas desejadas e aquecidas.",
              "Recreates the service and verifies the model; uses the greater of desired and warm replicas.",
            ),
            x(
              "Aplica mínimo aquecido, executa probes e comprova containers distintos até prazo fixado.",
              "Applies a warm minimum, runs probes and verifies distinct containers until the fixed deadline.",
            ),
          ],
          [
            x("cooldown · Liberar modelo", "cooldown · Release model"),
            x(
              "Drena e escala serviço a zero; libera o modelo ao encerrar processos.",
              "Drains and scales the service to zero; releases the model by ending processes.",
            ),
            x(
              "Zera autoscaler e aguarda pool frio sem parar o deployment.",
              "Zeros the autoscaler and waits for a cold pool without stopping the deployment.",
            ),
          ],
          [
            x(
              "apply_profile · Aplicar perfil",
              "apply_profile · Apply profile",
            ),
            x(
              "Drena, recria com o snapshot e valida réplicas/modelo/revisão.",
              "Drains, recreates with the snapshot and validates replicas/model/revision.",
            ),
            x(
              "Faz redeploy e aplica limites/pool do snapshot; verifica estado real.",
              "Redeploys and applies snapshot limits/pool; verifies actual state.",
            ),
          ],
          [
            x("benchmark", "benchmark"),
            x(
              "Disponível via CLI, não no adapter do controlador.",
              "Available through CLI, not the controller adapter.",
            ),
            x(
              "Disponível via CLI com orçamento, não no adapter do controlador.",
              "Available through CLI with a budget, not the controller adapter.",
            ),
          ],
        ],
      },
      {
        title: x("Requisitos funcionais", "Functional requirements"),
        head: requirementHead,
        rows: [
          [
            x("OPS-01 · Capabilities", "OPS-01 · Capabilities"),
            x(
              "Exibir somente features e ações suportadas/autorizadas com razão do bloqueio. Consultar capabilities para a feature selecionada; ação não descrita não pode ser executada.",
              "Show only supported/authorized features and actions with blocking reasons. Query capabilities for the selected feature; an undescribed action cannot execute.",
            ),
          ],
          [
            x("OPS-02 · Prévia", "OPS-02 · Preview"),
            x(
              "Criar plano sem iniciar recursos: congelar versão da engine, revisão, hash, identidade, recursos afetados, efeitos, etapas, custo e expiração de cinco minutos.",
              "Create a plan without starting resources: freeze engine version, revision, hash, identity, affected resources, effects, stages, cost and a five-minute expiration.",
            ),
          ],
          [
            x("OPS-03 · Execução idempotente", "OPS-03 · Idempotent execution"),
            x(
              "Executar plan_id + plan_hash com Idempotency-Key; retornar 202 e operation_id. Retry da mesma requisição usa a mesma chave e não duplica efeitos. Outra intenção exige nova chave/plano.",
              "Execute plan_id + plan_hash with Idempotency-Key; return 202 and operation_id. Retry the same request with the same key without duplicating effects. Different intent needs a new key/plan.",
            ),
          ],
          [
            x(
              "OPS-04 · Locks, drenagem e readiness",
              "OPS-04 · Locks, drain and readiness",
            ),
            x(
              "Reservar recursos canônicos, cobrir desejado e aplicado, bloquear colocações afetadas e aguardar ledger/live/Celery. Timeout de drain falha sem desligar à força. Verificar inferência, imagem e réplica; processo vivo não basta.",
              "Reserve canonical resources, cover desired and applied state, block affected placements and wait for ledger/live/Celery. A drain timeout fails without forced shutdown. Verify inference, image and replicas; a live process is insufficient.",
            ),
          ],
          [
            x("OPS-05 · Eventos e auditoria", "OPS-05 · Events and audit"),
            x(
              "Persistir histórico, snapshot e eventos com seq. Polling after/next ou SSE com Authorization recupera eventos após reconexão. Filtrar e revalidar sessão/escopo por lote; nunca pôr token na URL.",
              "Persist history, snapshots and sequenced events. Polling after/next or SSE with Authorization retrieves events after reconnection. Scope/filter and revalidate sessions per batch; never put tokens in URLs.",
            ),
          ],
          [
            x("OPS-06 · Cancelar e recuperar", "OPS-06 · Cancel and recover"),
            x(
              "can_cancel/can_recover dependem de estado e permissão atual. Cancelamento cooperativo não desfaz RPC aceito. Recovery observa exposição antes de continuar e usa o solicitante atual sem apagar o iniciador.",
              "can_cancel/can_recover depend on state and current permission. Cooperative cancellation does not undo an accepted RPC. Recovery observes exposure before continuing and uses the current requester without erasing the initiator.",
            ),
          ],
          [
            x(
              "OPS-07 · Exposição e revogação",
              "OPS-07 · Exposure and revocation",
            ),
            x(
              "Revalidar autoridade antes de cada efeito; revogação impede novos passos. Resultado incerto mantém locks/reservas; watchdog limpa exposição registrada sem iniciar recursos com uma sessão revogada.",
              "Revalidate authority before every effect; revocation blocks new steps. Unknown outcomes retain locks/reservations; the watchdog cleans recorded exposure without starting resources using a revoked session.",
            ),
          ],
        ],
      },
      {
        title: x(
          "Aplicações e fluxo de operação",
          "Use cases and operation workflow",
        ),
        steps: [
          x(
            "Manutenção: publique/vincule o perfil pretendido. Abra Operar engine, escolha feature e restart ou apply_profile. A prévia mostra recursos compartilhados e prazo de drain; revise antes de executar.",
            "Maintenance: publish/bind the intended profile. Open Operate engine, select the feature and restart or apply_profile. The preview shows shared resources and drain timeout; review before executing.",
          ),
          x(
            "Pico de demanda: revise max_replicas/desired_replicas e orçamento no perfil; vincule e planeje scale. Modal aplica política do autoscaler; local altera o serviço registrado. Confirme aplicado e observado.",
            "Demand spike: review max_replicas/desired_replicas and budget in the profile; bind it and plan scale. Modal applies autoscaler policy; local changes the registered service. Confirm applied and observed state.",
          ),
          x(
            "Reduzir custo: cooldown libera pool/modelo; drain_stop encerra o deployment remoto. Não use apenas pause para liberar GPU: pause controla novas colocações.",
            "Reduce cost: cooldown releases the pool/model; drain_stop ends a remote deployment. Do not rely on pause to release GPUs: pause controls new placements.",
          ),
          x(
            "Resposta perdida: consulte o snapshot ou repita a execução com a mesma chave/corpo. Em needs_attention, consulte eventos e exposição; use recovery autorizado, sem disparar outro start para tentar resolver.",
            "Lost response: read the snapshot or retry execution with the same key/body. For needs_attention, inspect events and exposure; use authorized recovery rather than issuing another start to resolve it.",
          ),
        ],
        code: `# ${"Prévia / Preview: substitute the current engine version and a bound profile"}
curl --fail "${DOCS_API_URL}/admin/engines/ENGINE_ID/operation-plans" \\
  -H "Authorization: Bearer JWT_SESSION" -H "Content-Type: application/json" \\
  --data '{"type":"apply_profile","feature":"transcription","engine_version":CURRENT_VERSION,"max_usd":"0.10","drain_timeout_seconds":900}'

# ${"After reviewing the preview; reuse the key only for this exact request"}
curl --fail "${DOCS_API_URL}/admin/engines/ENGINE_ID/operations" \\
  -H "Authorization: Bearer JWT_SESSION" -H "Content-Type: application/json" \\
  -H "Idempotency-Key: UNIQUE_REQUEST_ID" \\
  --data '{"plan_id":"PLAN_ID","plan_hash":"PLAN_HASH","confirm_paid_operation":true}'

curl --fail "${DOCS_API_URL}/admin/engine-operations/OPERATION_ID/events?after=0" \\
  -H "Authorization: Bearer JWT_SESSION"`,
      },
      {
        title: x("Estados e diagnóstico", "States and diagnostics"),
        head: [
          x("Estado / código", "State / code"),
          x("Interpretação e ação", "Meaning and action"),
        ],
        rows: [
          [
            x(
              "queued / running / reconciling",
              "queued / running / reconciling",
            ),
            x(
              "Aceita, em execução ou reconciliação. cancel_requested é um indicador de cancelamento cooperativo, não um estado. Acompanhe snapshot e eventos; não crie outra operação para a mesma intenção.",
              "Accepted, executing or reconciling. cancel_requested is a cooperative cancellation flag, not a state. Follow snapshots/events; do not create another operation for the same intent.",
            ),
          ],
          [
            x(
              "succeeded / failed / cancelled / needs_attention",
              "succeeded / failed / cancelled / needs_attention",
            ),
            x(
              "Estados terminais do fluxo; needs_attention pode manter exposição e locks. Mesmo failed não prova que todos os efeitos externos foram desfeitos.",
              "Terminal workflow states; needs_attention may retain exposure and locks. Even failed does not prove all external effects were undone.",
            ),
          ],
          [
            x(
              "CONTROL_NOT_ENABLED / ACCESS_NOT_ENABLED",
              "CONTROL_NOT_ENABLED / ACCESS_NOT_ENABLED",
            ),
            x(
              "Concluir migração e ativação coordenada dos serviços, sem apenas alterar o frontend.",
              "Complete migration and coordinated service activation instead of only changing the frontend.",
            ),
          ],
          [
            x(
              "RUNTIME_PROFILE_REQUIRED / HOST_AGENT_NOT_READY",
              "RUNTIME_PROFILE_REQUIRED / HOST_AGENT_NOT_READY",
            ),
            x(
              "Vincular perfil publicado ou corrigir registro/heartbeat do host.",
              "Bind a published profile or fix host registration/heartbeat.",
            ),
          ],
          [
            x("VERSION_CONFLICT / PLAN_STALE", "VERSION_CONFLICT / PLAN_STALE"),
            x(
              "Consultar estado atual e gerar nova prévia após revisar a intenção. Não trocar silenciosamente a versão do plano.",
              "Read current state and create a new preview after reviewing intent. Do not silently replace the plan version.",
            ),
          ],
          [
            x(
              "OPERATION_CONFLICT / RESOURCE_OWNERSHIP_CONFLICT",
              "OPERATION_CONFLICT / RESOURCE_OWNERSHIP_CONFLICT",
            ),
            x(
              "Há operação/exposição ou proprietário conflitante. Inspecionar histórico e recursos; não limpar locks manualmente.",
              "There is a conflicting operation/exposure or owner. Inspect history and resources; do not clear locks manually.",
            ),
          ],
          [
            x(
              "PAID_CONFIRMATION_REQUIRED / BUDGET_INSUFFICIENT",
              "PAID_CONFIRMATION_REQUIRED / BUDGET_INSUFFICIENT",
            ),
            x(
              "Revisar reserva e teto; confirmar apenas o plano aceito. max_usd não é limite garantido da fatura.",
              "Review reservation and cap; confirm only the accepted plan. max_usd is not a guaranteed invoice limit.",
            ),
          ],
          [
            x(
              "CLEANUP_WATCHDOG_NOT_READY / INVALID_OPERATION",
              "CLEANUP_WATCHDOG_NOT_READY / INVALID_OPERATION",
            ),
            x(
              "Restaurar watchdog ou ler message para o gate específico: TEST_CONNECTION_FIRST, WARM_EXPIRATION_REQUIRED, HASHED_MODEL_LOCK_REQUIRED, CONTROL_REDEPLOY_REQUIRED ou PROFILE_INVENTORY_CHANGED.",
              "Restore the watchdog or read message for the specific gate: TEST_CONNECTION_FIRST, WARM_EXPIRATION_REQUIRED, HASHED_MODEL_LOCK_REQUIRED, CONTROL_REDEPLOY_REQUIRED or PROFILE_INVENTORY_CHANGED.",
            ),
          ],
        ],
      },
    ],
    endpoints: [
      [
        "GET",
        "/admin/engines/{id}/capabilities",
        x(
          "Ações e dependências por feature",
          "Actions and dependencies per feature",
        ),
      ],
      [
        "GET",
        "/admin/engines/{id}/runtime-profile · /runtime-status",
        x("Desejado / aplicado / observado", "Desired / applied / observed"),
      ],
      [
        "PUT",
        "/admin/engines/{id}/runtime-profile",
        x(
          "Configuração bruta, bootstrap-only",
          "Raw configuration, bootstrap-only",
        ),
      ],
      [
        "POST",
        "/admin/engines/{id}/operation-plans",
        x("Prévia sem efeitos", "Preview without effects"),
      ],
      [
        "POST",
        "/admin/engines/{id}/operations",
        x("Execução com Idempotency-Key", "Execution with Idempotency-Key"),
      ],
      [
        "GET",
        "/admin/engine-operations",
        x(
          "Histórico com engine_id, limit e before",
          "History with engine_id, limit and before",
        ),
      ],
      [
        "GET",
        "/admin/engine-operations/{id}",
        x("Snapshot e permissões de ação", "Snapshot and action permissions"),
      ],
      [
        "GET",
        "/admin/engine-operations/{id}/events · /stream",
        x(
          "Eventos paginados / SSE com after",
          "Paged events / SSE using after",
        ),
      ],
      [
        "POST",
        "/admin/engine-operations/{id}/cancel · /recover",
        x(
          "Cancelar / recuperar com ator atual",
          "Cancel / recover with the current actor",
        ),
      ],
    ],
    related: ["engines", "execution-profiles", "engine-access"],
  },
  "execution-profiles": {
    title: x("Perfis de execução", "Execution profiles"),
    intro: x(
      "A biblioteca guarda configurações reutilizáveis de runtime por adapter, feature e ambiente. O vínculo fixa uma revisão publicada como desejado de uma engine; aplicar essa revisão é uma operação separada.",
      "The library stores reusable runtime settings per adapter, feature and environment. Binding pins a published revision as an engine's desired state; applying that revision is a separate operation.",
    ),
    parts: [
      {
        title: x("Requisitos para configurar", "Configuration prerequisites"),
        paragraphs: [
          x(
            "Abra Compute → Perfis de execução (/admin/execution-profiles). A biblioteca requer ENGINE_ACCESS_ENABLED, migração concluída e sessão JWT com grant adequado ou bootstrap ativo. O catálogo instalado e os descriptors fornecem opções; não é permitido enviar código, URL livre de modelo ou segredos.",
            "Open Compute → Execution profiles (/admin/execution-profiles). The library requires ENGINE_ACCESS_ENABLED, completed migration and a JWT session with an appropriate grant or active bootstrap. Installed catalogs and descriptors provide options; arbitrary code, model URLs or secrets are prohibited.",
          ),
          x(
            "Antes de vincular, o bootstrap classifica a engine como development, staging ou production. Adapter, feature e ambiente do perfil precisam corresponder à engine. Controle local requer host/serviço/GPU registrados; controle Modal requer identidade testada e credenciais na conexão.",
            "Before binding, bootstrap classifies the engine as development, staging or production. Profile adapter, feature and environment must match the engine. Local control needs registered host/service/GPU; Modal control needs a tested identity and connection credentials.",
          ),
        ],
      },
      {
        title: x("Requisitos funcionais", "Functional requirements"),
        head: requirementHead,
        rows: [
          [
            x(
              "PRF-01 · Biblioteca e metadata",
              "PRF-01 · Library and metadata",
            ),
            x(
              "Listar/detalhar somente perfis autorizados. Criar nome (1–100 caracteres), descrição (até 1.000), adapter, feature e ambiente; editar nome/descrição com versão esperada.",
              "List/detail authorized profiles only. Create a name (1–100 characters), description (up to 1,000), adapter, feature and environment; edit name/description with the expected version.",
            ),
          ],
          [
            x(
              "PRF-02 · Revisões e publicação",
              "PRF-02 · Revisions and publication",
            ),
            x(
              "Salvar novo payload como revisão imutável, publicar revision_id explícito com version. Rascunho posterior não substitui publicação anterior; catálogo aprovado é fixado por fingerprint.",
              "Save each new payload as an immutable revision; publish an explicit revision_id with version. A later draft does not replace an earlier publication; the approved catalog is pinned by fingerprint.",
            ),
          ],
          [
            x("PRF-03 · Vínculo", "PRF-03 · Binding"),
            x(
              "POST bind aceita versão da engine, feature e revisão publicada. Resolver host/GPU/modelo e gravar origem/hash/snapshot atomicamente. Não iniciar container, deploy ou reserva de orçamento.",
              "POST bind accepts engine version, feature and a published revision. Resolve host/GPU/model and atomically store source/hash/snapshot. Do not start containers, deployment or budget reservation.",
            ),
          ],
          [
            x(
              "PRF-04 · Histórico, clone e importação",
              "PRF-04 · History, clone and import",
            ),
            x(
              "Detalhe mostra revisões e vínculos permitidos. Clone pela UI cria perfil novo em rascunho; bootstrap pode importar desejado legado retirando campos resolvidos. Arquivar barra novos vínculos e preserva histórico/aplicado.",
              "Details show permitted revisions and bindings. UI cloning creates a new draft profile; bootstrap can import legacy desired settings after removing resolved fields. Archiving blocks new bindings and preserves history/applied state.",
            ),
          ],
          [
            x("PRF-05 · Compatibilidade", "PRF-05 · Compatibility"),
            x(
              "Validar schema/adapter, réplicas, VRAM, host/UUID, ambiente, modelo e fingerprint. Alteração do catálogo ou manifest exige revisão/vínculo explícito, não troca silenciosa em operação.",
              "Validate schema/adapter, replicas, VRAM, host/UUID, environment, model and fingerprint. Catalog or manifest changes require an explicit revision/binding rather than a silent operation update.",
            ),
          ],
          [
            x(
              "PRF-06 · Prazo e concorrência de edição",
              "PRF-06 · Deadline and concurrent edits",
            ),
            x(
              "warm_for_seconds até 86.400; template warm_until=null. Resolver deadline uma vez no vínculo. Retry não renova prazo; VERSION_CONFLICT pede leitura e revisão da intenção.",
              "warm_for_seconds up to 86,400; template warm_until=null. Resolve the deadline once on binding. Retry does not extend it; VERSION_CONFLICT requires rereading and reviewing intent.",
            ),
          ],
        ],
      },
      {
        title: x(
          "Campos, limites e aplicação",
          "Fields, limits and application",
        ),
        head: [
          x("Campo", "Field"),
          x("Requisito / efeito", "Requirement / effect"),
        ],
        rows: [
          [
            x(
              "adapter_version / schema_version",
              "adapter_version / schema_version",
            ),
            x(
              "Versão 1 nesta implementação. Contratos fechados rejeitam campos extras; campos provider são os do descriptor.",
              "Version 1 in this implementation. Closed contracts reject extra fields; provider fields come from descriptors.",
            ),
          ],
          [
            x("model_profile_id", "model_profile_id"),
            x(
              "ID do modelo aprovado para adapter/feature. Não é repositório arbitrário; aprovação e pegada precisam estar qualificadas.",
              "Approved model ID for adapter/feature. Not an arbitrary repository; approval and footprint must be qualified.",
            ),
          ],
          [
            x(
              "desired_replicas / max_replicas / min_ready_replicas",
              "desired_replicas / max_replicas / min_ready_replicas",
            ),
            x(
              "Inteiros 0–100; desejado e mínimo ≤ máximo. binding.workers = max_replicas. Local sobe desejado; Modal define máximo/mínimo do autoscaler conforme a ação. Zero permite liberar capacidade.",
              "Integers 0–100; desired and minimum ≤ maximum. binding.workers = max_replicas. Local starts desired replicas; Modal sets autoscaler maximum/minimum according to the action. Zero allows releasing capacity.",
            ),
          ],
          [
            x("binding.executions_per_worker", "binding.executions_per_worker"),
            x(
              "Concorrência por worker (schema 1–64); respeita restrições do adapter. GPU local e Modal: 1. Local sem GPU pode admitir mais; live tem no máximo uma réplica e E=1.",
              "Per-worker concurrency (schema 1–64); subject to adapter restrictions. Local GPU and Modal: 1. Local without GPU may allow more; live has at most one replica and E=1.",
            ),
          ],
          [
            x("binding.cpu / memory_mb", "binding.cpu / memory_mb"),
            x(
              "CPU por worker >0 até 64 (formulário começa em 0,25); memória 256–262.144 MiB. Perfil delegado precisa declarar ambos para validar tetos, sem depender de default do provider.",
              "Per-worker CPU >0 up to 64 (form starts at 0.25); memory 256–262,144 MiB. Delegated profiles must declare both to validate caps instead of depending on provider defaults.",
            ),
          ],
          [
            x(
              "binding.gpu_ref / binding.gpu_type",
              "binding.gpu_ref / binding.gpu_type",
            ),
            x(
              "Local usa alias declarado na engine e resolve UUID registrado; Modal usa tipo de GPU aceito pelo adapter. gpu_ref não é o UUID da política ABAC. VRAM inclui todos os consumidores.",
              "Local uses an engine-declared alias resolved to a registered UUID; Modal uses an adapter-supported GPU type. gpu_ref is not the ABAC policy UUID. VRAM includes all consumers.",
            ),
          ],
          [
            x("idle_timeout_seconds", "idle_timeout_seconds"),
            x(
              "2–3.600 segundos; janela ociosa do autoscaler Modal. Não é agendamento automático de desligamento do worker local.",
              "2–3,600 seconds; Modal autoscaler idle window. Not an automatic local worker shutdown schedule.",
            ),
          ],
          [
            x("warmup_mode", "warmup_mode"),
            x(
              "on_start ou manual, armazenado no perfil. Readiness depende de probes do executor; o campo não cria scheduler de aquecimento nem dispensa uma operação explícita.",
              "on_start or manual, stored in the profile. Readiness depends on executor probes; this field does not create a warmup scheduler or remove the need for an explicit operation.",
            ),
          ],
          [
            x("warm_for_seconds / warm_until", "warm_for_seconds / warm_until"),
            x(
              "Duração opcional 1–86.400 segundos na biblioteca; deadline UTC resolvido no vínculo. Modal com mínimo aquecido exige duração; start/warmup Modal exigem expiração e reserva suficiente.",
              "Optional library duration of 1–86,400 seconds; UTC deadline resolved on binding. Modal with a warm minimum requires duration; Modal start/warmup require expiry and sufficient reservation.",
            ),
          ],
          [
            x("provider_settings", "provider_settings"),
            x(
              "Local: somente host_id registrado. Modal: objeto vazio nesta versão. Credenciais ficam na conexão e nunca entram no template.",
              "Local: registered host_id only. Modal: empty object in this release. Credentials belong to the connection and never enter templates.",
            ),
          ],
        ],
      },
      {
        title: x(
          "Aplicações e fluxo na interface",
          "Use cases and UI workflow",
        ),
        steps: [
          x(
            "Padronizar documentos: crie perfil local/document_conversion/development com docling-local, host registrado e recursos compatíveis. Salve e publique a revisão escolhida.",
            "Standardize documents: create a local/document_conversion/development profile using docling-local, a registered host and compatible resources. Save and publish the chosen revision.",
          ),
          x(
            "Engine → Configuração → Perfil de execução: selecione perfil/revisão, confira diferenças e vincule. O desejado muda; aplicado continua anterior até apply_profile/scale/restart verificado.",
            "Engine → Configuration → Execution profile: select profile/revision, review differences and bind. Desired state changes; applied state remains earlier until a verified apply_profile/scale/restart.",
          ),
          x(
            "Preparar uma janela de transcrição Modal: clone um perfil permitido, revise limites/réplicas e duração aquecida, publique e vincule. Confira orçamento antes do plano start/warmup; a nova publicação não migra outras engines automaticamente.",
            "Prepare a Modal transcription window: clone a permitted profile, review limits/replicas and warm duration, publish and bind. Check budget before a start/warmup plan; a new publication does not migrate other engines automatically.",
          ),
          x(
            "Corrigir uma revisão: salve/publice outra e revincule explicitamente. Para voltar a uma configuração anterior, selecione uma revisão publicada ainda compatível e aplique novo plano; não há rollback físico automático.",
            "Correct a revision: save/publish another and explicitly rebind. To return to earlier settings, select a still-compatible published revision and apply a new plan; there is no automatic physical rollback.",
          ),
        ],
      },
      {
        title: x(
          "Exemplo de criar, publicar e vincular",
          "Create, publish and bind example",
        ),
        paragraphs: [
          x(
            "Exemplo ilustrativo de Docling em CPU; substitua IDs e valores pelo inventário real. A engine já deve estar classificada development e o agente deve registrar worker. As três escritas abaixo só mudam metadata/desejado; aplicação física exige o plano separado. Use os version retornados pelo servidor.",
            "Illustrative CPU Docling example; replace IDs and values with actual inventory. The engine must already be classified development and the agent must register worker. These three writes only change metadata/desired state; physical application needs a separate plan. Use server-returned versions.",
          ),
        ],
        code: `import requests
API = "${DOCS_API_URL}"
headers = {"Authorization": "Bearer JWT_SESSION"}
engine_id = "ENGINE_ID"

def call(method, path, **kwargs):
    response = requests.request(method, API + path, headers=headers, **kwargs)
    response.raise_for_status()
    return response.json()

profile = call("POST", "/admin/execution-profiles", json={
    "name": "Docling CPU dev", "description": "Document pipeline",
    "adapter_type": "local", "feature": "document_conversion",
    "environment": "development", "warm_for_seconds": None,
    "settings": {
        "adapter_version": 1, "schema_version": 1,
        "binding": {"workers": 1, "executions_per_worker": 1, "cpu": 2},
        "model_profile_id": "docling-local", "desired_replicas": 1,
        "max_replicas": 1, "min_ready_replicas": 0,
        "idle_timeout_seconds": 60, "memory_mb": 8192,
        "warmup_mode": "on_start", "warm_until": None,
        "provider_settings": {"host_id": "REGISTERED_HOST_ID"}
    }
})
revision_id = profile["revisions"][0]["id"]
call("POST", f"/admin/execution-profiles/{profile['id']}/publish",
     json={"version": profile["version"], "revision_id": revision_id})
engine = call("GET", f"/admin/engines/{engine_id}")
desired = call("POST", f"/admin/engines/{engine_id}/runtime-profile/bind",
               json={"version": engine["version"],
                     "feature": "document_conversion", "revision_id": revision_id})
print(desired)  # Desired snapshot only; review an operation plan to apply it.`,
      },
      {
        title: x("Erros e correções", "Errors and corrections"),
        head: [x("Código", "Code"), x("Ação", "Action")],
        rows: [
          [
            x(
              "PUBLISHED_REVISION_REQUIRED / PROFILE_ARCHIVED",
              "PUBLISHED_REVISION_REQUIRED / PROFILE_ARCHIVED",
            ),
            x(
              "Escolher revisão publicada de perfil ativo; arquivado não aceita novo vínculo.",
              "Choose a published revision from an active profile; archived profiles cannot receive new bindings.",
            ),
          ],
          [
            x(
              "ENGINE_ENVIRONMENT_REQUIRED / PROFILE_INCOMPATIBLE",
              "ENGINE_ENVIRONMENT_REQUIRED / PROFILE_INCOMPATIBLE",
            ),
            x(
              "Bootstrap classifica ambiente; confira correspondência de adapter/feature/ambiente.",
              "Bootstrap classifies the environment; check adapter/feature/environment correspondence.",
            ),
          ],
          [
            x(
              "MODEL_METADATA_CHANGED / MODEL_PROFILE_UNAVAILABLE",
              "MODEL_METADATA_CHANGED / MODEL_PROFILE_UNAVAILABLE",
            ),
            x(
              "Revisar catálogo/aprovação e publicar revisão compatível.",
              "Review catalog/approval and publish a compatible revision.",
            ),
          ],
          [
            x(
              "USE_WARM_DURATION / WARM_DURATION_REQUIRED",
              "USE_WARM_DURATION / WARM_DURATION_REQUIRED",
            ),
            x(
              "Usar warm_for_seconds e manter warm_until=null no template.",
              "Use warm_for_seconds and keep warm_until=null in the template.",
            ),
          ],
          [
            x(
              "VERSION_CONFLICT / ACCESS_DENIED / 404",
              "VERSION_CONFLICT / ACCESS_DENIED / 404",
            ),
            x(
              "Reler versão; verificar grant e escopo. 404 também evita revelar recurso fora do escopo.",
              "Reread version; check grant and scope. A 404 also avoids revealing an out-of-scope resource.",
            ),
          ],
          [
            x(
              "INVALID_CONFIGURATION / INVALID_OPERATION",
              "INVALID_CONFIGURATION / INVALID_OPERATION",
            ),
            x(
              "Ler message: pode indicar VRAM, GPU_UUID_NOT_REGISTERED, SERVICE_NOT_REGISTERED, LIVE_SINGLE_RESIDENT_REQUIRED ou PROFILE_INVENTORY_CHANGED.",
              "Read message: it may indicate VRAM, GPU_UUID_NOT_REGISTERED, SERVICE_NOT_REGISTERED, LIVE_SINGLE_RESIDENT_REQUIRED or PROFILE_INVENTORY_CHANGED.",
            ),
          ],
        ],
      },
    ],
    endpoints: [
      [
        "GET / POST",
        "/admin/execution-profiles",
        x(
          "Listar / criar com primeira revisão",
          "List / create with initial revision",
        ),
      ],
      [
        "GET / PUT",
        "/admin/execution-profiles/{id}",
        x("Detalhe / nome e descrição", "Detail / name and description"),
      ],
      [
        "POST",
        "/admin/execution-profiles/{id}/revisions",
        x(
          "Novo payload e version esperado",
          "New payload and expected version",
        ),
      ],
      [
        "POST",
        "/admin/execution-profiles/{id}/publish",
        x(
          "revision_id explícito e version",
          "Explicit revision_id and version",
        ),
      ],
      [
        "POST",
        "/admin/execution-profiles/{id}/archive",
        x("Arquivar com version", "Archive with version"),
      ],
      [
        "POST",
        "/admin/engines/{id}/runtime-profile/bind",
        x("Revisão publicada → desejado", "Published revision → desired"),
      ],
      [
        "POST",
        "/admin/engines/{id}/runtime-profile/import",
        x("Importação legada bootstrap", "Bootstrap legacy import"),
      ],
      [
        "GET",
        "/admin/execution-profile-hosts · /admin/model-profiles",
        x("Hosts e modelos permitidos", "Permitted hosts and models"),
      ],
    ],
    related: ["engine-operations", "engine-access", "engines"],
  },
  "engine-access": {
    title: x("Acesso a engines: RBAC e ABAC", "Engine access: RBAC and ABAC"),
    intro: x(
      "RBAC define a ação concedida por um papel. ABAC limita essa ação a engines, perfis, recursos e valores autorizados. A decisão consulta a autoridade SQL atual; possuir um job ou projeto não concede permissão para controlar o worker compartilhado.",
      "RBAC defines the action granted by a role. ABAC limits that action to authorized engines, profiles, resources and values. Decisions read current SQL authority; owning a job or project does not grant permission to control a shared worker.",
    ),
    parts: [
      {
        title: x("Requisitos e papéis", "Requirements and roles"),
        paragraphs: [
          x(
            "Compute → Acesso (/admin/access) usa sessão JWT, schema migrado e ENGINE_ACCESS_ENABLED. Bootstrap é o admin efetivo ativo (is_admin ou ADMIN_USER_IDS); mantém acesso de emergência e gerencia atributos confiáveis. Usuários delegados precisam de grants válidos e não se tornam admin global.",
            "Compute → Access (/admin/access) uses a JWT session, migrated schema and ENGINE_ACCESS_ENABLED. Bootstrap is the active effective admin (is_admin or ADMIN_USER_IDS); it retains emergency access and manages trusted attributes. Delegated users need valid grants and do not become global admins.",
          ),
        ],
        head: [
          x("Papel", "Role"),
          x("Permissões concedíveis", "Grantable permissions"),
          x("Aplicação", "Use case"),
        ],
        rows: [
          [
            x("observer", "observer"),
            x(
              "engines.read, execution_profiles.read, engine_operations.read.",
              "engines.read, execution_profiles.read, engine_operations.read.",
            ),
            x(
              "Acompanhar estado e histórico sem operar.",
              "Monitor state and history without operating.",
            ),
          ],
          [
            x("profile_editor", "profile_editor"),
            x(
              "execution_profiles.read/create/update/publish/archive.",
              "execution_profiles.read/create/update/publish/archive.",
            ),
            x(
              "Preparar configurações aprovadas sem aplicar em engines.",
              "Prepare approved settings without applying them to engines.",
            ),
          ],
          [
            x("runtime_configurator", "runtime_configurator"),
            x(
              "Leituras e engine_runtime.bind.",
              "Reads and engine_runtime.bind.",
            ),
            x(
              "Vincular publicação ao desejado; não executar efeitos.",
              "Bind a publication to desired state without executing effects.",
            ),
          ],
          [
            x("engine_operator", "engine_operator"),
            x(
              "Leituras, engine_operations.plan, execute.<ação>, cancel e recover. Grant pode conceder subconjunto.",
              "Reads, engine_operations.plan, execute.<action>, cancel and recover. A grant may allow a subset.",
            ),
            x(
              "Operar somente ações concedidas, como test/scale, no ambiente permitido.",
              "Operate granted actions only, such as test/scale, in a permitted environment.",
            ),
          ],
          [
            x("connection_manager", "connection_manager"),
            x(
              "Leituras e engine_connections.credentials.manage com senha atual.",
              "Reads and engine_connections.credentials.manage with the current password.",
            ),
            x(
              "Rotacionar credencial sem alterar orçamento, JSON bruto ou executar deploy.",
              "Rotate credentials without changing budgets, raw JSON or executing deployment.",
            ),
          ],
          [
            x("access_admin", "access_admin"),
            x(
              "access.grants.manage e envelope separado de delegação.",
              "access.grants.manage and a separate delegation envelope.",
            ),
            x(
              "Conceder/revogar escopos limitados; não recebe controle de runtime por esse papel.",
              "Grant/revoke limited scopes; this role does not grant runtime control.",
            ),
          ],
        ],
      },
      {
        title: x("Requisitos funcionais", "Functional requirements"),
        head: requirementHead,
        rows: [
          [
            x("ACL-01 · Sessão e navegação", "ACL-01 · Session and navigation"),
            x(
              "/access/me e /auth/me retornam estado e permissões; servidor autoriza cada ação e filtra listagens/catálogos/logs/SSE. Cache isolado por sessão não reaproveita dados entre logins.",
              "/access/me and /auth/me return status and permissions; the server authorizes each action and filters lists/catalogs/logs/SSE. Session-isolated caching does not reuse data between logins.",
            ),
          ],
          [
            x(
              "ACL-02 · Políticas revisionadas",
              "ACL-02 · Revisioned policies",
            ),
            x(
              "Criar política e revisões de constraints imutáveis; o grant fixa policy_revision_id. Revisão nova não amplia grants existentes.",
              "Create a policy and immutable constraint revisions; grants pin policy_revision_id. A new revision does not expand existing grants.",
            ),
          ],
          [
            x("ACL-03 · Grants e validade", "ACL-03 · Grants and expiry"),
            x(
              "Conceder a usuário ativo papel/subconjunto, revisão de política e expires_at UTC. Revogar com version; usuário inativo, grant vencido/revogado ou pai inválido perde autoridade.",
              "Grant an active user a role/subset, policy revision and UTC expires_at. Revoke with version; inactive users, expired/revoked grants or an invalid parent lose authority.",
            ),
          ],
          [
            x(
              "ACL-04 · Uma decisão completa",
              "ACL-04 · One complete decision",
            ),
            x(
              "Um único grant precisa cobrir todas as permissões, identidades e limites da decisão. Não combinar host de um grant com custo ou feature de outro.",
              "One grant must cover all permissions, identities and limits for a decision. Do not combine a host from one grant with cost or feature from another.",
            ),
          ],
          [
            x("ACL-05 · Delegação limitada", "ACL-05 · Limited delegation"),
            x(
              "Envelope limita permissões concedíveis, escopo, tetos e max_grant_seconds. Grant filho não amplia pai nem prazo; revogação/expiração parental invalida descendentes.",
              "An envelope limits grantable permissions, scope, caps and max_grant_seconds. A child grant cannot expand its parent or expiry; parent revocation/expiry invalidates descendants.",
            ),
          ],
          [
            x("ACL-06 · Recursos compartilhados", "ACL-06 · Shared resources"),
            x(
              "Bootstrap classifica ambiente e todos os consumidores de cada recurso. Autorizar união do desejado e aplicado; consumidor desconhecido, não qualificado ou fora do grant bloqueia operação delegada.",
              "Bootstrap classifies environments and all consumers of each resource. Authorize the union of desired and applied state; unknown, unqualified or out-of-grant consumers block delegated operations.",
            ),
          ],
          [
            x(
              "ACL-07 · Revogação e auditoria",
              "ACL-07 · Revocation and audit",
            ),
            x(
              "Autorizar novamente no enqueue, runner, agente e antes de RPC. Admission/epoch duráveis ordenam revogação e efeitos. Auditar publicação, vínculo, grant, estado, cancelamento e recovery, sem segredos.",
              "Reauthorize during enqueue, runner, agent and before RPC. Durable admission/epoch order revocation and effects. Audit publication, binding, grants, state, cancellation and recovery without secrets.",
            ),
          ],
          [
            x("ACL-08 · Bootstrap e CLI", "ACL-08 · Bootstrap and CLI"),
            x(
              "Gestão global de GPU, rota, orçamento, configuração bruta e lifecycle permanece bootstrap-only. Registrar/ativar/desativar installation principals e alterar estado de sujeitos com comparação esperada; CLI direta não usa sessão delegada.",
              "Global GPU, routing, budget, raw settings and lifecycle management remain bootstrap-only. Register/activate/deactivate installation principals and change subject state using expected comparisons; direct CLI does not use a delegated session.",
            ),
          ],
        ],
      },
      {
        title: x("Escopos e tetos ABAC", "ABAC scopes and caps"),
        head: [x("Constraint", "Constraint"), x("Significado", "Meaning")],
        rows: [
          [
            x(
              "engine_ids / adapters / features / environments",
              "engine_ids / adapters / features / environments",
            ),
            x(
              "Listas obrigatórias de IDs reais, tipos de adapter, feature e development/staging/production. Lista vazia não autoriza; ambiente é atributo confiável classificado pela plataforma.",
              "Required lists of actual IDs, adapter types, feature and development/staging/production. Empty lists do not authorize; environment is a platform-classified trusted attribute.",
            ),
          ],
          [
            x(
              "profile_ids / host_ids / gpu_uuids / model_ids",
              "profile_ids / host_ids / gpu_uuids / model_ids",
            ),
            x(
              "Listas opcionais: null não impõe restrição adicional; [] não permite identidades nessa dimensão. gpu_uuids são UUIDs físicos locais, não gpu_ref nem tipo Modal.",
              "Optional lists: null imposes no additional restriction; [] permits no identities in that dimension. gpu_uuids are physical local UUIDs, not gpu_ref or Modal types.",
            ),
          ],
          [
            x(
              "max_replicas / max_concurrency",
              "max_replicas / max_concurrency",
            ),
            x(
              "Tetos de réplicas e executions_per_worker; não representam um saldo somável entre grants. Considere também recursos compartilhados afetados.",
              "Replica and executions_per_worker caps; not an allowance that can be added across grants. Also consider affected shared resources.",
            ),
          ],
          [
            x("max_cpu / max_memory_mb", "max_cpu / max_memory_mb"),
            x(
              "Limites por worker; exigem valores explícitos em perfil delegado. max_memory_mb está em MiB.",
              "Per-worker limits; require explicit values in delegated profiles. max_memory_mb is in MiB.",
            ),
          ],
          [
            x("max_warm_seconds / max_usd", "max_warm_seconds / max_usd"),
            x(
              "Teto da duração aquecida e max_usd da operação. Não é crédito concedido nem substitui orçamento da engine/provider. Leitura de histórico usa identidade, sem exigir que custo antigo caiba no teto atual de execução.",
              "Caps warm duration and operation max_usd. Not granted credit and not a replacement for engine/provider budgets. History reads use identity without requiring old costs to fit current execution caps.",
            ),
          ],
        ],
      },
      {
        title: x(
          "Aplicações e concessão de acesso",
          "Use cases and granting access",
        ),
        steps: [
          x(
            "Observabilidade: bootstrap cria política limitada à engine/feature/ambiente, concede observer e validade; usuário vê somente estado, perfis e histórico permitidos.",
            "Observability: bootstrap creates a policy scoped to engine/feature/environment and grants observer with an expiry; the user sees only permitted state, profiles and history.",
          ),
          x(
            "Separação de funções: dê profile_editor a quem prepara configurações, runtime_configurator a quem vincula e engine_operator com plan + execute.apply_profile a quem aplica. Uma operação precisa de um grant completo; dividir plan e execute em grants separados não autoriza o plano.",
            "Separate responsibilities: grant profile_editor to configuration authors, runtime_configurator to binders and engine_operator with plan + execute.apply_profile to appliers. An operation needs a complete grant; splitting plan and execute into separate grants does not authorize a plan.",
          ),
          x(
            "Dev sem produção: fixe environments=[development], engine_ids/model_ids permitidos e tetos. Classifique os consumidores do host/GPU/worker em Acesso → Recursos; inclua features do worker genérico e engines que compartilham o recurso.",
            "Development without production: pin environments=[development], allowed engine_ids/model_ids and caps. Classify host/GPU/worker consumers under Access → Resources; include generic-worker features and engines sharing the resource.",
          ),
          x(
            "Delegação temporária: bootstrap concede access_admin com envelope explícito. O delegado cria revisão compatível e grant filho, com prazo limitado; revogar o pai interrompe novas admissões dos descendentes.",
            "Temporary delegation: bootstrap grants access_admin with an explicit envelope. The delegate creates a compatible revision and child grant with a bounded expiry; revoking the parent stops new descendant admissions.",
          ),
          x(
            "Revisão de autoridade: consulte grants/revisões antes de revogar ou trocar acesso. Use API para epoch/auditoria, não edite grants, usuários ou atributos diretamente no SQL durante operações.",
            "Authority review: inspect grants/revisions before revoking or replacing access. Use the API for epoch/audit; do not edit grants, users or attributes directly in SQL during operations.",
          ),
        ],
      },
      {
        title: x("Exemplo de política e grant", "Policy and grant example"),
        paragraphs: [
          x(
            "Exemplo para um operador Modal limitado a test e apply_profile em dev. Substitua ENGINE_ID, USER_ID, POLICY_REVISION_ID e a data futura UTC. Crie a política, pegue revisions[0].id da resposta e use-o no grant. Confirme se a identidade do deployment tem outros consumidores antes de conceder operação delegada.",
            "Example for a Modal operator limited to test and apply_profile in development. Replace ENGINE_ID, USER_ID, POLICY_REVISION_ID and the future UTC date. Create the policy, take revisions[0].id from the response and use it in the grant. Check whether the deployment identity has other consumers before granting delegated operations.",
          ),
        ],
        code: `// POST /admin/access/policies (JWT bootstrap or authorized access_admin)
{
  "name": "Modal dev limited operator",
  "constraints": {
    "engine_ids": ["ENGINE_ID"], "profile_ids": null,
    "adapters": ["modal"], "features": ["transcription"],
    "environments": ["development"], "host_ids": null, "gpu_uuids": null,
    "model_ids": ["whisper-turbo-modal"], "max_replicas": 1,
    "max_concurrency": 1, "max_cpu": 2, "max_memory_mb": 8192,
    "max_warm_seconds": 600, "max_usd": "0.10"
  }
}

// POST /admin/access/grants
{
  "user_id": "USER_ID", "role": "engine_operator",
  "policy_revision_id": "POLICY_REVISION_ID",
  "permissions": ["engines.read", "execution_profiles.read",
    "engine_operations.read", "engine_operations.plan",
    "engine_operations.execute.test", "engine_operations.execute.apply_profile"],
  "expires_at": "FUTURE_UTC_ISO_DATE", "delegation": null
}`,
      },
      {
        title: x(
          "Diagnóstico e limites de segurança",
          "Diagnostics and security limits",
        ),
        paragraphs: [
          x(
            "ACCESS_DENIED pede revisar papel, política, prazo e todos os consumidores. DELEGATION_EXCEEDED indica tentativa de ampliar envelope. VERSION_CONFLICT exige reler o estado. Um 404 em detalhe/cursor pode ocultar recurso fora do escopo, sem confirmar existência.",
            "ACCESS_DENIED requires reviewing role, policy, expiry and all consumers. DELEGATION_EXCEEDED means an attempted envelope expansion. VERSION_CONFLICT requires rereading state. A detail/cursor 404 may hide an out-of-scope resource without confirming existence.",
          ),
          x(
            "Revogar impede novos efeitos, mas não desfaz RPC já admitido. Resultado desconhecido mantém exposição até observação/cleanup autorizado. Sessão expirada encerra SSE e exige renovar autenticação; Redis e claims do JWT não são a fonte de autoridade.",
            "Revocation blocks new effects but does not undo an already admitted RPC. Unknown outcomes retain exposure until authorized observation/cleanup. An expired session ends SSE and requires renewed authentication; Redis and JWT claims are not authority sources.",
          ),
          x(
            "connection_manager não cria conexões nem ajusta orçamento: esses caminhos continuam bootstrap-only. installation:<nome> é principal de bootstrap do SO, não usuário delegado; requer registro ativo, configuração ENGINE_INSTALLATION_PRINCIPAL_ID e --installation-principal antes do comando CLI.",
            "connection_manager neither creates connections nor adjusts budgets: these paths remain bootstrap-only. installation:<name> is an OS bootstrap principal, not a delegated user; it requires active registration, ENGINE_INSTALLATION_PRINCIPAL_ID and --installation-principal before the CLI command.",
          ),
        ],
      },
    ],
    endpoints: [
      [
        "GET",
        "/admin/access/me · /admin/access/roles · /admin/access/subjects",
        x(
          "Navegação, papéis e sujeitos permitidos",
          "Navigation, roles and permitted subjects",
        ),
      ],
      [
        "GET / POST",
        "/admin/access/policies",
        x("Listar / criar política", "List / create policy"),
      ],
      [
        "POST",
        "/admin/access/policies/{id}/revisions",
        x("Revisar constraints com version", "Revise constraints with version"),
      ],
      [
        "GET / POST",
        "/admin/access/grants",
        x("Listar / conceder", "List / grant"),
      ],
      [
        "POST",
        "/admin/access/grants/{id}/revoke",
        x("Revogar com version", "Revoke with version"),
      ],
      [
        "GET",
        "/admin/access/engine-attributes",
        x("Ambientes confiáveis", "Trusted environments"),
      ],
      [
        "PUT",
        "/admin/access/engine-attributes/{id}",
        x("Classificar ambiente; bootstrap", "Classify environment; bootstrap"),
      ],
      [
        "GET / PUT",
        "/admin/access/resources",
        x(
          "Consumidores, qualified e version; bootstrap",
          "Consumers, qualified and version; bootstrap",
        ),
      ],
      [
        "GET / POST",
        "/admin/access/installation-principals",
        x(
          "Listar / registrar principal CLI; bootstrap",
          "List / register CLI principal; bootstrap",
        ),
      ],
      [
        "PUT",
        "/admin/access/installation-principals/{id}",
        x(
          "Ativar/desativar com version; bootstrap",
          "Activate/deactivate with version; bootstrap",
        ),
      ],
      [
        "PUT",
        "/admin/access/subjects/{id}/state",
        x(
          "Ativo/admin com expected_is_active/admin; bootstrap",
          "Active/admin with expected_is_active/admin; bootstrap",
        ),
      ],
    ],
    related: ["execution-profiles", "engine-operations", "engines"],
  },
};

const titles: Record<string, Text> = {
  compute: x("Visão geral de Compute", "Compute overview"),
  engines: guides.engines.title,
  "engine-operations": guides["engine-operations"].title,
  "execution-profiles": guides["execution-profiles"].title,
  "engine-access": guides["engine-access"].title,
  live: x("Captura ao vivo", "Live capture"),
};
function Grid({
  head,
  rows,
  lang,
}: {
  head: Text[];
  rows: Rows;
  lang: DocsLang;
}) {
  const i = lang === "pt" ? 0 : 1;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            {head.map((h, j) => (
              <th key={j} className="px-3 py-2 text-left font-medium">
                {h[i]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, j) => (
            <tr key={j} className="border-t align-top">
              {row.map((cell, k) => (
                <td key={k} className="px-3 py-2 [overflow-wrap:anywhere]">
                  {cell[i]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function ComputeGuide({
  topic,
  lang,
}: {
  topic: string;
  lang: DocsLang;
}) {
  const guide = guides[topic];
  if (!guide) return null;
  const i = lang === "pt" ? 0 : 1;
  return (
    <article className="space-y-8" data-compute-guide={topic}>
      <header className="space-y-4">
        <h1 className="text-3xl font-semibold tracking-tight">
          {guide.title[i]}
        </h1>
        <p className="text-muted-foreground">{guide.intro[i]}</p>
      </header>
      {guide.parts.map((part, index) => (
        <section
          key={index}
          id={`${topic}-${index + 1}`}
          className="space-y-4 scroll-mt-24"
        >
          <h2 className="text-xl font-semibold">{part.title[i]}</h2>
          {part.paragraphs?.map((p, j) => (
            <p
              key={j}
              className="text-muted-foreground [overflow-wrap:anywhere]"
            >
              {p[i]}
            </p>
          ))}
          {part.head && part.rows && (
            <Grid head={part.head} rows={part.rows} lang={lang} />
          )}
          {part.steps && (
            <ol className="list-decimal pl-6 space-y-3 text-muted-foreground">
              {part.steps.map((s, j) => (
                <li key={j}>{s[i]}</li>
              ))}
            </ol>
          )}
          {part.code && (
            <CodeBlock
              code={part.code}
              copyLabel={i === 0 ? "Copiar" : "Copy"}
            />
          )}
        </section>
      ))}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">
          {i === 0 ? "API e contratos" : "API and contracts"}
        </h2>
        <p className="text-muted-foreground">
          {i === 0
            ? "Rotas relativas à base da API; variantes abreviadas compartilham o prefixo indicado. Consulte o schema completo para corpos, parâmetros e respostas. Exemplos usam placeholders, sem credenciais reais."
            : "Routes relative to the API base; abbreviated variants share the indicated prefix. Consult the complete schema for bodies, parameters and responses. Examples use placeholders without real credentials."}
        </p>
        <Grid
          lang={lang}
          head={[x("Método", "Method"), x("Rota", "Route"), x("Uso", "Use")]}
          rows={guide.endpoints.map(([method, route, use]) => [
            x(method, method),
            x(route, route),
            use,
          ])}
        />
        <Link
          className="text-primary underline underline-offset-4"
          href={
            DOCS_TOPICS.some((t) => t.slug === "api-reference")
              ? docsHref("api-reference", lang)
              : `${DOCS_API_URL}/docs`
          }
        >
          {i === 0 ? "Referência completa da API" : "Complete API reference"}
        </Link>
      </section>
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">
          {i === 0
            ? "Guias relacionados e operação da instalação"
            : "Related guides and installation operations"}
        </h2>
        <ul className="list-disc pl-6 space-y-2">
          {guide.related.map((slug) => (
            <li key={slug}>
              <Link
                className="text-primary underline underline-offset-4"
                href={docsHref(slug, lang)}
              >
                {titles[slug][i]}
              </Link>
            </li>
          ))}
        </ul>
        <p className="text-muted-foreground">
          {i === 0
            ? "O dev tem controle e acesso granular habilitados. Migração/ativação verificam a plataforma; canários físicos e concessões delegadas limitadas continuam sendo etapas próprias do rollout, sem garantia de qualificação de produção."
            : "Development has control and granular access enabled. Migration/activation validate the platform; physical canaries and limited delegated grants remain separate rollout steps without a production qualification guarantee."}
        </p>
        <ul className="list-disc pl-6 space-y-2">
          {[
            [
              "docs/features/engines.md",
              x(
                "Guia do operador e benchmark CLI",
                "Operator guide and CLI benchmarks",
              ),
            ],
            [
              "docs/runbooks/engine-control-bootstrap.md",
              x(
                "Bootstrap do controle e agente de host",
                "Control and host-agent bootstrap",
              ),
            ],
            [
              "docs/runbooks/execution-profiles-access.md",
              x(
                "Migração, ativação e rollback de acesso",
                "Access migration, activation and rollback",
              ),
            ],
            [
              "docs/benchmarks/execution-profiles-validation.md",
              x("Evidências de testes e limites", "Test evidence and limits"),
            ],
          ].map(([path, label]) => (
            <li key={path as string}>
              <a
                className="text-primary underline underline-offset-4"
                href={`https://github.com/geda-valentim/ingestify-to-ai/blob/main/${path}`}
              >
                {(label as Text)[i]}
              </a>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

export function ComputeGuideLinks({ lang }: { lang: DocsLang }) {
  const i = lang === "pt" ? 0 : 1;
  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold pt-2">
        {i === 0
          ? "Guias de requisitos e aplicações"
          : "Requirements and use case guides"}
      </h2>
      <ul className="list-disc pl-6 space-y-2">
        {[
          "engines",
          "engine-operations",
          "execution-profiles",
          "engine-access",
        ].map((slug) => (
          <li key={slug}>
            <Link
              className="text-primary underline underline-offset-4"
              href={docsHref(slug, lang)}
            >
              {titles[slug][i]}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
